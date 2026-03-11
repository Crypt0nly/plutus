"""Conversation summarizer — compresses old messages into concise summaries.

When a conversation grows beyond the context window, the summarizer:
1. Takes the oldest messages that would be dropped
2. Sends them to the LLM for summarization
3. Extracts key goals, decisions, facts, and progress
4. Returns a structured summary that replaces the raw messages

This keeps the agent aware of its goals and progress even across
very long conversations that exceed the context window.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger("plutus.summarizer")

# The prompt used to summarize conversation chunks
SUMMARIZE_PROMPT = """\
You are a conversation summarizer for an AI agent called Plutus.
Your job is to compress a chunk of conversation into a concise summary
that preserves ALL critical information the agent needs to continue working.

You MUST extract and preserve:
1. **GOALS**: What the user originally asked for (the top-level objective)
2. **PROGRESS**: What steps have been completed so far
3. **CURRENT STATE**: What the agent was working on when this chunk ended
4. **KEY DECISIONS**: Important choices made (e.g., which approach to use)
5. **KEY FACTS**: Technical details, file paths, URLs, credentials, names, etc.
6. **BLOCKERS**: Any issues encountered and how they were resolved (or not)
7. **NEXT STEPS**: What the agent planned to do next

Return your summary as a JSON object with this exact structure:
{
  "goals": ["Primary goal 1", "Sub-goal 2"],
  "progress": ["Step 1 completed: did X", "Step 2 completed: did Y"],
  "current_state": "Brief description of where things stand",
  "key_decisions": ["Decided to use approach A because..."],
  "key_facts": ["File is at /path/to/file", "User's name is X"],
  "blockers": ["Issue with X was resolved by Y"],
  "next_steps": ["Need to do A", "Then do B"],
  "summary": "One paragraph narrative summary of the entire conversation chunk"
}

