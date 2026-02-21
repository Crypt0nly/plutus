"""Shell tool — execute commands on the local system."""

from __future__ import annotations

import asyncio
import os
from typing import Any


from plutus.tools.base import Tool

# Commands that are always blocked regardless of tier
BLOCKED_COMMANDS = [
    "rm -rf /",
    "mkfs.",
    "dd if=/dev/zero",
    ":(){ :|:& };:",
    "> /dev/sda",
    "chmod -R 777 /",
]

MAX_OUTPUT_LENGTH = 50_000


class ShellTool(Tool):
    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return (
            "Execute a shell command on the local system. "
            "Use this for running scripts, installing packages, git operations, "
            "build commands, and any other terminal tasks."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "working_directory": {
                    "type": "string",
                    "description": "Working directory for the command (default: home directory)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 120)",
                },
            },
            "required": ["command"],
        }

    async def execute(self, **kwargs: Any) -> str:
        command: str = kwargs["command"]
        working_dir: str = kwargs.get("working_directory", os.path.expanduser("~"))
        timeout: int = kwargs.get("timeout", 120)

        # Safety check
        cmd_lower = command.lower().strip()
        for blocked in BLOCKED_COMMANDS:
            if blocked in cmd_lower:
                return f"[BLOCKED] Command contains blocked pattern: '{blocked}'"

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )

            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")

            # Truncate large outputs
            if len(stdout_text) > MAX_OUTPUT_LENGTH:
                stdout_text = stdout_text[:MAX_OUTPUT_LENGTH] + "\n... [truncated]"
            if len(stderr_text) > MAX_OUTPUT_LENGTH:
                stderr_text = stderr_text[:MAX_OUTPUT_LENGTH] + "\n... [truncated]"

            result_parts = []
            if stdout_text.strip():
                result_parts.append(f"stdout:\n{stdout_text.strip()}")
            if stderr_text.strip():
                result_parts.append(f"stderr:\n{stderr_text.strip()}")
            result_parts.append(f"exit_code: {process.returncode}")

            return "\n".join(result_parts)

        except asyncio.TimeoutError:
            return f"[TIMEOUT] Command timed out after {timeout} seconds"
        except Exception as e:
            return f"[ERROR] {e}"
