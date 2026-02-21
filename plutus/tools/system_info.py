"""System info tool — CPU, memory, disk, network, and OS details."""

from __future__ import annotations

import platform
from typing import Any

import psutil

from plutus.tools.base import Tool


class SystemInfoTool(Tool):
    @property
    def name(self) -> str:
        return "system_info"

    @property
    def description(self) -> str:
        return (
            "Get system information: CPU usage, memory stats, disk space, "
            "network interfaces, and OS details. "
            "Operations: overview, cpu, memory, disk, network, os."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["overview", "cpu", "memory", "disk", "network", "os"],
                    "description": "What system info to retrieve",
                },
            },
            "required": ["operation"],
        }

    async def execute(self, **kwargs: Any) -> str:
        operation: str = kwargs["operation"]

        handlers = {
            "overview": self._overview,
            "cpu": self._cpu,
            "memory": self._memory,
            "disk": self._disk,
            "network": self._network,
            "os": self._os_info,
        }

        handler = handlers.get(operation)
        if not handler:
            return f"[ERROR] Unknown operation: {operation}"
        return handler()

    def _overview(self) -> str:
        cpu_pct = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        return (
            f"CPU: {cpu_pct}% ({psutil.cpu_count()} cores)\n"
            f"Memory: {mem.percent}% ({_fmt_bytes(mem.used)} / {_fmt_bytes(mem.total)})\n"
            f"Disk: {disk.percent}% ({_fmt_bytes(disk.used)} / {_fmt_bytes(disk.total)})\n"
            f"OS: {platform.system()} {platform.release()}\n"
            f"Python: {platform.python_version()}\n"
            f"Uptime: {_fmt_seconds(psutil.boot_time())}"
        )

    def _cpu(self) -> str:
        freq = psutil.cpu_freq()
        per_cpu = psutil.cpu_percent(interval=0.5, percpu=True)
        lines = [
            f"Total CPU: {psutil.cpu_percent(interval=0.1)}%",
            f"Cores: {psutil.cpu_count(logical=False)} physical, {psutil.cpu_count()} logical",
        ]
        if freq:
            lines.append(f"Frequency: {freq.current:.0f} MHz")
        for i, pct in enumerate(per_cpu):
            lines.append(f"  Core {i}: {pct}%")
        return "\n".join(lines)

    def _memory(self) -> str:
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return (
            f"RAM: {_fmt_bytes(mem.used)} / {_fmt_bytes(mem.total)} ({mem.percent}%)\n"
            f"  Available: {_fmt_bytes(mem.available)}\n"
            f"  Cached: {_fmt_bytes(getattr(mem, 'cached', 0))}\n"
            f"Swap: {_fmt_bytes(swap.used)} / {_fmt_bytes(swap.total)} ({swap.percent}%)"
        )

    def _disk(self) -> str:
        lines = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                lines.append(
                    f"{part.mountpoint} ({part.fstype}): "
                    f"{_fmt_bytes(usage.used)} / {_fmt_bytes(usage.total)} ({usage.percent}%)"
                )
            except PermissionError:
                continue
        return "\n".join(lines) if lines else "No accessible disk partitions"

    def _network(self) -> str:
        lines = []
        addrs = psutil.net_if_addrs()
        for iface, addr_list in addrs.items():
            for addr in addr_list:
                if addr.family.name == "AF_INET":
                    lines.append(f"{iface}: {addr.address}")
        io = psutil.net_io_counters()
        lines.append(f"\nNetwork I/O:")
        lines.append(f"  Sent: {_fmt_bytes(io.bytes_sent)}")
        lines.append(f"  Received: {_fmt_bytes(io.bytes_recv)}")
        return "\n".join(lines)

    def _os_info(self) -> str:
        return (
            f"System: {platform.system()}\n"
            f"Release: {platform.release()}\n"
            f"Version: {platform.version()}\n"
            f"Machine: {platform.machine()}\n"
            f"Processor: {platform.processor()}\n"
            f"Python: {platform.python_version()}\n"
            f"Hostname: {platform.node()}"
        )


def _fmt_bytes(b: int | float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024:
            return f"{b:.1f}{unit}"
        b /= 1024
    return f"{b:.1f}PB"


def _fmt_seconds(boot_time: float) -> str:
    import time
    uptime = time.time() - boot_time
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    return f"{hours}h {minutes}m"