Be thorough but concise. Every piece of information that the agent might
need to continue its work MUST be preserved. Do NOT lose any goals,
file paths, technical details, or user preferences.
"""


class ConversationSummarizer:
    """Summarizes conversation chunks to compress context."""

    def __init__(self, llm_client: Any):
        """Initialize with an LLMClient instance."""
        self._llm = llm_client

    async def summarize_messages(
        self,
        messages: list[dict[str, Any]],
        existing_summary: str | None = None,
    ) -> dict[str, Any]:
        """Summarize a list of messages into a structured summary.

        Args:
            messages: The messages to summarize (in chronological order)
            existing_summary: If provided, the new summary should build on this

        Returns:
            A structured summary dict with goals, progress, etc.
        """
        if not messages:
            return _empty_summary()

        # Build the conversation text for summarization
        conv_text = _format_messages_for_summary(messages)

        prompt_parts = [SUMMARIZE_PROMPT]

        if existing_summary:
            prompt_parts.append(
                f"\n\n## Previous Summary (build on this):\n{existing_summary}"
            )

        prompt_parts.append(f"\n\n## Conversation to Summarize:\n{conv_text}")

        try:
            response = await self._llm.complete(
                messages=[
                    {"role": "system", "content": "\n".join(prompt_parts)},
                    {"role": "user", "content": "Summarize the conversation above. Return ONLY the JSON object."},
                ],
                max_tokens=2048,
            )

            if response.content:
                return _parse_summary(response.content)
            else:
                logger.warning("Empty response from summarizer LLM")
                return _fallback_summary(messages)

        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            return _fallback_summary(messages)

    def format_summary_for_context(self, summary: dict[str, Any]) -> str:
        """Format a structured summary as readable text for the system prompt."""
        parts = ["## Conversation History Summary"]
        parts.append("*(Earlier messages were summarized to save context space)*\n")

        if summary.get("goals"):
            parts.append("### Original Goals")
            for g in summary["goals"]:
                parts.append(f"  - {g}")
            parts.append("")

        if summary.get("progress"):
            parts.append("### Progress So Far")
            for p in summary["progress"]:
                parts.append(f"  - {p}")
            parts.append("")

        if summary.get("current_state"):
            parts.append(f"### Current State\n{summary['current_state']}\n")

        if summary.get("key_decisions"):
            parts.append("### Key Decisions")
            for d in summary["key_decisions"]:
                parts.append(f"  - {d}")
            parts.append("")

        if summary.get("key_facts"):
            parts.append("### Key Facts")
            for f in summary["key_facts"]:
                parts.append(f"  - {f}")
            parts.append("")

        if summary.get("blockers"):
            parts.append("### Issues & Resolutions")
            for b in summary["blockers"]:
                parts.append(f"  - {b}")
            parts.append("")

        if summary.get("next_steps"):
            parts.append("### Next Steps")
            for n in summary["next_steps"]:
                parts.append(f"  - {n}")
            parts.append("")

        if summary.get("summary"):
            parts.append(f"### Narrative Summary\n{summary['summary']}")

        return "\n".join(parts)


def _format_messages_for_summary(messages: list[dict[str, Any]]) -> str:
    """Convert messages to a readable text format for the summarizer."""
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")

        if role == "system":
            continue  # Skip system messages in summary input

        if role == "tool":
            # Truncate very long tool results
            tool_id = msg.get("tool_call_id", "unknown")
            if content and len(content) > 500:
                content = content[:500] + "... [truncated]"
            lines.append(f"[Tool Result ({tool_id})]: {content}")
        elif role == "assistant":
            if content:
                lines.append(f"[Assistant]: {content}")
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    if isinstance(tc, dict):
                        name = tc.get("name", tc.get("function", {}).get("name", "unknown"))
                        args = tc.get("arguments", tc.get("function", {}).get("arguments", {}))
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                pass
                        # Summarize the tool call
                        args_brief = _brief_args(args) if isinstance(args, dict) else str(args)[:200]
                        lines.append(f"[Assistant called {name}]: {args_brief}")
        elif role == "user":
            lines.append(f"[User]: {content}")

    return "\n".join(lines)


def _brief_args(args: dict) -> str:
    """Create a brief summary of tool arguments."""
    parts = []
    for k, v in args.items():
        val_str = str(v)
        if len(val_str) > 100:
            val_str = val_str[:100] + "..."
        parts.append(f"{k}={val_str}")
    return ", ".join(parts)


def _parse_summary(text: str) -> dict[str, Any]:
    """Parse the LLM's JSON response into a summary dict."""
    # Try to extract JSON from the response
    text = text.strip()

    # Handle markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (```json and ```)
        json_lines = []
        in_block = False
        for line in lines:
            if line.strip().startswith("```") and not in_block:
                in_block = True
                continue
            elif line.strip() == "```" and in_block:
                break
            elif in_block:
                json_lines.append(line)
        text = "\n".join(json_lines)

    try:
        data = json.loads(text)
        # Validate expected fields
        return {
            "goals": data.get("goals", []),
            "progress": data.get("progress", []),
            "current_state": data.get("current_state", ""),
            "key_decisions": data.get("key_decisions", []),
            "key_facts": data.get("key_facts", []),
            "blockers": data.get("blockers", []),
            "next_steps": data.get("next_steps", []),
            "summary": data.get("summary", ""),
            "created_at": time.time(),
        }
    except json.JSONDecodeError:
        logger.warning("Could not parse summary JSON, using fallback")
        return {
            "goals": [],
            "progress": [],
            "current_state": "",
            "key_decisions": [],
            "key_facts": [],
            "blockers": [],
            "next_steps": [],
            "summary": text[:1000],  # Use raw text as summary
            "created_at": time.time(),
        }


def _empty_summary() -> dict[str, Any]:
    return {
        "goals": [],
        "progress": [],
        "current_state": "",
        "key_decisions": [],
        "key_facts": [],
        "blockers": [],
        "next_steps": [],
        "summary": "",
        "created_at": time.time(),
    }


def _fallback_summary(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a basic summary without LLM when summarization fails."""
    goals = []
    progress = []

    for msg in messages:
        if msg.get("role") == "user" and msg.get("content"):
            content = msg["content"]
            if len(content) > 200:
                content = content[:200] + "..."
            goals.append(content)

    # Only keep first user message as the primary goal
    if goals:
        goals = [goals[0]]

    return {
        "goals": goals,
        "progress": progress,
        "current_state": f"Conversation had {len(messages)} messages before summarization",
        "key_decisions": [],
        "key_facts": [],
        "blockers": [],
        "next_steps": [],
        "summary": f"Conversation with {len(messages)} messages. Primary request: {goals[0] if goals else 'unknown'}",
        "created_at": time.time(),
    }
