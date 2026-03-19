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

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
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

    total_size = sum(
        f.stat().st_size for f in ws.rglob("*") if f.is_file()
    )
    file_count = sum(1 for f in ws.rglob("*") if f.is_file())

    return {
        "user_id": user["user_id"],
        "path": str(ws),
        "total_size_bytes": total_size,
        "file_count": file_count,
    }
