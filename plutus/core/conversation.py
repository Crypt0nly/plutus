"""Conversation management — builds LLM message arrays from memory.

The ConversationManager is the brain of context management. It ensures the
agent NEVER forgets its goals, even when conversations grow very long.

Architecture:
  1. **Pinned Context** — Goals and plan are ALWAYS at the top of the prompt
  2. **Summarized History** — Old messages are compressed into structured summaries
  3. **Recent Messages** — The most recent N messages are kept verbatim
  4. **Facts** — Persistent facts about the user/environment are always included

When the conversation exceeds the context window:
  - Messages beyond the window are summarized and stored
  - The summary is injected as a system message before recent history
  - Goals extracted from the summary are pinned at the very top
  - This creates a "never forget" effect even across very long tasks
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from plutus.core.memory import MemoryStore

logger = logging.getLogger("plutus.conversation")

# This system prompt is used as a fallback; the agent.py overrides it
# with the full OpenClaw-style prompt. Kept here for standalone usage.
SYSTEM_PROMPT = """\
You are Plutus, an autonomous AI assistant with full control of the user's local machine.
You can run shell commands, edit files, browse the web, control the desktop, and more.

## Planning
For any non-trivial task, **always create a plan first** using the `plan` tool.
1. Create a plan — break the task into clear steps.
2. Mark each step in-progress before you begin.
3. Mark each step done when finished.
4. If a step fails, mark it failed and decide whether to retry or skip.

## Memory
You have a persistent memory system. Use the `memory` tool to:
- Save important facts, decisions, and progress
- Recall information from earlier in the conversation
- The memory persists across context window boundaries

