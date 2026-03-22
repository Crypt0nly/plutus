"""Workspace sync tool — lets the local Plutus agent push, pull, and manage
files between the local ~/plutus-workspace and the cloud workspace.

Actions:
  push   — upload local files to the cloud (newer-only by default)
  pull   — download cloud files to local (newer-only by default)
  status — show which files differ between local and cloud
  delete — delete a specific file from the cloud workspace
  list   — list all files currently stored in the cloud workspace
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from plutus.tools.base import Tool

logger = logging.getLogger("plutus.tools.workspace_sync")

WORKSPACE_ROOT = Path.home() / "plutus-workspace"
# Top-level dirs inside the workspace that are Plutus internals — never sync
_SKIP_TOP = {"plutus", ".plutus", "plutus_ai", "plutus-ai"}
# Segment names to skip anywhere in the tree
_SKIP = {"__pycache__", ".git", "node_modules", ".DS_Store", ".venv", "venv", ".env"}


def _is_user_file(f: Path, ws: Path) -> bool:
    rel = f.relative_to(ws)
    parts = rel.parts
    if parts and parts[0] in _SKIP_TOP:
        return False
    rel_str = str(rel)
    if any(skip in rel_str for skip in _SKIP):
        return False
    return True


class WorkspaceSyncTool(Tool):
    """Push/pull/delete files between local workspace and the cloud."""

    def __init__(self, config: Any = None):
        self._config = config  # PlutusConfig instance injected at startup

    @property
    def name(self) -> str:
        return "workspace_sync"

    @property
    def description(self) -> str:
        return (
            "Sync files between the local ~/plutus-workspace and the cloud workspace. "
            "Actions:\n"
            "  push   — upload local files to the cloud (skips unchanged files unless force=true)\n"
            "  pull   — download cloud files to local (skips unchanged files unless force=true)\n"
            "  status — compare local and cloud workspaces and show what differs\n"
            "  delete — delete a specific file from the cloud workspace by path\n"
            "  list   — list all files currently stored in the cloud workspace\n"
            "Use this to keep the local and cloud workspaces in sync, to save files "
            "to the cloud for persistence, or to retrieve files from the cloud."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["push", "pull", "status", "delete", "list"],
                    "description": "Sync action to perform.",
                },
                "path": {
                    "type": "string",
                    "description": (
                        "For 'delete': the relative file path to delete from the cloud workspace "
                        "(e.g. 'report.pdf' or 'projects/myapp/main.py'). "
                        "Not used for other actions."
                    ),
                },
                "force": {
                    "type": "boolean",
                    "description": (
                        "For 'push'/'pull': if true, transfer all files regardless of "
                        "modification time. Defaults to false (only newer files)."
                    ),
                },
            },
            "required": ["action"],
        }

    def _get_sync_config(self) -> tuple[str, str]:
        """Return (url, token) from config, raising ValueError if not configured."""
        cfg = None
        if self._config is not None:
            cfg = getattr(self._config, "cloud_sync", None)
        if cfg is None:
            # Try loading from disk as fallback
            try:
                from plutus.gateway.server import get_state
                state = get_state()
                config = state.get("config")
                if config:
                    cfg = config.cloud_sync
            except Exception:
                pass
        if cfg is None or not cfg.url or not cfg.token:
            raise ValueError(
                "Cloud sync is not configured. "
                "Go to Settings → Workspace Sync in the Plutus UI and generate a sync token."
            )
        url = cfg.url.rstrip("/")
        return url, cfg.token

    async def execute(self, **kwargs: Any) -> str:
        import httpx

        action = kwargs.get("action", "status")
        force = bool(kwargs.get("force", False))
        file_path = kwargs.get("path", "")

        try:
            url, token = self._get_sync_config()
        except ValueError as e:
            return str(e)

        headers = {"Authorization": f"Bearer {token}"}
        ws = WORKSPACE_ROOT
        ws.mkdir(parents=True, exist_ok=True)

        if action == "list":
            return await self._list(url, headers)
        elif action == "status":
            return await self._status(url, headers, ws)
        elif action == "push":
            return await self._push(url, headers, ws, force=force)
        elif action == "pull":
            return await self._pull(url, headers, ws, force=force)
        elif action == "delete":
            if not file_path:
                return "Error: 'path' is required for the delete action."
            return await self._delete(url, headers, file_path)
        else:
            return f"Unknown action: {action}"

    # ── List ──────────────────────────────────────────────────────────────────

    async def _list(self, url: str, headers: dict) -> str:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{url}/api/workspace/manifest", headers=headers)
                resp.raise_for_status()
                files = resp.json().get("files", [])
        except Exception as e:
            return f"Error fetching cloud workspace: {e}"

        if not files:
            return "The cloud workspace is empty — no files stored yet."

        lines = [f"Cloud workspace ({len(files)} file{'s' if len(files) != 1 else ''}):"]
        for f in sorted(files, key=lambda x: x["path"]):
            size = f.get("size", 0)
            if size < 1024:
                size_str = f"{size} B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size / (1024 * 1024):.1f} MB"
            lines.append(f"  {f['path']}  ({size_str})")
        return "\n".join(lines)

    # ── Status ────────────────────────────────────────────────────────────────

    async def _status(self, url: str, headers: dict, ws: Path) -> str:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{url}/api/workspace/manifest", headers=headers)
                resp.raise_for_status()
                remote_files = {f["path"]: f for f in resp.json().get("files", [])}
        except Exception as e:
            return f"Error fetching cloud manifest: {e}"

        local_files: dict[str, Path] = {}
        for f in ws.rglob("*"):
            if f.is_file() and _is_user_file(f, ws):
                rel = str(f.relative_to(ws))
                local_files[rel] = f

        local_only = [p for p in local_files if p not in remote_files]
        cloud_only = [p for p in remote_files if p not in local_files]
        newer_local = []
        newer_cloud = []
        in_sync = []

        for p in local_files:
            if p in remote_files:
                lm = local_files[p].stat().st_mtime
                rm = remote_files[p].get("mtime", 0)
                if lm > rm + 1:
                    newer_local.append(p)
                elif rm > lm + 1:
                    newer_cloud.append(p)
                else:
                    in_sync.append(p)

        lines = ["Workspace sync status:"]
        if local_only:
            lines.append(f"\n  Local only ({len(local_only)}) — run push to upload:")
            for p in sorted(local_only):
                lines.append(f"    + {p}")
        if cloud_only:
            lines.append(f"\n  Cloud only ({len(cloud_only)}) — run pull to download:")
            for p in sorted(cloud_only):
                lines.append(f"    - {p}")
        if newer_local:
            lines.append(f"\n  Newer locally ({len(newer_local)}) — run push to update:")
            for p in sorted(newer_local):
                lines.append(f"    ↑ {p}")
        if newer_cloud:
            lines.append(f"\n  Newer in cloud ({len(newer_cloud)}) — run pull to update:")
            for p in sorted(newer_cloud):
                lines.append(f"    ↓ {p}")
        if in_sync:
            lines.append(f"\n  In sync: {len(in_sync)} file(s)")
        if not (local_only or cloud_only or newer_local or newer_cloud):
            lines.append("\n  Everything is in sync.")
        return "\n".join(lines)

    # ── Push ──────────────────────────────────────────────────────────────────

    async def _push(self, url: str, headers: dict, ws: Path, force: bool) -> str:
        import httpx

        # Fetch remote manifest
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{url}/api/workspace/manifest", headers=headers)
                resp.raise_for_status()
                remote_files = {f["path"]: f for f in resp.json().get("files", [])}
        except Exception as e:
            return f"Error fetching cloud manifest: {e}"

        to_upload: list[tuple[str, Path]] = []
        for f in ws.rglob("*"):
            if not f.is_file() or not _is_user_file(f, ws):
                continue
            rel = str(f.relative_to(ws))
            remote = remote_files.get(rel)
            if force or remote is None or f.stat().st_mtime > remote.get("mtime", 0) + 1:
                to_upload.append((rel, f))

        if not to_upload:
            return "Already up to date — nothing to push."

        ok, fail = 0, 0
        failed_files: list[str] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for rel, local_path in to_upload:
                try:
                    raw = local_path.read_bytes()
                    try:
                        content = raw.decode("utf-8")
                        is_binary = False
                    except UnicodeDecodeError:
                        content = base64.b64encode(raw).decode("ascii")
                        is_binary = True
                    resp = await client.post(
                        f"{url}/api/workspace/files",
                        headers={**headers, "Content-Type": "application/json"},
                        json={"path": rel, "content": content, "binary": is_binary},
                    )
                    resp.raise_for_status()
                    ok += 1
                except Exception as e:
                    logger.warning(f"[WorkspaceSync] Push failed for {rel}: {e}")
                    fail += 1
                    failed_files.append(rel)

        # Trigger cloud sandbox pull so the agent sees the files immediately
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                await client.post(f"{url}/api/workspace/pull", headers=headers)
        except Exception:
            pass  # Non-fatal — files are on the server, sandbox sync is best-effort

        result = f"Push complete: {ok} file(s) uploaded."
        if fail:
            result += f" {fail} failed: {', '.join(failed_files)}"
        return result

    # ── Pull ──────────────────────────────────────────────────────────────────

    async def _pull(self, url: str, headers: dict, ws: Path, force: bool) -> str:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{url}/api/workspace/manifest", headers=headers)
                resp.raise_for_status()
                remote_files = resp.json().get("files", [])
        except Exception as e:
            return f"Error fetching cloud manifest: {e}"

        if not remote_files:
            return "Cloud workspace is empty — nothing to pull."

        to_download = []
        for rf in remote_files:
            rel = rf["path"]
            local_path = ws / rel
            if force or not local_path.exists() or rf.get("mtime", 0) > local_path.stat().st_mtime + 1:
                to_download.append(rf)

        if not to_download:
            return "Already up to date — nothing to pull."

        ok, fail = 0, 0
        failed_files: list[str] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for rf in to_download:
                rel = rf["path"]
                try:
                    resp = await client.get(
                        f"{url}/api/workspace/files/{rel}",
                        headers=headers,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    local_path = ws / rel
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    if data.get("binary"):
                        local_path.write_bytes(base64.b64decode(data["content"]))
                    else:
                        local_path.write_text(data.get("content", ""), encoding="utf-8")
                    ok += 1
                except Exception as e:
                    logger.warning(f"[WorkspaceSync] Pull failed for {rel}: {e}")
                    fail += 1
                    failed_files.append(rel)

        result = f"Pull complete: {ok} file(s) downloaded to ~/plutus-workspace/."
        if fail:
            result += f" {fail} failed: {', '.join(failed_files)}"
        return result

    # ── Delete ────────────────────────────────────────────────────────────────

    async def _delete(self, url: str, headers: dict, file_path: str) -> str:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.delete(
                    f"{url}/api/workspace/files/{file_path.lstrip('/')}",
                    headers=headers,
                )
                resp.raise_for_status()
            return f"Deleted '{file_path}' from the cloud workspace."
        except Exception as e:
            return f"Error deleting '{file_path}': {e}"
