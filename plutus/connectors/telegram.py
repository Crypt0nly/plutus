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
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Awaitable

import aiohttp

from plutus.connectors.base import BaseConnector

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
        self._session: aiohttp.ClientSession | None = None

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

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _api_call(self, method: str, **params: Any) -> dict[str, Any]:
        """Make a Telegram Bot API call."""
        session = await self._get_session()
        url = f"{self._api_url}/{method}"
        async with session.post(url, json=params) as resp:
            data = await resp.json()
            if not data.get("ok"):
                raise Exception(f"Telegram API error: {data.get('description', 'Unknown error')}")
            return data.get("result", {})

    async def test_connection(self) -> dict[str, Any]:
        """Test the bot token by calling getMe, and try to detect chat_id."""
        if not self._token:
            return {"success": False, "message": "Bot token is required"}

        try:
            # Verify the token
            me = await self._api_call("getMe")
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
            updates = await self._api_call("getUpdates", limit=10, timeout=1)
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
        """Send a message via Telegram."""
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
                result = await self._api_call(
                    "sendMessage",
                    chat_id=target,
                    text=chunk,
                    parse_mode=parse_mode,
                )
                results.append(result)

            return {
                "success": True,
                "message": f"Sent to Telegram ({len(chunks)} message{'s' if len(chunks) > 1 else ''})",
                "message_ids": [r.get("message_id") for r in results],
            }
        except Exception as e:
            # Retry without parse_mode if HTML parsing fails
            if parse_mode == "HTML":
                try:
                    result = await self._api_call(
                        "sendMessage",
                        chat_id=target,
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
            session = await self._get_session()
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

        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("Telegram polling started")

    async def stop(self) -> None:
        """Stop polling."""
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        self._poll_task = None

        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

        logger.info("Telegram polling stopped")

    async def _poll_loop(self) -> None:
        """Long-poll for updates from Telegram."""
        offset = 0
        while self._running:
            try:
                updates = await self._api_call(
                    "getUpdates",
                    offset=offset,
                    timeout=30,
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
                        metadata = {
                            "chat_id": chat.get("id"),
                            "from_user": from_user.get("username", ""),
                            "from_name": (
                                from_user.get("first_name", "") + " " + from_user.get("last_name", "")
                            ).strip(),
                            "message_id": msg.get("message_id"),
                            "source": "telegram",
                        }
                        try:
                            await self._on_message(text, metadata)
                        except Exception as e:
                            logger.error(f"Error handling Telegram message: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Telegram poll error: {e}")
                await asyncio.sleep(5)  # Back off on error


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
