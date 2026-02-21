"""Conversation management — builds LLM message arrays from memory."""

from __future__ import annotations

import uuid
from typing import Any

from plutus.core.memory import MemoryStore

SYSTEM_PROMPT = """You are Plutus, an autonomous AI assistant running on the user's local machine.

You have access to tools that let you interact with the computer: executing shell commands,
reading and writing files, browsing the web, managing processes, and more.

Key principles:
1. Be helpful and proactive — anticipate what the user needs.
2. Respect the guardrails — if a tool action is denied or requires approval, explain why
   and wait for the user's decision. Never try to circumvent permissions.
3. Be transparent — always tell the user what you're about to do before doing it.
4. Be safe — avoid destructive actions unless explicitly asked. Prefer reversible operations.
5. Remember context — use your memory to provide personalized, context-aware assistance.

When you need to perform an action, use the appropriate tool. If the action requires approval,
the user will be prompted in the UI. Wait for their response before proceeding.
"""


class ConversationManager:
    """Manages active conversations and builds message arrays for the LLM."""

    def __init__(self, memory: MemoryStore, context_window: int = 20):
        self._memory = memory
        self._context_window = context_window
        self._active_conversation_id: str | None = None

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
            for msg in history:
                entry: dict[str, Any] = {"role": msg["role"]}
                if msg["content"]:
                    entry["content"] = msg["content"]
                if msg["tool_calls"]:
                    entry["tool_calls"] = msg["tool_calls"]
                if msg["tool_call_id"]:
                    entry["tool_call_id"] = msg["tool_call_id"]
                messages.append(entry)

        return messages

    async def list_conversations(self, limit: int = 20) -> list[dict[str, Any]]:
        return await self._memory.list_conversations(limit)

    async def delete_conversation(self, conv_id: str) -> None:
        await self._memory.delete_conversation(conv_id)
        if self._active_conversation_id == conv_id:
            self._active_conversation_id = None
