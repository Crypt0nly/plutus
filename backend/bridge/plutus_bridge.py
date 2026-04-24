#!/usr/bin/env python3
"""Plutus Local Bridge Daemon.

A lightweight background process that runs on the user's PC and connects
to the Plutus Cloud via WebSocket.  It allows the cloud agent to execute
tasks on the user's local machine (open apps, access files, run commands, etc.)
and keeps the local memory store in sync with the cloud.

Usage:
    python plutus_bridge.py                          # run with saved config
    python plutus_bridge.py --setup                  # interactive first-time setup
    python plutus_bridge.py --install                # install as system auto-start service
    python plutus_bridge.py --uninstall              # remove the auto-start service
    python plutus_bridge.py --service-status         # check service status
    python plutus_bridge.py --server wss://... --token <jwt>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import logging.handlers
import os
import platform
import shutil
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Lazy dependency bootstrap – install missing packages automatically
# ---------------------------------------------------------------------------
_REQUIRED_PACKAGES = {
    "websockets": "websockets>=12.0",
    "httpx": "httpx>=0.25",
}


def _ensure_packages() -> None:
    missing: list[str] = []
    for mod, spec in _REQUIRED_PACKAGES.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(spec)
    if missing:
        print(f"Installing missing packages: {', '.join(missing)}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", *missing])


_ensure_packages()

import websockets  # noqa: E402
import websockets.exceptions  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VERSION = "0.4.0"
DEFAULT_SERVER = "wss://api.useplutus.ai/api/bridge/ws"
CONFIG_DIR = Path.home() / ".plutus"
CONFIG_FILE = CONFIG_DIR / "bridge_config.json"
LOG_FILE = CONFIG_DIR / "bridge.log"
SERVICE_NAME = "ai.plutus.bridge"

HEARTBEAT_INTERVAL = 30  # seconds between heartbeats
RECONNECT_DELAY_INIT = 5  # initial reconnect back-off
RECONNECT_DELAY_MAX = 300  # cap at 5 minutes
TASK_OUTPUT_LIMIT = 10_000  # max chars for stdout in task results
TASK_STDERR_LIMIT = 5_000   # max chars for stderr in task results

# ---------------------------------------------------------------------------
# Logging  – dual handler: console (INFO) + rotating file (DEBUG)
# ---------------------------------------------------------------------------


def _setup_logging() -> logging.Logger:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("plutus_bridge")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console – INFO and above
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # Rotating file – DEBUG and above, 5 MB × 3 backups
    fh = logging.handlers.RotatingFileHandler(
        str(LOG_FILE), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


log = _setup_logging()

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------


def load_config() -> dict[str, Any]:
    """Load bridge configuration from ~/.plutus/bridge_config.json."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Failed to load config (%s) – using defaults.", exc)
    return {}


