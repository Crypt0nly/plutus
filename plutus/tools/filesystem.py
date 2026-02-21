"""Filesystem tool — read, write, search, and manage files."""

from __future__ import annotations

import glob
import os
from pathlib import Path
from typing import Any

from plutus.tools.base import Tool

MAX_FILE_SIZE = 1_000_000  # 1MB read limit
MAX_READ_LINES = 2000


class FilesystemTool(Tool):
    @property
    def name(self) -> str:
        return "filesystem"

    @property
    def description(self) -> str:
        return (
            "Interact with the local filesystem. Read, write, search, list, and manage files "
            "and directories. Supports operations: read, write, append, list, search, "
            "mkdir, delete, move, copy, info."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "read", "write", "append", "list", "search",
                        "mkdir", "delete", "move", "copy", "info",
                    ],
                    "description": "The filesystem operation to perform",
                },
                "path": {
                    "type": "string",
                    "description": "Target file or directory path",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write (for write/append operations)",
                },
                "destination": {
                    "type": "string",
                    "description": "Destination path (for move/copy operations)",
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob or search pattern (for search/list operations)",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Recurse into subdirectories (default: false)",
                },
            },
            "required": ["operation", "path"],
        }

    async def execute(self, **kwargs: Any) -> str:
        operation: str = kwargs["operation"]
        path: str = kwargs["path"]

        # Expand ~ and resolve
        resolved = Path(path).expanduser().resolve()

        handlers = {
            "read": self._read,
            "write": self._write,
            "append": self._append,
            "list": self._list,
            "search": self._search,
            "mkdir": self._mkdir,
            "delete": self._delete,
            "move": self._move,
            "copy": self._copy,
            "info": self._info,
        }

        handler = handlers.get(operation)
        if not handler:
            return f"[ERROR] Unknown operation: {operation}"

        try:
            return await handler(resolved, kwargs)
        except PermissionError:
            return f"[ERROR] Permission denied: {resolved}"
        except FileNotFoundError:
            return f"[ERROR] File not found: {resolved}"
        except Exception as e:
            return f"[ERROR] {e}"

    async def _read(self, path: Path, kwargs: dict) -> str:
        if not path.exists():
            return f"[ERROR] File not found: {path}"
        if path.stat().st_size > MAX_FILE_SIZE:
            return f"[ERROR] File too large ({path.stat().st_size} bytes). Max: {MAX_FILE_SIZE}"

        content = path.read_text(errors="replace")
        lines = content.split("\n")
        if len(lines) > MAX_READ_LINES:
            content = "\n".join(lines[:MAX_READ_LINES])
            content += f"\n... [{len(lines) - MAX_READ_LINES} more lines]"
        return content

    async def _write(self, path: Path, kwargs: dict) -> str:
        content = kwargs.get("content", "")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return f"Written {len(content)} bytes to {path}"

    async def _append(self, path: Path, kwargs: dict) -> str:
        content = kwargs.get("content", "")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(content)
        return f"Appended {len(content)} bytes to {path}"

    async def _list(self, path: Path, kwargs: dict) -> str:
        if not path.is_dir():
            return f"[ERROR] Not a directory: {path}"

        pattern = kwargs.get("pattern", "*")
        recursive = kwargs.get("recursive", False)

        if recursive:
            entries = sorted(path.rglob(pattern))
        else:
            entries = sorted(path.glob(pattern))

        if not entries:
            return f"No entries matching '{pattern}' in {path}"

        lines = []
        for entry in entries[:200]:  # limit output
            prefix = "d" if entry.is_dir() else "f"
            size = entry.stat().st_size if entry.is_file() else 0
            lines.append(f"[{prefix}] {entry.relative_to(path)}  ({size} bytes)")

        result = "\n".join(lines)
        if len(entries) > 200:
            result += f"\n... [{len(entries) - 200} more entries]"
        return result

    async def _search(self, path: Path, kwargs: dict) -> str:
        pattern = kwargs.get("pattern", "")
        if not pattern:
            return "[ERROR] Search requires a 'pattern' parameter"

        results = []
        search_path = path if path.is_dir() else path.parent

        for file_path in search_path.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.stat().st_size > MAX_FILE_SIZE:
                continue
            try:
                content = file_path.read_text(errors="replace")
                for i, line in enumerate(content.split("\n"), 1):
                    if pattern.lower() in line.lower():
                        results.append(f"{file_path}:{i}: {line.strip()}")
                        if len(results) >= 50:
                            return "\n".join(results) + "\n... [more results truncated]"
            except (PermissionError, UnicodeDecodeError):
                continue

        return "\n".join(results) if results else f"No matches for '{pattern}'"

    async def _mkdir(self, path: Path, kwargs: dict) -> str:
        path.mkdir(parents=True, exist_ok=True)
        return f"Created directory: {path}"

    async def _delete(self, path: Path, kwargs: dict) -> str:
        if path.is_file():
            path.unlink()
            return f"Deleted file: {path}"
        elif path.is_dir():
            import shutil
            shutil.rmtree(path)
            return f"Deleted directory: {path}"
        return f"[ERROR] Path does not exist: {path}"

    async def _move(self, path: Path, kwargs: dict) -> str:
        dest = kwargs.get("destination")
        if not dest:
            return "[ERROR] Move requires a 'destination' parameter"
        dest_path = Path(dest).expanduser().resolve()
        path.rename(dest_path)
        return f"Moved {path} → {dest_path}"

    async def _copy(self, path: Path, kwargs: dict) -> str:
        import shutil
        dest = kwargs.get("destination")
        if not dest:
            return "[ERROR] Copy requires a 'destination' parameter"
        dest_path = Path(dest).expanduser().resolve()
        if path.is_file():
            shutil.copy2(path, dest_path)
        else:
            shutil.copytree(path, dest_path)
        return f"Copied {path} → {dest_path}"

    async def _info(self, path: Path, kwargs: dict) -> str:
        if not path.exists():
            return f"[ERROR] Path does not exist: {path}"
        stat = path.stat()
        return (
            f"path: {path}\n"
            f"type: {'directory' if path.is_dir() else 'file'}\n"
            f"size: {stat.st_size} bytes\n"
            f"permissions: {oct(stat.st_mode)}\n"
            f"modified: {stat.st_mtime}\n"
        )
