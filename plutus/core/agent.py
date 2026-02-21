"""Agent runtime — the main execution loop that coordinates LLM, tools, and guardrails.

Enhanced with:
  - Subprocess orchestration for parallel task execution
  - Dynamic tool creation support
  - Improved system prompt with tool awareness
  - Better error recovery
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

# System prompt that instructs the agent on how to use its capabilities
SYSTEM_PROMPT = """\
You are Plutus, an autonomous AI agent with full computer control capabilities.

## Core Capabilities
You have access to powerful tools that let you:
1. **Execute shell commands** — Run any terminal command
2. **Edit and create files** — Read, write, and surgically edit any file using the code_editor tool
3. **Analyze code** — Deep AST-based analysis of Python files (functions, classes, complexity, call graphs)
4. **Spawn subprocesses** — Run isolated worker processes for parallel task execution
5. **Create new tools** — Write Python scripts that become new tools you can use
6. **Manage processes** — List, monitor, and control system processes
7. **Browse the web** — Navigate and interact with websites
8. **Access the filesystem** — Full filesystem operations

## How to Work
- **Plan first**: For complex tasks, create a plan with clear steps before executing.
- **Use subprocesses**: For file editing and code analysis, prefer the code_editor and code_analysis tools — they run in isolated subprocesses.
- **Be surgical with edits**: Use the code_editor's 'edit' operation with find/replace for precise changes instead of rewriting entire files.
- **Create tools when needed**: If you need a capability that doesn't exist, use tool_creator to write a new tool.
- **Parallelize**: Use the subprocess tool's spawn_many to run multiple tasks simultaneously.
- **Verify your work**: After making changes, read the file back or run tests to confirm correctness.

## Tool Usage Patterns

### Editing files (preferred approach):
1. Read the file first: code_editor(operation="read", path="...")
2. Apply surgical edits: code_editor(operation="edit", path="...", edits=[{"find": "old", "replace": "new"}])
3. Verify: code_editor(operation="read", path="...", start_line=X, end_line=Y)

### Creating new files:
code_editor(operation="write", path="...", content="...")

### Analyzing code:
code_analysis(operation="analyze", path="...") — full analysis
code_analysis(operation="complexity", path="...") — just complexity
code_analysis(operation="find_functions", path="...") — list functions

### Running commands:
shell(operation="exec", command="...") — for simple commands
subprocess(operation="spawn", worker_type="shell", command={"action": "exec", "command": "..."}) — for isolated execution

### Creating custom tools:
tool_creator(operation="create", tool_name="my_tool", description="...", code="def main(args): ...")

## Guidelines
- Always explain what you're doing and why.
- If a tool call fails, analyze the error and try a different approach.
- For destructive operations, confirm with the user first (unless in autonomous tier).
- Keep responses concise but informative.
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

    Flow:
      1. User sends message
      2. Agent builds context (system prompt + memory + history)
      3. Agent sends to LLM with available tools
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

        # Add available tools summary
        if self._tool_registry:
            tool_names = self._tool_registry.list_tools()
            parts.append(f"\n## Available Tools: {', '.join(tool_names)}")

        # Add tier info
        tier = self._config.guardrails.tier
        tier_descriptions = {
            "observer": "You are in OBSERVER mode — read-only, no actions allowed.",
            "assistant": "You are in ASSISTANT mode — all actions require user approval.",
            "operator": "You are in OPERATOR mode — pre-approved actions run automatically, risky ones need approval.",
            "autonomous": "You are in AUTONOMOUS mode — full control, no restrictions.",
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
        """Get tool definitions from the registry for LLM function calling."""
        defs: list[ToolDefinition] = []
        if self._tool_registry:
            defs = self._tool_registry.get_definitions()
        # Always include the built-in plan tool
        if self._config.planner.enabled:
            defs.append(PLAN_TOOL_DEF)
        return defs
