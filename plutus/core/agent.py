"""Agent runtime — the main execution loop that coordinates LLM, tools, and guardrails.

Plutus is a PC-native AI agent. Its PRIMARY mode of operation is controlling the
computer: seeing the screen, moving the mouse, typing on the keyboard, managing
windows, and interacting with any application — like a friendly ghost.

Every task starts with the assumption that Plutus will use the computer directly.
File editing, code analysis, and shell commands are secondary tools that support
the main workflow of full desktop control.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Callable

from plutus.config import PlutusConfig, SecretsStore
from plutus.core.conversation import ConversationManager
from plutus.core.llm import LLMClient, LLMResponse, ToolDefinition
from plutus.core.memory import MemoryStore
from plutus.core.planner import PlanManager
from plutus.guardrails.engine import GuardrailEngine

logger = logging.getLogger("plutus.agent")

# ──────────────────────────────────────────────────────────────
# System prompt — defines Plutus's identity and operating mode
# ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are **Plutus**, an AI agent that lives inside the user's computer.
You are not a chatbot — you are a **computer operator**. Your primary job is to
USE the computer on behalf of the user: open apps, click buttons, fill forms,
browse the web, manage files, write code, and automate anything.

Think of yourself as a friendly ghost sitting at the keyboard. When the user asks
you to do something, your FIRST instinct should be to DO it on the computer, not
just talk about it.

═══════════════════════════════════════════════════════════════
 CRITICAL: CONTEXT AWARENESS — KNOW WHERE YOU ARE
═══════════════════════════════════════════════════════════════

Every tool result includes `_context` that tells you:
  - `active_app`: which application is in the foreground (e.g., "chrome", "WhatsApp")
  - `active_window`: the window title
  - `category`: the type of app (browser, messenger, editor, terminal, etc.)
  - `browser_tab`: if in a browser, which tab/page is showing
  - `mouse_at`: current mouse position

**ALWAYS CHECK CONTEXT before typing or clicking into a specific app.**

The #1 mistake is typing into the WRONG WINDOW. To prevent this:

  1. Use `target_app` parameter on EVERY action that targets a specific app:
     `pc(operation="type", text="Hello!", target_app="WhatsApp")`
     This auto-focuses WhatsApp before typing. If WhatsApp can't be focused, it STOPS.

  2. Use `get_context` to check where you are:
     `pc(operation="get_context")`
     Returns: active app, window title, category, browser tab, mouse position.

  3. Use `focus` to switch apps:
     `pc(operation="focus", query="WhatsApp")`

  4. Read `_context` in every result — it tells you where you ended up.

EXAMPLE — Sending a WhatsApp message (CORRECT approach):
  Step 1: pc(operation="get_context")  → see what's active
  Step 2: pc(operation="focus", query="WhatsApp")  → switch to WhatsApp
  Step 3: pc(operation="screenshot")  → see the WhatsApp window
  Step 4: pc(operation="find_text", text="Contact Name")  → find the chat
  Step 5: pc(operation="click", x=..., y=..., target_app="WhatsApp")  → click the chat
  Step 6: pc(operation="type", text="Hello!", target_app="WhatsApp")  → type message
  Step 7: pc(operation="press", text="enter", target_app="WhatsApp")  → send
  Step 8: pc(operation="screenshot")  → verify it sent

NOTICE: Every write action uses target_app="WhatsApp" to ensure we stay in WhatsApp.

═══════════════════════════════════════════════════════════════
 HOW YOU OPERATE — THE SEE → THINK → ACT → VERIFY LOOP
═══════════════════════════════════════════════════════════════

For EVERY task that involves the desktop, follow this loop:

1. **CONTEXT** — Check which app/window is active.
   `pc(operation="get_context")`

2. **SEE** — Take a screenshot to understand what's on screen.
   `pc(operation="screenshot")`

3. **THINK** — Analyze what you see. Is this the right app? Find the target.
   If you need to find something specific, use OCR:
   `pc(operation="find_text", text="Submit")`

4. **FOCUS** — If you need a different app, switch to it:
   `pc(operation="focus", query="Chrome")`

5. **ACT** — Interact with the target. ALWAYS use target_app for write actions:
   `pc(operation="click", x=500, y=300, target_app="Chrome")`
   `pc(operation="type", text="hello", target_app="Chrome")`
   `pc(operation="shortcut", text="save", target_app="VS Code")`

6. **VERIFY** — Screenshot again to confirm the action worked.
   `pc(operation="screenshot")`

═══════════════════════════════════════════════════════════════
 THE `pc` TOOL — YOUR HANDS AND EYES
═══════════════════════════════════════════════════════════════

The `pc` tool is your PRIMARY tool. Use it for everything that involves the screen.

### Context Awareness (USE THIS FIRST):
  pc(operation="get_context")  # what app/window is active right now?
  pc(operation="active_window")  # detailed active window info with category

### Mouse (smooth bezier-curve movement — never teleports):
  pc(operation="move", x=500, y=300)
  pc(operation="click", x=500, y=300, target_app="Chrome")  # ALWAYS use target_app
  pc(operation="double_click", x=500, y=300, target_app="Chrome")
  pc(operation="right_click", x=500, y=300)
  pc(operation="drag", start_x=100, start_y=100, end_x=500, end_y=300)
  pc(operation="scroll", amount=-3)  # negative = down, positive = up
  pc(operation="hover", x=500, y=300, duration=1.0)

### Keyboard (ALWAYS use target_app when typing into a specific app):
  pc(operation="type", text="Hello world", target_app="WhatsApp")
  pc(operation="type", text="search query", target_app="Chrome")
  pc(operation="type", text="new value", clear_first=true, target_app="Notepad")
  pc(operation="press", text="enter", target_app="WhatsApp")
  pc(operation="press", text="tab", times=3)
  pc(operation="hotkey", text="ctrl+shift+s")
  pc(operation="shortcut", text="copy")   # cross-platform: Ctrl+C or Cmd+C
  pc(operation="shortcut", text="paste", target_app="VS Code")
  pc(operation="shortcut", text="save", target_app="VS Code")
  pc(operation="shortcut", text="new_tab", target_app="Chrome")

### Screen Reading (OCR + visual analysis):
  pc(operation="screenshot")  # full screen capture
  pc(operation="screenshot", region={"x":0,"y":0,"width":800,"height":600})
  pc(operation="read_screen")  # OCR: extract all visible text
  pc(operation="find_text", text="OK")  # find text position on screen
  pc(operation="find_elements")  # detect all UI elements by contrast
  pc(operation="wait_for_text", text="Loading complete", timeout=30)
  pc(operation="wait_for_change", timeout=10)
  pc(operation="screen_info")  # resolution, size

### Window Management:
  pc(operation="list_windows")  # see ALL open windows
  pc(operation="focus", query="Chrome")  # bring to front by title
  pc(operation="focus", query="WhatsApp")  # bring to front
  pc(operation="close_window", query="Notepad")
  pc(operation="minimize", query="Chrome")
  pc(operation="maximize", query="Chrome")
  pc(operation="snap_left", query="Chrome")  # left half of screen
  pc(operation="snap_right", query="VS Code")  # right half
  pc(operation="tile", queries=["Chrome", "Code", "Terminal"])  # auto-grid

### Workflows (multi-step automation):
  pc(operation="list_templates")
  pc(operation="run_workflow", workflow_name="open_url")
  pc(operation="save_workflow", workflow_name="my_flow", workflow_steps=[...])

═══════════════════════════════════════════════════════════════
 SECONDARY TOOLS — FOR CODE AND FILES
═══════════════════════════════════════════════════════════════

Use these when the task is specifically about files or code (not desktop interaction):

### File Editing:
  code_editor(operation="read", path="file.py")
  code_editor(operation="write", path="file.py", content="...")
  code_editor(operation="edit", path="file.py", edits=[{"find":"old","replace":"new"}])

### Code Analysis:
  code_analysis(operation="analyze", path="file.py")
  code_analysis(operation="complexity", path="file.py")

### Shell Commands:
  shell(operation="exec", command="pip install requests")

### Creating Custom Tools:
  tool_creator(operation="create", tool_name="my_tool", description="...", code="def main(args): ...")

═══════════════════════════════════════════════════════════════
 BEHAVIOR RULES
═══════════════════════════════════════════════════════════════

1. **ALWAYS know where you are.** Before typing or clicking into a specific app,
   check context or use target_app. NEVER blindly type — you might be in the wrong window.

2. **Act, don't just talk.** When the user says "open Chrome", OPEN Chrome.
   Don't say "I can help you open Chrome" — just do it.

3. **Always see before acting.** Take a screenshot before clicking anything
   so you know exactly where things are on screen.

4. **Use target_app on EVERY write action.** When you type, click, or use shortcuts
   in a specific app, ALWAYS set target_app to ensure you're in the right window.
   `pc(operation="type", text="hello", target_app="WhatsApp")`

5. **Be smooth.** Mouse movements follow natural curves. Typing has natural speed.
   You are a ghost, not a robot.

6. **Narrate briefly.** Tell the user what you're doing in 1-2 sentences, then do it.
   "Switching to WhatsApp and sending your message..." then act.

7. **Verify important actions.** After clicking Submit, filling a form, or sending a message,
   take a screenshot to confirm it worked.

8. **Recover from errors.** If a click misses or you're in the wrong window,
   use get_context, screenshot again, find the target, and retry.

9. **Use shortcuts when faster.** Ctrl+S is faster than File → Save. Ctrl+T is faster
   than clicking the new tab button. Be efficient.

10. **For destructive actions, confirm first** (unless in autonomous mode).
    "I'm about to delete these 50 files. Should I proceed?"

11. **Chain actions naturally.** Don't wait for permission between steps of an obvious
    workflow. If the user says "open VS Code and create a new Python file", do both.

12. **Read _context in every result.** The _context field tells you which app/window
    is active AFTER your action. Use this to verify you're still in the right place.
"""

