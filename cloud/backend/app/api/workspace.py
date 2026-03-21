"""
Per-user cloud workspace — file storage backed by the server filesystem.

Each user gets an isolated directory at:
  /data/workspaces/<user_id>/

Endpoints:
  GET    /api/workspace/files           — list files (optionally under a path)
  POST   /api/workspace/files           — create or overwrite a file
  GET    /api/workspace/files/{path}    — read a file
  DELETE /api/workspace/files/{path}    — delete a file
  POST   /api/workspace/upload          — multipart file upload
  GET    /api/workspace/download/{path} — download a file
"""

import hashlib
import hmac
import os
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.api.auth import get_current_user
from app.config import settings

router = APIRouter()

# Root directory for all user workspaces — configurable via env var
WORKSPACE_ROOT = Path(getattr(settings, "workspace_root", "/data/workspaces"))


def _user_workspace(user_id: str) -> Path:
    """Return (and create) the workspace directory for a user."""
    ws = WORKSPACE_ROOT / user_id
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _safe_path(workspace: Path, relative: str) -> Path:
    """
    Resolve a relative path inside the workspace, preventing path traversal.
    Raises HTTPException 400 if the resolved path escapes the workspace.
    """
    # Normalise: strip leading slashes so Path doesn't treat it as absolute
    clean = relative.lstrip("/")
    resolved = (workspace / clean).resolve()
    if not str(resolved).startswith(str(workspace.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path")
    return resolved


# ---------------------------------------------------------------------------
# List files
# ---------------------------------------------------------------------------


@router.get("/files")
async def list_files(
    path: str | None = None,
    user=Depends(get_current_user),
):
    """List files and directories in the workspace (or a sub-path)."""
    ws = _user_workspace(user["user_id"])
    target = _safe_path(ws, path or "") if path else ws

    if not target.exists():
        return {"files": [], "path": path or "/"}

    entries = []
    for item in sorted(target.iterdir()):
        entries.append(
            {
                "name": item.name,
                "path": str(item.relative_to(ws)),
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
                "modified": item.stat().st_mtime if item.exists() else None,
            }
        )
    return {"files": entries, "path": path or "/"}


# ---------------------------------------------------------------------------
# Create / overwrite a file
# ---------------------------------------------------------------------------


@router.post("/files")
async def create_file(
    payload: dict,
    user=Depends(get_current_user),
):
    """
    Create or overwrite a text file.
    Body: { "path": "notes/todo.txt", "content": "..." }
    """
    ws = _user_workspace(user["user_id"])
    file_path = _safe_path(ws, payload.get("path", "untitled.txt"))
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(payload.get("content", ""), encoding="utf-8")
    return {
        "path": str(file_path.relative_to(ws)),
        "size": file_path.stat().st_size,
    }


# ---------------------------------------------------------------------------
# Read a file
# ---------------------------------------------------------------------------


@router.get("/files/{file_path:path}")
async def read_file(
    file_path: str,
    user=Depends(get_current_user),
):
    """Read a text file from the workspace."""
    ws = _user_workspace(user["user_id"])
    target = _safe_path(ws, file_path)

    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    if target.is_dir():
        raise HTTPException(status_code=400, detail="Path is a directory")

    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="File is binary — use the download endpoint instead",
        )

    return {
        "path": file_path,
        "content": content,
        "size": target.stat().st_size,
    }


# ---------------------------------------------------------------------------
# Delete a file or directory
# ---------------------------------------------------------------------------


@router.delete("/files/{file_path:path}")
async def delete_file(
    file_path: str,
    user=Depends(get_current_user),
):
    """Delete a file or directory from the workspace."""
    ws = _user_workspace(user["user_id"])
    target = _safe_path(ws, file_path)

    if not target.exists():
        raise HTTPException(status_code=404, detail="Not found")

    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()

    return {"deleted": file_path}


# ---------------------------------------------------------------------------
# Upload a file (multipart)
# ---------------------------------------------------------------------------


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    path: str | None = None,
    user=Depends(get_current_user),
):
    """Upload a file to the workspace (multipart/form-data)."""
    ws = _user_workspace(user["user_id"])
    dest_name = path or file.filename or "upload"
    dest = _safe_path(ws, dest_name)
    dest.parent.mkdir(parents=True, exist_ok=True)

    with dest.open("wb") as f:
        content = await file.read()
        f.write(content)

    return {
        "path": str(dest.relative_to(ws)),
        "size": dest.stat().st_size,
        "filename": dest.name,
    }


# ---------------------------------------------------------------------------
# Download a file
# ---------------------------------------------------------------------------


