"""Shell tool — execute commands on the local system.

Supports running commands via:
  - Default system shell (cmd.exe on Windows, bash on Linux/macOS)
  - WSL (Windows Subsystem for Linux) when use_wsl=True
  - PowerShell when use_powershell=True
"""

from __future__ import annotations

import asyncio
import os
import platform
import shutil
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
IS_WINDOWS = platform.system() == "Windows"
HAS_WSL = IS_WINDOWS and shutil.which("wsl") is not None


class ShellTool(Tool):
    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        wsl_note = (
            " WSL (Windows Subsystem for Linux) is available — set use_wsl=true "
            "to run bash/Linux commands. This is recommended for scripting, "
            "file manipulation, and development tasks."
        ) if HAS_WSL else ""
        return (
            "Execute a shell command on the local system. "
            "Use this for running scripts, installing packages, git operations, "
            "build commands, and any other terminal tasks."
            f"{wsl_note}"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        props: dict[str, Any] = {
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
        }

        if HAS_WSL:
            props["use_wsl"] = {
                "type": "boolean",
                "description": (
                    "Run the command in WSL (bash/Linux environment) instead of "
                    "the Windows shell. Recommended for scripting and file operations. "
                    "WSL can access Windows files at /mnt/c/Users/... (default: false)"
                ),
            }

        if IS_WINDOWS:
            props["use_powershell"] = {
                "type": "boolean",
                "description": (
                    "Run the command in PowerShell instead of cmd.exe. "
                    "Useful for Windows-specific automation. (default: false)"
                ),
            }

        return {
            "type": "object",
            "properties": props,
            "required": ["command"],
        }

    async def execute(self, **kwargs: Any) -> str:
        command: str = kwargs["command"]
        working_dir: str = kwargs.get("working_directory", os.path.expanduser("~"))
        timeout: int = kwargs.get("timeout", 120)
        use_wsl: bool = kwargs.get("use_wsl", False)
        use_powershell: bool = kwargs.get("use_powershell", False)

        # Safety check
        cmd_lower = command.lower().strip()
        for blocked in BLOCKED_COMMANDS:
            if blocked in cmd_lower:
                return f"[BLOCKED] Command contains blocked pattern: '{blocked}'"

        # Build the actual command based on shell preference
        if use_wsl and HAS_WSL:
            # Wrap command for WSL execution
            # Escape single quotes in the command for bash
            escaped_cmd = command.replace("'", "'\\''")
            actual_command = f'wsl bash -c \'{escaped_cmd}\''
        elif use_powershell and IS_WINDOWS:
            # Wrap command for PowerShell execution
            # Escape double quotes for PowerShell -Command
            escaped_cmd = command.replace('"', '\\"')
            actual_command = f'powershell -NoProfile -Command "{escaped_cmd}"'
        else:
            actual_command = command

        try:
            process = await asyncio.create_subprocess_shell(
                actual_command,
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

            shell_type = "WSL" if (use_wsl and HAS_WSL) else ("PowerShell" if (use_powershell and IS_WINDOWS) else "shell")
            result_parts.append(f"shell: {shell_type}")

            return "\n".join(result_parts)

        except asyncio.TimeoutError:
            return f"[TIMEOUT] Command timed out after {timeout} seconds"
        except Exception as e:
            return f"[ERROR] {e}"
