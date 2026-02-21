"""Clipboard tool — read and write system clipboard."""

from __future__ import annotations

import asyncio
import platform
from typing import Any

from plutus.tools.base import Tool


class ClipboardTool(Tool):
    @property
    def name(self) -> str:
        return "clipboard"

    @property
    def description(self) -> str:
        return "Read from or write to the system clipboard. Operations: read, write."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["read", "write"],
                    "description": "Read from or write to the clipboard",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to clipboard (for write operation)",
                },
            },
            "required": ["operation"],
        }

    async def execute(self, **kwargs: Any) -> str:
        operation: str = kwargs["operation"]

        if operation == "read":
            return await self._read()
        elif operation == "write":
            content = kwargs.get("content", "")
            return await self._write(content)
        return f"[ERROR] Unknown operation: {operation}"

    async def _read(self) -> str:
        system = platform.system()
        try:
            if system == "Darwin":
                cmd = "pbpaste"
            elif system == "Linux":
                cmd = "xclip -selection clipboard -o"
            elif system == "Windows":
                cmd = "powershell Get-Clipboard"
            else:
                return "[ERROR] Unsupported platform for clipboard"

            proc = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                return f"[ERROR] Clipboard read failed: {stderr.decode()}"
            return stdout.decode("utf-8", errors="replace")
        except Exception as e:
            return f"[ERROR] {e}"

    async def _write(self, content: str) -> str:
        system = platform.system()
        try:
            if system == "Darwin":
                cmd = "pbcopy"
            elif system == "Linux":
                cmd = "xclip -selection clipboard"
            elif system == "Windows":
                cmd = "powershell Set-Clipboard"
            else:
                return "[ERROR] Unsupported platform for clipboard"

            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate(content.encode())
            if proc.returncode != 0:
                return f"[ERROR] Clipboard write failed: {stderr.decode()}"
            return f"Written {len(content)} characters to clipboard"
        except Exception as e:
            return f"[ERROR] {e}"
