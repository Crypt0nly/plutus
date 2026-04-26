"""Plutus Local Bridge Daemon.

A lightweight background process that runs on the user's PC and connects
to Plutus Cloud via WebSocket.  It allows the cloud AI agent to execute
commands, read/write files, and open apps on the local machine.

Requirements: Python 3.10+, websockets (``pip install websockets``)

Usage (standalone):
    python -m plutus.bridge.bridge --token <bridge_token>
    python -m plutus.bridge.bridge --setup
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
import traceback
import uuid
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Lazy dependency bootstrap (only needed for standalone usage)
# ---------------------------------------------------------------------------
try:
    import websockets
    import websockets.exceptions
except ImportError:
    print("Installing websockets…")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "websockets>=12.0"])
    import websockets
    import websockets.exceptions

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VERSION = "2.0.0"
DEFAULT_SERVER = "wss://api.useplutus.ai/api/bridge/ws"
CONFIG_DIR = Path.home() / ".plutus"
CONFIG_FILE = CONFIG_DIR / "bridge_config.json"
LOG_FILE = CONFIG_DIR / "bridge.log"

HEARTBEAT_INTERVAL = 25  # seconds between heartbeats
RECONNECT_DELAY_INIT = 3  # initial reconnect back-off
RECONNECT_DELAY_MAX = 120  # cap at 2 minutes
OUTPUT_LIMIT = 50_000  # max chars for stdout/stderr
AGENT_REPLY_TIMEOUT = 120.0  # max seconds to wait for cloud agent reply

# Module-level logger — configured lazily
log: logging.Logger = logging.getLogger("plutus.bridge")
_logging_configured = False


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def _setup_standalone_logging() -> None:
    """Configure logging for standalone (non-embedded) mode.

    When running embedded inside the Plutus gateway, the gateway's own
    logging config handles everything — we just use ``logging.getLogger``.
    """
    global _logging_configured
    if _logging_configured:
        return
    _logging_configured = True

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    log.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(fmt)
    log.addHandler(ch)
    try:
        fh = logging.handlers.RotatingFileHandler(
            str(LOG_FILE),
            maxBytes=2 * 1024 * 1024,
            backupCount=2,
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except OSError:
        pass  # File logging not available (permissions, etc.)


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------
def extract_server_url(token: str, server_url: str | None = None) -> str:
    """Resolve the cloud server URL from a token or explicit URL.

    Supports two token formats:
    - ``pk_...`` — Cloud-issued API key (requires explicit server_url or default)
    - ``plutus_<base64url(server_url)>.<hex_secret>`` — legacy bridge token
    """
    if token.startswith("pk_"):
        # API key — server URL must be provided or use default
        if server_url:
            return server_url
        # Derive from DEFAULT_SERVER (strip /api/bridge/ws path)
        base = DEFAULT_SERVER.replace("wss://", "https://").replace("ws://", "http://")
        base = base.split("/api/bridge")[0]
        return base
    if not token.startswith("plutus_"):
        raise ValueError(
            "Invalid token format — must start with 'pk_' (API key) or 'plutus_' (legacy)"
        )
    body = token[len("plutus_") :]
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
# Config (standalone mode)
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
    print("  To connect, you need an API key from Plutus Cloud.")
    print("  Go to: app.useplutus.ai → Settings → API Keys")
    print("  Create a key with client type 'Local App' and paste it below.\n")
    config = load_config()
    token = input("  API key (pk_...) or legacy token: ").strip()
    if token:
        config["token"] = token
        if token.startswith("pk_"):
            server = input(
                f"  Cloud server URL [{DEFAULT_SERVER.replace('wss://', 'https://').split('/api/bridge')[0]}]: "
            ).strip()
            if server:
                config["server_url"] = server
            else:
                config["server_url"] = (
                    DEFAULT_SERVER.replace("wss://", "https://")
                    .replace("ws://", "http://")
                    .split("/api/bridge")[0]
                )
            print(f"  → Server: {config['server_url']}")
        else:
            try:
                url = extract_server_url(token)
                config["server_url"] = url
                print(f"  → Server: {url}")
            except Exception:
                print("  ⚠ Could not extract server URL from token.")
    save_config(config)
    print("\n  ✓ Saved. Run `python -m plutus.bridge.bridge` to start.\n")
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
        if tool == "file_pull":
            return _tool_file_pull(args)
        if tool == "open_app":
            return _tool_open_app(args)
        if tool == "ping":
            return {
                "success": True,
                "message": "pong",
                "system": get_system_info(),
            }
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
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        return {
            "success": False,
            "error": f"Command timed out after {timeout}s",
        }
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
        sys.executable,
        "-c",
        code,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        return {
            "success": False,
            "error": f"Python timed out after {timeout}s",
        }
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
        return {
            "success": True,
            "content": content,
            "size": path.stat().st_size,
        }
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
        return {
            "success": True,
            "message": f"Written {len(content)} chars to {path}",
        }
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
                entries.append(
                    {
                        "name": f.name,
                        "path": str(f),
                        "is_dir": f.is_dir(),
                        "size": stat.st_size if f.is_file() else 0,
                    }
                )
            except OSError:
                entries.append({"name": f.name, "path": str(f)})
        return {"success": True, "files": entries, "count": len(entries)}
    except Exception as exc:
        return {"success": False, "error": f"List failed: {exc}"}


def _tool_file_pull(args: dict[str, Any]) -> dict[str, Any]:
    """Read a file as base64 for binary-safe transfer to the cloud."""
    import base64

    raw = args.get("path", "")
    if not raw:
        return {"success": False, "error": "No path provided"}
    path = Path(raw).expanduser()
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
        return {
            "success": False,
            "error": f"Failed to open {app_name}: {exc}",
        }


# ---------------------------------------------------------------------------
# Bridge daemon
# ---------------------------------------------------------------------------
class PlutusBridge:
    """Main bridge daemon — WebSocket connection + heartbeat + tool execution.

    When ``embedded=True`` (running inside the Plutus gateway), the bridge:
    - Skips signal handler installation (gateway manages lifecycle)
    - Uses the gateway's existing logging configuration
    - Exposes ``is_connected`` for the status endpoint to query
    """

    def __init__(
        self,
        server_url: str,
        token: str,
        *,
        embedded: bool = False,
        on_agent_message=None,
    ) -> None:
        self.server_url = server_url
        self.token = token
        self._ws_url = f"{derive_ws_url(server_url)}/{token}"
        self._shutdown = asyncio.Event()
        self._ws = None
        self._embedded = embedded
        self._connected = False  # True only when WS is open and handshake done
        # Callback for incoming agent messages from the cloud.
        # Signature: async def callback(content: str, sender: str, reply_to: str | None, ws)
        self._on_agent_message = on_agent_message
        # Pending futures for local→cloud request-reply pattern.
        # message_id → asyncio.Future that resolves with the cloud agent's reply.
        self._pending_cloud_replies: dict[str, asyncio.Future] = {}

    @property
    def is_connected(self) -> bool:
        """Whether the bridge currently has an active WebSocket connection."""
        return self._connected

    async def run(self) -> None:
        """Start the bridge and block until shutdown."""
        if not self._embedded:
            _setup_standalone_logging()
            self._install_signal_handlers()
        log.info("Plutus Bridge v%s starting…", VERSION)
        log.info("Bridge server: %s", self.server_url)
        log.info("Bridge WS URL: %s…", self._ws_url[:80])
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
                log.info("Bridge connecting to %s …", self.server_url)
                async with websockets.connect(
                    self._ws_url,
                    ping_interval=None,
                    ping_timeout=None,
                    close_timeout=10,
                    max_size=10 * 1024 * 1024,
                    open_timeout=30,
                ) as ws:
                    self._ws = ws
                    log.info("Bridge: ✓ WebSocket connected")
                    delay = RECONNECT_DELAY_INIT

                    # Handshake
                    log.info("Bridge: sending handshake…")
                    await self._send(
                        ws,
                        {
                            "type": "handshake",
                            "system": get_system_info(),
                            "version": VERSION,
                        },
                    )

                    # Mark connected after handshake sent
                    self._connected = True
                    log.info("Bridge: handshake sent, connection active")

                    # Run heartbeat + receiver concurrently
                    hb = asyncio.create_task(self._heartbeat(ws), name="bridge_heartbeat")
                    recv = asyncio.create_task(self._receiver(ws), name="bridge_receiver")
                    shutdown = asyncio.create_task(self._shutdown.wait(), name="bridge_shutdown")

                    done, pending = await asyncio.wait(
                        [hb, recv, shutdown],
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    # Mark disconnected
                    self._connected = False

                    # Log which task(s) completed and why
                    for t in done:
                        name = t.get_name()
                        if t.cancelled():
                            log.warning("Bridge task '%s' was cancelled", name)
                        elif t.exception():
                            log.error(
                                "Bridge task '%s' raised exception: %s\n%s",
                                name,
                                t.exception(),
                                "".join(
                                    traceback.format_exception(
                                        type(t.exception()),
                                        t.exception(),
                                        t.exception().__traceback__,
                                    )
                                ),
                            )
                        else:
                            log.info(
                                "Bridge task '%s' completed normally",
                                name,
                            )

                    for t in pending:
                        t.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)

                    if self._shutdown.is_set():
                        log.info("Bridge: shutdown requested — exiting")
                        return

                    log.warning("Bridge: connection lost — will reconnect")

            except websockets.exceptions.InvalidStatusCode as exc:
                self._connected = False
                log.error(
                    "Bridge: server rejected with HTTP %s — check token. Retrying in %ds",
                    exc.status_code,
                    delay,
                )
            except websockets.exceptions.ConnectionClosed as exc:
                self._connected = False
                log.warning(
                    "Bridge: connection closed: code=%s reason='%s' — retrying in %ds",
                    exc.code,
                    exc.reason,
                    delay,
                )
            except ConnectionRefusedError:
                self._connected = False
                log.warning(
                    "Bridge: connection refused — retrying in %ds",
                    delay,
                )
            except OSError as exc:
                self._connected = False
                log.warning(
                    "Bridge: network error: %s — retrying in %ds",
                    exc,
                    delay,
                )
            except asyncio.CancelledError:
                self._connected = False
                log.info("Bridge: task cancelled — exiting")
                return
            except Exception as exc:
                self._connected = False
                log.error(
                    "Bridge: unexpected error: %s\n%s",
                    exc,
                    traceback.format_exc(),
                )

            if self._shutdown.is_set():
                return
            log.info("Bridge: waiting %ds before reconnecting…", delay)
            await self._sleep(delay)
            delay = min(delay * 2, RECONNECT_DELAY_MAX)

    async def _heartbeat(self, ws) -> None:
        """Send periodic heartbeats to keep the connection alive."""
        hb_count = 0
        while not self._shutdown.is_set():
            await self._sleep(HEARTBEAT_INTERVAL)
            if self._shutdown.is_set():
                return
            try:
                hb_count += 1
                await self._send(ws, {"type": "heartbeat", "ts": time.time()})
                log.debug("Bridge: heartbeat #%d OK", hb_count)
            except websockets.exceptions.ConnectionClosed as exc:
                log.warning(
                    "Bridge: heartbeat #%d failed — closed: code=%s reason='%s'",
                    hb_count,
                    exc.code,
                    exc.reason,
                )
                return
            except Exception as exc:
                log.error(
                    "Bridge: heartbeat #%d failed: %s\n%s",
                    hb_count,
                    exc,
                    traceback.format_exc(),
                )
                return

    async def _receiver(self, ws) -> None:
        """Receive and dispatch messages from the cloud server."""
        msg_count = 0
        try:
            async for raw in ws:
                if self._shutdown.is_set():
                    return
                msg_count += 1
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    log.warning(
                        "Bridge: invalid JSON (msg #%d): %s",
                        msg_count,
                        raw[:200],
                    )
                    continue

                msg_type = data.get("type", "")

                if msg_type == "tool_call":
                    asyncio.create_task(self._handle_tool_call(ws, data))
                elif msg_type == "heartbeat_ack":
                    log.debug("Bridge: heartbeat ACK")
                elif msg_type == "handshake_ack":
                    log.info("Bridge: ✓ handshake acknowledged by server")
                elif msg_type == "agent_message":
                    content = data.get("content", "")
                    sender = data.get("sender", "cloud_agent")
                    reply_to = data.get("reply_to")
                    msg_id = data.get("id")  # unique message ID for request-reply
                    log.info(
                        "Bridge: agent_message from %s (id=%s, reply_to=%s): %s",
                        sender,
                        msg_id[:8] if msg_id else "None",
                        reply_to[:8] if reply_to else "None",
                        content[:80],
                    )

                    # Check if this is a REPLY to a message WE sent to cloud.
                    # If reply_to matches a pending future, resolve it so the
                    # send_to_cloud_and_wait() caller gets the reply as a
                    # return value (tool output), NOT as a new agent message.
                    if reply_to and reply_to in self._pending_cloud_replies:
                        fut = self._pending_cloud_replies.pop(reply_to)
                        if not fut.done():
                            fut.set_result(content)
                            log.info(
                                "Bridge: resolved pending cloud reply for msg_id %s",
                                reply_to[:8],
                            )
                        continue

                    # Otherwise this is a cloud-INITIATED message → dispatch
                    # to the on_agent_message callback (cloud_bridge.py).
                    if self._on_agent_message:
                        asyncio.create_task(
                            self._on_agent_message(content, sender, msg_id or reply_to, ws)
                        )
                    else:
                        log.warning(
                            "Bridge: no on_agent_message handler registered — message dropped"
                        )
                elif msg_type == "cancel_agent_conversations":
                    # Kill switch from cloud — cancel all pending futures
                    count = self.cancel_pending_cloud_replies()
                    log.info(
                        "Bridge: received cancel_agent_conversations from cloud, "
                        "cancelled %d pending futures",
                        count,
                    )
                elif msg_type == "error":
                    log.error(
                        "Bridge: server error: %s",
                        data.get("message", data),
                    )
                else:
                    log.debug("Bridge: unknown msg type: %s", msg_type)

            log.info(
                "Bridge: WebSocket closed normally after %d msgs",
                msg_count,
            )

        except websockets.exceptions.ConnectionClosed as exc:
            log.warning(
                "Bridge: receiver closed after %d msgs: code=%s reason='%s'",
                msg_count,
                exc.code,
                exc.reason,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error(
                "Bridge: receiver error after %d msgs: %s\n%s",
                msg_count,
                exc,
                traceback.format_exc(),
            )

    async def _handle_tool_call(self, ws, data: dict) -> None:
        call_id = data.get("call_id", "unknown")
        tool = data.get("tool", "")
        args = data.get("args", {})
        log.info("Bridge: tool_call %s [%s]", tool, call_id[:8])
        t0 = time.monotonic()

        result = await handle_tool_call(tool, args)

        elapsed = time.monotonic() - t0
        log.info(
            "Bridge: tool %s done in %.1fs — success=%s",
            tool,
            elapsed,
            result.get("success"),
        )
        try:
            await self._send(
                ws,
                {
                    "type": "tool_result",
                    "call_id": call_id,
                    "result": result,
                },
            )
        except Exception as exc:
            log.warning("Bridge: failed to send tool result: %s", exc)

    async def send_to_cloud(
        self,
        content: str,
        sender: str = "local_agent",
        reply_to: str | None = None,
    ) -> bool:
        """Send an agent message to the cloud agent over the bridge WS.

        This is the fire-and-forget version used for REPLIES to cloud-initiated
        messages (where ``reply_to`` is set).  The cloud side resolves its
        pending future when it sees the ``reply_to`` field.

        Returns True if the message was sent successfully.
        """
        if not self._ws or not self._connected:
            log.warning("Bridge: cannot send to cloud — not connected")
            return False
        try:
            payload: dict[str, Any] = {
                "type": "agent_message",
                "content": content,
                "sender": sender,
                "ts": time.time(),
            }
            if reply_to:
                payload["reply_to"] = reply_to
            await self._send(self._ws, payload)
            log.info("Bridge: sent agent_message to cloud (%d chars)", len(content))
            return True
        except Exception as exc:
            log.warning("Bridge: failed to send agent_message: %s", exc)
            return False

    async def send_to_cloud_and_wait(
        self,
        content: str,
        sender: str = "local_agent",
        timeout: float = AGENT_REPLY_TIMEOUT,
    ) -> dict[str, Any]:
        """Send a message to the cloud agent and WAIT for the reply.

        This is the synchronous request-reply pattern used when the LOCAL
        agent initiates a conversation with the cloud agent.  It:
          1. Generates a unique ``message_id``
          2. Registers an ``asyncio.Future`` keyed by ``message_id``
          3. Sends the message over the bridge WS with ``id: message_id``
          4. Awaits the future with a timeout
          5. Returns the cloud agent's reply text

        The local agent sees the reply as a tool/API result — NOT as a new
        incoming agent message — so no loop is possible.
        """
        if not self._ws or not self._connected:
            return {"success": False, "error": "Not connected to cloud"}

        message_id = str(uuid.uuid4())
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()

        # Register BEFORE sending so we never miss an instant reply
        self._pending_cloud_replies[message_id] = fut

        try:
            payload: dict[str, Any] = {
                "type": "agent_message",
                "id": message_id,
                "content": content,
                "sender": sender,
                "ts": time.time(),
            }
            await self._send(self._ws, payload)
            log.info(
                "Bridge: sent agent_message to cloud (msg_id %s, %d chars) — awaiting reply",
                message_id[:8],
                len(content),
            )

            reply_content = await asyncio.wait_for(fut, timeout=timeout)

            return {
                "success": True,
                "reply": reply_content,
                "message_id": message_id,
            }

        except TimeoutError:
            log.warning(
                "Bridge: cloud agent reply timeout for msg_id %s",
                message_id[:8],
            )
            return {
                "success": False,
                "error": (
                    f"The cloud agent did not reply within {int(timeout)}s. "
                    "It may still be processing — try again later."
                ),
            }
        except Exception as exc:
            return {"success": False, "error": f"Failed to send/receive: {exc}"}
        finally:
            self._pending_cloud_replies.pop(message_id, None)

    def cancel_pending_cloud_replies(self) -> int:
        """Cancel all pending cloud reply futures.  Returns the count cancelled."""
        count = 0
        for msg_id, fut in list(self._pending_cloud_replies.items()):
            if not fut.done():
                fut.cancel()
                count += 1
        self._pending_cloud_replies.clear()
        if count:
            log.info("Bridge: cancelled %d pending cloud reply futures", count)
        return count

    @staticmethod
    async def _send(ws, data: dict) -> None:
        await ws.send(json.dumps(data))

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._shutdown.wait(), timeout=seconds)
        except TimeoutError:
            pass


# ---------------------------------------------------------------------------
# CLI (standalone mode)
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plutus Local Bridge — connect your PC to Plutus Cloud",
    )
    parser.add_argument(
        "--api-key",
        help="Plutus Cloud API key (pk_...) from Settings → API Keys",
    )
    parser.add_argument(
        "--token",
        help="Legacy bridge token (plutus_...) — use --api-key instead",
    )
    parser.add_argument(
        "--server",
        help="Cloud server URL (default: https://api.useplutus.ai)",
    )
    parser.add_argument("--setup", action="store_true", help="Interactive setup wizard")
    parser.add_argument("--version", action="version", version=f"v{VERSION}")
    args = parser.parse_args()

    if args.setup:
        run_setup()
        return

    config = load_config()
    token = args.api_key or args.token or config.get("token", "")
    server = args.server or config.get("server_url", "")

    if not token:
        print("Error: No API key or bridge token configured.")
        print("")
        print("  Get an API key from: app.useplutus.ai → Settings → API Keys")
        print("")
        print("  Then run:")
        print("    python -m plutus.bridge.bridge --api-key pk_your_key_here")
        print("    python -m plutus.bridge.bridge --setup")
        sys.exit(1)

    # Save new token/key to config
    if token != config.get("token"):
        config["token"] = token
        save_config(config)

    try:
        server_url = extract_server_url(token, server_url=server or None)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    if server and server != config.get("server_url"):
        config["server_url"] = server
        save_config(config)

    bridge = PlutusBridge(server_url=server_url, token=token)
    try:
        asyncio.run(bridge.run())
    except KeyboardInterrupt:
        log.info("Interrupted — exiting.")


if __name__ == "__main__":
    main()
