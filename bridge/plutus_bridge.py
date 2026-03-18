#!/usr/bin/env python3
"""Plutus Local Bridge Daemon.

A lightweight background process that runs on the user's PC and connects
to the Plutus Cloud via WebSocket.  It allows the cloud agent to execute
tasks on the user's local machine (open apps, access files, run commands, etc.)
and keeps the local memory store in sync with the cloud.

Usage:
    python plutus_bridge.py                          # run with saved config
    python plutus_bridge.py --setup                  # interactive first-time setup
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
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Lazy dependency bootstrap – install missing packages automatically
# ---------------------------------------------------------------------------
_REQUIRED_PACKAGES = {
    "websockets": "websockets>=12.0",
    "httpx": "httpx>=0.25",
    "aiosqlite": "aiosqlite>=0.19",
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
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", *missing]
        )


_ensure_packages()

import websockets  # noqa: E402
import websockets.exceptions  # noqa: E402

from sync_client import LocalSyncClient, SyncError  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VERSION = "0.2.0"
DEFAULT_SERVER = "ws://localhost:8000/api/bridge/ws"
CONFIG_DIR = Path.home() / ".plutus"
CONFIG_FILE = CONFIG_DIR / "bridge_config.json"
LOG_FILE = CONFIG_DIR / "bridge.log"

HEARTBEAT_INTERVAL = 30       # seconds between heartbeats
SYNC_INTERVAL = 60            # seconds between sync cycles
RECONNECT_DELAY_INIT = 5      # initial reconnect back-off
RECONNECT_DELAY_MAX = 300     # cap at 5 minutes
TASK_OUTPUT_LIMIT = 10_000    # max chars for stdout in task results
TASK_STDERR_LIMIT = 5_000     # max chars for stderr in task results

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

def load_config() -> Dict[str, Any]:
    """Load bridge configuration from ~/.plutus/bridge_config.json."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Failed to load config (%s) – using defaults.", exc)
    return {}


