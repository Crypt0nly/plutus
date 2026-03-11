"""OpenAI-native Computer Use agent loop.

This module implements the agent loop that uses OpenAI's Computer Use Tool
via the Responses API (GPT-5.4). The model returns `computer_call` objects
with desktop actions; we execute them via the shared ComputerUseExecutor and
send back `computer_call_output` with a screenshot.

Key differences from the Anthropic computer use agent:
  - Uses the OpenAI Responses API (`openai.responses.create`)
  - Tool definition is simply `{"type": "computer"}`
  - Actions use OpenAI's naming: click(x,y), type(text), keypress(keys), etc.
  - Screenshots are sent as data URIs in `computer_call_output`
  - Continuation uses `previous_response_id` instead of message history

Reference: https://developers.openai.com/api/docs/guides/tools-computer-use/
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Callable

logger = logging.getLogger("plutus.agent.openai_computer_use")


def execute_openai_computer_action(
    executor: Any, action: dict[str, Any]
) -> dict[str, Any]:
    """Translate an OpenAI computer_call action to executor calls.

    Standalone function so it can be reused by both the dedicated
    OpenAIComputerUseAgent and the main agent loop (native computer use).

    OpenAI action types:
      screenshot, click, double_click, scroll, type, keypress,
      wait, drag, move
    """
    action_type = action.get("type", "")

    if action_type == "screenshot":
        return executor.execute_action("screenshot")

    elif action_type == "click":
        x, y = action.get("x", 0), action.get("y", 0)
        button = action.get("button", "left")
        action_name = {
            "left": "left_click",
            "right": "right_click",
            "middle": "middle_click",
        }.get(button, "left_click")
        return executor.execute_action(action_name, coordinate=[x, y])

    elif action_type == "double_click":
        x, y = action.get("x", 0), action.get("y", 0)
        return executor.execute_action("double_click", coordinate=[x, y])

    elif action_type == "scroll":
        delta_x = action.get("delta_x") or action.get("deltaX") or 0
        delta_y = (
            action.get("delta_y") or action.get("deltaY") or action.get("scroll_y") or 0
        )
        coord = None
        if action.get("x") is not None and action.get("y") is not None:
            coord = [action["x"], action["y"]]
        if delta_y != 0:
            direction = "up" if delta_y < 0 else "down"
            amount = abs(delta_y)
            kwargs: dict[str, Any] = {"direction": direction, "amount": amount}
            if coord:
                kwargs["coordinate"] = coord
            return executor.execute_action("scroll", **kwargs)
        elif delta_x != 0:
            direction = "left" if delta_x < 0 else "right"
            amount = abs(delta_x)
            kwargs = {"direction": direction, "amount": amount}
            if coord:
                kwargs["coordinate"] = coord
            return executor.execute_action("scroll", **kwargs)
        return {"type": "text", "text": "No scroll amount specified"}

    elif action_type == "type":
        text = action.get("text", "")
        return executor.execute_action("type", text=text)

    elif action_type == "keypress":
        keys = action.get("keys") or []
        if not keys:
            single = action.get("key", "")
            keys = [single] if single else []
        if len(keys) == 1:
            return executor.execute_action("key", text=keys[0])
        elif len(keys) > 1:
            combo = "+".join(keys)
            return executor.execute_action("key", text=combo)
        return {"type": "text", "text": "No keys specified"}

    elif action_type == "wait":
        ms = action.get("ms") or action.get("duration_ms") or 1000
        return executor.execute_action("wait", duration=ms / 1000.0)

    elif action_type == "drag":
        start_x = action.get("x", 0)
        start_y = action.get("y", 0)
        path = action.get("path", [])
        if path:
            end = path[-1]
            end_x = end.get("x", start_x)
            end_y = end.get("y", start_y)
        else:
            end_x, end_y = start_x, start_y
        return executor.execute_action(
            "left_click_drag",
            start_coordinate=[start_x, start_y],
            coordinate=[end_x, end_y],
        )

    elif action_type == "move":
        x, y = action.get("x", 0), action.get("y", 0)
        return executor.execute_action("mouse_move", coordinate=[x, y])

    else:
        return {"type": "error", "error": f"Unknown action type: {action_type}"}


def capture_screenshot_data_uri(executor: Any) -> str | None:
    """Capture a screenshot and return as a data URI string."""
    result = executor.execute_action("screenshot")
    if result.get("type") == "image" and result.get("base64"):
        media = result.get("media_type", "image/png")
        return f"data:{media};base64,{result['base64']}"
    return None


class OpenAIComputerUseEvent:
    """Events emitted by the OpenAI computer use agent for the UI."""

    def __init__(self, type: str, data: dict[str, Any] | None = None):
        self.type = type
        self.data = data or {}

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, **self.data}


class OpenAIComputerUseAgent:
    """Agent loop that uses OpenAI's native Computer Use Tool (GPT-5.4).

    Flow:
      1. User sends a task
      2. Agent sends to OpenAI Responses API with {"type": "computer"} tool
      3. OpenAI returns computer_call with actions (click, type, scroll, etc.)
      4. Agent executes each action via ComputerUseExecutor
      5. Agent captures a screenshot and sends it back as computer_call_output
      6. Repeat until response has no computer_call (task complete)
    """

    MAX_ITERATIONS = 50
    ACTION_DELAY = 0.5

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5.4",
        executor: Any = None,
        max_iterations: int = 50,
    ):
        self._api_key = api_key
        self._model = model
        self._max_iterations = max_iterations

        if executor is None:
            from plutus.pc.computer_use import ComputerUseExecutor
            # OpenAI supports up to 10.24M px with detail="original".
            # Use native resolution (no Anthropic-style downscaling) so
            # coordinates map 1:1 and click accuracy is maximized.
            self._executor = ComputerUseExecutor(native_resolution=True)
        else:
            self._executor = executor

        self._event_handlers: list[Callable] = []
        self._running = False
        self._iteration_count = 0

    def on_event(self, handler: Callable) -> None:
        self._event_handlers.append(handler)

    async def _emit(self, event: OpenAIComputerUseEvent) -> None:
        for handler in self._event_handlers:
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result

    def _execute_action(self, action: dict[str, Any]) -> dict[str, Any]:
        """Translate an OpenAI computer_call action to executor calls."""
        return execute_openai_computer_action(self._executor, action)

    def _capture_screenshot_b64(self) -> str | None:
        """Capture a screenshot and return as a data URI string."""
        return capture_screenshot_data_uri(self._executor)

    async def run_task(self, user_message: str) -> AsyncIterator[OpenAIComputerUseEvent]:
        """Run a computer use task, yielding events for the UI."""
        self._running = True
        self._iteration_count = 0

        yield OpenAIComputerUseEvent("thinking", {"message": f"Starting task: {user_message}"})

        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self._api_key)
        previous_response_id = None

        # Initial request
        try:
            response = await client.responses.create(
                model=self._model,
                tools=[{"type": "computer"}],
                truncation="auto",
                input=user_message,
            )
        except Exception as e:
            yield OpenAIComputerUseEvent("error", {"message": f"OpenAI API error: {e}"})
            return

        for iteration in range(self._max_iterations):
            if not self._running:
                yield OpenAIComputerUseEvent("cancelled", {"message": "Task cancelled"})
                return

            self._iteration_count = iteration + 1
            yield OpenAIComputerUseEvent("iteration", {
                "number": iteration + 1,
                "max": self._max_iterations,
            })

            # Find computer_call in output
            computer_call = None
            for item in response.output:
                if getattr(item, "type", None) == "computer_call":
                    computer_call = item
                elif getattr(item, "type", None) == "message":
                    # Extract text content from message items
                    content = getattr(item, "content", [])
                    for block in content:
                        if getattr(block, "type", None) == "output_text":
                            yield OpenAIComputerUseEvent("text", {
                                "content": block.text
                            })

            if computer_call is None:
                # No computer_call means task is done
                yield OpenAIComputerUseEvent("done", {
                    "iterations": iteration + 1,
                    "message": "Task completed",
                })
                return

            # Execute all actions in the computer_call
            call_id = computer_call.call_id
            actions = computer_call.actions or []

            yield OpenAIComputerUseEvent("tool_call", {
                "id": call_id,
                "tool": "computer",
                "actions": [
                    {"type": getattr(a, "type", "unknown")} for a in actions
                ],
            })

            for action_obj in actions:
                action = {}
                # Convert the SDK action object to a plain dict
                if hasattr(action_obj, "model_dump"):
                    action = action_obj.model_dump()
                elif hasattr(action_obj, "__dict__"):
                    action = {
                        k: v for k, v in action_obj.__dict__.items()
                        if not k.startswith("_")
                    }
                else:
                    action = {"type": getattr(action_obj, "type", "unknown")}

                # Run synchronous desktop action in a thread to avoid blocking
                # the event loop (PyAutoGUI / screenshot capture is blocking I/O).
                try:
                    result = await asyncio.to_thread(self._execute_action, action)
                except Exception as e:
                    logger.exception(f"Action execution failed: {action.get('type')}")
                    result = {"type": "error", "error": str(e)}

                yield OpenAIComputerUseEvent("tool_result", {
                    "id": call_id,
                    "tool": "computer",
                    "action": action.get("type", "unknown"),
                    "result": result,
                })

                await asyncio.sleep(self.ACTION_DELAY)

            # Capture screenshot after executing actions
            try:
                screenshot_url = await asyncio.to_thread(self._capture_screenshot_b64)
            except Exception as e:
                logger.exception("Screenshot capture failed")
                yield OpenAIComputerUseEvent("error", {
                    "message": f"Screenshot capture failed: {e}"
                })
                return
            if not screenshot_url:
                yield OpenAIComputerUseEvent("error", {
                    "message": "Failed to capture screenshot after actions"
                })
                return

            # Send computer_call_output back to OpenAI
            previous_response_id = response.id

            try:
                response = await client.responses.create(
                    model=self._model,
                    tools=[{"type": "computer"}],
                    truncation="auto",
                    previous_response_id=previous_response_id,
                    input=[{
                        "type": "computer_call_output",
                        "call_id": call_id,
                        "output": {
                            "type": "computer_screenshot",
                            "image_url": screenshot_url,
                        },
                    }],
                )
            except Exception as e:
                yield OpenAIComputerUseEvent("error", {
                    "message": f"OpenAI API error: {e}"
                })
                return

        yield OpenAIComputerUseEvent("error", {
            "message": f"Reached max iterations ({self._max_iterations}). Task may be incomplete."
        })

    def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def iteration_count(self) -> int:
        return self._iteration_count
