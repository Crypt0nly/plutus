"""WSL tool — execute commands inside Windows Subsystem for Linux.

Gives Plutus fluent access to a full Linux environment from Windows, including
package management, shell scripting, Linux-native CLI tools, and cross-OS
file operations.  On non-Windows hosts the tool falls back to the native shell
so prompts that target "the Linux side" still work everywhere.
"""

from __future__ import annotations

import asyncio
import os
import platform
import shutil
from typing import Any

from plutus.tools.base import Tool

# Hard-blocked regardless of guardrail tier
BLOCKED_PATTERNS = [
    "rm -rf /",
    "mkfs.",
    "dd if=/dev/zero",
    ":(){ :|:& };:",
    "> /dev/sda",
    "chmod -R 777 /",
]

MAX_OUTPUT_LENGTH = 50_000


def _wsl_available() -> bool:
    """Return True when a usable WSL installation is detected."""
    if platform.system() != "Windows":
        return False
    return shutil.which("wsl") is not None or shutil.which("wsl.exe") is not None


class WSLTool(Tool):
    """Execute commands inside WSL or the native Linux/macOS shell.

    On **Windows** the tool routes commands through ``wsl.exe`` so the agent
    can leverage the full Linux toolchain (apt, grep, sed, awk, ssh, docker,
    …).  On **Linux / macOS** it runs commands natively, so prompts that ask
    for "Linux" behaviour work on every platform.
    """

    # ── Tool interface ────────────────────────────────────────

    @property
    def name(self) -> str:
        return "wsl"

    @property
    def description(self) -> str:
        host = platform.system()
        if host == "Windows":
            return (
                "Execute commands inside the Windows Subsystem for Linux (WSL). "
                "Use this when you need Linux tools, package managers (apt, pip), "
                "shell scripting, SSH, Docker, compilers, or any Linux-native CLI "
                "utility. Supports choosing a specific WSL distro, setting the "
                "working directory, managing distros, and translating paths between "
                "Windows and Linux. "
                "The command string is passed directly to bash — write normal Linux "
                "commands with quotes, pipes, and redirects as-is (no Windows escaping needed)."
            )
        return (
            "Execute Linux / Unix shell commands. "
            "Use this for package management (apt, brew, pip), shell scripting, "
            "SSH, Docker, compilers, and any Unix-native CLI utility."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "run",
                        "list_distros",
                        "set_default",
                        "path_to_linux",
                        "path_to_windows",
                        "info",
                    ],
                    "description": (
                        "Operation to perform. "
                        "'run' — execute a command; "
                        "'list_distros' — list installed WSL distributions; "
                        "'set_default' — change the default distro; "
                        "'path_to_linux' — convert a Windows path to its /mnt/… equivalent; "
                        "'path_to_windows' — convert a Linux /mnt/… path to Windows; "
                        "'info' — show WSL version, default distro, and status."
                    ),
                },
                "command": {
                    "type": "string",
                    "description": "Shell command to execute (required for 'run').",
                },
                "distro": {
                    "type": "string",
                    "description": (
                        "Target WSL distribution name (e.g. 'Ubuntu', 'Debian'). "
                        "If omitted the default distro is used."
                    ),
                },
                "working_directory": {
                    "type": "string",
                    "description": (
                        "Working directory *inside* WSL / the Linux shell. "
                        "Defaults to the user's home directory."
                    ),
                },
                "path": {
                    "type": "string",
                    "description": "Path to translate (for path_to_linux / path_to_windows).",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 120).",
                },
                "user": {
                    "type": "string",
                    "description": "Run the command as this Linux user (WSL -u flag).",
                },
            },
            "required": ["operation"],
        }

    # ── Execution dispatch ────────────────────────────────────

    async def execute(self, **kwargs: Any) -> str:
        operation: str = kwargs.get("operation", "run")

        handlers = {
            "run": self._run,
            "list_distros": self._list_distros,
            "set_default": self._set_default,
            "path_to_linux": self._path_to_linux,
            "path_to_windows": self._path_to_windows,
            "info": self._info,
        }

        handler = handlers.get(operation)
        if handler is None:
            return f"[ERROR] Unknown operation: {operation}"

        try:
            return await handler(kwargs)
        except Exception as e:
            return f"[ERROR] {e}"

    # ── Operations ────────────────────────────────────────────

    async def _run(self, kwargs: dict[str, Any]) -> str:
        command: str | None = kwargs.get("command")
        if not command:
            return "[ERROR] 'command' is required for the 'run' operation."

        # Safety check
        cmd_lower = command.lower().strip()
        for blocked in BLOCKED_PATTERNS:
            if blocked in cmd_lower:
                return f"[BLOCKED] Command contains blocked pattern: '{blocked}'"

        distro: str | None = kwargs.get("distro")
        user: str | None = kwargs.get("user")
        working_dir: str | None = kwargs.get("working_directory")
        timeout: int = kwargs.get("timeout", 120)

        if platform.system() == "Windows" and _wsl_available():
            # Use argv list so CMD.exe never interprets the command string.
            argv = self._build_wsl_argv(
                command, distro=distro, user=user, cwd=working_dir,
            )
            return await self._exec(argv, timeout=timeout)

        # Native Linux / macOS — run through the shell directly.
        shell_cmd = self._build_native_shell_cmd(command, cwd=working_dir)
        cwd = working_dir or os.path.expanduser("~")
        return await self._exec(shell_cmd, cwd=cwd, timeout=timeout)

    async def _list_distros(self, _kwargs: dict[str, Any]) -> str:
        if platform.system() != "Windows":
            return (
                "platform: Linux / macOS (native)\n"
                "WSL is not applicable — commands already run in a native Unix shell."
            )

        if not _wsl_available():
            return "[ERROR] WSL is not installed or not found on PATH."

        # wsl --list --verbose gives name, state, and version
        return await self._exec(["wsl.exe", "--list", "--verbose"], timeout=15)

    async def _set_default(self, kwargs: dict[str, Any]) -> str:
        distro: str | None = kwargs.get("distro")
        if not distro:
            return "[ERROR] 'distro' is required for set_default."

        if platform.system() != "Windows":
            return "[ERROR] set_default is only available on Windows with WSL."

        if not _wsl_available():
            return "[ERROR] WSL is not installed or not found on PATH."

        return await self._exec(["wsl.exe", "--set-default", distro], timeout=15)

    async def _path_to_linux(self, kwargs: dict[str, Any]) -> str:
        path: str | None = kwargs.get("path")
        if not path:
            return "[ERROR] 'path' is required."

        if platform.system() != "Windows":
            return f"linux_path: {path}  (already on a Unix system)"

        if not _wsl_available():
            return "[ERROR] WSL is not installed or not found on PATH."

        result = await self._exec(["wsl.exe", "wslpath", "-u", path], timeout=10)
        return f"linux_path: {result.strip()}" if "[" not in result else result

    async def _path_to_windows(self, kwargs: dict[str, Any]) -> str:
        path: str | None = kwargs.get("path")
        if not path:
            return "[ERROR] 'path' is required."

        if platform.system() != "Windows":
            return f"windows_path: (not applicable — running on {platform.system()})"

        if not _wsl_available():
            return "[ERROR] WSL is not installed or not found on PATH."

        result = await self._exec(["wsl.exe", "wslpath", "-w", path], timeout=10)
        return f"windows_path: {result.strip()}" if "[" not in result else result

    async def _info(self, _kwargs: dict[str, Any]) -> str:
        host = platform.system()
        parts: list[str] = [f"host_os: {host}"]

        if host == "Windows":
            if not _wsl_available():
                parts.append("wsl_status: not installed")
                return "\n".join(parts)

            # WSL version
            ver = await self._exec(["wsl.exe", "--version"], timeout=10)
            parts.append(f"wsl_version:\n{ver.strip()}")

            # Default distro
            distros = await self._exec(["wsl.exe", "--list", "--verbose"], timeout=10)
            parts.append(f"distros:\n{distros.strip()}")
        else:
            import shutil as _shutil

            shell = os.environ.get("SHELL", "unknown")
            parts.append(f"shell: {shell}")
            parts.append(f"wsl_status: not applicable (native {host})")
            # Useful info for the agent to know what's available
            for cmd in ("apt", "brew", "dnf", "pacman", "docker", "ssh", "python3", "node", "gcc"):
                loc = _shutil.which(cmd)
                if loc:
                    parts.append(f"  {cmd}: {loc}")

        return "\n".join(parts)

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _build_wsl_argv(
        command: str,
        *,
        distro: str | None = None,
        user: str | None = None,
        cwd: str | None = None,
    ) -> list[str]:
        """Build an argument list for ``wsl.exe`` that bypasses CMD parsing.

        Returns a list of strings suitable for ``create_subprocess_exec`` so
        that Windows CMD.exe never interprets quotes, pipes, redirects, or
        heredocs in *command*.
        """
        argv = ["wsl.exe"]
        if distro:
            argv += ["-d", distro]
        if user:
            argv += ["-u", user]
        if cwd:
            argv += ["--cd", cwd]
        # Pass the command to bash -ic as a single token.
        # Because we use create_subprocess_exec (no shell), the command
        # string is handed to wsl.exe → bash verbatim — no CMD mangling.
        argv += ["--", "bash", "-ic", command]
        return argv

    @staticmethod
    def _build_native_shell_cmd(
        command: str,
        *,
        cwd: str | None = None,
    ) -> str:
        """Build a shell command string for native Linux/macOS execution."""
        if cwd:
            return f"cd {_shell_quote(cwd)} && {command}"
        return command

    @staticmethod
    async def _exec(
        cmd: str | list[str], *, cwd: str | None = None, timeout: int = 120
    ) -> str:
        """Run *cmd* asynchronously and return formatted output.

        *cmd* can be a string (passed to the shell) or a list of arguments
        (executed directly, bypassing the shell).  On Windows the list form
        **must** be used for WSL commands so that CMD.exe does not mangle
        quotes, pipes, or special characters.
        """
        try:
            if isinstance(cmd, list):
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                )
            else:
                process = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )

            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")

            if len(stdout_text) > MAX_OUTPUT_LENGTH:
                stdout_text = stdout_text[:MAX_OUTPUT_LENGTH] + "\n... [truncated]"
            if len(stderr_text) > MAX_OUTPUT_LENGTH:
                stderr_text = stderr_text[:MAX_OUTPUT_LENGTH] + "\n... [truncated]"

            result_parts: list[str] = []
            if stdout_text.strip():
                result_parts.append(f"stdout:\n{stdout_text.strip()}")
            if stderr_text.strip():
                result_parts.append(f"stderr:\n{stderr_text.strip()}")
            result_parts.append(f"exit_code: {process.returncode}")

            return "\n".join(result_parts)

        except TimeoutError:
            # Kill the process to prevent zombies
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass
            return f"[TIMEOUT] Command timed out after {timeout} seconds"
        except Exception as e:
            return f"[ERROR] {e}"


def _shell_quote(s: str) -> str:
    """Simple POSIX-style single-quote wrapper."""
    return "'" + s.replace("'", "'\\''") + "'"
