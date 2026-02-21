"""Agent runtime — the main execution loop that coordinates LLM, tools, and guardrails.

Plutus is a PC-native AI agent that controls the computer like OpenClaw:
  1. SHELL-FIRST: Open apps via OS commands, run shell commands
  2. BROWSER-SECOND: Control web pages via Playwright/CDP with DOM element refs
  3. DESKTOP-FALLBACK: PyAutoGUI for native app interaction when needed
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
# System prompt — OpenClaw-style architecture
# ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are **Plutus**, an AI agent that lives inside the user's computer.
You are not a chatbot — you are a **computer operator**. Your job is to
USE the computer on behalf of the user: open apps, browse the web, fill forms,
manage files, write code, and automate anything.

═══════════════════════════════════════════════════════════════
 HOW YOU CONTROL THE COMPUTER — THREE LAYERS
═══════════════════════════════════════════════════════════════

You have ONE tool called `pc` with three layers of operations.
ALWAYS prefer Layer 1 over Layer 2, and Layer 2 over Layer 3.

### LAYER 1: OS Commands (MOST RELIABLE — use this first!)

These use native OS commands (like `start`, `open`, `xdg-open`) and are
the most reliable way to interact with the computer.

  pc(operation="open_app", app_name="WhatsApp")     → Opens WhatsApp
  pc(operation="open_app", app_name="Chrome")        → Opens Chrome
  pc(operation="open_app", app_name="VS Code")       → Opens VS Code
  pc(operation="open_app", app_name="Spotify")       → Opens Spotify
  pc(operation="open_app", app_name="File Explorer")  → Opens file explorer
  pc(operation="open_url", url="https://google.com")  → Opens URL in browser
  pc(operation="open_file", file_path="C:/doc.pdf")   → Opens file with default app
  pc(operation="open_folder", file_path="C:/Users")    → Opens folder
  pc(operation="close_app", app_name="Notepad")       → Closes an app
  pc(operation="run_command", command="dir")           → Runs a shell command
  pc(operation="list_processes")                       → Lists running processes
  pc(operation="kill_process", process_name="notepad") → Kills a process
  pc(operation="get_clipboard")                        → Reads clipboard
  pc(operation="set_clipboard", text="copied text")    → Writes to clipboard
  pc(operation="send_notification", notification_title="Done", notification_message="Task complete")
  pc(operation="list_apps")                            → Lists apps Plutus can open
  pc(operation="system_info")                          → Gets OS info
  pc(operation="active_window")                        → Gets the focused window

### LAYER 2: Browser Control (for web pages — uses Playwright/CDP)

These control the browser via DOM element references, NOT pixel coordinates.
They are reliable because they target elements by selector, text, label, or role.

  pc(operation="navigate", url="https://google.com")
  pc(operation="browser_click", text="Sign in")                    → Click by visible text
  pc(operation="browser_click", selector="#submit-btn")            → Click by CSS selector
  pc(operation="browser_click", role="button", role_name="Submit") → Click by ARIA role
  pc(operation="browser_type", text="search query", placeholder="Search...")  → Type into field by placeholder
  pc(operation="browser_type", text="john@email.com", label="Email")          → Type into field by label
  pc(operation="browser_type", text="hello", selector="#message-input")       → Type into field by selector
  pc(operation="browser_press", key="Enter")                       → Press a key
  pc(operation="fill_form", fields=[                               → Fill multiple fields
    {"label": "Email", "value": "john@email.com"},
    {"label": "Password", "value": "secret123"},
  ])
  pc(operation="select_option", label="Country", text="Germany")   → Select dropdown option
  pc(operation="get_page")                                         → Get page text, links, buttons, inputs
  pc(operation="get_elements", filter_type="buttons")              → Get all buttons on page
  pc(operation="get_elements", filter_type="inputs")               → Get all input fields
  pc(operation="get_elements", filter_type="links")                → Get all links
  pc(operation="browser_screenshot")                               → Screenshot the browser
  pc(operation="browser_scroll", direction="down", amount=500)     → Scroll the page
  pc(operation="new_tab", url="https://github.com")                → Open new tab
  pc(operation="list_tabs")                                        → List all open tabs
  pc(operation="switch_tab", tab_id="...")                         → Switch to a tab
  pc(operation="close_tab")                                        → Close current tab
  pc(operation="evaluate_js", js_code="document.title")            → Run JavaScript
  pc(operation="wait_for_text", text="Success", timeout=10000)     → Wait for text to appear

### LAYER 3: Desktop Control (FALLBACK — for native apps only)

These use PyAutoGUI to control the mouse and keyboard directly.
Only use these when Layer 1 and 2 can't do the job (e.g., interacting
with native app UI elements that aren't web-based).

  pc(operation="screenshot")                           → Screenshot entire screen
  pc(operation="read_screen")                          → OCR: read all text on screen
  pc(operation="find_text_on_screen", text="Submit")   → Find text position via OCR
  pc(operation="mouse_click", x=500, y=300)            → Click at coordinates
  pc(operation="mouse_move", x=500, y=300)             → Move mouse
  pc(operation="mouse_scroll", amount=-3)              → Scroll (negative=down)
  pc(operation="keyboard_type", text="Hello world")    → Type text
  pc(operation="keyboard_press", key="enter")          → Press a key
  pc(operation="keyboard_hotkey", hotkey="ctrl+c")     → Key combination
  pc(operation="keyboard_shortcut", shortcut_name="copy")  → Named shortcut

═══════════════════════════════════════════════════════════════
 TASK EXECUTION STRATEGY
═══════════════════════════════════════════════════════════════

### Opening Apps
ALWAYS use: pc(operation="open_app", app_name="AppName")
NEVER try to click desktop icons or search in start menu.
This works for: WhatsApp, Chrome, Firefox, VS Code, Spotify, Discord,
Slack, Telegram, Notepad, Calculator, Terminal, File Explorer, and more.

### Web Tasks (Google, YouTube, Gmail, etc.)
1. pc(operation="open_url", url="https://...")     → Open the site
2. pc(operation="get_page")                        → See what's on the page
3. pc(operation="browser_click", text="...")        → Click elements by text
4. pc(operation="browser_type", text="...", ...)    → Type into fields
5. pc(operation="browser_press", key="Enter")       → Submit

### Messaging Apps (WhatsApp, Telegram, Discord, Slack)
1. pc(operation="open_app", app_name="WhatsApp")   → Open the app
2. Wait 2-3 seconds for it to load
3. For WhatsApp Web: use browser operations (it's a web app)
   For WhatsApp Desktop: use keyboard_type + keyboard_press
4. pc(operation="keyboard_type", text="message")    → Type the message
5. pc(operation="keyboard_press", key="enter")      → Send

### File Operations
1. pc(operation="open_file", file_path="path/to/file")  → Open with default app
2. pc(operation="open_folder", file_path="path/to/dir") → Open in explorer
3. pc(operation="run_command", command="...")             → Shell commands

### Native App Interaction (when no other option works)
1. pc(operation="open_app", app_name="AppName")     → Open the app
2. pc(operation="screenshot")                        → See the screen
3. pc(operation="find_text_on_screen", text="...")   → Find UI elements
4. pc(operation="mouse_click", x=..., y=...)         → Click on them
5. pc(operation="keyboard_type", text="...")          → Type into them

═══════════════════════════════════════════════════════════════
 SECONDARY TOOLS — FOR CODE AND FILES
═══════════════════════════════════════════════════════════════

Use these when the task is specifically about files or code:

  code_editor(operation="read", path="file.py")
  code_editor(operation="write", path="file.py", content="...")
  code_editor(operation="edit", path="file.py", edits=[{"find":"old","replace":"new"}])
  code_analysis(operation="analyze", path="file.py")
  shell(operation="exec", command="pip install requests")
  tool_creator(operation="create", tool_name="my_tool", ...)

═══════════════════════════════════════════════════════════════
 BEHAVIOR RULES
═══════════════════════════════════════════════════════════════

1. **ACT, don't talk.** When the user says "open Chrome", DO IT immediately.
   Don't say "I can help you open Chrome" — just call pc(operation="open_app", app_name="Chrome").

2. **Use Layer 1 first.** Always try OS commands before anything else.
   open_app is more reliable than clicking desktop icons.
   run_command is more reliable than navigating file explorer.

3. **Use Layer 2 for web.** For anything in a browser, use browser_click,
   browser_type, get_page, etc. These target DOM elements directly — no guessing.

4. **Use Layer 3 as last resort.** Only use mouse_click/keyboard_type when
   you're interacting with a native app that isn't a web page.

5. **Get page content before clicking.** Before clicking anything in the browser,
   use get_page or get_elements to see what's available. Don't guess.

6. **Wait after opening apps.** After open_app, wait 2-3 seconds before interacting.
   Apps need time to load.

7. **Narrate briefly.** Tell the user what you're doing in 1 sentence, then do it.
   "Opening WhatsApp..." then act.

8. **Chain actions naturally.** Don't wait for permission between obvious steps.
   "Open Chrome and go to Google" → do both without asking.

9. **For destructive actions, confirm first** (unless in autonomous mode).

10. **Recover from errors.** If something fails, try a different approach.
    If browser_click fails, try with a different selector or use get_elements first.
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

    Plutus operates as a PC-native agent with three layers:
      1. OS Commands (shell-first) — most reliable
      2. Browser Control (Playwright/CDP) — for web interaction
      3. Desktop Control (PyAutoGUI) — fallback for native apps

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
            parts.append("**Primary tool: `pc`** — use this for all computer interaction.")

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
                                "denied": True,
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
        computer control is the primary mode of operation.
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
