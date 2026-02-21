#!/usr/bin/env python3
"""File Edit Worker — creates, reads, edits, and manages files in a subprocess.

Protocol: JSON over stdin/stdout (one line per message).

Supported actions:
  - read: Read file content (with optional line range)
  - write: Create or overwrite a file
  - append: Append content to a file
  - edit: Apply surgical edits (find/replace) to a file
  - patch: Apply a unified diff patch
  - delete: Delete a file
  - move: Move/rename a file
  - copy: Copy a file
  - mkdir: Create directories
  - list: List directory contents
  - find: Find files by pattern
  - grep: Search file contents
  - diff: Show diff between two files or before/after edit
  - quit: Shut down the worker
"""

import difflib
import fnmatch
import json
import os
import re
import shutil
import signal
import sys
from pathlib import Path


def read_file(path: str, start_line: int | None = None, end_line: int | None = None) -> dict:
    """Read file content, optionally with line range."""
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return {"success": False, "error": f"File not found: {path}"}
        if not p.is_file():
            return {"success": False, "error": f"Not a file: {path}"}

        content = p.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines(keepends=True)
        total_lines = len(lines)

        if start_line is not None or end_line is not None:
            s = max(0, (start_line or 1) - 1)
            e = end_line if end_line else total_lines
            lines = lines[s:e]
            content = "".join(lines)

        return {
            "success": True,
            "result": {
                "content": content,
                "total_lines": total_lines,
                "path": str(p),
                "size": p.stat().st_size,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_file(path: str, content: str, create_dirs: bool = True) -> dict:
    """Write content to a file, creating directories if needed."""
    try:
        p = Path(path).expanduser().resolve()
        if create_dirs:
            p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {
            "success": True,
            "result": {
                "path": str(p),
                "size": p.stat().st_size,
                "lines": len(content.splitlines()),
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def append_file(path: str, content: str) -> dict:
    """Append content to a file."""
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return write_file(path, content)
        with open(p, "a", encoding="utf-8") as f:
            f.write(content)
        return {
            "success": True,
            "result": {"path": str(p), "size": p.stat().st_size},
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def edit_file(path: str, edits: list[dict]) -> dict:
    """Apply find/replace edits to a file.

    Each edit: {"find": "old text", "replace": "new text", "all": false}
    """
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return {"success": False, "error": f"File not found: {path}"}

        content = p.read_text(encoding="utf-8")
        original = content
        changes_made = 0

        for edit in edits:
            find_text = edit.get("find", "")
            replace_text = edit.get("replace", "")
            replace_all = edit.get("all", False)

            if not find_text:
                continue

            if find_text not in content:
                return {
                    "success": False,
                    "error": f"Text not found in file: {repr(find_text[:100])}",
                }

            if replace_all:
                count = content.count(find_text)
                content = content.replace(find_text, replace_text)
                changes_made += count
            else:
                content = content.replace(find_text, replace_text, 1)
                changes_made += 1

        p.write_text(content, encoding="utf-8")

        # Generate diff
        diff = list(difflib.unified_diff(
            original.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=f"a/{p.name}",
            tofile=f"b/{p.name}",
        ))

        return {
            "success": True,
            "result": {
                "path": str(p),
                "changes": changes_made,
                "diff": "".join(diff),
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_file(path: str) -> dict:
    """Delete a file or directory."""
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return {"success": False, "error": f"Not found: {path}"}
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return {"success": True, "result": {"deleted": str(p)}}
    except Exception as e:
        return {"success": False, "error": str(e)}


def move_file(src: str, dst: str) -> dict:
    """Move or rename a file/directory."""
    try:
        s = Path(src).expanduser().resolve()
        d = Path(dst).expanduser().resolve()
        if not s.exists():
            return {"success": False, "error": f"Source not found: {src}"}
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(s), str(d))
        return {"success": True, "result": {"from": str(s), "to": str(d)}}
    except Exception as e:
        return {"success": False, "error": str(e)}


def copy_file(src: str, dst: str) -> dict:
    """Copy a file or directory."""
    try:
        s = Path(src).expanduser().resolve()
        d = Path(dst).expanduser().resolve()
        if not s.exists():
            return {"success": False, "error": f"Source not found: {src}"}
        d.parent.mkdir(parents=True, exist_ok=True)
        if s.is_dir():
            shutil.copytree(str(s), str(d))
        else:
            shutil.copy2(str(s), str(d))
        return {"success": True, "result": {"from": str(s), "to": str(d)}}
    except Exception as e:
        return {"success": False, "error": str(e)}


def make_dir(path: str) -> dict:
    """Create a directory (and parents)."""
    try:
        p = Path(path).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return {"success": True, "result": {"path": str(p)}}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_dir(path: str, recursive: bool = False, pattern: str | None = None) -> dict:
    """List directory contents."""
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return {"success": False, "error": f"Directory not found: {path}"}
        if not p.is_dir():
            return {"success": False, "error": f"Not a directory: {path}"}

        entries = []
        if recursive:
            for item in sorted(p.rglob("*")):
                if pattern and not fnmatch.fnmatch(item.name, pattern):
                    continue
                rel = item.relative_to(p)
                entries.append({
                    "path": str(rel),
                    "type": "dir" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else 0,
                })
        else:
            for item in sorted(p.iterdir()):
                if pattern and not fnmatch.fnmatch(item.name, pattern):
                    continue
                entries.append({
                    "path": item.name,
                    "type": "dir" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else 0,
                })

        return {"success": True, "result": {"entries": entries, "count": len(entries)}}
    except Exception as e:
        return {"success": False, "error": str(e)}


def find_files(path: str, pattern: str, max_results: int = 100) -> dict:
    """Find files matching a glob pattern."""
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return {"success": False, "error": f"Directory not found: {path}"}

        matches = []
        for item in p.rglob(pattern):
            matches.append({
                "path": str(item),
                "type": "dir" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else 0,
            })
            if len(matches) >= max_results:
                break

        return {"success": True, "result": {"matches": matches, "count": len(matches)}}
    except Exception as e:
        return {"success": False, "error": str(e)}


def grep_files(
    path: str,
    regex: str,
    file_pattern: str = "*",
    max_results: int = 100,
    context_lines: int = 0,
) -> dict:
    """Search file contents using regex."""
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return {"success": False, "error": f"Directory not found: {path}"}

        compiled = re.compile(regex)
        matches = []

        for filepath in p.rglob(file_pattern):
            if not filepath.is_file():
                continue
            try:
                lines = filepath.read_text(encoding="utf-8", errors="replace").splitlines()
                for i, line in enumerate(lines):
                    if compiled.search(line):
                        context_before = lines[max(0, i - context_lines):i]
                        context_after = lines[i + 1:i + 1 + context_lines]
                        matches.append({
                            "file": str(filepath),
                            "line_number": i + 1,
                            "line": line,
                            "context_before": context_before,
                            "context_after": context_after,
                        })
                        if len(matches) >= max_results:
                            break
            except (UnicodeDecodeError, PermissionError):
                continue
            if len(matches) >= max_results:
                break

        return {"success": True, "result": {"matches": matches, "count": len(matches)}}
    except Exception as e:
        return {"success": False, "error": str(e)}


def diff_files(file_a: str, file_b: str) -> dict:
    """Show unified diff between two files."""
    try:
        a = Path(file_a).expanduser().resolve()
        b = Path(file_b).expanduser().resolve()
        if not a.exists():
            return {"success": False, "error": f"File not found: {file_a}"}
        if not b.exists():
            return {"success": False, "error": f"File not found: {file_b}"}

        a_lines = a.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        b_lines = b.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)

        diff = list(difflib.unified_diff(a_lines, b_lines, fromfile=str(a), tofile=str(b)))
        return {"success": True, "result": {"diff": "".join(diff)}}
    except Exception as e:
        return {"success": False, "error": str(e)}


def handle_command(cmd: dict) -> dict:
    """Route a command to the appropriate handler."""
    action = cmd.get("action", "")

    if action == "quit":
        return {"success": True, "result": "goodbye"}

    handlers = {
        "read": lambda: read_file(
            cmd.get("path", ""),
            cmd.get("start_line"),
            cmd.get("end_line"),
        ),
        "write": lambda: write_file(
            cmd.get("path", ""),
            cmd.get("content", ""),
            cmd.get("create_dirs", True),
        ),
        "append": lambda: append_file(cmd.get("path", ""), cmd.get("content", "")),
        "edit": lambda: edit_file(cmd.get("path", ""), cmd.get("edits", [])),
        "delete": lambda: delete_file(cmd.get("path", "")),
        "move": lambda: move_file(cmd.get("src", ""), cmd.get("dst", "")),
        "copy": lambda: copy_file(cmd.get("src", ""), cmd.get("dst", "")),
        "mkdir": lambda: make_dir(cmd.get("path", "")),
        "list": lambda: list_dir(
            cmd.get("path", "."),
            cmd.get("recursive", False),
            cmd.get("pattern"),
        ),
        "find": lambda: find_files(
            cmd.get("path", "."),
            cmd.get("pattern", "*"),
            cmd.get("max_results", 100),
        ),
        "grep": lambda: grep_files(
            cmd.get("path", "."),
            cmd.get("regex", ""),
            cmd.get("file_pattern", "*"),
            cmd.get("max_results", 100),
            cmd.get("context_lines", 0),
        ),
        "diff": lambda: diff_files(cmd.get("file_a", ""), cmd.get("file_b", "")),
    }

    handler = handlers.get(action)
    if not handler:
        return {"success": False, "error": f"Unknown action: {action}"}

    return handler()


def main():
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            cmd = json.loads(line)
        except json.JSONDecodeError as e:
            response = {"success": False, "error": f"Invalid JSON: {e}"}
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
            continue

        response = handle_command(cmd)
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()

        if cmd.get("action") == "quit":
            break


if __name__ == "__main__":
    main()
