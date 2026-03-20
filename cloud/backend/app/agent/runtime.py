"""
Cloud agent runtime.

Calls the LLM using the API key stored in the user's connector_credentials
column (set during onboarding via PUT /connectors/{name}/config).
Falls back to the server-level settings key only if no per-user key is found.

Tool execution is handled by HybridExecutor:
  - If the user's local Plutus bridge is connected → delegate to local machine
  - Otherwise → run in an E2B cloud sandbox
"""

from __future__ import annotations

import json
import logging
from uuid import uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.agent_service import AgentService
from app.services.hybrid_executor import TOOL_DEFINITIONS, TOOL_DEFINITIONS_OPENAI, HybridExecutor

logger = logging.getLogger(__name__)

# Maximum number of tool-call rounds before forcing a final answer
_MAX_TOOL_ROUNDS = 10


class CloudAgentRuntime:
    def __init__(self, user_id: str, session: AsyncSession, config: dict = None):
        self.user_id = user_id
        self.session = session
        self.config = config or {}
        self.agent_service = AgentService(session)
        self.executor = HybridExecutor.get_instance()

    async def process_message(self, message: str, conversation_id: str = None) -> dict:
        """
        Main entry point.

        1. Creates/loads conversation
        2. Runs the agentic loop (LLM → tool calls → LLM → … → final answer)
        3. Persists all messages and returns the final response
        """
        if conversation_id is None:
            conversation_id = str(uuid4())
            await self.agent_service.create_conversation(conversation_id, self.user_id)

        await self._save_message(conversation_id, "user", message)

        history = await self.agent_service.get_messages(conversation_id)
        messages = [{"role": m.role, "content": m.content} for m in history]

        system_prompt = await self._build_system_prompt()
        provider = self.config.get("provider", settings.default_llm_provider)

        # Run the agentic loop
        if provider == "openai":
            response_text = await self._agentic_loop_openai(messages, system_prompt)
        else:
            response_text = await self._agentic_loop_anthropic(messages, system_prompt)

        await self._save_message(conversation_id, "assistant", response_text)

        return {
            "response": response_text,
            "conversation_id": conversation_id,
        }

    # ── Agentic loops ─────────────────────────────────────────────────────────

    async def _agentic_loop_anthropic(self, messages: list[dict], system_prompt: str) -> str:
        """
        Anthropic agentic loop with tool use.

        Keeps calling the API until the model returns a text-only response
        (stop_reason == "end_turn") or we hit _MAX_TOOL_ROUNDS.
        """
        api_key = await self._get_user_api_key("anthropic")
        if not api_key:
            raise ValueError(
                "No Anthropic API key configured. "
                "Please add your key in Settings → Connectors → Anthropic."
            )
        model = self.config.get("model", "claude-opus-4-5")

        # Work on a copy so we don't mutate the caller's list
        msgs = list(messages)

        for _round in range(_MAX_TOOL_ROUNDS):
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    json={
                        "model": model,
                        "max_tokens": 4096,
                        "system": system_prompt,
                        "messages": msgs,
                        "tools": TOOL_DEFINITIONS,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            stop_reason = data.get("stop_reason", "end_turn")
            content_blocks = data.get("content", [])

            # Collect text and tool_use blocks
            text_parts: list[str] = []
            tool_calls: list[dict] = []
            for block in content_blocks:
                if block.get("type") == "text":
                    text_parts.append(block["text"])
                elif block.get("type") == "tool_use":
                    tool_calls.append(block)

            if stop_reason != "tool_use" or not tool_calls:
                # Final answer
                return "\n".join(text_parts).strip()

            # Append assistant message (with tool_use blocks) to history
            msgs.append({"role": "assistant", "content": content_blocks})

            # Execute each tool call and collect results
            tool_results = []
            for tc in tool_calls:
                tool_name = tc["name"]
                tool_args = tc.get("input", {})
                tc_id = tc["id"]

                logger.info(f"[Agent] Tool call: {tool_name}({tool_args}) for user {self.user_id}")

                try:
                    result = await self.executor.execute(self.user_id, tool_name, tool_args)
                    result_text = _format_tool_result(tool_name, result)
                except Exception as e:
                    result_text = f"Error executing {tool_name}: {e}"
                    logger.error(f"[Agent] Tool error: {e}", exc_info=True)

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tc_id,
                        "content": result_text,
                    }
                )

            # Append tool results as a user message
            msgs.append({"role": "user", "content": tool_results})

        # Fallback: ask for a final answer without tools
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": model,
                    "max_tokens": 2048,
                    "system": system_prompt,
                    "messages": msgs
                    + [
                        {
                            "role": "user",
                            "content": "Please provide your final answer now.",
                        }
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return _extract_text_anthropic(data)

    async def _agentic_loop_openai(self, messages: list[dict], system_prompt: str) -> str:
        """
        OpenAI agentic loop with function calling.
        """
        api_key = await self._get_user_api_key("openai")
        if not api_key:
            raise ValueError(
                "No OpenAI API key configured. "
                "Please add your key in Settings → Connectors → OpenAI."
            )
        model = self.config.get("model", "gpt-4o")

        msgs = [{"role": "system", "content": system_prompt}] + list(messages)

        for _round in range(_MAX_TOOL_ROUNDS):
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "messages": msgs,
                        "tools": TOOL_DEFINITIONS_OPENAI,
                        "tool_choice": "auto",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            choice = data["choices"][0]
            msg = choice["message"]
            finish_reason = choice.get("finish_reason", "stop")

            if finish_reason != "tool_calls" or not msg.get("tool_calls"):
                return msg.get("content", "").strip()

            # Append assistant message
            msgs.append(msg)

            # Execute tool calls
            for tc in msg["tool_calls"]:
                tool_name = tc["function"]["name"]
                try:
                    tool_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    tool_args = {}
                tc_id = tc["id"]

                logger.info(f"[Agent] Tool call: {tool_name}({tool_args}) for user {self.user_id}")

                try:
                    result = await self.executor.execute(self.user_id, tool_name, tool_args)
                    result_text = _format_tool_result(tool_name, result)
                except Exception as e:
                    result_text = f"Error executing {tool_name}: {e}"
                    logger.error(f"[Agent] Tool error: {e}", exc_info=True)

                msgs.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": result_text,
                    }
                )

        # Fallback
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "messages": msgs},
            )
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"].get("content", "").strip()

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _get_user_api_key(self, provider: str) -> str:
        """
        Return the API key for *provider* from the user's connector_credentials.
        Falls back to the server-level settings key if none is stored.
        """
        from app.models.user import User

        user_row = await self.session.get(User, self.user_id)
        if user_row:
            creds: dict = user_row.connector_credentials or {}
            key = creds.get(provider, {}).get("api_key", "")
            if key:
                return key

        if provider == "anthropic":
            return settings.anthropic_api_key
        if provider == "openai":
            return settings.openai_api_key
        return ""

    async def _build_system_prompt(self) -> str:
        """Build system prompt with user context and memory facts."""
        facts = await self.agent_service.get_memory_facts(self.user_id)
        facts_block = "\n".join(f"- {f}" for f in facts) if facts else "None"

        bridge_status = (
            "Your local Plutus installation is connected — tool calls will run on your machine."
            if self.executor.is_bridge_connected(self.user_id)
            else "Running in cloud sandbox mode (E2B)."
        )

        return (
            "You are Plutus, a highly capable personal AI assistant.\n"
            "You have access to a real execution environment with tools for:\n"
            "  - Running shell commands and Python code\n"
            "  - Reading and writing files\n"
            "  - Searching the web and browsing URLs\n\n"
            "Always use tools to complete tasks rather than just describing what "
            "you would do. Be proactive and get things done.\n\n"
            f"Execution environment: {bridge_status}\n\n"
            f"Memory facts about this user:\n{facts_block}"
        )

    async def _save_message(self, conv_id: str, role: str, content: str) -> None:
        """Save a message to the database."""
        await self.agent_service.save_message(conv_id, role, content, user_id=self.user_id)


