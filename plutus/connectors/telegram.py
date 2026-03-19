"""Telegram connector for Plutus.

Uses the Telegram Bot API to:
  - Send messages to the user (notifications, skill results, summaries)
  - Receive messages from the user (forward to Plutus agent for processing)
  - Auto-detect chat_id on first message to the bot

Setup:
  1. Create a bot via @BotFather on Telegram
  2. Enter the bot token in the Plutus Connectors tab
  3. Send any message to the bot — Plutus auto-detects your chat_id
  4. Done! Plutus can now send you messages via Telegram

Architecture:
  - Uses TWO separate aiohttp sessions to prevent any contention:
    * _poll_session  — dedicated to the long-polling getUpdates loop
    * _send_session  — dedicated to sendMessage, sendChatAction, etc.
  - The poll loop uses a short timeout (5s) for responsiveness
  - Messages are delivered via the _on_message callback (set by TelegramBridge)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from plutus.connectors.base import BaseConnector
from plutus.utils.ssl_utils import make_aiohttp_connector

logger = logging.getLogger("plutus.connectors.telegram")

TELEGRAM_API = "https://api.telegram.org/bot{token}"


class TelegramConnector(BaseConnector):
    name = "telegram"
    display_name = "Telegram"
    description = "Send and receive messages via a Telegram bot"
    icon = "Send"  # Lucide icon

    def __init__(self):
        super().__init__()
        self._poll_task: asyncio.Task | None = None
        self._on_message: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None
        # Separate sessions for polling vs sending to prevent contention
        self._poll_session: aiohttp.ClientSession | None = None
        self._send_session: aiohttp.ClientSession | None = None

    def _sensitive_fields(self) -> list[str]:
        return ["bot_token"]

    def config_schema(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "bot_token",
                "label": "Bot Token",
                "type": "password",
                "required": True,
                "placeholder": "123456789:AAG...",
                "help": "Get this from @BotFather on Telegram",
            },
            {
                "name": "chat_id",
                "label": "Chat ID",
                "type": "text",
                "required": False,
                "placeholder": "Auto-detected when you message the bot",
                "help": "Leave empty — send any message to your bot and Plutus will detect it automatically",
            },
            {
                "name": "bot_username",
                "label": "Bot Username",
                "type": "text",
                "required": False,
                "placeholder": "Auto-detected",
                "help": "Filled automatically after testing connection",
            },
        ]

    @property
    def _token(self) -> str:
        return self._config.get("bot_token", "")

    @property
    def _chat_id(self) -> str | int:
        return self._config.get("chat_id", "")

    @property
    def _api_url(self) -> str:
        return TELEGRAM_API.format(token=self._token)

    async def _get_send_session(self) -> aiohttp.ClientSession:
        """Get or create the session used for sending messages."""
        if self._send_session is None or self._send_session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            # Use certifi CA bundle so macOS Python can verify Telegram's TLS cert.
            self._send_session = aiohttp.ClientSession(
                connector=make_aiohttp_connector(),
                timeout=timeout,
            )
        return self._send_session

    async def _get_poll_session(self) -> aiohttp.ClientSession:
        """Get or create the session used for long-polling getUpdates."""
        if self._poll_session is None or self._poll_session.closed:
            # Poll session needs a longer timeout since getUpdates blocks.
            # Use certifi CA bundle so macOS Python can verify Telegram's TLS cert.
            timeout = aiohttp.ClientTimeout(total=60)
            self._poll_session = aiohttp.ClientSession(
                connector=make_aiohttp_connector(),
                timeout=timeout,
            )
        return self._poll_session

    async def _send_api_call(self, method: str, **params: Any) -> dict[str, Any]:
        """Make a Telegram Bot API call using the SEND session (non-blocking)."""
        session = await self._get_send_session()
        url = f"{self._api_url}/{method}"
        try:
            async with session.post(url, json=params) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    desc = data.get("description", "Unknown error")
                    logger.error(f"Telegram API error ({method}): {desc}")
                    raise Exception(f"Telegram API error: {desc}")
                return data.get("result", {})
        except aiohttp.ClientError as e:
            logger.error(f"Telegram HTTP error ({method}): {e}")
            raise

    async def _poll_api_call(self, method: str, **params: Any) -> dict[str, Any]:
        """Make a Telegram Bot API call using the POLL session (for getUpdates)."""
        session = await self._get_poll_session()
        url = f"{self._api_url}/{method}"
        try:
            async with session.post(url, json=params) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    desc = data.get("description", "Unknown error")
                    logger.error(f"Telegram API error ({method}): {desc}")
                    raise Exception(f"Telegram API error: {desc}")
                return data.get("result", {})
        except aiohttp.ClientError as e:
            logger.error(f"Telegram HTTP error ({method}): {e}")
            raise

    async def test_connection(self) -> dict[str, Any]:
        """Test the bot token by calling getMe, and try to detect chat_id."""
        if not self._token:
            return {"success": False, "message": "Bot token is required"}

        try:
            # Verify the token
            me = await self._send_api_call("getMe")
            bot_username = me.get("username", "")
            bot_name = me.get("first_name", "")

            # Save bot info
            self._config["bot_username"] = f"@{bot_username}"
            self._config["bot_name"] = bot_name
            self._config_store.save(self._config)

            # Try to detect chat_id from recent messages
            chat_id = self._chat_id
            if not chat_id:
                chat_id = await self._detect_chat_id()

            result: dict[str, Any] = {
                "success": True,
                "message": f"Connected to bot {bot_name} (@{bot_username})",
                "bot_username": f"@{bot_username}",
                "bot_name": bot_name,
            }

            if chat_id:
                result["chat_id"] = str(chat_id)
                result["message"] += f" — Chat ID: {chat_id}"
            else:
                result["message"] += (
                    f" — Now send any message to @{bot_username} on Telegram, "
                    "then click Test again to detect your Chat ID"
                )
                result["needs_chat_id"] = True

            return result

        except Exception as e:
            return {"success": False, "message": f"Connection failed: {str(e)}"}

    async def _detect_chat_id(self) -> str | int:
        """Try to detect the user's chat_id from recent updates."""
        try:
            updates = await self._send_api_call("getUpdates", limit=10, timeout=1)
            if updates:
                # Get the most recent message's chat_id
                for update in reversed(updates):
                    msg = update.get("message", {})
                    chat = msg.get("chat", {})
                    chat_id = chat.get("id")
                    if chat_id:
                        # Save it
                        self._config["chat_id"] = str(chat_id)
                        self._config["chat_name"] = (
                            chat.get("first_name", "") + " " + chat.get("last_name", "")
                        ).strip()
                        self._config_store.save(self._config)
                        logger.info(f"Auto-detected Telegram chat_id: {chat_id}")
                        return chat_id
        except Exception as e:
            logger.debug(f"Could not detect chat_id: {e}")
        return ""

    async def send_message(
        self,
        text: str,
        chat_id: str | int | None = None,
        parse_mode: str = "HTML",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a message via Telegram (uses the send session, never blocked by polling)."""
        target = chat_id or self._chat_id
        if not target:
            return {"success": False, "message": "No chat_id configured — send a message to the bot first"}

        if not self._token:
            return {"success": False, "message": "Bot token not configured"}

        try:
            # Telegram has a 4096 char limit — split long messages
            chunks = _split_message(text, 4000)
            results = []
            for chunk in chunks:
                result = await self._send_api_call(
                    "sendMessage",
                    chat_id=int(target) if str(target).lstrip("-").isdigit() else target,
                    text=chunk,
                    parse_mode=parse_mode,
                )
                results.append(result)
                logger.info(f"Sent Telegram message to {target} (msg_id={result.get('message_id')})")

            return {
                "success": True,
                "message": f"Sent to Telegram ({len(chunks)} message{'s' if len(chunks) > 1 else ''})",
                "message_ids": [r.get("message_id") for r in results],
            }
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            # Retry without parse_mode if HTML parsing fails
            if parse_mode == "HTML":
                try:
                    result = await self._send_api_call(
                        "sendMessage",
                        chat_id=int(target) if str(target).lstrip("-").isdigit() else target,
                        text=text[:4000],
                    )
                    return {
                        "success": True,
                        "message": "Sent to Telegram (plain text fallback)",
                        "message_ids": [result.get("message_id")],
                    }
                except Exception:
                    pass
            return {"success": False, "message": f"Failed to send: {str(e)}"}

    async def send_typing(self, chat_id: str | int | None = None) -> None:
        """Send a 'typing' indicator (non-critical, errors are swallowed)."""
        target = chat_id or self._chat_id
        if not target:
            return
        try:
            await self._send_api_call(
                "sendChatAction",
                chat_id=int(target) if str(target).lstrip("-").isdigit() else target,
                action="typing",
            )
        except Exception:
            pass

    async def send_photo(
        self,
        file_path: str,
        caption: str = "",
        chat_id: str | int | None = None,
    ) -> dict[str, Any]:
        """Send a photo via Telegram (displayed inline, not as a file attachment)."""
        import os
        target = chat_id or self._chat_id
        if not target:
            return {"success": False, "message": "No chat_id configured"}

        try:
            session = await self._get_send_session()
            url = f"{self._api_url}/sendPhoto"

            data = aiohttp.FormData()
            data.add_field("chat_id", str(target))
            if caption:
                data.add_field("caption", caption[:1024])
            data.add_field(
                "photo",
                open(file_path, "rb"),
                filename=os.path.basename(file_path),
            )

            async with session.post(url, data=data) as resp:
                result = await resp.json()
                if result.get("ok"):
                    return {"success": True, "message": "Photo sent via Telegram"}
                else:
                    desc = result.get("description", "Failed")
                    logger.warning(f"sendPhoto failed: {desc}, falling back to sendDocument")
                    return await self.send_document(file_path, caption, chat_id)

        except Exception as e:
            return {"success": False, "message": f"Failed to send photo: {str(e)}"}

    async def send_document(
        self,
        file_path: str,
        caption: str = "",
        chat_id: str | int | None = None,
    ) -> dict[str, Any]:
        """Send a file via Telegram."""
        import os
        target = chat_id or self._chat_id
        if not target:
            return {"success": False, "message": "No chat_id configured"}

        try:
            session = await self._get_send_session()
            url = f"{self._api_url}/sendDocument"

            data = aiohttp.FormData()
            data.add_field("chat_id", str(target))
            if caption:
                data.add_field("caption", caption[:1024])
            data.add_field(
                "document",
                open(file_path, "rb"),
                filename=os.path.basename(file_path),
            )

            async with session.post(url, data=data) as resp:
                result = await resp.json()
                if result.get("ok"):
                    return {"success": True, "message": "File sent via Telegram"}
                else:
                    return {"success": False, "message": result.get("description", "Failed")}

        except Exception as e:
            return {"success": False, "message": f"Failed to send file: {str(e)}"}

    # ── Polling for incoming messages ──────────────────────────

    def set_message_handler(self, handler: Callable[[str, dict[str, Any]], Awaitable[None]]) -> None:
        """Set the callback for incoming messages.

        handler(text, metadata) where metadata includes chat_id, from_user, etc.
        """
        self._on_message = handler

    async def start(self) -> None:
        """Start polling for incoming Telegram messages."""
        if self._running:
            return
        self._running = True

        if not self._token:
            logger.warning("Cannot start Telegram polling — no bot token")
            self._running = False
            return

        # Clear any pending updates so we only get NEW messages
        try:
            await self._send_api_call("getUpdates", offset=-1, timeout=1)
            logger.info("Cleared pending Telegram updates")
        except Exception as e:
            logger.debug(f"Could not clear pending updates: {e}")

        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("Telegram polling started")

    async def stop(self) -> None:
        """Stop polling and close sessions."""
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        self._poll_task = None

        # Close both sessions
        for session in (self._poll_session, self._send_session):
            if session and not session.closed:
                await session.close()
        self._poll_session = None
        self._send_session = None

        logger.info("Telegram polling stopped")

    async def _poll_loop(self) -> None:
        """Long-poll for updates from Telegram.

        Uses a dedicated poll session and short timeout (5s) for responsiveness.
        The short timeout means we check self._running every 5 seconds.
        """
        offset = 0

        # Get the latest update_id so we skip old messages
        try:
            updates = await self._poll_api_call("getUpdates", offset=-1, timeout=1)
            if updates:
                offset = updates[-1]["update_id"] + 1
                logger.info(f"Starting poll from offset {offset}")
        except Exception as e:
            logger.debug(f"Could not get initial offset: {e}")

        while self._running:
            try:
                updates = await self._poll_api_call(
                    "getUpdates",
                    offset=offset,
                    timeout=5,  # Short timeout for responsiveness
                    allowed_updates=["message"],
                )

                for update in updates:
                    offset = update["update_id"] + 1
                    msg = update.get("message", {})
                    text = msg.get("text", "")
                    chat = msg.get("chat", {})
                    from_user = msg.get("from", {})

                    # Auto-save chat_id if not set
                    if not self._chat_id and chat.get("id"):
                        self._config["chat_id"] = str(chat["id"])
                        self._config["chat_name"] = (
                            chat.get("first_name", "") + " " + chat.get("last_name", "")
                        ).strip()
                        self._config_store.save(self._config)
                        logger.info(f"Auto-detected chat_id: {chat['id']}")

                    if text and self._on_message:
                        from_name = (
                            from_user.get("first_name", "") + " " + from_user.get("last_name", "")
                        ).strip()
                        logger.info(f"Received Telegram message from {from_name}: {text[:80]}")

                        metadata = {
                            "chat_id": chat.get("id"),
                            "from_user": from_user.get("username", ""),
                            "from_name": from_name,
                            "message_id": msg.get("message_id"),
                            "source": "telegram",
                        }
                        try:
                            await self._on_message(text, metadata)
                        except Exception as e:
                            logger.exception(f"Error in message handler: {e}")
                            # Try to send error back to user
                            try:
                                await self.send_message(
                                    f"⚠️ Error processing your message: {str(e)[:200]}",
                                    chat_id=chat.get("id"),
                                    parse_mode="",
                                )
                            except Exception:
                                pass
                    elif not text and msg:
                        # Non-text message (photo, sticker, etc.)
                        logger.debug(f"Ignoring non-text Telegram message: {list(msg.keys())}")

            except asyncio.CancelledError:
                break
            except aiohttp.ClientError as e:
                logger.error(f"Telegram poll HTTP error: {e}")
                await asyncio.sleep(3)
            except Exception as e:
                logger.error(f"Telegram poll error: {e}")
                await asyncio.sleep(3)


def _split_message(text: str, max_len: int = 4000) -> list[str]:
    """Split a long message into chunks that fit Telegram's limit."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Try to split at a newline
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks
