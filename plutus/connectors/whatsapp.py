"""
WhatsApp connector for Plutus (local version).

Uses whatsapp-web.js via a Node.js subprocess bridge.  The bridge handles
the WhatsApp Web protocol, session persistence (LocalAuth), and phone-number
pairing.  Python communicates with the bridge via newline-delimited JSON over
stdin/stdout.

Setup (automatic on first use):
    npm install --prefix <connectors_dir>
This installs whatsapp-web.js + puppeteer (which downloads its own Chromium).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from plutus.connectors.base import BaseConnector

logger = logging.getLogger("plutus.connectors.whatsapp")

# Directory that contains this file — used to resolve the bridge script and
# the npm install location.
_CONNECTOR_DIR = Path(__file__).parent

# Where whatsapp-web.js session data is stored
_SESSION_DIR = _CONNECTOR_DIR / ".wwebjs_auth"

# Pairing code / QR code timeout (seconds)
_PAIRING_TIMEOUT = 300


def _get_node_path() -> str | None:
    """Return the path to the node executable, or None if not found."""
    return shutil.which("node") or shutil.which("node.exe")


def _npm_installed() -> bool:
    """Return True if whatsapp-web.js is already installed."""
    return (_CONNECTOR_DIR / "node_modules" / "whatsapp-web.js").exists()


async def _ensure_npm_installed() -> tuple[bool, str]:
    """
    Run ``npm install`` in the connectors directory if not already done.
    Returns (success, message).
    """
    if _npm_installed():
        return True, "Already installed"

    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        return False, "npm not found. Please install Node.js from https://nodejs.org"

    logger.info("Installing whatsapp-web.js (this may take a few minutes)…")
    try:
        proc = await asyncio.create_subprocess_exec(
            npm,
            "install",
            "--prefix",
            str(_CONNECTOR_DIR),
            "whatsapp-web.js",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        if proc.returncode != 0:
            return False, f"npm install failed: {stderr.decode()[:300]}"
        return True, "Installed successfully"
    except asyncio.TimeoutError:
        return False, "npm install timed out (>5 min)"
    except Exception as exc:
        return False, f"npm install error: {exc}"


class WhatsAppConnector(BaseConnector):
    """WhatsApp connector backed by whatsapp-web.js via a Node.js bridge."""

    name = "whatsapp"
    display_name = "WhatsApp"
    description = "Chat with Plutus via WhatsApp. Requires a dedicated second phone number — Plutus controls that number and you message it from your personal phone."
    icon = "MessageCircle"
    category = "messaging"

    # ── Internal state ────────────────────────────────────────────────────────
    _proc: asyncio.subprocess.Process | None = None
    _ready: bool = False
    _pairing_code: str | None = None
    _qr_string: str | None = None
    _connected_info: dict[str, str]
    _message_queue: asyncio.Queue  # type: ignore[type-arg]
    _reader_task: asyncio.Task | None  # type: ignore[type-arg]
    _message_callback: Any = None  # set by bridge to route incoming messages
    _running: bool = False

    def __init__(self) -> None:
        super().__init__()
        self._connected_info = {}
        self._message_queue = asyncio.Queue()
        self._reader_task = None

    # ── BaseConnector interface ───────────────────────────────────────────────

    def _sensitive_fields(self) -> list[str]:
        return []

    def config_schema(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "phone_number",
                "label": "Plutus Bot Number",
                "type": "text",
                "required": True,
                "placeholder": "+49 176 1234 5678",
                "help": (
                    "The phone number of the dedicated WhatsApp account Plutus will control "
                    "(your second SIM / prepaid number). This is NOT your personal number. "
                    "You will message this number from your personal phone to talk to Plutus. "
                    "Enter it in international format, e.g. +14155552671."
                ),
            },
            {
                "name": "default_contact",
                "label": "Your Personal Number (optional)",
                "type": "text",
                "required": False,
                "placeholder": "e.g. +49 176 9876 5432",
                "help": (
                    "Your own personal WhatsApp number. If set, Plutus can proactively "
                    "send you messages (e.g. alerts or task results) without you messaging first."
                ),
            },
        ]

    async def test_connection(self) -> dict[str, Any]:
        """Check Node.js availability and npm install status."""
        node = _get_node_path()
        if not node:
            return {
                "success": False,
                "message": (
                    "Node.js not found.  Please install Node.js (v18+) from "
                    "https://nodejs.org and restart Plutus."
                ),
            }

        if not self._config.get("phone_number"):
            return {
                "success": False,
                "message": "Please enter your phone number first, then save.",
            }

        if not _npm_installed():
            ok, msg = await _ensure_npm_installed()
            if not ok:
                return {"success": False, "message": msg}

        if self._ready:
            info = self._connected_info
            return {
                "success": True,
                "message": (
                    f"Connected as {info.get('name', 'Unknown')} "
                    f"({info.get('phone', '')})"
                ),
            }

        return {
            "success": True,
            "message": (
                "Node.js and whatsapp-web.js are installed.  "
                "Click 'Start' to connect and receive a pairing code."
            ),
        }

    async def send_message(self, text: str, **kwargs: Any) -> dict[str, Any]:
        """Send a WhatsApp message to a contact."""
        contact = kwargs.get("contact") or self._config.get("default_contact", "")
        if not contact:
            return {"success": False, "message": "Contact phone number is required"}

        if not self._ready or self._proc is None:
            return {"success": False, "message": "WhatsApp is not connected"}

        cmd = json.dumps({"cmd": "send", "to": contact, "text": text}) + "\n"
        try:
            self._proc.stdin.write(cmd.encode())
            await self._proc.stdin.drain()
            # Wait for send_result event (up to 15 s)
            try:
                result = await asyncio.wait_for(
                    self._wait_for_send_result(), timeout=15
                )
                return result
            except asyncio.TimeoutError:
                return {"success": False, "message": "Send timed out"}
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    async def _wait_for_send_result(self) -> dict[str, Any]:
        """Block until a send_result event arrives on the queue."""
        while True:
            evt = await self._message_queue.get()
            if evt.get("event") == "send_result":
                return {
                    "success": evt.get("success", False),
                    "message": evt.get("message", ""),
                }

    async def send_file(
        self,
        file_path: str,
        caption: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a file via WhatsApp (not yet implemented in bridge)."""
        return {
            "success": False,
            "message": "File sending via WhatsApp is not yet supported in this version.",
        }

    def set_message_handler(self, handler: Any) -> None:
        """Register a callback for incoming WhatsApp messages.

        The handler is called with the raw event dict from the bridge:
        ``{event: 'message', from: '...', from_name: '...', text: '...', ...}``
        """
        self._message_callback = handler

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the Node.js bridge process."""
        if self._proc is not None:
            return  # already running

        node = _get_node_path()
        if not node:
            logger.error("Node.js not found — cannot start WhatsApp bridge")
            return

        if not _npm_installed():
            ok, msg = await _ensure_npm_installed()
            if not ok:
                logger.error("npm install failed: %s", msg)
                return

        bridge_script = str(_CONNECTOR_DIR / "whatsapp_bridge.js")
        phone = (
            self._config.get("phone_number", "")
            .replace("+", "")
            .replace(" ", "")
            .replace("-", "")
        )

        env = {**os.environ}
        env["WA_SESSION_DIR"] = str(_SESSION_DIR)
        if phone:
            env["WA_PHONE_NUMBER"] = phone

        # Optionally use a pre-existing Chromium (puppeteer / Playwright)
        chromium = _find_chromium()
        if chromium:
            env["WA_CHROMIUM_PATH"] = chromium

        logger.info("Starting WhatsApp bridge: %s %s", node, bridge_script)
        self._proc = await asyncio.create_subprocess_exec(
            node,
            bridge_script,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._ready = False
        self._pairing_code = None
        self._qr_string = None
        self._running = True

        self._reader_task = asyncio.create_task(self._read_bridge_output())
        asyncio.create_task(self._read_bridge_stderr())

    async def stop(self) -> None:
        """Stop the Node.js bridge process."""
        self._running = False
        self._ready = False
        if self._proc is not None:
            try:
                cmd = json.dumps({"cmd": "stop"}) + "\n"
                self._proc.stdin.write(cmd.encode())
                await self._proc.stdin.drain()
                await asyncio.wait_for(self._proc.wait(), timeout=10)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
        if self._reader_task is not None:
            self._reader_task.cancel()
            self._reader_task = None

    # ── Bridge I/O ────────────────────────────────────────────────────────────

    async def _read_bridge_output(self) -> None:
        """Read and dispatch JSON events from the bridge stdout."""
        assert self._proc is not None
        try:
            async for line in self._proc.stdout:
                raw = line.decode().strip()
                if not raw:
                    continue
                try:
                    evt = json.loads(raw)
                except json.JSONDecodeError:
                    logger.debug("Bridge non-JSON: %s", raw)
                    continue
                await self._handle_bridge_event(evt)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("Bridge reader error: %s", exc)

    async def _read_bridge_stderr(self) -> None:
        """Log bridge stderr for debugging."""
        assert self._proc is not None
        try:
            async for line in self._proc.stderr:
                raw = line.decode().strip()
                if raw:
                    logger.debug("WhatsApp bridge stderr: %s", raw)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def _handle_bridge_event(self, evt: dict[str, Any]) -> None:
        """Dispatch a bridge event."""
        event_type = evt.get("event")

        if event_type == "ready":
            self._ready = True
            self._pairing_code = None
            self._qr_string = None
            self._connected_info = evt.get("info", {})
            logger.info(
                "WhatsApp ready: %s (%s)",
                self._connected_info.get("name"),
                self._connected_info.get("phone"),
            )
            # Broadcast ready event so the UI clears the pairing code banner
            await self._broadcast_ready()

        elif event_type == "pairing_code":
            self._pairing_code = evt.get("code", "")
            logger.info("WhatsApp pairing code: %s", self._pairing_code)
            await self._broadcast_pairing_code(self._pairing_code)

        elif event_type == "qr":
            self._qr_string = evt.get("qr", "")
            logger.info("WhatsApp QR code received (use phone-number pairing instead)")

        elif event_type == "disconnected":
            self._ready = False
            logger.warning("WhatsApp disconnected: %s", evt.get("reason"))

        elif event_type == "message":
            if self._message_callback is not None:
                try:
                    await self._message_callback(evt)
                except Exception as exc:
                    logger.error("Message callback error: %s", exc)
            else:
                logger.info(
                    "WhatsApp message from %s: %s",
                    evt.get("from_name") or evt.get("from"),
                    evt.get("text", "")[:80],
                )

        elif event_type in ("send_result", "status"):
            await self._message_queue.put(evt)

        elif event_type == "error":
            logger.error("WhatsApp bridge error: %s", evt.get("message"))

    async def _broadcast_pairing_code(self, code: str) -> None:
        """Broadcast the pairing code to all connected WebSocket clients."""
        try:
            from plutus.gateway.server import get_server  # type: ignore[import]

            server = get_server()
            if server is not None:
                await server.broadcast(
                    {
                        "type": "whatsapp_pairing_code",
                        "code": code,
                    }
                )
        except Exception as exc:
            logger.debug("Could not broadcast pairing code: %s", exc)

    async def _broadcast_ready(self) -> None:
        """Broadcast a whatsapp_ready event to all connected WebSocket clients."""
        try:
            from plutus.gateway.server import get_server  # type: ignore[import]
            server = get_server()
            if server is not None:
                await server.broadcast(
                    {
                        "type": "whatsapp_ready",
                        "info": self._connected_info,
                    }
                )
        except Exception as exc:
            logger.debug("Could not broadcast whatsapp_ready: %s", exc)

    # ── Status ─────────────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        base = super().status()
        base["whatsapp_ready"] = self._ready
        base["whatsapp_pairing_code"] = self._pairing_code
        base["whatsapp_connected_info"] = self._connected_info
        return base


def _find_chromium() -> str | None:
    """
    Try to find a bundled Chromium executable (puppeteer or Playwright).
    Returns None if not found — puppeteer will download its own.
    """
    import glob

    home = str(Path.home())
    candidates = [
        # puppeteer's own download (Linux / CI)
        f"{home}/.cache/puppeteer/chrome/*/chrome-linux64/chrome",
        # puppeteer (macOS)
        (
            f"{home}/.cache/puppeteer/chrome/*/chrome-mac-x64/"
            "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
        ),
        # Playwright (Linux)
        f"{home}/.cache/ms-playwright/chromium-*/chrome-linux/chrome",
        # Playwright (macOS)
        (
            f"{home}/.cache/ms-playwright/chromium-*/"
            "chrome-mac/Chromium.app/Contents/MacOS/Chromium"
        ),
    ]
    for pattern in candidates:
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[-1]  # newest version
    return None