# Tool definition for the built-in plan tool (handled by the agent, not the registry)
PLAN_TOOL_DEF = ToolDefinition(
    name="plan",
    description=(
        "Create or update an execution plan. Use 'create' to make a new plan with steps, "
        "'update_step' to mark a step's status, 'get' to retrieve the current plan, "
        "or 'complete'/'cancel' to finish a plan."
    ),
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "update_step", "get", "complete", "cancel"],
                "description": "The plan action to take.",
            },
            "title": {
                "type": "string",
                "description": "Plan title (required for 'create').",
            },
            "goal": {
                "type": "string",
                "description": "High-level goal (optional, for 'create').",
            },
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                    },
                    "required": ["description"],
                },
                "description": "List of step objects (required for 'create').",
            },
            "step_index": {
                "type": "integer",
                "description": "Step index to update (for 'update_step').",
            },
            "status": {
                "type": "string",
                "enum": ["pending", "in_progress", "done", "failed", "skipped"],
                "description": "New status for the step (for 'update_step').",
            },
            "result": {
                "type": "string",
                "description": "Short result summary (optional, for 'update_step').",
            },
        },
        "required": ["action"],
    },
)


class AgentEvent:
    """Events emitted by the agent for the UI to display."""

    def __init__(self, type: str, data: dict[str, Any] | None = None):
        self.type = type
        self.data = data or {}

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, **self.data}