def save_config(config: dict[str, Any]) -> None:
    """Persist bridge configuration."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
    log.info("Config saved to %s", CONFIG_FILE)


def run_setup() -> dict[str, Any]:
    """Interactive first-time setup wizard."""
    print("\n╔══════════════════════════════════════╗")
    print("║     Plutus Bridge – Initial Setup    ║")
    print("╚══════════════════════════════════════╝\n")

    config = load_config()

    token = input(f"  Auth token [{config.get('token', '')[:8]}…]: ").strip()
    if token:
        config["token"] = token

    server = input(f"  Server URL [{config.get('server', DEFAULT_SERVER)}]: ").strip()
    if server:
        config["server"] = server
    elif "server" not in config:
        config["server"] = DEFAULT_SERVER

    save_config(config)
    print("\n  ✓ Configuration saved.\n")
    return config


# ---------------------------------------------------------------------------
# System info
# ---------------------------------------------------------------------------


def get_system_info() -> dict[str, Any]:
    """Gather local system information for handshake."""
    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "hostname": platform.node(),
        "python": platform.python_version(),
        "arch": platform.machine(),
        "user": os.getenv("USER") or os.getenv("USERNAME", "unknown"),
        "bridge_version": VERSION,
    }


# ---------------------------------------------------------------------------
# Local task execution
# ---------------------------------------------------------------------------


async def execute_local_task(task: dict[str, Any]) -> dict[str, Any]:
    """Execute a task dispatched by the cloud agent."""
    task_type: str = task.get("type", "")
    payload: dict[str, Any] = task.get("payload", {})
    task_id: str = task.get("task_id", "unknown")

    log.info("Executing task %s [%s]", task_id, task_type)
    t0 = time.monotonic()

    try:
        result = await _dispatch_task(task_type, payload)
    except TimeoutError:
        result = {"success": False, "error": f"Task timed out: {task_type}"}
    except Exception as exc:
        log.exception("Task %s failed with unhandled error", task_id)
        result = {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    elapsed = time.monotonic() - t0
    log.info(
        "Task %s [%s] finished in %.2fs – success=%s",
        task_id, task_type, elapsed, result.get("success"),
    )
    return result


async def _dispatch_task(task_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if task_type == "shell":
        return await _task_shell(payload)
    if task_type == "python_exec":
        return await _task_shell({"command": f'python3 -c {payload.get("code", ""!r)}'})
    if task_type == "open_app":
        return _task_open_app(payload)
    if task_type == "read_file":
        return _task_read_file(payload)
    if task_type == "write_file":
        return _task_write_file(payload)
    if task_type == "list_files":
        return _task_list_files(payload)
    if task_type in ("file_pull", "pull_file"):
        return _task_file_pull(payload)
    if task_type == "ping":
        return {"success": True, "message": "pong", "system": get_system_info()}
    return {"success": False, "error": f"Unknown task type: {task_type}"}


async def _task_shell(payload: dict[str, Any]) -> dict[str, Any]:
    cmd: str = payload.get("command", "")
    timeout: int = min(payload.get("timeout", 60), 300)
    cwd: str | None = payload.get("cwd")
    if not cmd:
        return {"success": False, "error": "Empty command"}
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return {
        "success": proc.returncode == 0,
        "stdout": stdout.decode(errors="replace")[:TASK_OUTPUT_LIMIT],
        "stderr": stderr.decode(errors="replace")[:TASK_STDERR_LIMIT],
        "exit_code": proc.returncode,
    }


def _task_open_app(payload: dict[str, Any]) -> dict[str, Any]:
    app_name: str = payload.get("app_name", "")
    if not app_name:
        return {"success": False, "error": "No app_name provided"}
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(app_name)  # type: ignore[attr-defined]
        elif system == "Darwin":
            subprocess.Popen(["open", "-a", app_name])
        else:
            subprocess.Popen(["xdg-open", app_name])
        return {"success": True, "message": f"Opened {app_name}"}
    except Exception as exc:
        return {"success": False, "error": f"Failed to open {app_name}: {exc}"}


def _task_read_file(payload: dict[str, Any]) -> dict[str, Any]:
    raw_path: str = payload.get("path", "")
    if not raw_path:
        return {"success": False, "error": "No path provided"}
    path = Path(raw_path).expanduser()
    if not path.exists():
        return {"success": False, "error": f"File not found: {path}"}
    if not path.is_file():
        return {"success": False, "error": f"Not a file: {path}"}
    max_size: int = payload.get("max_size", 50_000)
    try:
        content = path.read_text(errors="replace")[:max_size]
        return {"success": True, "content": content, "size": path.stat().st_size}
    except Exception as exc:
        return {"success": False, "error": f"Read failed: {exc}"}


def _task_write_file(payload: dict[str, Any]) -> dict[str, Any]:
    raw_path: str = payload.get("path", "")
    content: str = payload.get("content", "")
    if not raw_path:
        return {"success": False, "error": "No path provided"}
    path = Path(raw_path).expanduser()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"success": True, "message": f"Written {len(content)} chars to {path}"}
    except Exception as exc:
        return {"success": False, "error": f"Write failed: {exc}"}


def _task_list_files(payload: dict[str, Any]) -> dict[str, Any]:
    raw_path: str = payload.get("path", ".")
    pattern: str = payload.get("pattern", "*")
    limit: int = min(payload.get("limit", 500), 2000)
    path = Path(raw_path).expanduser()
    if not path.exists():
        return {"success": False, "error": f"Path not found: {path}"}
    try:
        files = [str(f) for f in path.glob(pattern)][:limit]
        return {"success": True, "files": files, "count": len(files)}
    except Exception as exc:
        return {"success": False, "error": f"List failed: {exc}"}


def _task_file_pull(payload: dict[str, Any]) -> dict[str, Any]:
    """Read a file as base64 for binary-safe transfer to the cloud."""
    import base64

    raw_path: str = payload.get("path", "")
    if not raw_path:
        return {"success": False, "error": "No path provided"}
    path = Path(raw_path).expanduser()
    if not path.exists():
        return {"success": False, "error": f"File not found: {path}"}
    if not path.is_file():
        return {"success": False, "error": f"Not a file: {path}"}

    max_bytes = 50 * 1024 * 1024  # 50 MB limit
    size = path.stat().st_size
    if size > max_bytes:
        return {
            "success": False,
            "error": (
                f"File too large for transfer: {size / (1024 * 1024):.1f} MB "
                f"(limit is {max_bytes // (1024 * 1024)} MB)"
            ),
        }
    try:
        data = path.read_bytes()
        return {
            "success": True,
            "filename": path.name,
            "size": size,
            "data_b64": base64.b64encode(data).decode("ascii"),
        }
    except Exception as exc:
        return {"success": False, "error": f"Read failed: {exc}"}


# ---------------------------------------------------------------------------
# ██████╗ ███████╗██████╗ ██╗   ██╗██╗ ██████╗███████╗
# ██╔════╝██╔════╝██╔══██╗██║   ██║██║██╔════╝██╔════╝
# ███████╗█████╗  ██████╔╝██║   ██║██║██║     █████╗
# ╚════██║██╔══╝  ██╔══██╗╚██╗ ██╔╝██║██║     ██╔══╝
# ███████║███████╗██║  ██║ ╚████╔╝ ██║╚██████╗███████╗
# ╚══════╝╚══════╝╚═╝  ╚═╝  ╚═══╝  ╚═╝ ╚═════╝╚══════╝
# Auto-start service management (macOS / Linux / Windows)
# ---------------------------------------------------------------------------


def _python_exe() -> str:
    """Absolute path to the current Python interpreter."""
    return str(Path(sys.executable).resolve())


def _bridge_script() -> str:
    """Absolute path to this script."""
    return str(Path(__file__).resolve())


# ── macOS (launchd) ──────────────────────────────────────────────────────────

def _macos_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{SERVICE_NAME}.plist"


def _macos_install(config: dict) -> None:
    """Register as a launchd user agent so it starts on login."""
    plist_path = _macos_plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    server = config.get("server", DEFAULT_SERVER)
    token = config.get("token", "")

    plist_content = textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
            "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
            <key>Label</key>
            <string>{SERVICE_NAME}</string>

            <key>ProgramArguments</key>
            <array>
                <string>{_python_exe()}</string>
                <string>{_bridge_script()}</string>
                <string>--server</string>
                <string>{server}</string>
                <string>--token</string>
                <string>{token}</string>
            </array>

            <key>RunAtLoad</key>
            <true/>

            <key>KeepAlive</key>
            <true/>

            <key>StandardOutPath</key>
            <string>{LOG_FILE}</string>

            <key>StandardErrorPath</key>
            <string>{LOG_FILE}</string>

            <key>WorkingDirectory</key>
            <string>{Path.home()}</string>

            <key>ThrottleInterval</key>
            <integer>10</integer>
        </dict>
        </plist>
    """)

    plist_path.write_text(plist_content, encoding="utf-8")
    print(f"  ✓ Launch agent written to {plist_path}")

    # Unload first (ignore errors), then load
    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    result = subprocess.run(["launchctl", "load", "-w", str(plist_path)], capture_output=True)
    if result.returncode == 0:
        print("  ✓ Service loaded and started (launchctl load -w)")
    else:
        print(f"  ⚠  launchctl load returned {result.returncode}: {result.stderr.decode().strip()}")

    print(f"\n  🟢 Plutus Bridge will now start automatically on every login.")
    print(f"     Logs: {LOG_FILE}")


