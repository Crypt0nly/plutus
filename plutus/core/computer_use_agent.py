"""Anthropic-native Computer Use agent loop.

This module implements the agent loop that uses Anthropic's native Computer Use
Tool (computer_20250124). Instead of the standard function-calling approach,
this sends screenshots as images directly to Claude's vision model and lets
Claude decide what to click, type, or scroll.

Key differences from the standard agent loop:
  - Uses the Anthropic beta API with `computer-use-2025-01-24` header
  - Sends the `computer` tool as a schema-less tool (type: computer_20250124)
  - Screenshots are sent as base64 images in tool_result content blocks
  - Coordinate scaling is handled by the ComputerUseExecutor
  - The loop continues until Claude stops requesting tool calls

This is the PROVEN approach used by Anthropic's reference implementation and
by OpenClaw. Claude literally SEES the screen and decides what to do.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator, Callable

logger = logging.getLogger("plutus.agent.computer_use")


class ComputerUseEvent:
    """Events emitted by the computer use agent for the UI."""

    def __init__(self, type: str, data: dict[str, Any] | None = None):
        self.type = type
        self.data = data or {}

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, **self.data}


class ComputerUseAgent:
    """Agent loop that uses Anthropic's native Computer Use Tool.

    This agent talks directly to the Anthropic API (not via LiteLLM) because
    the Computer Use Tool requires:
      1. The `computer-use-2025-01-24` beta header
      2. Schema-less tool definitions (type: computer_20250124)
      3. Image content blocks in tool_result messages
      4. Specific message format for multi-turn tool use

    Flow:
      1. User sends a task (e.g., "Open WhatsApp and send a message")
      2. Agent sends the task to Claude with the computer tool definition
      3. Claude responds with tool_use blocks (screenshot, click, type, etc.)
      4. Agent executes each action via ComputerUseExecutor
      5. Agent sends results (including screenshots) back to Claude
      6. Repeat until Claude sends a text response (task complete)
    """

    MAX_ITERATIONS = 50  # Safety limit
    ACTION_DELAY = 0.5   # Seconds between actions for stability

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        executor: Any = None,
        max_iterations: int = 50,
    ):
        self._api_key = api_key
        self._model = model
        self._max_iterations = max_iterations

        # Lazy import executor
        if executor is None:
            from plutus.pc.computer_use import ComputerUseExecutor
            self._executor = ComputerUseExecutor()
        else:
            self._executor = executor

        self._event_handlers: list[Callable] = []
        self._messages: list[dict[str, Any]] = []
        self._running = False
        self._iteration_count = 0

    def on_event(self, handler: Callable) -> None:
        """Register an event handler."""
        self._event_handlers.append(handler)

    async def _emit(self, event: ComputerUseEvent) -> None:
        for handler in self._event_handlers:
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Get the tool definitions for the Anthropic API.

        Returns the computer use tool plus bash and text editor tools.
        """
        tools = []

        # Computer use tool (schema-less — Anthropic's native tool)
        tools.append(self._executor.get_tool_definition())

        # Bash tool — for running shell commands
        tools.append({
            "type": "bash_20250124",
            "name": "bash",
        })

        # Text editor tool — for reading/editing files
        tools.append({
            "type": "text_editor_20250124",
            "name": "str_replace_editor",
        })

        return tools

    def _build_system_prompt(self) -> str:
        """Build the system prompt for computer use."""
        return (
            "You are Plutus, an AI assistant that controls the user's computer to complete tasks. "
            "You can see the screen via screenshots, click on elements, type text, use keyboard shortcuts, "
            "and run shell commands.\n\n"
            "IMPORTANT RULES:\n"
            "1. ALWAYS take a screenshot first to see what's on screen before acting.\n"
            "2. After clicking or typing, take another screenshot to verify the result.\n"
            "3. If you need to open an application:\n"
            "   - On Windows: Use the Windows key to open Start, then type the app name\n"
            "   - On macOS: Use Command+Space for Spotlight, then type the app name\n"
            "   - On Linux: Use the application menu or terminal\n"
            "4. Be precise with clicks — click exactly on the element you want.\n"
            "5. Wait briefly after actions for the UI to update before taking the next screenshot.\n"
            "6. If something doesn't work, try an alternative approach.\n"
            "7. When typing into a field, click on it first to make sure it's focused.\n"
            "8. For web browsing, you can type URLs directly into the address bar.\n"
            "9. Use keyboard shortcuts when they're faster (Ctrl+C, Ctrl+V, etc.).\n"
            "10. Tell the user what you're doing at each step.\n\n"
            "You have access to three tools:\n"
            "- `computer`: Take screenshots, click, type, scroll, and interact with the desktop\n"
            "- `bash`: Run shell commands\n"
            "- `str_replace_editor`: View and edit text files\n\n"
            "Always start by taking a screenshot to understand the current state of the screen."
        )

    async def run_task(self, user_message: str) -> AsyncIterator[ComputerUseEvent]:
        """Run a computer use task from a user message.

        Yields ComputerUseEvent objects for the UI to display.
        """
        self._running = True
        self._iteration_count = 0

        yield ComputerUseEvent("thinking", {"message": f"Starting task: {user_message}"})

        # Initialize the conversation
        self._messages = [
            {"role": "user", "content": user_message}
        ]

        try:
            import anthropic
        except ImportError:
            yield ComputerUseEvent("error", {
                "message": "The 'anthropic' package is required for computer use. "
                           "Install it with: pip install anthropic"
            })
            return

        client = anthropic.AsyncAnthropic(api_key=self._api_key)

        tools = self.get_tool_definitions()
        system_prompt = self._build_system_prompt()

        for iteration in range(self._max_iterations):
            if not self._running:
                yield ComputerUseEvent("cancelled", {"message": "Task cancelled by user"})
                return

            self._iteration_count = iteration + 1

            yield ComputerUseEvent("iteration", {
                "number": iteration + 1,
                "max": self._max_iterations,
            })

            try:
                # Call the Anthropic API with computer use beta
                response = await client.beta.messages.create(
                    model=self._model,
                    max_tokens=4096,
                    system=system_prompt,
                    tools=tools,
                    messages=self._messages,
                    betas=["computer-use-2025-01-24"],
                )
            except anthropic.APIError as e:
                yield ComputerUseEvent("error", {"message": f"API error: {e}"})
                return
            except Exception as e:
                yield ComputerUseEvent("error", {"message": f"Unexpected error: {e}"})
                return

            # Process the response
            assistant_content = response.content
            has_tool_use = any(
                block.type == "tool_use" for block in assistant_content
            )

            # Emit text blocks
            for block in assistant_content:
                if block.type == "text":
                    yield ComputerUseEvent("text", {"content": block.text})

            # If no tool use, the task is complete
            if not has_tool_use or response.stop_reason == "end_turn":
                # Check if there were any tool_use blocks — if so, we still need to process them
                if not has_tool_use:
                    yield ComputerUseEvent("done", {
                        "iterations": iteration + 1,
                        "message": "Task completed"
                    })
                    return

            # Add assistant message to history
            self._messages.append({
                "role": "assistant",
                "content": [self._serialize_block(b) for b in assistant_content],
            })

            # Process tool calls
            tool_results = []
            for block in assistant_content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input
                tool_id = block.id

                yield ComputerUseEvent("tool_call", {
                    "id": tool_id,
                    "tool": tool_name,
                    "input": tool_input,
                })

                # Execute the tool
                result = await self._execute_tool(tool_name, tool_input)

                yield ComputerUseEvent("tool_result", {
                    "id": tool_id,
                    "tool": tool_name,
                    "result": result,
                })

                # Build the tool_result content block
                if result.get("type") == "image":
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": result["media_type"],
                                    "data": result["base64"],
                                },
                            }
                        ],
                    })
                elif result.get("type") == "error":
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": result.get("error", "Unknown error"),
                        "is_error": True,
                    })
                else:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": result.get("text", str(result)),
                    })

                # Brief delay between actions for UI stability
                await asyncio.sleep(self.ACTION_DELAY)

            # Add tool results to messages
            self._messages.append({
                "role": "user",
                "content": tool_results,
            })

            # Check if we should stop
            if response.stop_reason == "end_turn" and not has_tool_use:
                yield ComputerUseEvent("done", {
                    "iterations": iteration + 1,
                    "message": "Task completed"
                })
                return

        # Exhausted iterations
        yield ComputerUseEvent("error", {
            "message": f"Reached maximum iterations ({self._max_iterations}). Task may be incomplete."
        })

    async def _execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool call from Claude."""
        if tool_name == "computer":
            action = tool_input.get("action", "")
            # Pass all params except 'action' to the executor
            params = {k: v for k, v in tool_input.items() if k != "action"}
            # Run in a thread to avoid blocking the event loop — execute_action
            # uses synchronous pyautogui calls and time.sleep() internally.
            return await asyncio.to_thread(self._executor.execute_action, action, **params)

        elif tool_name == "bash":
            return await self._execute_bash(tool_input)

        elif tool_name == "str_replace_editor":
            return await self._execute_text_editor(tool_input)

        else:
            return {"type": "error", "error": f"Unknown tool: {tool_name}"}

    async def _execute_bash(self, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Execute a bash command."""
        command = tool_input.get("command", "")
        if not command:
            return {"type": "error", "error": "No command provided"}

        try:
            import subprocess
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(Path.home()) if not command.startswith("cd ") else None,
            )
            output = result.stdout
            if result.stderr:
                output += f"\nSTDERR:\n{result.stderr}"
            if result.returncode != 0:
                output += f"\n(exit code: {result.returncode})"
            return {"type": "text", "text": output or "(no output)"}
        except subprocess.TimeoutExpired:
            return {"type": "error", "error": "Command timed out after 30 seconds"}
        except Exception as e:
            return {"type": "error", "error": f"Command failed: {e}"}

    async def _execute_text_editor(self, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Execute a text editor command (view, create, str_replace, insert)."""
        from pathlib import Path

        command = tool_input.get("command", "")
        path = tool_input.get("path", "")

        if not path:
            return {"type": "error", "error": "No path provided"}

        file_path = Path(path).expanduser()

        try:
            if command == "view":
                if not file_path.exists():
                    return {"type": "error", "error": f"File not found: {path}"}
                view_range = tool_input.get("view_range")
                content = file_path.read_text()
                lines = content.splitlines()
                if view_range and len(view_range) == 2:
                    start, end = view_range
                    lines = lines[start - 1:end]
                    header = f"Lines {start}-{end} of {path}:\n"
                else:
                    header = f"Contents of {path}:\n"
                numbered = "\n".join(
                    f"{i + 1:4d} | {line}" for i, line in enumerate(lines)
                )
                return {"type": "text", "text": header + numbered}

            elif command == "create":
                file_content = tool_input.get("file_text", "")
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(file_content)
                return {"type": "text", "text": f"Created {path}"}

            elif command == "str_replace":
                if not file_path.exists():
                    return {"type": "error", "error": f"File not found: {path}"}
                old_str = tool_input.get("old_str", "")
                new_str = tool_input.get("new_str", "")
                content = file_path.read_text()
                if old_str not in content:
                    return {"type": "error", "error": f"String not found in {path}: {old_str[:100]}"}
                # Only replace first occurrence
                new_content = content.replace(old_str, new_str, 1)
                file_path.write_text(new_content)
                return {"type": "text", "text": f"Replaced text in {path}"}

            elif command == "insert":
                if not file_path.exists():
                    return {"type": "error", "error": f"File not found: {path}"}
                insert_line = tool_input.get("insert_line", 0)
                new_str = tool_input.get("new_str", "")
                content = file_path.read_text()
                lines = content.splitlines(keepends=True)
                lines.insert(insert_line, new_str + "\n")
                file_path.write_text("".join(lines))
                return {"type": "text", "text": f"Inserted text at line {insert_line} in {path}"}

            elif command == "undo_edit":
                return {"type": "text", "text": "Undo not supported yet"}

            else:
                return {"type": "error", "error": f"Unknown editor command: {command}"}

        except Exception as e:
            return {"type": "error", "error": f"Editor error: {e}"}

    def _serialize_block(self, block: Any) -> dict[str, Any]:
        """Serialize an API content block to a dict for message history."""
        if block.type == "text":
            return {"type": "text", "text": block.text}
        elif block.type == "tool_use":
            return {
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            }
        else:
            return {"type": block.type}

    def stop(self) -> None:
        """Stop the current task."""
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def iteration_count(self) -> int:
        return self._iteration_count


# ── Import fix for bash tool ────────────────────────────────────────
from pathlib import Path