@router.get("/download/{file_path:path}")
async def download_file(
    file_path: str,
    user=Depends(get_current_user),
):
    """Download a file from the workspace."""
    ws = _user_workspace(user["user_id"])
    target = _safe_path(ws, file_path)

    if not target.exists() or target.is_dir():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=str(target),
        filename=target.name,
        media_type="application/octet-stream",
    )


# ---------------------------------------------------------------------------
# Workspace info
# ---------------------------------------------------------------------------


@router.get("")
async def workspace_info(user=Depends(get_current_user)):
    """Return workspace metadata for the current user."""
    ws = _user_workspace(user["user_id"])

    total_size = sum(f.stat().st_size for f in ws.rglob("*") if f.is_file())
    file_count = sum(1 for f in ws.rglob("*") if f.is_file())

    return {
        "user_id": user["user_id"],
        "path": str(ws),
        "total_size_bytes": total_size,
        "file_count": file_count,
    }


# ---------------------------------------------------------------------------
# Manifest — list all files with mtime for sync diff
# ---------------------------------------------------------------------------

_SKIP_PATTERNS = {"__pycache__", ".git", "node_modules", ".DS_Store"}


@router.get("/manifest")
async def workspace_manifest(user=Depends(get_current_user)):
    """
    Return a flat list of all files in the workspace with their modification
    timestamps. Used by the local Plutus client to compute push/pull diffs.
    """
    ws = _user_workspace(user["user_id"])
    files = []
    for f in ws.rglob("*"):
        if not f.is_file():
            continue
        rel = str(f.relative_to(ws))
        if any(skip in rel for skip in _SKIP_PATTERNS):
            continue
        files.append(
            {
                "path": rel,
                "size": f.stat().st_size,
                "mtime": f.stat().st_mtime,
            }
        )
    return {"files": files, "total": len(files)}


# ---------------------------------------------------------------------------
# API token management — for local ↔ cloud sync authentication
# ---------------------------------------------------------------------------


def _token_store_path(user_id: str) -> Path:
    """Path to the file storing the user's sync token hash."""
    return WORKSPACE_ROOT / user_id / ".sync_token"


def _derive_server_url(request: Request) -> str:
    """
    Determine the public base URL of this server.

    Priority:
    1. ``X-Forwarded-Proto`` + ``X-Forwarded-Host`` headers (set by reverse proxies)
    2. ``Host`` header from the incoming request
    3. ``settings.server_base_url`` — only if it is not the localhost default
    4. Fall back to ``settings.server_base_url`` regardless
    """
    forwarded_host = request.headers.get("x-forwarded-host")
    forwarded_proto = request.headers.get("x-forwarded-proto", "https")
    if forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}"

    host = request.headers.get("host", "")
    # Only trust the Host header when it is not a loopback address
    if host and not host.startswith("localhost") and not host.startswith("127."):
        proto = forwarded_proto if forwarded_proto != "https" else "https"
        # Detect plain-HTTP deployments via the request scope
        if request.url.scheme == "http":
            proto = "http"
        return f"{proto}://{host}"

    # Fall back to the configured value
    return settings.server_base_url


@router.post("/token")
async def generate_sync_token(request: Request, user=Depends(get_current_user)):
    """
    Generate (or regenerate) a long-lived API token for workspace sync.

    The token embeds the server base URL so the local Plutus client can
    connect without requiring a separate "Cloud URL" configuration field.

    Token format:  plutus_<base64url(server_url)>.<hex_secret>

    The server URL is derived from the incoming request headers first
    (X-Forwarded-Host, Host) so that it reflects the real public address
    even when SERVER_BASE_URL is not explicitly configured.

    The token is returned once — only the hash of the full token is stored
    server-side.
    """
    import base64

    raw = os.urandom(32).hex()
    server_url = _derive_server_url(request)
    # Encode the server URL into the token so the local client can extract it
    url_b64 = base64.urlsafe_b64encode(server_url.encode()).decode().rstrip("=")
    token = f"plutus_{url_b64}.{raw}"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    store = _token_store_path(user["user_id"])
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(f"{token_hash}:{time.time()}", encoding="utf-8")
    return {
        "token": token,
        "note": (
            "Copy this token now — it will not be shown again. "
            "Paste it into local Plutus → Settings → Cloud Sync. "
            "The server URL is embedded in the token — no separate URL field needed."
        ),
    }


@router.delete("/token")
async def revoke_sync_token(user=Depends(get_current_user)):
    """Revoke the current sync token."""
    store = _token_store_path(user["user_id"])
    if store.exists():
        store.unlink()
    return {"revoked": True}


@router.get("/token/status")
async def sync_token_status(user=Depends(get_current_user)):
    """Check whether a sync token exists for this user."""
    store = _token_store_path(user["user_id"])
    if not store.exists():
        return {"has_token": False, "created_at": None}
    parts = store.read_text().split(":")
    created_at = float(parts[1]) if len(parts) > 1 else None
    return {"has_token": True, "created_at": created_at}