def _macos_uninstall() -> None:
    plist_path = _macos_plist_path()
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", "-w", str(plist_path)], capture_output=True)
        plist_path.unlink()
        print(f"  ✓ Launch agent removed ({plist_path})")
    else:
        print("  ℹ  No launch agent found.")


def _macos_service_status() -> str:
    result = subprocess.run(
        ["launchctl", "list", SERVICE_NAME],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return "running"
    plist = _macos_plist_path()
    if plist.exists():
        return "installed-stopped"
    return "not-installed"


# ── Linux (systemd user) ─────────────────────────────────────────────────────

def _linux_service_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / f"{SERVICE_NAME}.service"


def _linux_install(config: dict) -> None:
    svc_path = _linux_service_path()
    svc_path.parent.mkdir(parents=True, exist_ok=True)

    server = config.get("server", DEFAULT_SERVER)
    token = config.get("token", "")

    unit_content = textwrap.dedent(f"""\
        [Unit]
        Description=Plutus Local Bridge Daemon
        After=network-online.target
        Wants=network-online.target

        [Service]
        Type=simple
        ExecStart={_python_exe()} {_bridge_script()} --server {server} --token {token}
        Restart=always
        RestartSec=10
        StandardOutput=append:{LOG_FILE}
        StandardError=append:{LOG_FILE}
        WorkingDirectory={Path.home()}

        [Install]
        WantedBy=default.target
    """)

    svc_path.write_text(unit_content, encoding="utf-8")
    print(f"  ✓ Systemd unit written to {svc_path}")

    cmds = [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", f"{SERVICE_NAME}.service"],
        ["systemctl", "--user", "start",  f"{SERVICE_NAME}.service"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            print(f"  ⚠  {' '.join(cmd)} failed: {result.stderr.decode().strip()}")
        else:
            print(f"  ✓ {' '.join(cmd)}")

    # Enable lingering so it runs even without an active login session
    subprocess.run(["loginctl", "enable-linger", os.getenv("USER", "")], capture_output=True)

    print(f"\n  🟢 Plutus Bridge will now start automatically on every login.")
    print(f"     Logs: {LOG_FILE}")


def _linux_uninstall() -> None:
    svc = f"{SERVICE_NAME}.service"
    subprocess.run(["systemctl", "--user", "stop", svc], capture_output=True)
    subprocess.run(["systemctl", "--user", "disable", svc], capture_output=True)
    svc_path = _linux_service_path()
    if svc_path.exists():
        svc_path.unlink()
        print(f"  ✓ Systemd unit removed ({svc_path})")
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    print("  ✓ Service disabled and removed.")


def _linux_service_status() -> str:
    result = subprocess.run(
        ["systemctl", "--user", "is-active", f"{SERVICE_NAME}.service"],
        capture_output=True, text=True,
    )
    status = result.stdout.strip()
    if status == "active":
        return "running"
    svc_path = _linux_service_path()
    if svc_path.exists():
        return "installed-stopped"
    return "not-installed"


# ── Windows (Task Scheduler) ─────────────────────────────────────────────────

def _windows_install(config: dict) -> None:
    server = config.get("server", DEFAULT_SERVER)
    token = config.get("token", "")
    python = _python_exe()
    script = _bridge_script()

    task_xml = textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-16"?>
        <Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
          <Triggers>
            <LogonTrigger>
              <Enabled>true</Enabled>
            </LogonTrigger>
          </Triggers>
          <Settings>
            <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
            <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
            <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
            <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
            <RestartOnFailure>
              <Interval>PT1M</Interval>
              <Count>999</Count>
            </RestartOnFailure>
          </Settings>
          <Actions>
            <Exec>
              <Command>{python}</Command>
              <Arguments>"{script}" --server {server} --token {token}</Arguments>
              <WorkingDirectory>{Path.home()}</WorkingDirectory>
            </Exec>
          </Actions>
          <Principals>
            <Principal>
              <LogonType>InteractiveToken</LogonType>
              <RunLevel>LeastPrivilege</RunLevel>
            </Principal>
          </Principals>
        </Task>
    """)

    xml_path = CONFIG_DIR / "bridge_task.xml"
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    xml_path.write_text(task_xml, encoding="utf-16")

    result = subprocess.run(
        ["schtasks", "/Create", "/TN", SERVICE_NAME, "/XML", str(xml_path), "/F"],
        capture_output=True, text=True,
    )
    xml_path.unlink(missing_ok=True)

    if result.returncode == 0:
        # Start it immediately
        subprocess.run(["schtasks", "/Run", "/TN", SERVICE_NAME], capture_output=True)
        print(f"  ✓ Task Scheduler entry created: {SERVICE_NAME}")
        print(f"\n  🟢 Plutus Bridge will now start automatically on every login.")
        print(f"     Logs: {LOG_FILE}")
    else:
        print(f"  ✗ schtasks failed: {result.stderr.strip()}")
        print("  Tip: run this script as Administrator if you see access denied errors.")


def _windows_uninstall() -> None:
    result = subprocess.run(
        ["schtasks", "/Delete", "/TN", SERVICE_NAME, "/F"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"  ✓ Task Scheduler entry removed: {SERVICE_NAME}")
    else:
        print(f"  ℹ  {result.stderr.strip()}")


def _windows_service_status() -> str:
    result = subprocess.run(
        ["schtasks", "/Query", "/TN", SERVICE_NAME, "/FO", "CSV", "/NH"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return "not-installed"
    line = result.stdout.strip()
    if "Running" in line:
        return "running"
    return "installed-stopped"


# ── Public service API ────────────────────────────────────────────────────────

def install_service(config: dict) -> None:
    """Install the bridge as a system auto-start service."""
    print("\n╔══════════════════════════════════════════╗")
    print("║   Plutus Bridge – Auto-start Install     ║")
    print("╚══════════════════════════════════════════╝\n")
    system = platform.system()
    if system == "Darwin":
        _macos_install(config)
    elif system == "Linux":
        _linux_install(config)
    elif system == "Windows":
        _windows_install(config)
    else:
        print(f"  ✗ Unsupported OS: {system}")
        sys.exit(1)


def uninstall_service() -> None:
    """Remove the auto-start service entry."""
    print("\n╔══════════════════════════════════════════╗")
    print("║   Plutus Bridge – Auto-start Uninstall   ║")
    print("╚══════════════════════════════════════════╝\n")
    system = platform.system()
    if system == "Darwin":
        _macos_uninstall()
    elif system == "Linux":
        _linux_uninstall()
    elif system == "Windows":
        _windows_uninstall()
    else:
        print(f"  ✗ Unsupported OS: {system}")


def service_status() -> str:
    """Return service status string: running | installed-stopped | not-installed."""
    system = platform.system()
    if system == "Darwin":
        return _macos_service_status()
    if system == "Linux":
        return _linux_service_status()
    if system == "Windows":
        return _windows_service_status()
    return "unsupported"


# ---------------------------------------------------------------------------
# Graceful shutdown coordinator
# ---------------------------------------------------------------------------


class ShutdownCoordinator:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    @property
    def is_shutting_down(self) -> bool:
        return self._event.is_set()

    def trigger(self) -> None:
        log.info("Shutdown triggered.")
        self._event.set()

    async def wait(self) -> None:
        await self._event.wait()


# ---------------------------------------------------------------------------
# Bridge daemon
# ---------------------------------------------------------------------------


class PlutusBridge:
    """Main bridge daemon – manages WS connection, heartbeat, and tasks."""

    def __init__(self, server_url: str, token: str) -> None:
        self.server_url = server_url
        self.token = token
        self.shutdown = ShutdownCoordinator()
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._tasks: list[asyncio.Task] = []
        # Pending tool_call futures keyed by call_id
        self._pending: dict[str, asyncio.Future] = {}

    async def run(self) -> None:
        self._install_signal_handlers()
        log.info("Plutus Bridge v%s starting…", VERSION)
        log.info("Server : %s", self.server_url)
        log.info("Log    : %s", LOG_FILE)

        connection_task = asyncio.create_task(self._connection_loop(), name="connection_loop")
        shutdown_task = asyncio.create_task(self.shutdown.wait(), name="shutdown_wait")
        self._tasks = [connection_task]

        await asyncio.wait(
            [connection_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        await self._cleanup()
        log.info("Plutus Bridge stopped.")

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.shutdown.trigger)
            except NotImplementedError:
                signal.signal(sig, lambda *_: self.shutdown.trigger())

    async def _cleanup(self) -> None:
        for t in self._tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._ws and not self._ws.closed:
            try:
                await self._ws.close()
            except Exception:
                pass

    async def _connection_loop(self) -> None:
        reconnect_delay = RECONNECT_DELAY_INIT
        while not self.shutdown.is_shutting_down:
            try:
                ws_url = f"{self.server_url}/{self.token}"
                log.info("Connecting to %s …", self.server_url)
                async with websockets.connect(
                    ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                    additional_headers={"Authorization": f"Bearer {self.token}"},
                ) as ws:
                    self._ws = ws
                    log.info("✓ Connected to Plutus Cloud.")
                    reconnect_delay = RECONNECT_DELAY_INIT

                    await self._send(ws, {
                        "type": "handshake",
                        "system": get_system_info(),
                        "version": VERSION,
                    })

                    hb = asyncio.create_task(self._heartbeat_loop(ws), name="heartbeat")
                    recv = asyncio.create_task(self._receive_loop(ws), name="receiver")
                    shutdown_wait = asyncio.create_task(self.shutdown.wait())

                    done, pending = await asyncio.wait(
                        [hb, recv, shutdown_wait],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for p in pending:
                        p.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)

                    if self.shutdown.is_shutting_down:
                        return

            except (
                websockets.exceptions.ConnectionClosed,
                websockets.exceptions.InvalidStatusCode,
                ConnectionRefusedError,
                OSError,
            ) as exc:
                log.warning("Connection lost: %s. Retrying in %ds…", exc, reconnect_delay)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                log.error("Unexpected WS error: %s. Retrying in %ds…", exc, reconnect_delay, exc_info=True)

            if self.shutdown.is_shutting_down:
                return
            await self._interruptible_sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, RECONNECT_DELAY_MAX)

    async def _heartbeat_loop(self, ws: websockets.WebSocketClientProtocol) -> None:
        while not self.shutdown.is_shutting_down:
            try:
                await self._interruptible_sleep(HEARTBEAT_INTERVAL)
                if self.shutdown.is_shutting_down:
                    return
                await self._send(ws, {"type": "heartbeat", "ts": time.time()})
                log.debug("Heartbeat sent.")
            except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
                return
            except Exception as exc:
                log.warning("Heartbeat error: %s", exc)
                return

    async def _receive_loop(self, ws: websockets.WebSocketClientProtocol) -> None:
        try:
            async for raw in ws:
                if self.shutdown.is_shutting_down:
                    return
                try:
                    data: dict[str, Any] = json.loads(raw)
                except json.JSONDecodeError:
                    log.warning("Received non-JSON message, ignoring.")
                    continue

                msg_type = data.get("type", "")
                log.debug("Received message type=%s", msg_type)

                if msg_type == "task":
                    asyncio.create_task(
                        self._handle_task(ws, data), name=f"task-{data.get('task_id')}"
                    )
                elif msg_type == "tool_call":
                    asyncio.create_task(
                        self._handle_tool_call(ws, data), name=f"tool-{data.get('call_id')}"
                    )
                elif msg_type == "tool_result":
                    call_id = data.get("call_id")
                    fut = self._pending.pop(call_id, None)
                    if fut and not fut.done():
                        fut.set_result(data.get("result", {}))
                elif msg_type == "heartbeat_ack":
                    log.debug("Heartbeat ACK received.")
                elif msg_type == "error":
                    log.error("Server error: %s", data.get("message", data))
                else:
                    log.warning("Unknown message type: %s", msg_type)

        except websockets.exceptions.ConnectionClosed:
            log.info("WebSocket closed by server.")
        except asyncio.CancelledError:
            return

    async def _handle_task(self, ws: websockets.WebSocketClientProtocol, data: dict[str, Any]) -> None:
        task_id = data.get("task_id", "unknown")
        try:
            result = await execute_local_task(data)
            await self._send(ws, {"type": "task_result", "task_id": task_id, "result": result})
        except websockets.exceptions.ConnectionClosed:
            log.warning("Cannot send result for task %s – connection closed.", task_id)
        except Exception as exc:
            log.error("Failed to handle task %s: %s", task_id, exc, exc_info=True)

    async def _handle_tool_call(self, ws: websockets.WebSocketClientProtocol, data: dict[str, Any]) -> None:
        """Handle a tool_call dispatched by the cloud hybrid_executor."""
        call_id = data.get("call_id", "unknown")
        tool = data.get("tool", "")
        args = data.get("args", {})
        try:
            result = await execute_local_task({"type": tool, "task_id": call_id, "payload": args})
            await self._send(ws, {"type": "tool_result", "call_id": call_id, "result": result})
        except websockets.exceptions.ConnectionClosed:
            log.warning("Cannot send tool result for call %s – connection closed.", call_id)
        except Exception as exc:
            log.error("Failed to handle tool call %s: %s", call_id, exc, exc_info=True)
            try:
                await self._send(ws, {
                    "type": "tool_result",
                    "call_id": call_id,
                    "result": {"success": False, "error": str(exc)},
                })
            except Exception:
                pass

    @staticmethod
    async def _send(ws: websockets.WebSocketClientProtocol, data: dict[str, Any]) -> None:
        await ws.send(json.dumps(data))

    async def _interruptible_sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self.shutdown.wait(), timeout=seconds)
        except TimeoutError:
            pass


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plutus Local Bridge Daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python plutus_bridge.py --setup           # first-time config\n"
            "  python plutus_bridge.py --install         # install auto-start service\n"
            "  python plutus_bridge.py --uninstall       # remove auto-start service\n"
            "  python plutus_bridge.py --service-status  # check service status\n"
            "  python plutus_bridge.py                   # run manually (foreground)\n"
        ),
    )
    parser.add_argument("--server", default=None, help="Cloud WebSocket URL")
    parser.add_argument("--token", default=None, help="JWT authentication token")
    parser.add_argument("--setup", action="store_true", help="Run interactive setup wizard")
    parser.add_argument("--install", action="store_true", help="Install as system auto-start service")
    parser.add_argument("--uninstall", action="store_true", help="Remove the auto-start service")
    parser.add_argument("--service-status", action="store_true", help="Print service status and exit")
    parser.add_argument("--version", action="version", version=f"Plutus Bridge v{VERSION}")
    args = parser.parse_args()

    # --- Service status ---
    if args.service_status:
        status = service_status()
        icons = {"running": "🟢", "installed-stopped": "🟡", "not-installed": "⚫"}
        print(f"  {icons.get(status, '?')} Bridge service status: {status}")
        sys.exit(0 if status == "running" else 1)

    # --- Load config, apply CLI overrides ---
    config = load_config()
    if args.server:
        config["server"] = args.server
    if args.token:
        config["token"] = args.token

    # --- Setup mode ---
    if args.setup:
        config = run_setup()

    server = config.get("server", DEFAULT_SERVER)
    token = config.get("token", "")

    # --- Install / Uninstall ---
    if args.uninstall:
        uninstall_service()
        return

    if args.install:
        if not token:
            print("Error: No auth token. Run --setup first or pass --token <jwt>.")
            sys.exit(1)
        config["server"] = server
        save_config(config)
        install_service(config)
        return

    # --- Normal run ---
    if not token:
        print("Error: No auth token configured.")
        print("Run `python plutus_bridge.py --setup` or pass --token <jwt>.")
        sys.exit(1)

    # Persist any overrides
    if args.server or args.token:
        save_config(config)

    bridge = PlutusBridge(server_url=server, token=token)
    try:
        asyncio.run(bridge.run())
    except KeyboardInterrupt:
        log.info("Interrupted – exiting.")


if __name__ == "__main__":
    main()
