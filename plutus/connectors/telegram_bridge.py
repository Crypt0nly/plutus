"""Telegram ↔ Agent bridge — makes Telegram a full two-way interface to Plutus.

Flow:
  1. User sends message to the Telegram bot
  2. Polling loop in TelegramConnector picks it up
  3. This bridge receives it via the on_message callback
  4. Sends an immediate "thinking..." indicator to Telegram
  5. Routes it through the dedicated Telegram session agent
     (session_id = "session_telegram") — completely isolated from the
     main UI chat so messages never bleed into the user's chat view.
  6. Collects the agent's text response events
  7. Sends the response back to the user via Telegram
  8. Also broadcasts events to WebSocket tagged with session_id="session_telegram"
     so the Sessions panel in the UI stays in sync.
  9. Screenshots and files generated during processing are sent as photos/docs

The bridge processes messages sequentially via a queue to prevent
concurrent agent calls from interfering with each other.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger("plutus.connectors.telegram_bridge")

# The session_id used for all Telegram traffic — must match the value in
# session_registry.CONNECTOR_SESSIONS.
_TELEGRAM_SESSION_ID = "session_telegram"


class TelegramBridge:
    """Routes Telegram messages through the Plutus agent and sends responses back."""

    def __init__(self) -> None:
        self._running = False
        self._processing = False
        self._queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the bridge — begins processing incoming Telegram messages."""
        if self._running:
            logger.info("Telegram bridge already running")
            return

        telegram = self._get_telegram()
        if not telegram:
            logger.error(
                "Cannot start Telegram bridge — "
                "Telegram connector not available or not configured"
            )
            return

        # Set ourselves as the message handler BEFORE starting polling
        telegram.set_message_handler(self._on_telegram_message)
        logger.info("Message handler registered")

        # Start the Telegram polling loop
        await telegram.start()
        logger.info("Telegram polling started")

        # Start our message processing worker
        self._running = True
        self._worker_task = asyncio.create_task(self._process_queue())
        logger.info("Telegram bridge started — two-way messaging active")

    async def stop(self) -> None:
        """Stop the bridge."""
        self._running = False

        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        self._worker_task = None

        # Stop the Telegram polling
        telegram = self._get_telegram()
        if telegram:
            await telegram.stop()

        logger.info("Telegram bridge stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def _get_telegram(self):
        """Get the Telegram connector from the server state."""
        try:
            from plutus.gateway.server import get_state
            state = get_state()
            connector_mgr = state.get("connector_manager")
            if not connector_mgr:
                return None
            telegram = connector_mgr.get("telegram")
            if not telegram or not telegram.is_configured:
                return None
            return telegram
        except Exception as e:
            logger.error(f"Failed to get Telegram connector: {e}")
            return None

    def _get_agent(self):
        """Get the dedicated Telegram session agent from the session registry.

        Falls back to the global main agent if the session registry is not
        available (e.g. during early startup).
        """
        try:
            from plutus.core.session_registry import get_registry
            registry = get_registry()
            session = registry.get(_TELEGRAM_SESSION_ID)
            if session:
                return session.agent, session.lock
        except Exception as e:
            logger.warning(f"Session registry not available: {e}")

        # Fallback — use the global agent (no dedicated lock)
        try:
            from plutus.gateway.server import get_state, _agent_lock
            state = get_state()
            return state.get("agent"), _agent_lock
        except Exception as e:
            logger.error(f"Failed to get fallback agent: {e}")
            return None, None

    async def _broadcast(self, payload: dict[str, Any]) -> None:
        """Broadcast a WebSocket event tagged with the Telegram session_id."""
        try:
            from plutus.gateway.ws import manager as ws_manager
            await ws_manager.broadcast_to_session(_TELEGRAM_SESSION_ID, payload)
        except Exception as e:
            logger.debug(f"Could not broadcast to WebSocket: {e}")

    async def _on_telegram_message(self, text: str, metadata: dict[str, Any]) -> None:
        """Callback when a Telegram message arrives — queue it for processing."""
        logger.info(
            f"Queuing Telegram message from "
            f"{metadata.get('from_name', 'unknown')}: {text[:80]}"
        )
        await self._queue.put((text, metadata))

    async def _process_queue(self) -> None:
        """Worker that processes queued Telegram messages one at a time."""
        logger.info("Queue processor started")
        while self._running:
            try:
                text, metadata = await asyncio.wait_for(
                    self._queue.get(), timeout=2.0
                )
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            logger.info(f"Processing queued message: {text[:80]}")
            try:
                self._processing = True
                await self._handle_message(text, metadata)
            except Exception as e:
                logger.exception(f"Error processing Telegram message: {e}")
                await self._send_reply(
                    f"⚠️ Sorry, I encountered an error:\n{str(e)[:500]}",
                    metadata,
                )
            finally:
                self._processing = False

    async def _handle_message(self, text: str, metadata: dict[str, Any]) -> None:
        """Route a Telegram message through the agent and send the response back."""
        agent, agent_lock = self._get_agent()
        telegram = self._get_telegram()

        if not agent:
            logger.error("Agent not available for Telegram message processing")
            await self._send_reply(
                "⚠️ Plutus agent is not initialized. "
                "Please check the web UI and ensure an API key is configured.",
                metadata,
            )
            return

        if not telegram:
            logger.error("Telegram connector not available")
            return

        chat_id = metadata.get("chat_id")

        # Send typing indicator immediately
        await telegram.send_typing(chat_id=chat_id)

        # Broadcast the incoming Telegram message to the Sessions panel in the UI
        # (tagged with session_id so it only appears in the Telegram session view)
        await self._broadcast({
            "type": "text",
            "content": (
                f"📱 **{metadata.get('from_name', 'User')}**: {text}"
            ),
            "role": "user",
        })
        await self._broadcast({"type": "thinking"})

        # Process through the dedicated Telegram session agent
        response_parts: list[str] = []
        tool_summaries: list[str] = []
        screenshots_sent = 0

        try:
            logger.info("Sending message to Telegram session agent...")
            lock_ctx = agent_lock if agent_lock else _NullLock()
            async with lock_ctx:
                async for event in agent.process_message(text):
                    # Broadcast every event to the Sessions panel (with session_id)
                    await self._broadcast(event.to_dict())

                    if event.type == "text" and event.data.get("content"):
                        content = event.data["content"]
                        response_parts.append(content)
                        logger.debug(f"Agent text: {content[:100]}")

                    elif event.type == "tool_call":
                        tool_name = event.data.get("tool", "")
                        if tool_name not in ("plan", "memory"):
                            operation = (
                                event.data.get("arguments", {}).get("operation", "")
                            )
                            summary = (
                                f"🔧 {tool_name}.{operation}"
                                if operation
                                else f"🔧 {tool_name}"
                            )
                            tool_summaries.append(summary)
                            logger.debug(f"Agent tool call: {summary}")

                            # Refresh typing indicator for long operations
                            await telegram.send_typing(chat_id=chat_id)

                    elif event.type == "tool_result":
                        # Forward screenshots to Telegram as photos
                        if event.data.get("screenshot") and event.data.get("image_base64"):
                            sent = await self._send_screenshot(
                                event.data["image_base64"], chat_id, telegram
                            )
                            if sent:
                                screenshots_sent += 1

                    elif event.type == "error":
                        error_msg = event.data.get("message", "Unknown error")
                        response_parts.append(f"⚠️ {error_msg}")
                        logger.warning(f"Agent error event: {error_msg}")

                    elif event.type == "done":
                        logger.info("Agent processing complete")

        except Exception as e:
            logger.exception("Agent processing failed for Telegram message")
            response_parts.append(f"⚠️ Processing error: {str(e)[:300]}")
            await self._broadcast({"type": "error", "message": str(e)[:300]})

        await self._broadcast({"type": "done"})

        # Build the final response
        final_response = "\n".join(response_parts).strip()

        if not final_response:
            if tool_summaries or screenshots_sent:
                final_response = "✅ Done!"
            else:
                final_response = (
                    "I received your message but had no response to give. "
                    "Could you try rephrasing?"
                )

        # Append tool call summary if there were any (max 8)
        if tool_summaries:
            shown = tool_summaries[:8]
            actions_str = "\n".join(shown)
            if len(tool_summaries) > 8:
                actions_str += f"\n... and {len(tool_summaries) - 8} more"
            final_response = (
                f"{final_response}\n\n📋 Actions:\n{actions_str}"
            )

        logger.info(f"Sending reply to Telegram ({len(final_response)} chars)")

        # Send the response back via Telegram
        await self._send_reply(final_response, metadata)

    async def _send_reply(self, text: str, metadata: dict[str, Any]) -> None:
        """Send a reply back to the Telegram user."""
        telegram = self._get_telegram()
        if not telegram:
            logger.error("Cannot send reply — Telegram connector not available")
            return

        chat_id = metadata.get("chat_id") or telegram._chat_id
        if not chat_id:
            logger.error("Cannot send reply — no chat_id")
            return

        # Send as plain text (no parse_mode) to avoid HTML/Markdown parsing issues
        result = await telegram.send_message(text, chat_id=chat_id, parse_mode="")
        if result.get("success"):
            logger.info(
                f"Reply sent to Telegram (msg_ids={result.get('message_ids')})"
            )
        else:
            logger.error(
                f"Failed to send Telegram reply: {result.get('message')}"
            )

    async def _send_screenshot(
        self,
        image_base64: str,
        chat_id: str | int | None,
        telegram: Any,
    ) -> bool:
        """Decode a base64 screenshot and send it as a photo to Telegram."""
        try:
            img_bytes = base64.b64decode(image_base64)

            # Write to a temp file so send_photo can read it
            with tempfile.NamedTemporaryFile(
                suffix=".png", delete=False
            ) as tmp:
                tmp.write(img_bytes)
                tmp_path = tmp.name

            try:
                result = await telegram.send_photo(
                    tmp_path, caption="📸 Screenshot", chat_id=chat_id
                )
                if result.get("success"):
                    logger.info("Screenshot sent to Telegram")
                    return True
                else:
                    logger.warning(
                        f"Failed to send screenshot to Telegram: "
                        f"{result.get('message')}"
                    )
                    return False
            finally:
                # Clean up temp file
                Path(tmp_path).unlink(missing_ok=True)

        except Exception as e:
            logger.error(f"Failed to send screenshot to Telegram: {e}")
            return False


class _NullLock:
    """A no-op async context manager used when no lock is needed."""
    async def __aenter__(self):
        return self
    async def __aexit__(self, *_):
        pass


# Singleton bridge instance
_bridge: TelegramBridge | None = None


def get_telegram_bridge() -> TelegramBridge:
    """Get or create the singleton Telegram bridge."""
    global _bridge
    if _bridge is None:
        _bridge = TelegramBridge()
    return _bridge
