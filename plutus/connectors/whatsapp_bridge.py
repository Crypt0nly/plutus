"""WhatsApp ↔ Agent bridge — makes WhatsApp a full two-way interface to Plutus.

Flow:
  1. User sends a WhatsApp message to the linked phone number
  2. whatsapp-web.js picks it up and emits a "message" event via stdout JSON
  3. The WhatsAppConnector receives it and calls the registered message callback
  4. This bridge receives it via the callback
  5. Routes it through the dedicated WhatsApp session agent
     (session_id = "session_whatsapp") — completely isolated from the
     main UI chat so messages never bleed into the user's chat view.
  6. Collects the agent's text response events
  7. Sends the response back to the user via WhatsApp
  8. Also broadcasts events to WebSocket tagged with session_id="session_whatsapp"
     so the Sessions panel in the UI stays in sync.

The bridge processes messages sequentially via a queue to prevent
concurrent agent calls from interfering with each other.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("plutus.connectors.whatsapp_bridge")

# The session_id used for all WhatsApp traffic — must match the value in
# session_registry.CONNECTOR_SESSIONS.
_WHATSAPP_SESSION_ID = "session_whatsapp"


class WhatsAppBridge:
    """Routes WhatsApp messages through the Plutus agent and sends responses back."""

    def __init__(self) -> None:
        self._running = False
        self._processing = False
        self._queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the bridge — begins processing incoming WhatsApp messages."""
        if self._running:
            logger.info("WhatsApp bridge already running")
            return

        whatsapp = self._get_whatsapp()
        if not whatsapp:
            logger.error(
                "Cannot start WhatsApp bridge — "
                "WhatsApp connector not available or not configured"
            )
            return

        # Set ourselves as the message handler BEFORE starting the connector
        whatsapp.set_message_handler(self._on_whatsapp_message)
        logger.info("Message handler registered")

        # Start the WhatsApp connector (launches the Node.js bridge)
        await whatsapp.start()
        logger.info("WhatsApp connector started")

        # Start our message processing worker
        self._running = True
        self._worker_task = asyncio.create_task(self._process_queue())
        logger.info("WhatsApp bridge started — two-way messaging active")

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

        # Stop the WhatsApp connector
        whatsapp = self._get_whatsapp()
        if whatsapp:
            await whatsapp.stop()
        logger.info("WhatsApp bridge stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def _get_whatsapp(self):
        """Get the WhatsApp connector from the server state."""
        try:
            from plutus.gateway.server import get_state
            state = get_state()
            connector_mgr = state.get("connector_manager")
            if not connector_mgr:
                return None
            whatsapp = connector_mgr.get("whatsapp")
            if not whatsapp or not whatsapp.is_configured:
                return None
            return whatsapp
        except Exception as e:
            logger.error(f"Failed to get WhatsApp connector: {e}")
            return None

    def _get_agent(self):
        """Get the dedicated WhatsApp session agent from the session registry.

        Falls back to the global main agent if the session registry is not
        available (e.g. during early startup).
        """
        try:
            from plutus.core.session_registry import get_registry
            registry = get_registry()
            session = registry.get(_WHATSAPP_SESSION_ID)
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
        """Broadcast a WebSocket event tagged with the WhatsApp session_id."""
        try:
            from plutus.gateway.ws import manager as ws_manager
            await ws_manager.broadcast_to_session(_WHATSAPP_SESSION_ID, payload)
        except Exception as e:
            logger.debug(f"Could not broadcast to WebSocket: {e}")

    async def _on_whatsapp_message(self, evt: dict[str, Any]) -> None:
        """Callback when a WhatsApp message arrives — queue it for processing."""
        text = evt.get("text", "")
        metadata = {
            "from": evt.get("from", ""),
            "from_name": evt.get("from_name", ""),
            "timestamp": evt.get("timestamp"),
            "is_group": evt.get("is_group", False),
        }
        logger.info(
            f"Queuing WhatsApp message from "
            f"{metadata.get('from_name') or metadata.get('from', 'unknown')}: "
            f"{text[:80]}"
        )
        await self._queue.put((text, metadata))

    async def _process_queue(self) -> None:
        """Worker loop — processes queued messages one at a time."""
        logger.info("WhatsApp message queue worker started")
        while self._running:
            try:
                text, metadata = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
                self._processing = True
                try:
                    await self._handle_message(text, metadata)
                except Exception as e:
                    logger.exception(f"Error handling WhatsApp message: {e}")
                finally:
                    self._processing = False
                    self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Queue worker error: {e}")
        logger.info("WhatsApp message queue worker stopped")

    async def _handle_message(self, text: str, metadata: dict[str, Any]) -> None:
        """Process a single WhatsApp message through the agent."""
        from_name = metadata.get("from_name") or metadata.get("from", "WhatsApp user")
        logger.info(f"Processing WhatsApp message from {from_name}: {text[:80]}")

        agent, lock = self._get_agent()
        if not agent:
            logger.error("No agent available to process WhatsApp message")
            await self._send_reply(
                "Sorry, I'm not available right now. Please try again later.",
                metadata,
            )
            return

        # Broadcast that we're starting to process
        await self._broadcast(
            {
                "type": "user_message",
                "content": text,
                "session_id": _WHATSAPP_SESSION_ID,
                "metadata": metadata,
            }
        )

        response_parts: list[str] = []
        tool_summaries: list[str] = []

        try:
            async with lock:
                async for event in agent.run(text):
                    await self._broadcast(
                        {
                            "type": event.type,
                            "data": event.data,
                            "session_id": _WHATSAPP_SESSION_ID,
                        }
                    )
                    if event.type == "text_delta":
                        chunk = event.data.get("delta", "")
                        if chunk:
                            response_parts.append(chunk)
                    elif event.type == "tool_call":
                        tool_name = event.data.get("tool_name", "")
                        tool_input = event.data.get("tool_input", {})
                        summary = f"🔧 {tool_name}"
                        if isinstance(tool_input, dict):
                            first_val = next(iter(tool_input.values()), None)
                            if first_val and isinstance(first_val, str):
                                preview = first_val[:60]
                                summary += f": {preview}"
                        tool_summaries.append(summary)
                    elif event.type == "error":
                        error_msg = event.data.get("message", "Unknown error")
                        response_parts.append(f"⚠️ {error_msg}")
                        logger.warning(f"Agent error event: {error_msg}")
                    elif event.type == "done":
                        logger.info("Agent processing complete")
        except Exception as e:
            logger.exception("Agent processing failed for WhatsApp message")
            response_parts.append(f"⚠️ Processing error: {str(e)[:300]}")
            await self._broadcast({"type": "error", "message": str(e)[:300]})

        await self._broadcast({"type": "done"})

        # Build the final response
        final_response = "".join(response_parts).strip()
        if not final_response:
            if tool_summaries:
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
            final_response = f"{final_response}\n\n📋 Actions:\n{actions_str}"

        logger.info(f"Sending reply to WhatsApp ({len(final_response)} chars)")
        await self._send_reply(final_response, metadata)

    async def _send_reply(self, text: str, metadata: dict[str, Any]) -> None:
        """Send a reply back to the WhatsApp user."""
        whatsapp = self._get_whatsapp()
        if not whatsapp:
            logger.error("Cannot send reply — WhatsApp connector not available")
            return

        contact = metadata.get("from", "")
        if not contact:
            logger.error("Cannot send reply — no 'from' in metadata")
            return

        result = await whatsapp.send_message(text, contact=contact)
        if result.get("success"):
            logger.info(f"Reply sent to WhatsApp contact {contact}")
        else:
            logger.error(
                f"Failed to send WhatsApp reply: {result.get('message')}"
            )


# Singleton bridge instance
_bridge: WhatsAppBridge | None = None


def get_whatsapp_bridge() -> WhatsAppBridge:
    """Get or create the singleton WhatsApp bridge."""
    global _bridge
    if _bridge is None:
        _bridge = WhatsAppBridge()
    return _bridge