def save_config(config: Dict[str, Any]) -> None:
    """Persist bridge configuration."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
    log.info("Config saved to %s", CONFIG_FILE)


def run_setup() -> Dict[str, Any]:
    """Interactive first-time setup wizard."""
    print("\n╔══════════════════════════════════════╗")
    print("║     Plutus Bridge – Initial Setup    ║")
    print("╚══════════════════════════════════════╝\n")

    config = load_config()

    token = input(f"  Auth token [{config.get('token', '')[:8]}…]: ").strip()
    if token:
        config["token"] = token

    server = input(
        f"  Server URL [{config.get('server', DEFAULT_SERVER)}]: "
    ).strip()
    if server:
        config["server"] = server
    elif "server" not in config:
        config["server"] = DEFAULT_SERVER

    sync_input = input(
        f"  Sync interval secs [{config.get('sync_interval', SYNC_INTERVAL)}]: "
    ).strip()
    if sync_input.isdigit():
        config["sync_interval"] = int(sync_input)
    elif "sync_interval" not in config:
        config["sync_interval"] = SYNC_INTERVAL

    save_config(config)
    print("\n  ✓ Configuration saved. Run `python plutus_bridge.py` to start.\n")
    return config


# ---------------------------------------------------------------------------
# System info
# ---------------------------------------------------------------------------

def get_system_info() -> Dict[str, Any]:
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

async def execute_local_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a task dispatched by the cloud agent.

    Supported task types:
        shell, open_app, read_file, write_file, list_files, ping
    """
    task_type: str = task.get("type", "")
    payload: Dict[str, Any] = task.get("payload", {})
    task_id: str = task.get("task_id", "unknown")

    log.info("Executing task %s [%s]", task_id, task_type)
    t0 = time.monotonic()

    try:
        result = await _dispatch_task(task_type, payload)
    except asyncio.TimeoutError:
        result = {"success": False, "error": f"Task timed out: {task_type}"}
    except Exception as exc:
        log.exception("Task %s failed with unhandled error", task_id)
        result = {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    elapsed = time.monotonic() - t0
    log.info(
        "Task %s [%s] finished in %.2fs – success=%s",
        task_id,
        task_type,
        elapsed,
        result.get("success"),
    )
    return result


async def _dispatch_task(task_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Route a task to the correct handler."""

    if task_type == "shell":
        return await _task_shell(payload)
    if task_type == "open_app":
        return _task_open_app(payload)
    if task_type == "read_file":
        return _task_read_file(payload)
    if task_type == "write_file":
        return _task_write_file(payload)
    if task_type == "list_files":
        return _task_list_files(payload)
    if task_type == "ping":
        return {"success": True, "message": "pong", "system": get_system_info()}

    return {"success": False, "error": f"Unknown task type: {task_type}"}


async def _task_shell(payload: Dict[str, Any]) -> Dict[str, Any]:
    cmd: str = payload.get("command", "")
    timeout: int = min(payload.get("timeout", 60), 300)  # cap at 5 min
    cwd: Optional[str] = payload.get("cwd")

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


def _task_open_app(payload: Dict[str, Any]) -> Dict[str, Any]:
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


def _task_read_file(payload: Dict[str, Any]) -> Dict[str, Any]:
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


def _task_write_file(payload: Dict[str, Any]) -> Dict[str, Any]:
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


def _task_list_files(payload: Dict[str, Any]) -> Dict[str, Any]:
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


# ---------------------------------------------------------------------------
# Graceful shutdown coordinator
# ---------------------------------------------------------------------------

class ShutdownCoordinator:
    """Manages graceful shutdown across all async tasks."""

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
    """Main bridge daemon – manages WS connection, heartbeat, sync, tasks."""

    def __init__(
        self,
        server_url: str,
        token: str,
        sync_interval: int = SYNC_INTERVAL,
    ) -> None:
        self.server_url = server_url
        self.token = token
        self.sync_interval = sync_interval

        # Derive HTTP base URL from WS URL for sync client
        http_url = server_url.replace("wss://", "https://").replace("ws://", "http://")
        # Strip the /api/bridge/ws path to get the base
        base_url = http_url.split("/api/bridge")[0] if "/api/bridge" in http_url else http_url

        self.sync_client = LocalSyncClient(
            server_url=base_url,
            token=token,
        )
        self.shutdown = ShutdownCoordinator()
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._tasks: list[asyncio.Task] = []

    # ---- Main entry point ------------------------------------------------

    async def run(self) -> None:
        """Start the bridge and block until shutdown."""
        self._install_signal_handlers()
        log.info("Plutus Bridge v%s starting…", VERSION)
        log.info("Server : %s", self.server_url)
        log.info("Sync   : every %ds", self.sync_interval)
        log.info("Log    : %s", LOG_FILE)

        # Run connection loop and sync loop concurrently
        connection_task = asyncio.create_task(
            self._connection_loop(), name="connection_loop"
        )
        sync_task = asyncio.create_task(
            self._sync_loop(), name="sync_loop"
        )
        shutdown_task = asyncio.create_task(
            self.shutdown.wait(), name="shutdown_wait"
        )

        self._tasks = [connection_task, sync_task]

        # Wait for shutdown signal
        done, _ = await asyncio.wait(
            [connection_task, sync_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # If shutdown was triggered (or a task died unexpectedly), clean up
        await self._cleanup()
        log.info("Plutus Bridge stopped.")

    # ---- Signal handlers -------------------------------------------------

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.shutdown.trigger)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler; fall back
                signal.signal(sig, lambda *_: self.shutdown.trigger())

    # ---- Cleanup ---------------------------------------------------------

    async def _cleanup(self) -> None:
        log.info("Cleaning up…")
        for t in self._tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

        if self._ws and not self._ws.closed:
            try:
                await self._ws.close()
            except Exception:
                pass

    # ---- WebSocket connection loop with exponential back-off -------------

    async def _connection_loop(self) -> None:
        reconnect_delay = RECONNECT_DELAY_INIT

        while not self.shutdown.is_shutting_down:
            try:
                ws_url = f"{self.server_url}?token={self.token}"
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

                    # Handshake
                    await self._send(ws, {
                        "type": "handshake",
                        "system": get_system_info(),
                        "version": VERSION,
                    })

                    # Run heartbeat + message receiver concurrently
                    hb = asyncio.create_task(
                        self._heartbeat_loop(ws), name="heartbeat"
                    )
                    recv = asyncio.create_task(
                        self._receive_loop(ws), name="receiver"
                    )

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

    # ---- Heartbeat -------------------------------------------------------

    async def _heartbeat_loop(self, ws: websockets.WebSocketClientProtocol) -> None:
        """Send periodic heartbeats to keep the connection alive."""
        while not self.shutdown.is_shutting_down:
            try:
                await self._interruptible_sleep(HEARTBEAT_INTERVAL)
                if self.shutdown.is_shutting_down:
                    return
                await self._send(ws, {"type": "heartbeat", "ts": time.time()})
                log.debug("Heartbeat sent.")
            except (
                websockets.exceptions.ConnectionClosed,
                asyncio.CancelledError,
            ):
                return
            except Exception as exc:
                log.warning("Heartbeat error: %s", exc)
                return

    # ---- Message receiver ------------------------------------------------

    async def _receive_loop(self, ws: websockets.WebSocketClientProtocol) -> None:
        """Listen for incoming messages and dispatch them."""
        try:
            async for raw in ws:
                if self.shutdown.is_shutting_down:
                    return
                try:
                    data: Dict[str, Any] = json.loads(raw)
                except json.JSONDecodeError:
                    log.warning("Received non-JSON message, ignoring.")
                    continue

                msg_type = data.get("type", "")
                log.debug("Received message type=%s", msg_type)

                if msg_type == "task":
                    # Execute task and send result (non-blocking)
                    asyncio.create_task(
                        self._handle_task(ws, data), name=f"task-{data.get('task_id')}"
                    )

                elif msg_type == "sync_request":
                    asyncio.create_task(
                        self._handle_sync_request(ws, data), name="sync_request"
                    )

                elif msg_type == "heartbeat_ack":
                    log.debug("Heartbeat ACK received.")

                elif msg_type == "error":
                    log.error("Server error: %s", data.get("message", data))

                elif msg_type == "token_refresh":
                    new_token = data.get("token")
                    if new_token:
                        log.info("Token refreshed by server.")
                        self.token = new_token
                        self.sync_client.update_token(new_token)

                else:
                    log.warning("Unknown message type: %s", msg_type)

        except websockets.exceptions.ConnectionClosed:
            log.info("WebSocket closed by server.")
        except asyncio.CancelledError:
            return

    # ---- Task handler ----------------------------------------------------

    async def _handle_task(
        self, ws: websockets.WebSocketClientProtocol, data: Dict[str, Any]
    ) -> None:
        task_id = data.get("task_id", "unknown")
        try:
            result = await execute_local_task(data)
            await self._send(ws, {
                "type": "task_result",
                "task_id": task_id,
                "result": result,
            })
        except websockets.exceptions.ConnectionClosed:
            log.warning("Cannot send result for task %s – connection closed.", task_id)
        except Exception as exc:
            log.error("Failed to handle task %s: %s", task_id, exc, exc_info=True)

    # ---- Sync request handler (cloud-initiated) --------------------------

    async def _handle_sync_request(
        self, ws: websockets.WebSocketClientProtocol, data: Dict[str, Any]
    ) -> None:
        try:
            version = await self.sync_client.full_sync()
            await self._send(ws, {
                "type": "sync_response",
                "success": True,
                "server_version": version,
            })
        except SyncError as exc:
            log.error("Cloud-initiated sync failed: %s", exc)
            await self._send(ws, {
                "type": "sync_response",
                "success": False,
                "error": str(exc),
            })
        except websockets.exceptions.ConnectionClosed:
            pass

    # ---- Periodic background sync ----------------------------------------

    async def _sync_loop(self) -> None:
        """Periodically sync local DB with the cloud."""
        # Wait a bit before first sync to let the connection establish
        await self._interruptible_sleep(10)

        while not self.shutdown.is_shutting_down:
            try:
                log.debug("Starting periodic sync…")
                version = await self.sync_client.full_sync()
                log.debug("Periodic sync complete – version %d.", version)
            except SyncError as exc:
                log.warning("Periodic sync failed: %s", exc)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                log.error("Unexpected sync error: %s", exc, exc_info=True)

            await self._interruptible_sleep(self.sync_interval)

    # ---- Helpers ---------------------------------------------------------

    @staticmethod
    async def _send(
        ws: websockets.WebSocketClientProtocol, data: Dict[str, Any]
    ) -> None:
        await ws.send(json.dumps(data))

    async def _interruptible_sleep(self, seconds: float) -> None:
        """Sleep that can be interrupted by shutdown."""
        try:
            await asyncio.wait_for(self.shutdown.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass  # Normal – timeout means we slept the full duration


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plutus Local Bridge Daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python plutus_bridge.py --setup              # first-time config\n"
            "  python plutus_bridge.py                      # run with saved config\n"
            "  python plutus_bridge.py --token <jwt>        # override token\n"
        ),
    )
    parser.add_argument("--server", default=None, help="Cloud WebSocket URL")
    parser.add_argument("--token", default=None, help="JWT authentication token")
    parser.add_argument("--sync-interval", type=int, default=None, help="Sync interval in seconds")
    parser.add_argument("--setup", action="store_true", help="Run interactive setup wizard")
    parser.add_argument("--version", action="version", version=f"Plutus Bridge v{VERSION}")
    args = parser.parse_args()

    # --- Setup mode ---
    if args.setup:
        run_setup()
        return

    # --- Load config, apply CLI overrides ---
    config = load_config()

    server = args.server or config.get("server", DEFAULT_SERVER)
    token = args.token or config.get("token", "")
    sync_interval = args.sync_interval or config.get("sync_interval", SYNC_INTERVAL)

    if not token:
        print("Error: No auth token configured.")
        print("Run `python plutus_bridge.py --setup` or pass --token <jwt>.")
        sys.exit(1)

    # --- Persist any CLI overrides ---
    updated = False
    if args.server and args.server != config.get("server"):
        config["server"] = args.server
        updated = True
    if args.token and args.token != config.get("token"):
        config["token"] = args.token
        updated = True
    if args.sync_interval and args.sync_interval != config.get("sync_interval"):
        config["sync_interval"] = args.sync_interval
        updated = True
    if updated:
        save_config(config)

    # --- Launch bridge ---
    bridge = PlutusBridge(
        server_url=server,
        token=token,
        sync_interval=sync_interval,
    )

    try:
        asyncio.run(bridge.run())
    except KeyboardInterrupt:
        log.info("Interrupted – exiting.")


if __name__ == "__main__":
    main()