# ── Utility functions ─────────────────────────────────────────────────────────


def _extract_text_anthropic(data: dict) -> str:
    """Extract plain text from an Anthropic API response."""
    parts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
    return "\n".join(parts).strip()


def _format_tool_result(tool_name: str, result: dict) -> str:
    """Format a tool result dict into a readable string for the LLM."""
    if not result.get("success", True):
        err = result.get("error", "Unknown error")
        return f"Error: {err}"

    if tool_name == "shell_exec":
        parts = []
        if result.get("stdout"):
            parts.append(f"stdout:\n{result['stdout']}")
        if result.get("stderr"):
            parts.append(f"stderr:\n{result['stderr']}")
        parts.append(f"exit_code: {result.get('exit_code', 0)}")
        return "\n".join(parts)

    if tool_name == "python_exec":
        parts = []
        if result.get("stdout"):
            parts.append(result["stdout"])
        for r in result.get("results", []):
            if r.get("type") == "text":
                parts.append(r["value"])
            elif r.get("type") in ("image/png", "image/jpeg"):
                parts.append("[Image output generated]")
        if result.get("error"):
            parts.append(f"Error: {result['error']}")
        return "\n".join(parts) if parts else "(no output)"

    if tool_name == "file_read":
        return result.get("content", "")

    if tool_name == "file_write":
        return f"File written to {result.get('path', '?')}"

    if tool_name == "file_list":
        items = result.get("items", [])
        if not items:
            return "(empty directory)"
        lines = [f"{'[DIR] ' if i['type'] == 'dir' else '      '}{i['name']}" for i in items]
        return "\n".join(lines)

    if tool_name == "web_search":
        results = result.get("results", [])
        if not results:
            return "No results found."
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.get('title', 'No title')}")
            lines.append(f"   URL: {r.get('url', '')}")
            if r.get("snippet"):
                lines.append(f"   {r['snippet']}")
        return "\n".join(lines)

    if tool_name == "web_browse":
        return result.get("content", "(no content)")

    # Generic fallback
    return json.dumps(result, indent=2)
