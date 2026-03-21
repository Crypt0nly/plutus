"""
Workspace Sync Service
======================
Bidirectional sync between the E2B cloud sandbox and the per-user
server-side workspace directory (``/data/workspaces/{user_id}/``).

Flow
----
* **Sandbox boot** → pull all files from server workspace into sandbox,
  then ``pip install -r .sandbox_requirements.txt`` in the background.
* **Every 5 minutes** (while sandbox is active) → push changed files from
  sandbox back to server workspace + ``pip freeze`` → ``.sandbox_requirements.txt``.
* **Sandbox kill / idle expiry** → final push before killing.

The server workspace is the single source of truth.  The local Plutus
client syncs to/from the same server workspace via the ``/api/workspace``
REST endpoints (see ``workspace.py``).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.e2b_manager import _UserSandbox

logger = logging.getLogger(__name__)

# How often (seconds) to push sandbox files to the server workspace
_PERIODIC_SYNC_INTERVAL = 5 * 60  # 5 minutes

# Files / directories to exclude from sync (both directions)
_EXCLUDE_PATTERNS = {
    "__pycache__",
    ".git",
    "*.pyc",
    "*.pyo",
    ".DS_Store",
    "node_modules",
    ".npm",
    ".cache",
}

# Max individual file size to sync (bytes) — skip huge binaries
_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def _workspace_root() -> Path:
    from app.config import settings

    return Path(settings.workspace_root)


def _user_workspace(user_id: str) -> Path:
    ws = _workspace_root() / user_id
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _should_exclude(name: str) -> bool:
    for pat in _EXCLUDE_PATTERNS:
        if pat.startswith("*"):
            if name.endswith(pat[1:]):
                return True
        elif name == pat:
            return True
    return False


# ---------------------------------------------------------------------------
# Push: sandbox → server workspace
# ---------------------------------------------------------------------------


async def push_sandbox_to_workspace(entry: _UserSandbox, user_id: str) -> int:
    """
    Copy all files from the sandbox's ``/home/user`` into the server workspace.
    Also runs ``pip freeze`` and saves ``.sandbox_requirements.txt``.

    Returns the number of files synced.
    """
    ws = _user_workspace(user_id)
    synced = 0

    try:
        # 1. Freeze installed packages
        result = await entry.sandbox.commands.run("pip freeze 2>/dev/null || true", timeout=30)
        if result.stdout.strip():
            req_path = ws / ".sandbox_requirements.txt"
            req_path.write_text(result.stdout, encoding="utf-8")
            logger.debug(f"[WorkspaceSync] pip freeze saved for user {user_id}")

        # 2. List all files under /home/user
        list_result = await entry.sandbox.commands.run(
            "find /home/user -type f 2>/dev/null | head -2000", timeout=30
        )
        if not list_result.stdout.strip():
            return 0

        file_paths = [p.strip() for p in list_result.stdout.strip().splitlines() if p.strip()]

        for remote_path in file_paths:
            # Check exclusions
            parts = remote_path.split("/")
            if any(_should_exclude(p) for p in parts):
                continue

            # Relative path inside workspace
            rel = remote_path.removeprefix("/home/user/").lstrip("/")
            if not rel:
                continue

            local_path = ws / rel

            try:
                content = await entry.sandbox.files.read(remote_path)
                if isinstance(content, bytes):
                    if len(content) > _MAX_FILE_SIZE:
                        continue
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    local_path.write_bytes(content)
                else:
                    if len(content.encode("utf-8", errors="replace")) > _MAX_FILE_SIZE:
                        continue
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    local_path.write_text(content, encoding="utf-8", errors="replace")
                synced += 1
            except Exception as e:
                logger.debug(f"[WorkspaceSync] Could not read {remote_path}: {e}")

        logger.info(
            f"[WorkspaceSync] Pushed {synced} files from sandbox to workspace for user {user_id}"
        )
    except Exception as e:
        logger.warning(f"[WorkspaceSync] push_sandbox_to_workspace failed: {e}")

    return synced


# ---------------------------------------------------------------------------
# Pull: server workspace → sandbox
# ---------------------------------------------------------------------------


async def pull_workspace_to_sandbox(entry: _UserSandbox, user_id: str) -> int:
    """
    Copy all files from the server workspace into the sandbox's ``/home/user``.
    Then installs ``.sandbox_requirements.txt`` in the background if it exists.

    Returns the number of files synced.
    """
    ws = _user_workspace(user_id)
    synced = 0

    try:
        # Ensure /home/user exists in sandbox
        await entry.sandbox.commands.run("mkdir -p /home/user", timeout=10)

        all_files = [f for f in ws.rglob("*") if f.is_file()]
        for local_path in all_files:
            # Check exclusions
            if any(_should_exclude(p) for p in local_path.parts):
                continue
            if local_path.stat().st_size > _MAX_FILE_SIZE:
                continue

            rel = local_path.relative_to(ws)
            remote_path = f"/home/user/{rel}"

            try:
                content = local_path.read_bytes()
                await entry.sandbox.files.write(remote_path, content)
                synced += 1
            except Exception as e:
                logger.debug(f"[WorkspaceSync] Could not write {remote_path}: {e}")

        logger.info(
            f"[WorkspaceSync] Pulled {synced} files from workspace to sandbox for user {user_id}"
        )

        # Install saved requirements in the background (non-blocking)
        req_file = ws / ".sandbox_requirements.txt"
        if req_file.exists() and req_file.stat().st_size > 0:
            asyncio.create_task(_install_requirements_background(entry, user_id))

    except Exception as e:
        logger.warning(f"[WorkspaceSync] pull_workspace_to_sandbox failed: {e}")

    return synced


async def _install_requirements_background(entry: _UserSandbox, user_id: str) -> None:
    """Install .sandbox_requirements.txt in the background after sandbox boot."""
    try:
        result = await entry.sandbox.commands.run(
            "pip install -q -r /home/user/.sandbox_requirements.txt 2>&1 || true",
            timeout=120,
        )
        logger.info(
            f"[WorkspaceSync] pip install completed for user {user_id}: "
            f"{result.stdout[:200] if result.stdout else 'ok'}"
        )
    except Exception as e:
        logger.warning(f"[WorkspaceSync] pip install background failed: {e}")


# ---------------------------------------------------------------------------
# Periodic sync loop
# ---------------------------------------------------------------------------


async def run_periodic_sync(entry: _UserSandbox, user_id: str) -> None:
    """
    Background task that pushes sandbox files to the server workspace every
    ``_PERIODIC_SYNC_INTERVAL`` seconds.  Stops when the sandbox is killed.
    """
    while True:
        await asyncio.sleep(_PERIODIC_SYNC_INTERVAL)
        # Check if sandbox is still alive
        try:
            await entry.sandbox.commands.run("echo alive", timeout=5)
        except Exception:
            logger.info(f"[WorkspaceSync] Sandbox gone for user {user_id}, stopping periodic sync")
            break
        await push_sandbox_to_workspace(entry, user_id)


# ---------------------------------------------------------------------------
# Server workspace ↔ local client sync helpers
# ---------------------------------------------------------------------------


def list_workspace_manifest(user_id: str) -> list[dict[str, Any]]:
    """
    Return a manifest of all files in the server workspace with their
    relative paths, sizes, and modification timestamps.
    Used by the local Plutus client to compute a diff before push/pull.
    """
    ws = _user_workspace(user_id)
    manifest = []
    for f in ws.rglob("*"):
        if not f.is_file():
            continue
        if any(_should_exclude(p) for p in f.parts):
            continue
        rel = str(f.relative_to(ws))
        stat = f.stat()
        manifest.append(
            {
                "path": rel,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            }
        )
    return manifest
