"""Code Editor Tool — intelligent file creation and editing via subprocesses.

This tool provides Claude with powerful file manipulation capabilities:
  - Create new files with content
  - Read files with line ranges
  - Apply surgical find/replace edits
  - Search across files (grep)
  - Find files by pattern
  - Move, copy, delete files
  - List directory contents

All operations run in a file_edit subprocess for isolation.
"""

from __future__ import annotations

import json
from typing import Any

from plutus.core.subprocess_manager import SubprocessManager, SubprocessTask
from plutus.tools.base import Tool


class CodeEditorTool(Tool):
    """Create, read, and edit files with surgical precision."""

    def __init__(self, subprocess_manager: SubprocessManager | None = None):
        self._manager = subprocess_manager or SubprocessManager()

    @property
    def name(self) -> str:
        return "code_editor"

    @property
    def description(self) -> str:
        return (
            "Create, read, and edit code files. Supports surgical find/replace edits, "
            "file creation, directory listing, grep search, and more. "
            "Use this for all file operations — it runs in an isolated subprocess."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "read", "write", "append", "edit",
                        "delete", "move", "copy", "mkdir",
                        "list", "find", "grep", "diff",
                    ],
                    "description": (
                        "The file operation to perform:\n"
                        "- read: Read file content (with optional line range)\n"
                        "- write: Create or overwrite a file\n"
                        "- append: Append content to a file\n"
                        "- edit: Apply find/replace edits to a file\n"
                        "- delete: Delete a file or directory\n"
                        "- move: Move/rename a file\n"
                        "- copy: Copy a file or directory\n"
                        "- mkdir: Create directories\n"
                        "- list: List directory contents\n"
                        "- find: Find files by glob pattern\n"
                        "- grep: Search file contents with regex\n"
                        "- diff: Show diff between two files"
                    ),
                },
                "path": {
                    "type": "string",
                    "description": "File or directory path.",
                },
                "content": {
                    "type": "string",
                    "description": "File content (for write/append operations).",
                },
                "edits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "find": {"type": "string", "description": "Text to find"},
                            "replace": {"type": "string", "description": "Replacement text"},
                            "all": {"type": "boolean", "description": "Replace all occurrences"},
                        },
                        "required": ["find", "replace"],
                    },
                    "description": "List of find/replace edits (for 'edit' operation).",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Start line number for read (1-indexed).",
                },
                "end_line": {
                    "type": "integer",
                    "description": "End line number for read.",
                },
                "src": {
                    "type": "string",
                    "description": "Source path (for move/copy).",
                },
                "dst": {
                    "type": "string",
                    "description": "Destination path (for move/copy).",
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (for find) or file filter (for list).",
                },
                "regex": {
                    "type": "string",
                    "description": "Regex pattern (for grep).",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Recursive listing (for list operation).",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "File pattern filter for grep (e.g., '*.py').",
                },
                "context_lines": {
                    "type": "integer",
                    "description": "Context lines around grep matches.",
                },
                "file_a": {
                    "type": "string",
                    "description": "First file path (for diff).",
                },
                "file_b": {
                    "type": "string",
                    "description": "Second file path (for diff).",
                },
            },
            "required": ["operation"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        operation = kwargs.get("operation", "read")

        # Build the command for the file_edit worker
        command: dict[str, Any] = {"action": operation}

        # Map parameters to worker command fields
        param_map = {
            "path": "path",
            "content": "content",
            "edits": "edits",
            "start_line": "start_line",
            "end_line": "end_line",
            "src": "src",
            "dst": "dst",
            "pattern": "pattern",
            "regex": "regex",
            "recursive": "recursive",
            "file_pattern": "file_pattern",
            "context_lines": "context_lines",
            "file_a": "file_a",
            "file_b": "file_b",
        }

        for param, cmd_key in param_map.items():
            if param in kwargs and kwargs[param] is not None:
                command[cmd_key] = kwargs[param]

        task = SubprocessTask(
            worker_type="file_edit",
            command=command,
            timeout=30.0,
        )

        result = await self._manager.spawn(task)

        if result.error:
            return f"[ERROR] {result.error}"

        # Format output based on operation
        output = result.output
        if isinstance(output, dict):
            # For read operations, return content directly for readability
            if operation == "read" and "content" in output:
                lines_info = f" ({output.get('total_lines', '?')} lines total)"
                return f"File: {output.get('path', '')}{lines_info}\n\n{output['content']}"
            return json.dumps(output, indent=2)
        return str(output)
