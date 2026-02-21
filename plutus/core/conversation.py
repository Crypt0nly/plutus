"""Conversation management — builds LLM message arrays from memory."""

from __future__ import annotations

import json
import uuid
from typing import Any

from plutus.core.memory import MemoryStore

SYSTEM_PROMPT = """You are Plutus, an autonomous AI assistant with full control of the user's local machine.

You have access to powerful tools that let you operate the entire computer — like a friendly ghost
sitting at the keyboard. Your capabilities include:

- **Shell**: Run any terminal/PowerShell command, scripts, package managers, git, builds, etc.
- **Filesystem**: Read, write, search, copy, move, and manage files and directories.
- **Browser**: Navigate the web, take page screenshots, fill forms, click elements, run JavaScript.
  Cookie/consent banners are auto-dismissed on navigation. Prefer `click_text` over `click` when
  targeting buttons or links — it matches by visible text (e.g. value="Sign in") and is far more
  reliable than CSS selectors on dynamic sites. Use `wait` before interacting with slow-loading elements.
- **Desktop**: See the screen (screenshots), click anywhere, type text, press hotkeys (Ctrl+C,
  Alt+Tab, etc.), scroll, move the mouse — full GUI automation of any visible application.
- **App Manager**: Launch any application by name, list all open windows, focus/minimize/maximize/
  close/resize/move windows across the desktop.
- **Process**: List running processes, start new ones, stop existing ones.
- **System Info**: Check CPU, memory, disk, network, and OS details.
- **Clipboard**: Read from and write to the system clipboard.

You can chain these tools together to accomplish complex tasks: open an app, wait for it to load,
take a screenshot to see the current state, click buttons, type into fields, and verify the result.
Think step by step when automating GUI workflows — screenshot first to see what's on screen, then
act on what you see.

Key principles:
1. Be helpful and proactive — anticipate what the user needs.
2. Respect the guardrails — if a tool action is denied or requires approval, explain why
   and wait for the user's decision. Never try to circumvent permissions.
3. Be transparent — always tell the user what you're about to do before doing it.
4. Be safe — avoid destructive actions unless explicitly asked. Prefer reversible operations.
5. Remember context — use your memory to provide personalized, context-aware assistance.
6. For GUI automation — always take a screenshot first to orient yourself, then act on what
   you see. If something doesn't look right, screenshot again and adjust.

When you need to perform an action, use the appropriate tool. If the action requires approval,
the user will be prompted in the UI. Wait for their response before proceeding.

## Planning

For any non-trivial task (multi-step, complex, or long-running), **always create a plan first**
using the `plan` tool before you start working. This keeps you and the user in sync:

1. **Create a plan** — break the task into clear, discrete steps.
2. **Start each step** — mark it in-progress before you begin.
3. **Complete each step** — mark it done (with a short result summary) when finished.
4. **If a step fails** — mark it failed with the reason, then decide whether to retry or skip.

During heartbeat check-ins (automatic wake-ups), always review the current plan
and continue from where you left off. If there's no plan and nothing to do, just
confirm you're standing by.

The user can see your plan and its progress in real time through the UI.
"""


class ConversationManager:
    """Manages active conversations and builds message arrays for the LLM."""

    def __init__(self, memory: MemoryStore, context_window: int = 20, planner: Any = None):
        self._memory = memory
        self._context_window = context_window
        self._active_conversation_id: str | None = None
        self._planner = planner  # PlanManager instance (optional)

    @property
    def conversation_id(self) -> str | None:
        return self._active_conversation_id

    async def start_conversation(self, title: str | None = None) -> str:
        conv_id = str(uuid.uuid4())
        await self._memory.create_conversation(conv_id, title)
        self._active_conversation_id = conv_id
        return conv_id

    async def resume_conversation(self, conv_id: str) -> None:
        self._active_conversation_id = conv_id

    async def add_user_message(self, content: str) -> int:
        assert self._active_conversation_id
        return await self._memory.add_message(
            self._active_conversation_id, "user", content=content
        )

    async def add_assistant_message(
        self,
        content: str | None = None,
        tool_calls: list[dict] | None = None,
    ) -> int:
        assert self._active_conversation_id
        return await self._memory.add_message(
            self._active_conversation_id,
            "assistant",
            content=content,
            tool_calls=tool_calls,
        )

    async def add_tool_result(self, tool_call_id: str, content: str) -> int:
        assert self._active_conversation_id
        return await self._memory.add_message(
            self._active_conversation_id,
            "tool",
            content=content,
            tool_call_id=tool_call_id,
        )

    async def build_messages(self) -> list[dict[str, Any]]:
        """Build the message array for the LLM, including system prompt and context."""
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Inject the active plan so the agent always knows where it stands
        if self._planner and self._active_conversation_id:
            active_plan = await self._planner.get_active_plan(self._active_conversation_id)
            if active_plan:
                plan_text = self._planner.format_plan_for_context(active_plan)
                messages.append(
                    {
                        "role": "system",
                        "content": f"Current execution plan:\n\n{plan_text}",
                    }
                )

        # Add relevant facts as context
        facts = await self._memory.get_facts(limit=10)
        if facts:
            fact_text = "\n".join(f"- [{f['category']}] {f['content']}" for f in facts)
            messages.append(
                {
                    "role": "system",
                    "content": f"Known facts about the user and their environment:\n{fact_text}",
                }
            )

        # Add conversation history
        if self._active_conversation_id:
            history = await self._memory.get_messages(
                self._active_conversation_id, limit=self._context_window
            )

            raw: list[dict[str, Any]] = []
            for msg in history:
                entry: dict[str, Any] = {"role": msg["role"]}
                if msg["content"]:
                    entry["content"] = msg["content"]
                if msg["tool_calls"]:
                    # Convert stored format to OpenAI-compatible format for LiteLLM
                    entry["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": (
                                    json.dumps(tc["arguments"])
                                    if isinstance(tc["arguments"], dict)
                                    else tc["arguments"]
                                ),
                            },
                        }
                        for tc in msg["tool_calls"]
                    ]
                if msg["tool_call_id"]:
                    entry["tool_call_id"] = msg["tool_call_id"]
                raw.append(entry)

            # Remove orphaned tool results that lost their assistant tool_call
            # (can happen when context window truncation cuts mid-pair)
            tool_call_ids: set[str] = set()
            for entry in raw:
                if entry.get("tool_calls"):
                    for tc in entry["tool_calls"]:
                        tool_call_ids.add(tc["id"])

            for entry in raw:
                if entry["role"] == "tool" and entry.get("tool_call_id"):
                    if entry["tool_call_id"] not in tool_call_ids:
                        continue  # skip orphaned tool result
                messages.append(entry)

        return messages

    async def list_conversations(self, limit: int = 20) -> list[dict[str, Any]]:
        return await self._memory.list_conversations(limit)

    async def delete_conversation(self, conv_id: str) -> None:
        await self._memory.delete_conversation(conv_id)
        if self._active_conversation_id == conv_id:
            self._active_conversation_id = None
