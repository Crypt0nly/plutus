"""Shell tool — execute commands on the local system.

Supports running commands via:
  - Default system shell (cmd.exe on Windows, bash on Linux/macOS)
  - WSL (Windows Subsystem for Linux) when use_wsl=True
  - PowerShell when use_powershell=True
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import re
import shutil
from typing import Any


from plutus.tools.base import Tool

logger = logging.getLogger("plutus.shell")

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

# Regex patterns for commands that are known to prompt interactively and need
# CI=1 / npm_config_yes=true to suppress prompts.
_INTERACTIVE_CMD_PATTERNS = [
    re.compile(r"\bnpm\s+create\b", re.IGNORECASE),
    re.compile(r"\bnpx\s+create-", re.IGNORECASE),
    re.compile(r"\bnpx\s+.*@latest\b", re.IGNORECASE),
    re.compile(r"\bcreate-react-app\b", re.IGNORECASE),
    re.compile(r"\bcreate-next-app\b", re.IGNORECASE),
    re.compile(r"\bcreate-vite\b", re.IGNORECASE),
    re.compile(r"\bcreate-svelte\b", re.IGNORECASE),
    re.compile(r"\bcreate-astro\b", re.IGNORECASE),
    re.compile(r"\bcreate-nuxt\b", re.IGNORECASE),
    re.compile(r"\bcreate-vue\b", re.IGNORECASE),
    re.compile(r"\bnpm\s+init\b", re.IGNORECASE),
    re.compile(r"\byarn\s+create\b", re.IGNORECASE),
    re.compile(r"\bpnpm\s+create\b", re.IGNORECASE),
]


def _needs_ci_env(command: str) -> bool:
    """Return True if the command is likely to prompt interactively."""
    for pat in _INTERACTIVE_CMD_PATTERNS:
        if pat.search(command):
            return True
    return False


def _build_env(command: str) -> dict[str, str]:
    """Build the subprocess environment, injecting CI=1 when needed."""
    env = {**os.environ}
    if _needs_ci_env(command):
        env["CI"] = "1"
        env["npm_config_yes"] = "true"
        env["FORCE_COLOR"] = "0"
        logger.debug("[shell] Injected CI=1 for interactive command: %.80s", command)
    return env


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
        command = kwargs.get("command") or kwargs.get("cmd") or kwargs.get("script")
        if not command:
            return (
                "[ERROR] No 'command' parameter provided. "
                "You MUST pass command='your command here' to execute a shell command. "
                f"Received parameters: {list(kwargs.keys())}"
            )
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

        # Build environment — auto-inject CI=1 for interactive npm/npx commands
        # so they never hang waiting for "Ok to proceed? (y)".
        env = _build_env(command)

        try:
            process = await asyncio.create_subprocess_shell(
                actual_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
                env=env,
            )

            stdout_text, stderr_text = await self._communicate_with_heartbeat(
                process, timeout=timeout
            )

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
            # Kill the process to prevent zombies
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass
            return f"[TIMEOUT] Command timed out after {timeout} seconds"
        except Exception as e:
            return f"[ERROR] {e}"

    async def _communicate_with_heartbeat(
        self,
        process: asyncio.subprocess.Process,
        timeout: int,
        heartbeat_interval: float = 15.0,
    ) -> tuple[str, str]:
        """Collect stdout/stderr while yielding control every heartbeat_interval
        seconds.  This prevents the event loop from being starved during long-
        running commands (e.g. npm install, build steps) and keeps the agent's
        _last_activity watchdog from firing false stall warnings.

        Returns (stdout_text, stderr_text).
        """
        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        deadline = asyncio.get_event_loop().time() + timeout

        async def _read(stream: asyncio.StreamReader, bucket: list[bytes]) -> None:
            while True:
                try:
                    chunk = await asyncio.wait_for(stream.read(4096), timeout=5.0)
                except asyncio.TimeoutError:
                    if asyncio.get_event_loop().time() > deadline:
                        break
                    continue
                if not chunk:
                    break
                bucket.append(chunk)

        read_task = asyncio.create_task(
            asyncio.gather(
                _read(process.stdout, stdout_chunks),   # type: ignore[arg-type]
                _read(process.stderr, stderr_chunks),   # type: ignore[arg-type]
            )
        )

        while not read_task.done():
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                try:
                    process.kill()
                    await process.wait()
                except Exception:
                    pass
                read_task.cancel()
                raise asyncio.TimeoutError()
            await asyncio.sleep(min(heartbeat_interval, remaining, 1.0))

        await read_task
        await process.wait()

        return (
            b"".join(stdout_chunks).decode("utf-8", errors="replace"),
            b"".join(stderr_chunks).decode("utf-8", errors="replace"),
        )
