"""
Hybrid Executor
===============
Routes tool calls to the user's local Plutus bridge when it is connected,
and falls back to E2B cloud sandboxes when the bridge is offline.

Architecture::

    HybridExecutor.execute(user_id, tool_name, tool_args)
        │
        ├─ bridge connected? ──yes──► BridgeDelegate.execute()
        │                                  │
        │                              3 s timeout / error
        │                                  │
        └──────────────────────────────────▼
                                    E2BSandboxManager.execute()

Supported tools (mirroring the local Plutus tool set):
  - shell_exec        run a shell command
  - python_exec       run Python code (persistent kernel)
  - file_read         read a file
  - file_write        write a file
  - file_list         list directory
  - web_search        DuckDuckGo search
  - web_browse        fetch a URL and return text content
  - connector         send messages / interact with configured connectors
                      (Telegram, Discord, Email, Gmail, GitHub, Google Calendar,
                       Google Drive, custom APIs)
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# How long to wait for the local bridge before falling back to E2B
_BRIDGE_TIMEOUT = 5.0


class HybridExecutor:
    """
    Singleton hybrid executor.  Call ``HybridExecutor.get_instance()`` to
    obtain the shared instance.
    """

    _instance: HybridExecutor | None = None

    def __init__(self) -> None:
        from app.services.e2b_manager import E2BSandboxManager

        self._e2b = E2BSandboxManager.get_instance()

    @classmethod
    def get_instance(cls) -> HybridExecutor:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Public API ────────────────────────────────────────────────────────────

    def is_bridge_connected(self, user_id: str) -> bool:
        """Return True if the user's local Plutus bridge is currently connected."""
        from app.api.bridge import active_bridges

        return user_id in active_bridges

    async def execute(
        self,
        user_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
        *,
        db_session=None,
    ) -> dict[str, Any]:
        """
        Execute a tool call.  Tries the local bridge first; falls back to E2B.

        The ``connector`` tool is always handled cloud-side (no E2B / bridge
        needed) because it talks to external APIs using the user's stored
        credentials.  Pass ``db_session`` so the executor can load them.

        Returns a dict with at least ``success: bool`` and tool-specific fields.
        """
        if tool_name == "connector":
            return await self._execute_connector(user_id, tool_args, db_session=db_session)

        if self.is_bridge_connected(user_id):
            try:
                result = await asyncio.wait_for(
                    self._execute_via_bridge(user_id, tool_name, tool_args),
                    timeout=_BRIDGE_TIMEOUT,
                )
                if result.get("success", True):
                    return result
                # Bridge returned an error — fall through to E2B
                logger.info(
                    f"[Hybrid] Bridge returned error for {tool_name}, "
                    f"falling back to E2B: {result.get('error')}"
                )
            except TimeoutError:
                logger.warning(
                    f"[Hybrid] Bridge timeout for {tool_name} (user {user_id}), falling back to E2B"
                )
            except Exception as e:
                logger.warning(f"[Hybrid] Bridge error for {tool_name}: {e}, falling back to E2B")

        return await self._execute_via_e2b(user_id, tool_name, tool_args)

    # ── Connector tool ────────────────────────────────────────────────────────

    async def _execute_connector(
        self,
        user_id: str,
        tool_args: dict[str, Any],
        *,
        db_session=None,
    ) -> dict[str, Any]:
        """Execute a connector tool call using the user's stored credentials."""
        from app.services.cloud_connector_executor import CloudConnectorExecutor

        credentials: dict = {}

        if db_session is not None:
            try:
                from app.models.user import User

                user_row = await db_session.get(User, user_id)
                if user_row:
                    credentials = dict(user_row.connector_credentials or {})
            except Exception as exc:
                logger.warning(f"[Connector] Could not load credentials for {user_id}: {exc}")

        executor = CloudConnectorExecutor(user_id, credentials)
        try:
            result_text = await executor.execute(**tool_args)
            return {"success": True, "output": result_text}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # ── Bridge delegation ─────────────────────────────────────────────────────

    async def _execute_via_bridge(
        self,
        user_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Send a tool call to the local bridge and wait for the result.

        The bridge WebSocket protocol (bridge.py) supports a ``task`` message.
        We extend it here with a ``tool_call`` message type and a matching
        ``tool_result`` response.
        """
        from app.api.bridge import active_bridges

        ws = active_bridges.get(user_id)
        if not ws:
            raise RuntimeError("Bridge disconnected")

        call_id = str(uuid.uuid4())
        await ws.send_text(
            json.dumps(
                {
                    "type": "tool_call",
                    "call_id": call_id,
                    "tool": tool_name,
                    "args": tool_args,
                }
            )
        )

        # Wait for the matching tool_result message
        # We poll the bridge's receive queue with a short timeout
        deadline = asyncio.get_event_loop().time() + _BRIDGE_TIMEOUT
        while asyncio.get_event_loop().time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=0.5)
                msg = json.loads(raw)
                if msg.get("type") == "tool_result" and msg.get("call_id") == call_id:
                    return msg.get("result", {"success": False, "error": "empty result"})
                # Other message types (heartbeat, etc.) — ignore and keep waiting
            except TimeoutError:
                continue
            except Exception as e:
                raise RuntimeError(f"Bridge receive error: {e}") from e

        raise TimeoutError("Bridge did not respond in time")

    # ── E2B execution ─────────────────────────────────────────────────────────

    async def _execute_via_e2b(
        self,
        user_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> dict[str, Any]:
        """Dispatch to the appropriate E2B sandbox method."""
        e2b = self._e2b

        if tool_name == "shell_exec":
            return await e2b.shell_exec(
                user_id,
                tool_args.get("command", ""),
                timeout=tool_args.get("timeout", 30.0),
            )

        if tool_name == "python_exec":
            return await e2b.python_exec(
                user_id,
                tool_args.get("code", ""),
                timeout=tool_args.get("timeout", 30.0),
            )

        if tool_name == "file_read":
            return await e2b.file_read(user_id, tool_args.get("path", ""))

        if tool_name == "file_write":
            return await e2b.file_write(
                user_id,
                tool_args.get("path", ""),
                tool_args.get("content", ""),
            )

        if tool_name == "file_list":
            return await e2b.file_list(user_id, tool_args.get("path", "/home/user"))

        if tool_name == "web_search":
            return await e2b.web_search(
                user_id,
                tool_args.get("query", ""),
                num_results=tool_args.get("num_results", 5),
            )

        if tool_name == "web_browse":
            return await self._web_browse(user_id, tool_args.get("url", ""))

        if tool_name == "connector":
            # Should not reach here (handled above), but guard anyway
            return {"success": False, "error": "connector tool requires db_session"}

        return {"success": False, "error": f"Unknown tool: {tool_name}"}

    async def _web_browse(self, user_id: str, url: str) -> dict[str, Any]:
        """Fetch a URL and return its text content (via sandbox curl + python)."""
        e2b = self._e2b
        cmd = (
            f'python3 -c "'
            f"import urllib.request, html, re; "
            f"req = urllib.request.Request({repr(url)}, "
            f"headers={{'User-Agent': 'Mozilla/5.0'}}); "
            f"body = urllib.request.urlopen(req, timeout=15).read(); "
            f"body = body.decode('utf-8', errors='replace'); "
            f"text = re.sub(r'<[^>]+>', ' ', body); "
            f"text = re.sub(r'\\\\s+', ' ', html.unescape(text)).strip(); "
            f'print(text[:8000])"'
        )
        result = await e2b.shell_exec(user_id, cmd, timeout=20.0)
        return {
            "url": url,
            "content": result.get("stdout", ""),
            "success": result.get("success", False),
            "error": result.get("stderr") if not result.get("success") else None,
        }


# ── Tool definitions for LLM function calling ─────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "shell_exec",
        "description": (
            "Run a shell command in the user's sandbox environment. "
            "Has internet access, Python 3, common CLI tools. "
            "Use for file operations, running scripts, installing packages, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds (default 30).",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "python_exec",
        "description": (
            "Execute Python code in a persistent kernel. "
            "Variables and imports persist across calls within the same conversation. "
            "Use for data analysis, calculations, plotting, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute.",
                },
            },
            "required": ["code"],
        },
    },
    {
        "name": "file_read",
        "description": "Read the contents of a file in the sandbox.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "file_write",
        "description": "Write content to a file in the sandbox.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file.",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "file_list",
        "description": "List files and directories in a sandbox path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to list (default: /home/user).",
                },
            },
        },
    },
    {
        "name": "web_search",
        "description": (
            "Search the web using DuckDuckGo and return the top results. "
            "Use for finding current information, news, documentation, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query.",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (default 5, max 10).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "connector",
        "description": (
            "Interact with the user's configured external connectors. "
            "Supports: Telegram (send messages), Discord (send messages, manage server), "
            "Email / Gmail (send emails), GitHub (repos, issues, PRs, branches, files, "
            "releases, workflows), Google Calendar (list/create/update/delete events), "
            "Google Drive (list/read/upload files), custom API connectors. "
            "Use action='list' to see what is configured. "
            "Always check connector status before attempting to send."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "status", "send", "manage", "google", "github", "custom"],
                    "description": (
                        "Action to perform. "
                        "'list' — list all configured connectors. "
                        "'status' — check if a specific connector is configured. "
                        "'send' — send a message via Telegram/Discord/Email/Gmail/GitHub. "
                        "'manage' — manage a Discord server (channels, members, roles). "
                        "'google' — interact with Gmail, Google Calendar, or Google Drive. "
                        "'github' — interact with GitHub (repos, issues, PRs, files, etc.). "
                        "'custom' — call a user-configured custom API connector."
                    ),
                },
                "service": {
                    "type": "string",
                    "description": (
                        "Connector to use. For 'send': telegram, discord, email, gmail, github. "
                        "For 'google': gmail, google_calendar, google_drive. "
                        "For 'github': not needed (uses the github connector). "
                        "For 'custom': the name of your custom connector."
                    ),
                },
                "message": {
                    "type": "string",
                    "description": "Message text to send (required for action='send').",
                },
                "to": {
                    "type": "string",
                    "description": "Recipient email address (required for email/gmail send).",
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line.",
                },
                "channel_id": {
                    "type": "string",
                    "description": "Discord channel ID for send or manage actions.",
                },
                "google_action": {
                    "type": "string",
                    "description": (
                        "Google-specific action. "
                        "Gmail: list_messages, get_message, list_labels, send_message. "
                        "Calendar: list_events, create_event, update_event, delete_event. "
                        "Drive: list_files, get_file, get_file_metadata, upload_file, read_doc."
                    ),
                },
                "github_action": {
                    "type": "string",
                    "description": (
                        "GitHub-specific action: list_repos, get_repo, create_repo, "
                        "delete_repo, fork_repo, list_issues, get_issue, create_issue, "
                        "update_issue, comment_on_issue, list_pull_requests, get_pull_request, "
                        "create_pull_request, merge_pull_request, list_branches, create_branch, "
                        "delete_branch, get_file, create_or_update_file, delete_file, "
                        "list_commits, list_releases, create_release, list_workflows, "
                        "list_workflow_runs, trigger_workflow, list_collaborators, "
                        "add_collaborator, remove_collaborator, search_repos, search_code."
                    ),
                },
                "owner": {
                    "type": "string",
                    "description": "GitHub repository owner (username or org).",
                },
                "repo": {
                    "type": "string",
                    "description": "GitHub repository name.",
                },
                "discord_action": {
                    "type": "string",
                    "description": (
                        "Discord management action: guild_info, list_channels, create_channel, "
                        "delete_channel, list_members, kick_member, ban_member, list_roles, "
                        "create_role, assign_role, remove_role, delete_message."
                    ),
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "web_browse",
        "description": (
            "Fetch the text content of a web page. "
            "Use after web_search to read the full content of a result."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch.",
                },
            },
            "required": ["url"],
        },
    },
]

# OpenAI-format tool definitions (converted from Anthropic format)
TOOL_DEFINITIONS_OPENAI = [
    {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"],
        },
    }
    for t in TOOL_DEFINITIONS
]