def verify_sync_token(user_id: str, token: str) -> bool:
    """Verify a sync token against the stored hash. Used by sync endpoints."""
    store = _token_store_path(user_id)
    if not store.exists():
        return False
    stored_hash = store.read_text().split(":")[0]
    candidate_hash = hashlib.sha256(token.encode()).hexdigest()
    return hmac.compare_digest(stored_hash, candidate_hash)


# ---------------------------------------------------------------------------
# Manual push / pull — sandbox ↔ server workspace
# ---------------------------------------------------------------------------


@router.post("/push")
async def push_workspace(user=Depends(get_current_user)):
    """
    Manually push files from the active E2B sandbox into the server workspace.

    If no sandbox is currently active for this user the endpoint still
    succeeds but reports 0 files synced (nothing to push).
    """
    from app.services.e2b_manager import E2BSandboxManager
    from app.services.workspace_sync import push_sandbox_to_workspace

    user_id = user["user_id"]
    mgr = E2BSandboxManager.get_instance()

    # Peek at the active sandbox without creating a new one
    async with mgr._lock:
        entry = mgr._sandboxes.get(user_id)

    if not entry or entry.is_expired():
        return {"synced": 0, "message": "No active sandbox — nothing to push"}

    try:
        synced = await push_sandbox_to_workspace(entry, user_id)
        return {"synced": synced, "message": f"Pushed {synced} file(s) from sandbox to workspace"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Push failed: {e}") from e


@router.post("/pull")
async def pull_workspace(user=Depends(get_current_user)):
    """
    Manually pull files from the server workspace into the active E2B sandbox.

    If no sandbox is currently active the endpoint returns a 409 — the
    caller should start a sandbox first (e.g. by sending a chat message).
    """
    from app.services.e2b_manager import E2BSandboxManager
    from app.services.workspace_sync import pull_workspace_to_sandbox

    user_id = user["user_id"]
    mgr = E2BSandboxManager.get_instance()

    async with mgr._lock:
        entry = mgr._sandboxes.get(user_id)

    if not entry or entry.is_expired():
        raise HTTPException(
            status_code=409,
            detail="No active sandbox. Start a conversation first to launch a sandbox, then pull.",
        )

    try:
        synced = await pull_workspace_to_sandbox(entry, user_id)
        return {"synced": synced, "message": f"Pulled {synced} file(s) from workspace into sandbox"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pull failed: {e}") from e


@router.get("/sync-status")
async def workspace_sync_status(user=Depends(get_current_user)):
    """
    Compare the server workspace manifest against the active sandbox.
    Returns file counts per sync state.
    """
    from app.services.e2b_manager import E2BSandboxManager

    user_id = user["user_id"]
    mgr = E2BSandboxManager.get_instance()

    async with mgr._lock:
        entry = mgr._sandboxes.get(user_id)

    # Build server-side manifest
    ws = _user_workspace(user_id)
    server_files: dict[str, float] = {}
    for f in ws.rglob("*"):
        if f.is_file():
            rel = str(f.relative_to(ws))
            server_files[rel] = f.stat().st_mtime

    if not entry or entry.is_expired():
        # No sandbox — treat all server files as "cloud only"
        return {
            "in_sync": 0,
            "local_only": 0,
            "cloud_only": len(server_files),
            "newer_local": 0,
            "newer_cloud": 0,
        }

    # Get sandbox file list
    try:
        result = await entry.sandbox.commands.run(
            "find /home/user -type f 2>/dev/null | head -2000", timeout=30
        )
        sandbox_files: dict[str, float] = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            rel = line.removeprefix("/home/user/")
            stat_result = await entry.sandbox.commands.run(
                f"stat -c %Y {line!r} 2>/dev/null || echo 0", timeout=10
            )
            try:
                sandbox_files[rel] = float(stat_result.stdout.strip())
            except ValueError:
                sandbox_files[rel] = 0.0
    except Exception:
        sandbox_files = {}

    all_paths = set(server_files) | set(sandbox_files)
    in_sync = local_only = cloud_only = newer_local = newer_cloud = 0
    for p in all_paths:
        sm = server_files.get(p)
        sbm = sandbox_files.get(p)
        if sm is None:
            local_only += 1
        elif sbm is None:
            cloud_only += 1
        elif abs(sm - sbm) <= 1:
            in_sync += 1
        elif sbm > sm + 1:
            newer_local += 1
        else:
            newer_cloud += 1

    return {
        "in_sync": in_sync,
        "local_only": local_only,
        "cloud_only": cloud_only,
        "newer_local": newer_local,
        "newer_cloud": newer_cloud,
    }
