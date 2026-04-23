#!/usr/bin/env python3
"""Plutus Local Bridge Daemon.

A lightweight background process that runs on the user's PC and connects
to Plutus Cloud via WebSocket.  It allows the cloud AI agent to execute
commands, read/write files, and open apps on the local machine.

Requirements: Python 3.10+, websockets (``pip install websockets``)

Usage:
    python plutus_bridge.py --token <bridge_token>   # first run (saves config)
    python plutus_bridge.py                           # subsequent runs
    python plutus_bridge.py --setup                   # interactive setup
"""

from __future__ import annotations

import argparse
import asyncio
import base64
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
from typing import Any

# ---------------------------------------------------------------------------
# Lazy dependency bootstrap
# ---------------------------------------------------------------------------
try:
    import websockets
    import websockets.exceptions
except ImportError:
    print("Installing websockets…")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--quiet", "websockets>=12.0"]
    )
    import websockets
    import websockets.exceptions

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VERSION = "1.0.0"
CONFIG_DIR = Path.home() / ".plutus"
CONFIG_FILE = CONFIG_DIR / "bridge_config.json"
LOG_FILE = CONFIG_DIR / "bridge.log"

HEARTBEAT_INTERVAL = 25  # seconds between heartbeats
RECONNECT_DELAY_INIT = 3  # initial reconnect back-off
RECONNECT_DELAY_MAX = 120  # cap at 2 minutes
OUTPUT_LIMIT = 50_000  # max chars for stdout/stderr


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def _setup_logging() -> logging.Logger:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("plutus_bridge")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
    )
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    fh = logging.handlers.RotatingFileHandler(
        str(LOG_FILE), maxBytes=2 * 1024 * 1024, backupCount=2, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


log = _setup_logging()


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------
def extract_server_url(token: str) -> str:
    """Extract the cloud server URL embedded in a Plutus sync token.

    Token format: plutus_<base64url(server_url)>.<hex_secret>
    """
    if not token.startswith("plutus_"):
        raise ValueError("Invalid token format — must start with 'plutus_'")
    body = token[len("plutus_"):]
    url_b64 = body.split(".")[0]
    # Re-add padding
    padding = 4 - len(url_b64) % 4
    if padding != 4:
        url_b64 += "=" * padding
    url = base64.urlsafe_b64decode(url_b64).decode()
    return url


def derive_ws_url(server_url: str) -> str:
    """Convert an HTTP(S) server URL to the bridge WebSocket URL."""
    ws = server_url.replace("https://", "wss://").replace("http://", "ws://")
    ws = ws.rstrip("/")
    return f"{ws}/api/bridge/ws"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def load_config() -> dict[str, Any]:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_config(config: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")


def run_setup() -> dict[str, Any]:
    print("\n╔══════════════════════════════════════╗")
    print("║     Plutus Bridge — Setup Wizard     ║")
    print("╚══════════════════════════════════════╝\n")
    config = load_config()
    token = input("  Bridge token: ").strip()
    if token:
        config["token"] = token
        try:
            url = extract_server_url(token)
            print(f"  → Server: {url}")
        except Exception:
            print("  ⚠ Could not extract server URL from token.")
    save_config(config)
    print("\n  ✓ Saved. Run `python plutus_bridge.py` to start.\n")
    return config


# ---------------------------------------------------------------------------
# System info
# ---------------------------------------------------------------------------
def get_system_info() -> dict[str, Any]:
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
# Tool handlers
# ---------------------------------------------------------------------------
async def handle_tool_call(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool call from the cloud agent."""
    try:
        if tool == "shell_exec":
            return await _tool_shell(args)
        if tool == "python_exec":
            return await _tool_python(args)
        if tool == "file_read":
            return _tool_file_read(args)
        if tool == "file_write":
            return _tool_file_write(args)
        if tool == "file_list":
            return _tool_file_list(args)
        if tool == "open_app":
            return _tool_open_app(args)
        if tool == "ping":
            return {"success": True, "message": "pong", "system": get_system_info()}
        return {"success": False, "error": f"Unknown tool: {tool}"}
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


async def _tool_shell(args: dict[str, Any]) -> dict[str, Any]:
    cmd = args.get("command", "")
    timeout = min(args.get("timeout", 60), 300)
    cwd = args.get("cwd")
    if not cmd:
        return {"success": False, "error": "Empty command"}
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except TimeoutError:
        proc.kill()
        return {"success": False, "error": f"Command timed out after {timeout}s"}
    return {
        "success": proc.returncode == 0,
        "stdout": stdout.decode(errors="replace")[:OUTPUT_LIMIT],
        "stderr": stderr.decode(errors="replace")[:OUTPUT_LIMIT],
        "exit_code": proc.returncode,
    }


async def _tool_python(args: dict[str, Any]) -> dict[str, Any]:
    code = args.get("code", "")
    timeout = min(args.get("timeout", 60), 300)
    if not code:
        return {"success": False, "error": "Empty code"}
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", code,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except TimeoutError:
        proc.kill()
        return {"success": False, "error": f"Python timed out after {timeout}s"}
    return {
        "success": proc.returncode == 0,
        "stdout": stdout.decode(errors="replace")[:OUTPUT_LIMIT],
        "stderr": stderr.decode(errors="replace")[:OUTPUT_LIMIT],
        "exit_code": proc.returncode,
    }


def _tool_file_read(args: dict[str, Any]) -> dict[str, Any]:
    raw = args.get("path", "")
    if not raw:
        return {"success": False, "error": "No path provided"}
    path = Path(raw).expanduser()
    if not path.exists():
        return {"success": False, "error": f"File not found: {path}"}
    if not path.is_file():
        return {"success": False, "error": f"Not a file: {path}"}
    max_size = args.get("max_size", 100_000)
    try:
        content = path.read_text(errors="replace")[:max_size]
        return {"success": True, "content": content, "size": path.stat().st_size}
    except Exception as exc:
        return {"success": False, "error": f"Read failed: {exc}"}


def _tool_file_write(args: dict[str, Any]) -> dict[str, Any]:
    raw = args.get("path", "")
    content = args.get("content", "")
    if not raw:
        return {"success": False, "error": "No path provided"}
    path = Path(raw).expanduser()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"success": True, "message": f"Written {len(content)} chars to {path}"}
    except Exception as exc:
        return {"success": False, "error": f"Write failed: {exc}"}


def _tool_file_list(args: dict[str, Any]) -> dict[str, Any]:
    raw = args.get("path", ".")
    pattern = args.get("pattern", "*")
    limit = min(args.get("limit", 500), 2000)
    path = Path(raw).expanduser()
    if not path.exists():
        return {"success": False, "error": f"Path not found: {path}"}
    try:
        entries = []
        for f in sorted(path.glob(pattern))[:limit]:
            try:
                stat = f.stat()
                entries.append({
                    "name": f.name,
                    "path": str(f),
                    "is_dir": f.is_dir(),
                    "size": stat.st_size if f.is_file() else 0,
                })
            except OSError:
                entries.append({"name": f.name, "path": str(f)})
        return {"success": True, "files": entries, "count": len(entries)}
    except Exception as exc:
        return {"success": False, "error": f"List failed: {exc}"}


def _tool_open_app(args: dict[str, Any]) -> dict[str, Any]:
    app_name = args.get("app", "") or args.get("app_name", "")
    if not app_name:
        return {"success": False, "error": "No app name provided"}
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


# ---------------------------------------------------------------------------
# Bridge daemon
# ---------------------------------------------------------------------------
class PlutusBridge:
    """Main bridge daemon — WebSocket connection + heartbeat + tool execution."""

    def __init__(self, server_url: str, token: str) -> None:
        self.server_url = server_url
        self.token = token
        self._ws_url = f"{derive_ws_url(server_url)}/{token}"
        self._shutdown = asyncio.Event()
        self._ws = None

    async def run(self) -> None:
        """Start the bridge and block until shutdown."""
        self._install_signal_handlers()
        log.info("Plutus Bridge v%s starting…", VERSION)
        log.info("Server: %s", self.server_url)
        log.info("Log:    %s", LOG_FILE)
        await self._connection_loop()
        log.info("Plutus Bridge stopped.")

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._shutdown.set)
            except NotImplementedError:
                signal.signal(sig, lambda *_: self._shutdown.set())

    async def _connection_loop(self) -> None:
        delay = RECONNECT_DELAY_INIT
        while not self._shutdown.is_set():
            try:
                log.info("Connecting…")
                async with websockets.connect(
                    self._ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self._ws = ws
                    log.info("✓ Connected to Plutus Cloud")
                    delay = RECONNECT_DELAY_INIT

                    # Handshake
                    await self._send(ws, {
                        "type": "handshake",
                        "system": get_system_info(),
                        "version": VERSION,
                    })

                    # Run heartbeat + receiver concurrently
                    hb = asyncio.create_task(self._heartbeat(ws))
                    recv = asyncio.create_task(self._receiver(ws))
                    shutdown = asyncio.create_task(self._shutdown.wait())

                    done, pending = await asyncio.wait(
                        [hb, recv, shutdown],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for t in pending:
                        t.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)

                    if self._shutdown.is_set():
                        return

            except (
                websockets.exceptions.ConnectionClosed,
                websockets.exceptions.InvalidStatusCode,
                ConnectionRefusedError,
                OSError,
            ) as exc:
                log.warning("Connection lost: %s — retrying in %ds", exc, delay)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                log.error("Unexpected error: %s — retrying in %ds", exc, delay)

            if self._shutdown.is_set():
                return
            await self._sleep(delay)
            delay = min(delay * 2, RECONNECT_DELAY_MAX)

    async def _heartbeat(self, ws) -> None:
        while not self._shutdown.is_set():
            await self._sleep(HEARTBEAT_INTERVAL)
            if self._shutdown.is_set():
                return
            try:
                await self._send(ws, {"type": "heartbeat", "ts": time.time()})
            except Exception:
                return

    async def _receiver(self, ws) -> None:
        try:
            async for raw in ws:
                if self._shutdown.is_set():
                    return
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = data.get("type", "")

                if msg_type == "tool_call":
                    asyncio.create_task(
                        self._handle_tool_call(ws, data)
                    )
                elif msg_type == "heartbeat_ack":
                    log.debug("Heartbeat ACK")
                elif msg_type == "handshake_ack":
                    log.debug("Handshake acknowledged")
                elif msg_type == "error":
                    log.error("Server error: %s", data.get("message", data))
                else:
                    log.debug("Unknown message type: %s", msg_type)

        except websockets.exceptions.ConnectionClosed:
            log.info("WebSocket closed by server")
        except asyncio.CancelledError:
            return

    async def _handle_tool_call(self, ws, data: dict) -> None:
        call_id = data.get("call_id", "unknown")
        tool = data.get("tool", "")
        args = data.get("args", {})
        log.info("Tool call: %s [%s]", tool, call_id[:8])
        t0 = time.monotonic()

        result = await handle_tool_call(tool, args)

        elapsed = time.monotonic() - t0
        log.info(
            "Tool %s done in %.1fs — success=%s",
            tool, elapsed, result.get("success"),
        )
        try:
            await self._send(ws, {
                "type": "tool_result",
                "call_id": call_id,
                "result": result,
            })
        except Exception as exc:
            log.warning("Failed to send tool result: %s", exc)

    @staticmethod
    async def _send(ws, data: dict) -> None:
        await ws.send(json.dumps(data))

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._shutdown.wait(), timeout=seconds)
        except TimeoutError:
            pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plutus Local Bridge — connect your PC to Plutus Cloud",
    )
    parser.add_argument("--token", help="Bridge token (from Settings → Local Bridge)")
    parser.add_argument("--setup", action="store_true", help="Interactive setup wizard")
    parser.add_argument("--version", action="version", version=f"v{VERSION}")
    args = parser.parse_args()

    if args.setup:
        run_setup()
        return

    config = load_config()
    token = args.token or config.get("token", "")

    if not token:
        print("Error: No bridge token configured.")
        print("Run: python plutus_bridge.py --token <your_token>")
        print("  or: python plutus_bridge.py --setup")
        sys.exit(1)

    # Save token if provided via CLI
    if args.token and args.token != config.get("token"):
        config["token"] = args.token
        save_config(config)

    # Extract server URL from token
    try:
        server_url = extract_server_url(token)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    bridge = PlutusBridge(server_url=server_url, token=token)
    try:
        asyncio.run(bridge.run())
    except KeyboardInterrupt:
        log.info("Interrupted — exiting.")


if __name__ == "__main__":
    main()