Always review the conversation summary and active plan before starting work.
If there's a summary of earlier conversation, READ IT CAREFULLY — it contains
your original goals and progress that you must continue from.
"""


class ConversationManager:
    """Manages active conversations and builds message arrays for the LLM.

    Key innovation: Smart context window management that summarizes old
    messages instead of dropping them, ensuring goals are never lost.
    """

    def __init__(
        self,
        memory: MemoryStore,
        context_window: int = 20,
        planner: Any = None,
        summarizer: Any = None,
    ):
        self._memory = memory
        self._context_window = context_window
        self._active_conversation_id: str | None = None
        self._planner = planner  # PlanManager instance
        self._summarizer = summarizer  # ConversationSummarizer instance

        # In-memory cache of the current conversation's summary
        self._current_summary: dict[str, Any] | None = None

        # Track how many messages have been summarized
        self._summarized_up_to: int = 0  # message ID up to which we've summarized

        # Transient attachments for the current message (not persisted in DB)
        self.pending_attachments: list[dict[str, str]] = []

    @property
    def conversation_id(self) -> str | None:
        return self._active_conversation_id

    async def start_conversation(self, title: str | None = None) -> str:
        conv_id = str(uuid.uuid4())
        await self._memory.create_conversation(conv_id, title)
        self._active_conversation_id = conv_id
        self._current_summary = None
        self._summarized_up_to = 0
        return conv_id

    async def resume_conversation(self, conv_id: str) -> None:
        self._active_conversation_id = conv_id
        # Load existing summary if any
        self._current_summary = await self._memory.get_conversation_summary(conv_id)
        if self._current_summary:
            self._summarized_up_to = self._current_summary.get("summarized_up_to", 0)
        else:
            self._summarized_up_to = 0
        # Signal to the agent that this was a resume (not a fresh start)
        # so it can inject a mid-task context reminder if needed.
        self._just_resumed = True

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
        # Anthropic requires tool messages to always have non-empty content
        if not content or not content.strip():
            content = "(no output)"
        return await self._memory.add_message(
            self._active_conversation_id,
            "tool",
            content=content,
            tool_call_id=tool_call_id,
        )

    async def _maybe_summarize(self) -> None:
        """Check if we need to summarize old messages and do so if needed.

        Summarization is triggered when total messages exceed 1.5x the
        context window. We summarize the oldest messages, keeping the
        most recent context_window messages verbatim.
        """
        if not self._summarizer or not self._active_conversation_id:
            return

        # Quick count check — avoids loading all messages just to see if we should summarize
        total = await self._memory.get_message_count(self._active_conversation_id)

        # Only summarize when we have significantly more messages than the window
        threshold = int(self._context_window * 1.5)
        if total <= threshold:
            return

        # Now load the messages we actually need to summarize
        # (everything except the most recent context_window)
        keep_count = self._context_window
        all_messages = await self._memory.get_messages(self._active_conversation_id)
        messages_to_summarize = all_messages[:-keep_count]

        # Only summarize messages we haven't already summarized
        new_messages = [
            m for m in messages_to_summarize
            if m["id"] > self._summarized_up_to
        ]

        if not new_messages:
            return

        logger.info(
            "Summarizing %d messages (total: %d, window: %d)",
            len(new_messages), total, self._context_window
        )

        try:
            # Get existing summary text to build upon
            existing_summary_text = None
            if self._current_summary and self._current_summary.get("summary"):
                existing_summary_text = self._current_summary["summary"]

            # Summarize the new messages
            summary = await self._summarizer.summarize_messages(
                new_messages, existing_summary=existing_summary_text
            )

            # Track which messages we've summarized
            last_summarized_id = messages_to_summarize[-1]["id"]
            summary["summarized_up_to"] = last_summarized_id
            summary["message_count"] = total
            summary["summarized_count"] = len(messages_to_summarize)

            # Merge with existing summary (accumulate goals, facts, etc.)
            if self._current_summary:
                summary = _merge_summaries(self._current_summary, summary)

            # Persist the summary
            await self._memory.save_conversation_summary(
                self._active_conversation_id, summary
            )

            self._current_summary = summary
            self._summarized_up_to = last_summarized_id

            logger.info(
                "Summary updated: %d goals, %d facts, %d progress items",
                len(summary.get("goals", [])),
                len(summary.get("key_facts", [])),
                len(summary.get("progress", [])),
            )

        except Exception as e:
            logger.error(f"Summarization failed: {e}", exc_info=True)

    async def build_messages(self) -> list[dict[str, Any]]:
        """Build the message array for the LLM, including system prompt and context.

        Message structure (in order):
          1. System prompt (overridden by agent.py)
          2. [If exists] Conversation summary from earlier messages
          3. [If exists] Active plan with progress
          4. [If exists] Persistent facts
          5. Recent conversation messages (within context window)
        """
        # Trigger summarization if needed
        await self._maybe_summarize()

        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Inject conversation summary (from summarized old messages)
        if self._current_summary and self._summarizer:
            summary_text = self._summarizer.format_summary_for_context(self._current_summary)
            if summary_text.strip():
                messages.append({
                    "role": "system",
                    "content": summary_text,
                })

        # Inject the active plan so the agent always knows where it stands
        if self._planner and self._active_conversation_id:
            active_plan = await self._planner.get_active_plan(self._active_conversation_id)
            if active_plan:
                plan_text = self._planner.format_plan_for_context(active_plan)
                messages.append({
                    "role": "system",
                    "content": f"Current execution plan:\n\n{plan_text}",
                })

        # Add relevant facts as context
        facts = await self._memory.get_facts(limit=10)
        if facts:
            fact_text = "\n".join(f"- [{f['category']}] {f['content']}" for f in facts)
            messages.append({
                "role": "system",
                "content": f"Known facts about the user and their environment:\n{fact_text}",
            })

        # Add conversation history (recent messages within context window)
        if self._active_conversation_id:
            history = await self._memory.get_messages(
                self._active_conversation_id, limit=self._context_window
            )

            raw: list[dict[str, Any]] = []
            for msg in history:
                entry: dict[str, Any] = {"role": msg["role"]}
                if msg["content"]:
                    entry["content"] = msg["content"]
                elif msg["role"] == "tool":
                    # Anthropic requires tool messages to always have non-empty content
                    entry["content"] = "(no output)"
                elif msg["role"] == "assistant":
                    # Assistant messages need a content field even when they only
                    # carry tool_calls; some providers reject messages without it.
                    entry["content"] = ""
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

            # Remove orphaned tool messages that lost their pair due to
            # context window truncation cutting mid-pair.
            # 1. Collect all tool_call IDs from assistant messages
            # 2. Collect all tool_call IDs from tool result messages
            # 3. Strip orphaned tool results (no matching tool_use)
            # 4. Strip tool_calls from assistant messages (no matching tool_result)
            tool_use_ids: set[str] = set()
            tool_result_ids: set[str] = set()
            for entry in raw:
                if entry.get("tool_calls"):
                    for tc in entry["tool_calls"]:
                        tool_use_ids.add(tc["id"])
                if entry["role"] == "tool" and entry.get("tool_call_id"):
                    tool_result_ids.add(entry["tool_call_id"])

            for entry in raw:
                # Skip orphaned tool results (no matching assistant tool_use)
                # IMPORTANT: use explicit flag so we don't fall through to append
                if entry["role"] == "tool" and entry.get("tool_call_id"):
                    if entry["tool_call_id"] not in tool_use_ids:
                        logger.debug(
                            "Dropping orphaned tool result %s (no matching tool_call in window)",
                            entry["tool_call_id"],
                        )
                        continue  # skip — do NOT append
                # Strip orphaned tool_calls from assistant messages
                # (tool_results were summarized away or truncated)
                if entry.get("tool_calls"):
                    paired = [
                        tc for tc in entry["tool_calls"]
                        if tc["id"] in tool_result_ids
                    ]
                    if not paired:
                        # All tool_calls are orphaned — drop the tool_calls list
                        # but KEEP the message itself (it may have text content)
                        entry.pop("tool_calls", None)
                        # If the assistant message now has no content AND no tool_calls,
                        # skip it entirely to avoid sending an empty assistant turn
                        if not entry.get("content"):
                            logger.debug("Dropping empty assistant message (all tool_calls orphaned)")
                            continue
                    elif len(paired) < len(entry["tool_calls"]):
                        entry["tool_calls"] = paired
                messages.append(entry)

        # Attach pending file attachments to the last user message.
        # Attachments are transient (not persisted) and only apply to the
        # current message.  The LLM client handles provider-specific
        # formatting (Anthropic vs OpenAI) in _format_multimodal_content().
        if self.pending_attachments:
            # Find the last user message in the list
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("role") == "user":
                    messages[i]["attachments"] = self.pending_attachments
                    break
            # Clear after use — attachments are single-shot
            self.pending_attachments = []

        return messages

    async def get_summary(self) -> dict[str, Any] | None:
        """Get the current conversation summary (for UI display)."""
        if self._current_summary:
            return self._current_summary
        if self._active_conversation_id:
            return await self._memory.get_conversation_summary(self._active_conversation_id)
        return None

    async def list_conversations(self, limit: int = 20) -> list[dict[str, Any]]:
        return await self._memory.list_conversations(limit)

    async def delete_conversation(self, conv_id: str) -> None:
        await self._memory.delete_conversation(conv_id)
        if self._active_conversation_id == conv_id:
            self._active_conversation_id = None
            self._current_summary = None
            self._summarized_up_to = 0


def _merge_summaries(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Merge an old summary with a new one, keeping the most complete picture."""
    merged = dict(new)  # Start with new summary

    # Goals: keep all unique goals (old goals are the original ones)
    old_goals = set(old.get("goals", []))
    new_goals = set(new.get("goals", []))
    merged["goals"] = list(old_goals | new_goals)

    # Key facts: accumulate, deduplicate
    old_facts = set(old.get("key_facts", []))
    new_facts = set(new.get("key_facts", []))
    merged["key_facts"] = list(old_facts | new_facts)

    # Key decisions: accumulate
    old_decisions = old.get("key_decisions", [])
    new_decisions = new.get("key_decisions", [])
    seen = set()
    all_decisions = []
    for d in old_decisions + new_decisions:
        if d not in seen:
            seen.add(d)
            all_decisions.append(d)
    merged["key_decisions"] = all_decisions

    # Progress: new summary should have the full picture, but keep old items
    # that might have been dropped
    old_progress = old.get("progress", [])
    new_progress = new.get("progress", [])
    seen_progress = set(new_progress)
    for p in old_progress:
        if p not in seen_progress:
            new_progress.insert(0, p)  # Old progress goes first
    merged["progress"] = new_progress

    # Use new summary's current_state, next_steps, blockers (they're more recent)
    # But keep the summarized_up_to from new
    return merged