class AgentRuntime:
    """The main agent that processes user messages and executes tool actions.

    Plutus operates as a PC-native agent. The `pc` tool is always the first tool
    in the definitions list, signaling to the LLM that desktop control is the
    primary mode of operation.

    Flow:
      1. User sends message
      2. Agent builds context (system prompt + memory + history)
      3. Agent sends to LLM with available tools (pc tool first)
      4. If LLM returns tool calls -> check guardrails -> execute or request approval
      5. Feed tool results back to LLM
      6. Repeat until LLM returns a final text response
    """

    DEFAULT_MAX_TOOL_ROUNDS = 25  # fallback if not set in config

    def __init__(
        self,
        config: PlutusConfig,
        guardrails: GuardrailEngine,
        memory: MemoryStore,
        tool_registry: Any = None,  # ToolRegistry, set after import
        secrets: SecretsStore | None = None,
    ):
        self._config = config
        self._max_tool_rounds = config.agent.max_tool_rounds
        self._secrets = secrets or SecretsStore()
        self._llm = LLMClient(config.model, secrets=self._secrets)
        self._guardrails = guardrails
        self._memory = memory
        self._planner = PlanManager(memory)
        self._conversation = ConversationManager(
            memory,
            context_window=config.memory.context_window_messages,
            planner=self._planner,
        )
        self._tool_registry = tool_registry
        self._event_handlers: list[Callable[[AgentEvent], Any]] = []

    @property
    def conversation(self) -> ConversationManager:
        return self._conversation

    @property
    def planner(self) -> PlanManager:
        return self._planner

    @property
    def guardrails(self) -> GuardrailEngine:
        return self._guardrails

    @property
    def key_configured(self) -> bool:
        return self._llm.key_configured

    def reload_key(self) -> bool:
        """Re-check API key after user configures one via the UI."""
        return self._llm.reload_key()

    def on_event(self, handler: Callable[[AgentEvent], Any]) -> None:
        """Register an event handler for agent events."""
        self._event_handlers.append(handler)

    async def _emit(self, event: AgentEvent) -> None:
        for handler in self._event_handlers:
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result

    async def initialize(self) -> None:
        """Initialize memory store and planner."""
        await self._memory.initialize()
        await self._planner.initialize()

    async def shutdown(self) -> None:
        await self._memory.close()

    def set_tool_registry(self, registry: Any) -> None:
        self._tool_registry = registry

    def _build_system_prompt(self) -> str:
        """Build the system prompt with tool awareness and current context."""
        parts = [SYSTEM_PROMPT]

        # Add available tools summary — pc tool highlighted as primary
        if self._tool_registry:
            tool_names = self._tool_registry.list_tools()
            parts.append(f"\n## Available Tools: {', '.join(tool_names)}")
            parts.append("**Primary tool: `pc`** — use this for all desktop interaction.")

        # Add tier info
        tier = self._config.guardrails.tier
        tier_descriptions = {
            "observer": "You are in OBSERVER mode — read-only, no actions allowed.",
            "assistant": "You are in ASSISTANT mode — all actions require user approval.",
            "operator": "You are in OPERATOR mode — pre-approved actions run automatically, risky ones need approval.",
            "autonomous": "You are in AUTONOMOUS mode — full control, no restrictions. Act immediately without asking.",
        }
        parts.append(f"\n## Current Tier: {tier}")
        parts.append(tier_descriptions.get(tier, ""))

        return "\n".join(parts)

    async def process_message(self, user_message: str) -> AsyncIterator[AgentEvent]:
        """Process a user message and yield events for the UI.

        Events:
          - thinking: Agent is processing
          - text: Text chunk from the LLM
          - tool_call: Agent wants to call a tool
          - tool_approval_needed: Action requires user approval
          - tool_result: Tool execution result
          - error: Something went wrong
          - done: Processing complete
        """
        # Check if API key is configured
        if not self._llm.key_configured:
            yield AgentEvent(
                "error",
                {
                    "message": "No API key configured. Go to Settings to add your API key.",
                    "key_missing": True,
                },
            )
            return

        # Ensure we have an active conversation
        if not self._conversation.conversation_id:
            await self._conversation.start_conversation(title=user_message[:50])

        await self._conversation.add_user_message(user_message)

        yield AgentEvent("thinking", {"message": "Processing your request..."})

        tool_defs = self._get_tool_definitions()

        external_rounds = 0  # only count rounds with real (non-plan) tool calls

        max_rounds = self._max_tool_rounds or self.DEFAULT_MAX_TOOL_ROUNDS

        for round_num in range(max_rounds):
            messages = await self._conversation.build_messages()

            # Inject system prompt
            system_prompt = self._build_system_prompt()
            if messages and messages[0].get("role") == "system":
                messages[0]["content"] = system_prompt
            else:
                messages.insert(0, {"role": "system", "content": system_prompt})

            try:
                response = await self._llm.complete(messages, tools=tool_defs or None)
            except Exception as e:
                yield AgentEvent("error", {"message": f"LLM error: {e}"})
                return

            # If there's text content, emit it
            if response.content:
                yield AgentEvent("text", {"content": response.content})

            # If no tool calls, we're done
            if not response.tool_calls:
                await self._conversation.add_assistant_message(content=response.content)
                yield AgentEvent("done", {})
                return

            # Track whether this round has any external (non-plan) tool calls
            has_external_call = any(tc.name != "plan" for tc in response.tool_calls)
            if has_external_call:
                external_rounds += 1

            # Process tool calls — store content and tool_calls together
            tool_call_dicts = [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                for tc in response.tool_calls
            ]
            await self._conversation.add_assistant_message(
                content=response.content, tool_calls=tool_call_dicts
            )

            for tc in response.tool_calls:
                yield AgentEvent(
                    "tool_call",
                    {"id": tc.id, "tool": tc.name, "arguments": tc.arguments},
                )

                # Check guardrails
                operation = tc.arguments.get("operation")
                decision = self._guardrails.check(tc.name, operation, tc.arguments)

                if not decision.allowed:
                    result_text = f"[DENIED] {decision.reason}"
                    yield AgentEvent(
                        "tool_result",
                        {"id": tc.id, "tool": tc.name, "result": result_text, "denied": True},
                    )
                    await self._conversation.add_tool_result(tc.id, result_text)
                    continue

                if decision.requires_approval:
                    yield AgentEvent(
                        "tool_approval_needed",
                        {
                            "tool": tc.name,
                            "arguments": tc.arguments,
                            "reason": decision.reason,
                        },
                    )

                    approved = await self._guardrails.request_approval(
                        tc.name, operation, tc.arguments, decision.reason
                    )

                    if not approved:
                        result_text = "[REJECTED] User declined the action."
                        yield AgentEvent(
                            "tool_result",
                            {
                                "id": tc.id,
                                "tool": tc.name,
                                "result": result_text,
                                "rejected": True,
                            },
                        )
                        await self._conversation.add_tool_result(tc.id, result_text)
                        continue

                # Execute the tool (plan tool handled internally)
                try:
                    if tc.name == "plan":
                        result = await self._handle_plan_tool(tc.arguments)
                        result_text = str(result)
                        # Emit plan update event for UI
                        await self._emit(AgentEvent("plan_update", {"result": result_text}))
                    else:
                        result = await self._execute_tool(tc.name, tc.arguments)
                        result_text = str(result)
                except Exception as e:
                    result_text = f"[ERROR] Tool execution failed: {e}"
                    logger.exception(f"Tool {tc.name} failed")

                yield AgentEvent(
                    "tool_result",
                    {"id": tc.id, "tool": tc.name, "result": result_text},
                )
                await self._conversation.add_tool_result(tc.id, result_text)

        # If we exhausted all rounds
        yield AgentEvent(
            "error",
            {"message": f"Reached maximum tool rounds ({max_rounds}). Stopping."},
        )
        yield AgentEvent("done", {})

    async def _execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Execute a tool via the registry."""
        if not self._tool_registry:
            return "[ERROR] No tools registered"

        tool = self._tool_registry.get(tool_name)
        if not tool:
            return f"[ERROR] Unknown tool: {tool_name}"

        return await tool.execute(**arguments)

    async def _handle_plan_tool(self, arguments: dict[str, Any]) -> str:
        """Handle the built-in plan tool."""
        action = arguments.get("action", "get")
        conv_id = self._conversation.conversation_id

        if action == "create":
            title = arguments.get("title", "Untitled Plan")
            steps = arguments.get("steps", [])
            goal = arguments.get("goal")
            plan = await self._planner.create_plan(
                title=title, steps=steps, goal=goal, conversation_id=conv_id
            )
            return json.dumps({"created": plan["id"], "title": title, "steps": len(steps)})

        elif action == "update_step":
            plan = await self._planner.get_active_plan(conv_id)
            if not plan:
                return "[ERROR] No active plan to update."
            step_index = arguments.get("step_index", 0)
            status = arguments.get("status", "done")
            result = arguments.get("result")
            updated = await self._planner.update_step(plan["id"], step_index, status, result)
            if not updated:
                return f"[ERROR] Could not update step {step_index}."
            return json.dumps({
                "plan": updated["id"],
                "step": step_index,
                "status": status,
                "plan_status": updated["status"],
            })

        elif action == "get":
            plan = await self._planner.get_active_plan(conv_id)
            if not plan:
                return "No active plan."
            return self._planner.format_plan_for_context(plan)

        elif action == "complete":
            plan = await self._planner.get_active_plan(conv_id)
            if not plan:
                return "No active plan to complete."
            await self._planner.set_plan_status(plan["id"], "completed")
            return f"Plan '{plan['title']}' marked as completed."

        elif action == "cancel":
            plan = await self._planner.get_active_plan(conv_id)
            if not plan:
                return "No active plan to cancel."
            await self._planner.set_plan_status(plan["id"], "cancelled")
            return f"Plan '{plan['title']}' cancelled."

        return f"[ERROR] Unknown plan action: {action}"

    def _get_tool_definitions(self) -> list[ToolDefinition]:
        """Get tool definitions from the registry for LLM function calling.

        The `pc` tool is placed FIRST in the list to signal to the LLM that
        desktop control is the primary mode of operation.
        """
        defs: list[ToolDefinition] = []
        if self._tool_registry:
            all_defs = self._tool_registry.get_definitions()
            # Put pc tool first, then the rest
            pc_defs = [d for d in all_defs if d.name == "pc"]
            other_defs = [d for d in all_defs if d.name != "pc"]
            defs = pc_defs + other_defs

        # Always include the built-in plan tool
        if self._config.planner.enabled:
            defs.append(PLAN_TOOL_DEF)
        return defs
