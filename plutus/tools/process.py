"""Process tool — list, start, and manage system processes."""

from __future__ import annotations

import asyncio
import signal
from typing import Any

import psutil

from plutus.tools.base import Tool


class ProcessTool(Tool):
    @property
    def name(self) -> str:
        return "process"

    @property
    def description(self) -> str:
        return (
            "Manage system processes. List running processes, get detailed info, "
            "start new processes, or stop existing ones. "
            "Operations: list, info, start, stop."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["list", "info", "start", "stop"],
                    "description": "The process operation to perform",
                },
                "pid": {
                    "type": "integer",
                    "description": "Process ID (for info/stop operations)",
                },
                "command": {
                    "type": "string",
                    "description": "Command to start (for start operation)",
                },
                "filter": {
                    "type": "string",
                    "description": "Filter processes by name (for list operation)",
                },
            },
            "required": ["operation"],
        }

    async def execute(self, **kwargs: Any) -> str:
        operation: str = kwargs["operation"]

        try:
            if operation == "list":
                return self._list_processes(kwargs.get("filter"))
            elif operation == "info":
                pid = kwargs.get("pid")
                if pid is None:
                    return "[ERROR] Info requires a 'pid' parameter"
                return self._process_info(pid)
            elif operation == "start":
                command = kwargs.get("command")
                if not command:
                    return "[ERROR] Start requires a 'command' parameter"
                return await self._start_process(command)
            elif operation == "stop":
                pid = kwargs.get("pid")
                if pid is None:
                    return "[ERROR] Stop requires a 'pid' parameter"
                return self._stop_process(pid)
            else:
                return f"[ERROR] Unknown operation: {operation}"
        except Exception as e:
            return f"[ERROR] {e}"

    def _list_processes(self, name_filter: str | None) -> str:
        lines = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info", "status"]):
            try:
                info = proc.info
                if name_filter and name_filter.lower() not in info["name"].lower():
                    continue
                mem_mb = info["memory_info"].rss / (1024 * 1024) if info["memory_info"] else 0
                lines.append(
                    f"PID={info['pid']:>6}  "
                    f"CPU={info['cpu_percent']:>5.1f}%  "
                    f"MEM={mem_mb:>7.1f}MB  "
                    f"STATUS={info['status']:<10}  "
                    f"{info['name']}"
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not lines:
            return "No matching processes found"

        # Sort by memory usage, show top 50
        lines.sort(key=lambda l: float(l.split("MEM=")[1].split("MB")[0]), reverse=True)
        return "\n".join(lines[:50])

    def _process_info(self, pid: int) -> str:
        try:
            proc = psutil.Process(pid)
            info = proc.as_dict(attrs=[
                "pid", "name", "exe", "cmdline", "status",
                "cpu_percent", "memory_info", "create_time",
                "username", "cwd", "num_threads",
            ])
            lines = [f"{k}: {v}" for k, v in info.items() if v is not None]
            return "\n".join(lines)
        except psutil.NoSuchProcess:
            return f"[ERROR] No process with PID {pid}"

    async def _start_process(self, command: str) -> str:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        return f"Started process with PID {process.pid}: {command}"

    def _stop_process(self, pid: int) -> str:
        try:
            proc = psutil.Process(pid)
            name = proc.name()
            proc.send_signal(signal.SIGTERM)
            return f"Sent SIGTERM to PID {pid} ({name})"
        except psutil.NoSuchProcess:
            return f"[ERROR] No process with PID {pid}"
        except psutil.AccessDenied:
            return f"[ERROR] Access denied for PID {pid}"
