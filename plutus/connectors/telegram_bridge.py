"""Telegram ↔ Agent bridge — makes Telegram a full two-way interface to Plutus.

Flow:
  1. User sends message to the Telegram bot
  2. Polling loop in TelegramConnector picks it up
  3. This bridge receives it via the on_message callback
  4. Routes it through the Standard Agent (same as WebSocket chat)
  5. Collects the agent's text response events
  6. Sends the response back to the user via Telegram
  7. Also broadcasts events to WebSocket so the UI stays in sync

The bridge maintains a separate conversation context for Telegram messages
so they don't interfere with the web UI conversation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("plutus.connectors.telegram_bridge")


class TelegramBridge:
    """Routes Telegram messages through the Plutus agent and sends responses back."""

    def __init__(self) -> None:
        self._running = False
        self._processing = False  # Lock to prevent concurrent agent calls
        self._queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the bridge — begins processing incoming Telegram messages."""
        if self._running:
            return

        from plutus.gateway.server import get_state
        state = get_state()
        connector_mgr = state.get("connector_manager")

        if not connector_mgr:
            logger.error("Cannot start Telegram bridge — connector manager not available")
            return

        telegram = connector_mgr.get("telegram")
        if not telegram or not telegram.is_configured:
            logger.warning("Cannot start Telegram bridge — Telegram not configured")
            return

        # Set ourselves as the message handler
        telegram.set_message_handler(self._on_telegram_message)

        # Start the Telegram polling loop
        await telegram.start()

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
        from plutus.gateway.server import get_state
        state = get_state()
        connector_mgr = state.get("connector_manager")
        if connector_mgr:
            telegram = connector_mgr.get("telegram")
            if telegram:
                await telegram.stop()

        logger.info("Telegram bridge stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    async def _on_telegram_message(self, text: str, metadata: dict[str, Any]) -> None:
        """Callback when a Telegram message arrives — queue it for processing."""
        logger.info(f"Telegram message from {metadata.get('from_name', 'unknown')}: {text[:80]}")
        await self._queue.put((text, metadata))

    async def _process_queue(self) -> None:
        """Worker that processes queued Telegram messages one at a time."""
        while self._running:
            try:
                text, metadata = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                self._processing = True
                await self._handle_message(text, metadata)
            except Exception as e:
                logger.exception(f"Error processing Telegram message: {e}")
                # Try to send error back to user
                await self._send_reply(
                    f"Sorry, I encountered an error processing your message: {str(e)}",
                    metadata,
                )
            finally:
                self._processing = False

    async def _handle_message(self, text: str, metadata: dict[str, Any]) -> None:
        """Route a Telegram message through the agent and send the response back."""
        from plutus.gateway.server import get_state
        from plutus.gateway.ws import manager as ws_manager

        state = get_state()
        agent = state.get("agent")

        if not agent:
            await self._send_reply(
                "Plutus agent is not initialized. Please check the web UI.",
                metadata,
            )
            return

        # Send a "typing" indicator
        await self._send_typing(metadata)

        # Broadcast to WebSocket UI so the user can see Telegram messages there too
        await ws_manager.broadcast({
            "type": "text",
            "content": f"📱 **Telegram** ({metadata.get('from_name', 'User')}): {text}",
        })

        # Process through the agent — collect text responses
        response_parts: list[str] = []
        tool_summaries: list[str] = []

        try:
            async for event in agent.process_message(text):
                event_dict = event.to_dict()

                # Also broadcast to WebSocket so UI stays in sync
                await ws_manager.broadcast(event_dict)

                if event.type == "text" and event.data.get("content"):
                    response_parts.append(event.data["content"])

                elif event.type == "tool_call":
                    tool_name = event.data.get("tool", "")
                    # Don't report internal tools
                    if tool_name not in ("plan", "memory"):
                        operation = event.data.get("arguments", {}).get("operation", "")
                        if operation:
                            tool_summaries.append(f"🔧 {tool_name}.{operation}")
                        else:
                            tool_summaries.append(f"🔧 {tool_name}")

                elif event.type == "error":
                    error_msg = event.data.get("message", "Unknown error")
                    response_parts.append(f"⚠️ Error: {error_msg}")

        except Exception as e:
            logger.exception("Agent processing failed for Telegram message")
            response_parts.append(f"⚠️ Processing error: {str(e)}")

        # Build the final response
        final_response = "\n".join(response_parts).strip()

        if not final_response:
            final_response = "✅ Done! (No text response — I performed the requested actions.)"

        # If there were tool calls, add a brief summary
        if tool_summaries and len(tool_summaries) <= 5:
            actions_str = "\n".join(tool_summaries)
            final_response = f"{final_response}\n\n📋 Actions taken:\n{actions_str}"

        # Send the response back via Telegram
        await self._send_reply(final_response, metadata)

    async def _send_reply(self, text: str, metadata: dict[str, Any]) -> None:
        """Send a reply back to the Telegram user."""
        from plutus.gateway.server import get_state

        state = get_state()
        connector_mgr = state.get("connector_manager")
        if not connector_mgr:
            return

        telegram = connector_mgr.get("telegram")
        if not telegram:
            return

        chat_id = metadata.get("chat_id") or telegram._chat_id
        if not chat_id:
            return

        # Try HTML first, fall back to plain text
        result = await telegram.send_message(text, chat_id=chat_id, parse_mode="")
        if not result.get("success"):
            logger.error(f"Failed to send Telegram reply: {result.get('message')}")

    async def _send_typing(self, metadata: dict[str, Any]) -> None:
        """Send a 'typing' indicator to the Telegram chat."""
        from plutus.gateway.server import get_state

        state = get_state()
        connector_mgr = state.get("connector_manager")
        if not connector_mgr:
            return

        telegram = connector_mgr.get("telegram")
        if not telegram:
            return

        chat_id = metadata.get("chat_id") or telegram._chat_id
        if not chat_id:
            return

        try:
            await telegram._api_call("sendChatAction", chat_id=chat_id, action="typing")
        except Exception:
            pass  # Typing indicator is non-critical


# Singleton bridge instance
_bridge: TelegramBridge | None = None


def get_telegram_bridge() -> TelegramBridge:
    """Get or create the singleton Telegram bridge."""
    global _bridge
    if _bridge is None:
        _bridge = TelegramBridge()
    return _bridge
