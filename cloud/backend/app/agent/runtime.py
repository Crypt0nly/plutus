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

    async def _load_user_config(self) -> dict:
        """Load persisted agent config from the user's settings row."""
        from app.models.user import User

        user_row = await self.session.get(User, self.user_id)
        if user_row:
            return (user_row.settings or {}).get("agent_config", {}).get("model", {})
        return {}

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

        # Reset heartbeat consecutive counter when user sends a real message
        try:
            from app.services.cloud_heartbeat import CloudHeartbeatManager

            CloudHeartbeatManager.get_instance().reset_consecutive(self.user_id)
        except Exception:
            pass

        history = await self.agent_service.get_messages(conversation_id)
        messages = [{"role": m.role, "content": m.content} for m in history]

        system_prompt = await self._build_system_prompt()
        # Merge explicit config with persisted user preferences (explicit wins)
        user_model_cfg = await self._load_user_config()
        merged = {**user_model_cfg, **self.config}
        provider = merged.get(
            "provider", self.config.get("provider", settings.default_llm_provider)
        )

        # Run the agentic loop
        if provider == "openai":
            response_text = await self._agentic_loop_openai(messages, system_prompt, config=merged)
        else:
            response_text = await self._agentic_loop_anthropic(
                messages, system_prompt, config=merged
            )

        await self._save_message(conversation_id, "assistant", response_text)

        return {
            "response": response_text,
            "conversation_id": conversation_id,
        }

    # ── Agentic loops ─────────────────────────────────────────────────────────

    async def _agentic_loop_anthropic(
        self, messages: list[dict], system_prompt: str, config: dict = None
    ) -> str:
        """
        Anthropic agentic loop with tool use.

        Keeps calling the API until the model returns a text-only response
        (stop_reason == "end_turn") or we hit _MAX_TOOL_ROUNDS.
        """
        cfg = config or self.config
        api_key = await self._get_user_api_key("anthropic")
        if not api_key:
            raise ValueError(
                "No Anthropic API key configured. "
                "Please add your key in Settings → Connectors → Anthropic."
            )
        model = cfg.get("model", "claude-opus-4-6")

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
                    result = await self.executor.execute(
                        self.user_id,
                        tool_name,
                        tool_args,
                        db_session=self.session,
                    )
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

    async def _agentic_loop_openai(
        self, messages: list[dict], system_prompt: str, config: dict = None
    ) -> str:
        """
        OpenAI agentic loop with function calling.
        """
        cfg = config or self.config
        api_key = await self._get_user_api_key("openai")
        if not api_key:
            raise ValueError(
                "No OpenAI API key configured. "
                "Please add your key in Settings → Connectors → OpenAI."
            )
        model = cfg.get("model", "gpt-4o")

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
                    result = await self.executor.execute(
                        self.user_id,
                        tool_name,
                        tool_args,
                        db_session=self.session,
                    )
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

    async def _build_system_prompt(self, conversation_id: str | None = None) -> str:
        """Build system prompt with user context, memory facts, and active plan."""
        facts = await self.agent_service.get_memory_facts(self.user_id)
        facts_block = "\n".join(f"- {f}" for f in facts) if facts else "None"

        bridge_status = (
            "Your local Plutus installation is connected — tool calls will run on your machine."
            if self.executor.is_bridge_connected(self.user_id)
            else "Running in cloud sandbox mode (E2B)."
        )

        # Inject active plan so the agent always knows where it is in a
        # multi-step task, especially important during heartbeat wake-ups.
        plan_block = ""
        try:
            from app.services.cloud_plan_manager import CloudPlanManager

            manager = CloudPlanManager(self.user_id, self.session)
            # Use a savepoint (nested transaction) so that if the plans table
            # doesn't exist yet or any DB error occurs, only the savepoint is
            # rolled back — the outer transaction stays usable for all
            # subsequent queries (e.g. the user lookup that follows).
            active_plan = None
            try:
                async with self.session.begin_nested():
                    active_plan = await manager.get_active_plan()
            except Exception as inner_exc:
                logger.warning(
                    "[Runtime] Could not load active plan (savepoint rolled back): %s",
                    inner_exc,
                )
            if active_plan:
                plan_block = (
                    "\n\n"
                    + manager.format_plan(active_plan)
                    + "\n\nYou have an active plan above. On each heartbeat or new message, "
                    "check the plan, mark the current step in_progress, execute it, then "
                    "mark it done before moving to the next. Never ask the user for "
                    "permission to continue — just keep working autonomously."
                )
        except Exception as exc:
            logger.warning("[Runtime] Could not load active plan: %s", exc)

        return (
            "You are Plutus, a highly capable autonomous AI agent and personal assistant.\n"
            "You have access to a real execution environment with tools for:\n"
            "  - Running shell commands and Python code\n"
            "  - Reading and writing files\n"
            "  - Searching the web and browsing URLs\n"
            "  - Interacting with the user's configured connectors (Telegram, Discord, "
            "Email, Gmail, GitHub, Google Calendar, Google Drive, custom APIs)\n"
            "  - Creating and tracking persistent multi-step plans (plan tool)\n\n"
            "## Core Behaviour\n"
            "- ALWAYS use tools to complete tasks. Never just describe what you would do.\n"
            "- For any complex goal, IMMEDIATELY create a plan with the plan tool before "
            "starting work. Break it into concrete, executable steps.\n"
            "- After completing each step, mark it done and move to the next without "
            "waiting for the user. Keep working until the plan is complete.\n"
            "- You are woken up automatically by a heartbeat. When you wake up, check "
            "your active plan and continue the next pending step autonomously.\n"
            "- For steps that can run in parallel or take a long time, DELEGATE them to "
            "background workers: write a self-contained Python or shell script to "
            "~/workers/<task_name>.py, launch it with shell_exec in the background "
            "(e.g. 'nohup python3 ~/workers/task.py > ~/workers/task.log 2>&1 &'), "
            "then mark the plan step as in_progress and move on. On the next heartbeat, "
            "check the worker log to see if it finished, then mark the step done.\n\n"
            "## Self-Improvement Directive\n"
            "You must aggressively improve your own capabilities over time:\n"
            "- After completing any task, ask yourself: could a reusable skill or tool "
            "have made this faster or better? If yes, BUILD IT immediately.\n"
            "- Write new skills as shell scripts or Python modules in ~/skills/ with a "
            "SKILL.md file describing what they do and how to invoke them.\n"
            "- Build tools for: web scraping patterns you use repeatedly, API wrappers "
            "for services you interact with, data processing pipelines, automation "
            "scripts for recurring tasks.\n"
            "- Maintain a skills index at ~/skills/INDEX.md. Update it every time you "
            "create or improve a skill.\n"
            "- Before starting any new task, check ~/skills/INDEX.md to see if a "
            "relevant skill already exists and use it.\n\n"
            "## User Workspace\n"
            "The user's personal files (synced from their local machine via cloud sync) "
            "are stored at /home/user/. When the user asks about their files, projects, "
            "documents, or anything they may have uploaded or synced, ALWAYS check "
            "/home/user/ first using file_list with path='/home/user'. "
            "Do not assume the workspace is empty without checking.\n\n"
            "## Connector Usage\n"
            "When sending messages or interacting with external services, use the "
            "connector tool. Start with action='list' if unsure what is configured.\n\n"
            f"Execution environment: {bridge_status}\n\n"
            f"Memory facts about this user:\n{facts_block}"
            f"{plan_block}"
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

    if tool_name == "connector":
        return result.get("output", "(no output)")

    # Generic fallback
    return json.dumps(result, indent=2)
