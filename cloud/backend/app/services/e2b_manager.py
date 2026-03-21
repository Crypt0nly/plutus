"""
E2B Sandbox Manager
===================
Manages per-user E2B cloud sandboxes.  Each user gets one sandbox that is
kept alive for 30 minutes of inactivity, then killed.  A new sandbox is
created on the next tool call.

The sandbox provides:
  - shell_exec(cmd)       → run arbitrary shell commands
  - python_exec(code)     → run Python code (persistent kernel)
  - file_read(path)       → read a file
  - file_write(path, txt) → write a file
  - file_list(path)       → list directory contents
  - web_search(query)     → DuckDuckGo search via curl inside sandbox
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.services.workspace_sync import (
    pull_workspace_to_sandbox,
    push_sandbox_to_workspace,
    run_periodic_sync,
)

logger = logging.getLogger(__name__)

# Sandbox idle timeout in seconds (30 minutes)
_IDLE_TIMEOUT = 30 * 60
# E2B hard-caps sandbox lifetime at 3600 s (1 hour); exceeding this causes a 400 error.
_MAX_LIFETIME = 60 * 60


class _UserSandbox:
    """Wrapper around a single E2B AsyncSandbox instance for one user."""

    def __init__(self, sandbox: Any, user_id: str) -> None:
        self.sandbox = sandbox
        self.user_id = user_id
        self.created_at = time.monotonic()
        self.last_used = time.monotonic()
        self._python_context: Any = None  # persistent Python kernel context

    def touch(self) -> None:
        self.last_used = time.monotonic()

    def is_expired(self) -> bool:
        now = time.monotonic()
        idle = now - self.last_used > _IDLE_TIMEOUT
        old = now - self.created_at > _MAX_LIFETIME
        return idle or old


class E2BSandboxManager:
    """
    Singleton that manages per-user E2B sandboxes.

    Usage::

        mgr = E2BSandboxManager.get_instance()
        result = await mgr.shell_exec(user_id, "ls /home/user")
    """

    _instance: E2BSandboxManager | None = None

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._sandboxes: dict[str, _UserSandbox] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task | None = None

    @classmethod
    def get_instance(cls) -> E2BSandboxManager:
        from app.config import settings

        if cls._instance is None:
            cls._instance = cls(api_key=settings.e2b_api_key)
        return cls._instance

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def _get_or_create(self, user_id: str) -> _UserSandbox:
        """Return the sandbox for user_id, creating one if needed."""
        async with self._lock:
            entry = self._sandboxes.get(user_id)
            if entry and not entry.is_expired():
                entry.touch()
                return entry
            # Kill old sandbox if it exists but is expired
            if entry:
                try:
                    await entry.sandbox.kill()
                except Exception:
                    pass
                del self._sandboxes[user_id]

            # Create new sandbox
            from e2b_code_interpreter import AsyncSandbox

            logger.info(f"[E2B] Creating sandbox for user {user_id}")
            sb = await AsyncSandbox.create(
                api_key=self._api_key,
                timeout=_MAX_LIFETIME,
            )
            # Pre-install common packages
            await sb.commands.run(
                "pip install -q requests beautifulsoup4 pandas numpy matplotlib "
                "seaborn pillow httpx 2>/dev/null || true",
                timeout=60,
            )
            entry = _UserSandbox(sb, user_id)
            self._sandboxes[user_id] = entry
            logger.info(f"[E2B] Sandbox {sb.sandbox_id} ready for user {user_id}")

            # Pull workspace files into sandbox (non-blocking)
            asyncio.create_task(pull_workspace_to_sandbox(entry, user_id))

            # Start periodic sync loop
            asyncio.create_task(run_periodic_sync(entry, user_id))

            return entry

    async def kill_sandbox(self, user_id: str) -> None:
        """Explicitly kill the sandbox for a user."""
        async with self._lock:
            entry = self._sandboxes.pop(user_id, None)
        if entry:
            # Final sync before killing
            try:
                await push_sandbox_to_workspace(entry, user_id)
            except Exception as e:
                logger.warning(f"[E2B] Final sync failed for user {user_id}: {e}")
            try:
                await entry.sandbox.kill()
                logger.info(f"[E2B] Killed sandbox for user {user_id}")
            except Exception as e:
                logger.warning(f"[E2B] Error killing sandbox: {e}")

    async def start_cleanup_loop(self) -> None:
        """Start background task that reaps idle sandboxes."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            expired = []
            async with self._lock:
                for uid, entry in list(self._sandboxes.items()):
                    if entry.is_expired():
                        expired.append((uid, entry))
                        del self._sandboxes[uid]
            for uid, entry in expired:
                # Final sync before reaping
                try:
                    await push_sandbox_to_workspace(entry, uid)
                except Exception as e:
                    logger.warning(f"[E2B] Final sync on reap failed for {uid}: {e}")
                try:
                    await entry.sandbox.kill()
                    logger.info(f"[E2B] Reaped idle sandbox for user {uid}")
                except Exception:
                    pass

    # ── Tool implementations ─────────────────────────────────────────────────

    async def shell_exec(
        self,
        user_id: str,
        command: str,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """
        Run a shell command in the user's sandbox.

        Returns::

            {
                "stdout": "...",
                "stderr": "...",
                "exit_code": 0,
                "success": True,
            }
        """
        entry = await self._get_or_create(user_id)
        try:
            result = await entry.sandbox.commands.run(command, timeout=timeout)
            return {
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
                "exit_code": result.exit_code,
                "success": result.exit_code == 0,
            }
        except Exception as e:
            # CommandExitException is raised for non-zero exit codes
            from e2b import CommandExitException

            if isinstance(e, CommandExitException):
                return {
                    "stdout": e.stdout or "",
                    "stderr": e.stderr or "",
                    "exit_code": e.exit_code,
                    "success": False,
                }
            raise

    async def python_exec(
        self,
        user_id: str,
        code: str,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """
        Execute Python code in a persistent kernel context.

        Returns::

            {
                "stdout": "...",
                "stderr": "...",
                "results": [...],   # rich outputs (plots, dataframes, etc.)
                "success": True,
            }
        """
        entry = await self._get_or_create(user_id)
        # Create a persistent Python context if we don't have one
        if entry._python_context is None:
            entry._python_context = await entry.sandbox.create_code_context()
        try:
            execution = await entry.sandbox.run_code(
                code,
                context=entry._python_context,
                timeout=timeout,
            )
            stdout = "\n".join(execution.logs.stdout) if execution.logs.stdout else ""
            stderr = "\n".join(execution.logs.stderr) if execution.logs.stderr else ""
            results = []
            for r in execution.results:
                if hasattr(r, "text") and r.text:
                    results.append({"type": "text", "value": r.text})
                elif hasattr(r, "html") and r.html:
                    results.append({"type": "html", "value": r.html})
                elif hasattr(r, "png") and r.png:
                    results.append({"type": "image/png", "value": r.png})
            error = None
            if execution.error:
                error = f"{execution.error.name}: {execution.error.value}"
                if execution.error.traceback:
                    error += f"\n{execution.error.traceback}"
            return {
                "stdout": stdout,
                "stderr": stderr,
                "results": results,
                "error": error,
                "success": execution.error is None,
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": str(e),
                "results": [],
                "error": str(e),
                "success": False,
            }

    async def file_read(self, user_id: str, path: str) -> dict[str, Any]:
        """Read a file from the sandbox filesystem."""
        entry = await self._get_or_create(user_id)
        try:
            content = await entry.sandbox.files.read(path)
            return {"content": content, "success": True}
        except Exception as e:
            return {"content": "", "error": str(e), "success": False}

    async def file_write(self, user_id: str, path: str, content: str) -> dict[str, Any]:
        """Write a file to the sandbox filesystem."""
        entry = await self._get_or_create(user_id)
        try:
            await entry.sandbox.files.write(path, content)
            return {"success": True, "path": path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def file_list(self, user_id: str, path: str = "/home/user") -> dict[str, Any]:
        """List files in a sandbox directory."""
        entry = await self._get_or_create(user_id)
        try:
            entries = await entry.sandbox.files.list(path)
            items = [
                {
                    "name": e.name,
                    "type": "dir" if e.type.value == "dir" else "file",
                    "path": f"{path.rstrip('/')}/{e.name}",
                }
                for e in entries
            ]
            return {"items": items, "success": True}
        except Exception as e:
            return {"items": [], "error": str(e), "success": False}

    async def web_search(self, user_id: str, query: str, num_results: int = 5) -> dict[str, Any]:
        """
        Perform a web search using DuckDuckGo's HTML interface.
        Runs inside the sandbox so it uses the sandbox's IP.
        """
        entry = await self._get_or_create(user_id)
        # Use DuckDuckGo lite (no JS required) via curl + python parsing
        search_code = f"""
import urllib.request, urllib.parse, html, re, json

query = {repr(query)}
url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)
req = urllib.request.Request(url, headers={{"User-Agent": "Mozilla/5.0"}})
with urllib.request.urlopen(req, timeout=10) as resp:
    body = resp.read().decode("utf-8", errors="replace")

# Extract results
results = []
for m in re.finditer(
    r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    body, re.DOTALL
):
    href = m.group(1)
    title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
    title = html.unescape(title)
    if href.startswith("http") and title:
        results.append({{"title": title, "url": href}})
    if len(results) >= {num_results}:
        break

# Also grab snippets
snippets = re.findall(
    r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', body, re.DOTALL
)
for i, s in enumerate(snippets[:len(results)]):
    results[i]["snippet"] = html.unescape(re.sub(r"<[^>]+>", "", s).strip())

print(json.dumps(results))
"""
        try:
            result = await entry.sandbox.commands.run(f"python3 -c {repr(search_code)}", timeout=20)
            import json

            items = json.loads(result.stdout.strip()) if result.stdout.strip() else []
            return {"results": items, "success": True}
        except Exception as e:
            return {"results": [], "error": str(e), "success": False}

    async def sandbox_status(self, user_id: str) -> dict[str, Any]:
        """Return status info about the user's sandbox."""
        async with self._lock:
            entry = self._sandboxes.get(user_id)
        if not entry:
            return {"active": False}
        return {
            "active": True,
            "sandbox_id": entry.sandbox.sandbox_id,
            "idle_seconds": int(time.monotonic() - entry.last_used),
            "age_seconds": int(time.monotonic() - entry.created_at),
        }
