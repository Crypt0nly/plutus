"""Discord ↔ Agent bridge — makes Discord a full two-way interface to Plutus.

Flow:
  1. User sends message in a Discord channel
  2. discord.py client picks it up via on_message
  3. This bridge receives it via the on_message callback
  4. Sends a typing indicator to the channel
  5. Routes it through the dedicated Discord session agent
     (session_id = "session_discord") — completely isolated from the
     main UI chat so messages never bleed into the user's chat view.
  6. Collects the agent's text response events
  7. Sends the response back to the user via Discord
  8. Also broadcasts events to WebSocket tagged with session_id="session_discord"
     so the Sessions panel in the UI stays in sync.
  9. Screenshots and files generated during processing are sent as attachments

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

logger = logging.getLogger("plutus.connectors.discord_bridge")

# The session_id used for all Discord traffic — must match the value in
# session_registry.CONNECTOR_SESSIONS.
_DISCORD_SESSION_ID = "session_discord"


class DiscordBridge:
    """Routes Discord messages through the Plutus agent and sends responses back."""

    def __init__(self) -> None:
        self._running = False
        self._processing = False
        self._queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the bridge — begins processing incoming Discord messages."""
        if self._running:
            logger.info("Discord bridge already running")
            return

        discord_conn = self._get_discord()
        if not discord_conn:
            logger.error(
                "Cannot start Discord bridge — "
                "Discord connector not available or not configured"
            )
            return

        # Set ourselves as the message handler BEFORE starting the bot
        discord_conn.set_message_handler(self._on_discord_message)
        logger.info("Message handler registered")

        # Start the Discord bot client
        await discord_conn.start()
        logger.info("Discord bot started")

        # Start our message processing worker
        self._running = True
        self._worker_task = asyncio.create_task(self._process_queue())
        logger.info("Discord bridge started — two-way messaging active")

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

        # Stop the Discord bot
        discord_conn = self._get_discord()
        if discord_conn:
            await discord_conn.stop()

        logger.info("Discord bridge stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def _get_discord(self):
        """Get the Discord connector from the server state."""
        try:
            from plutus.gateway.server import get_state
            state = get_state()
            connector_mgr = state.get("connector_manager")
            if not connector_mgr:
                return None
            discord_conn = connector_mgr.get("discord")
            if not discord_conn or not discord_conn.is_configured:
                return None
            return discord_conn
        except Exception as e:
            logger.error(f"Failed to get Discord connector: {e}")
            return None

    def _get_agent(self):
        """Get the dedicated Discord session agent from the session registry.

        Falls back to the global main agent if the session registry is not
        available (e.g. during early startup).
        """
        try:
            from plutus.core.session_registry import get_registry
            registry = get_registry()
            session = registry.get(_DISCORD_SESSION_ID)
            if session:
                return session.agent, session.lock
        except Exception as e:
            logger.warning(f"Session registry not available: {e}")

        # Fallback — use the global agent
        try:
            from plutus.gateway.server import get_state, _agent_lock
            state = get_state()
            return state.get("agent"), _agent_lock
        except Exception as e:
            logger.error(f"Failed to get fallback agent: {e}")
            return None, None

    async def _broadcast(self, payload: dict) -> None:
        """Broadcast a WebSocket event tagged with the Discord session_id."""
        try:
            from plutus.gateway.ws import manager as ws_manager
            await ws_manager.broadcast_to_session(_DISCORD_SESSION_ID, payload)
        except Exception as e:
            logger.debug(f"Could not broadcast to WebSocket: {e}")

    async def _on_discord_message(self, text: str, metadata: dict[str, Any]) -> None:
        """Callback when a Discord message arrives — queue it for processing."""
        logger.info(
            f"Queuing Discord message from "
            f"{metadata.get('author_name', 'unknown')}: {text[:80]}"
        )
        await self._queue.put((text, metadata))

    async def _process_queue(self) -> None:
        """Worker that processes queued Discord messages one at a time."""
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
                logger.exception(f"Error processing Discord message: {e}")
                await self._send_reply(
                    f"⚠️ Sorry, I encountered an error:\n{str(e)[:500]}",
                    metadata,
                )
            finally:
                self._processing = False

    async def _handle_message(self, text: str, metadata: dict[str, Any]) -> None:
        """Route a Discord message through the agent and send the response back."""
        agent, agent_lock = self._get_agent()
        discord_conn = self._get_discord()

        if not agent:
            logger.error("Agent not available for Discord message processing")
            await self._send_reply(
                "⚠️ Plutus agent is not initialized. "
                "Please check the web UI and ensure an API key is configured.",
                metadata,
            )
            return

        if not discord_conn:
            logger.error("Discord connector not available")
            return

        channel_id = metadata.get("channel_id")

        # Send typing indicator immediately
        await discord_conn.send_typing(channel_id=channel_id)

        # Broadcast the incoming Discord message to the Sessions panel in the UI
        # (tagged with session_id so it only appears in the Discord session view)
        await self._broadcast({
            "type": "text",
            "content": (
                f"💬 **{metadata.get('author_display_name', 'User')}**: {text}"
            ),
            "role": "user",
        })
        await self._broadcast({"type": "thinking"})

        # Process through the dedicated Discord session agent
        response_parts: list[str] = []
        tool_summaries: list[str] = []
        screenshots_sent = 0

        try:
            logger.info("Sending message to Discord session agent...")
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
                            await discord_conn.send_typing(channel_id=channel_id)

                    elif event.type == "tool_result":
                        # Forward screenshots to Discord as files
                        if event.data.get("screenshot") and event.data.get("image_base64"):
                            sent = await self._send_screenshot(
                                event.data["image_base64"], channel_id, discord_conn
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
            logger.exception("Agent processing failed for Discord message")
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

        logger.info(f"Sending reply to Discord ({len(final_response)} chars)")

        # Send the response back via Discord
        await self._send_reply(final_response, metadata)

    async def _send_reply(self, text: str, metadata: dict[str, Any]) -> None:
        """Send a reply back to the Discord channel."""
        discord_conn = self._get_discord()
        if not discord_conn:
            logger.error("Cannot send reply — Discord connector not available")
            return

        channel_id = metadata.get("channel_id") or discord_conn._channel_id
        if not channel_id:
            logger.error("Cannot send reply — no channel_id")
            return

        result = await discord_conn.send_message(text, channel_id=channel_id)
        if result.get("success"):
            logger.info(
                f"Reply sent to Discord (msg_ids={result.get('message_ids')})"
            )
        else:
            logger.error(
                f"Failed to send Discord reply: {result.get('message')}"
            )

    async def _send_screenshot(
        self,
        image_base64: str,
        channel_id: int | str | None,
        discord_conn: Any,
    ) -> bool:
        """Decode a base64 screenshot and send it as a file to Discord."""
        try:
            img_bytes = base64.b64decode(image_base64)

            # Write to a temp file so send_file can read it
            with tempfile.NamedTemporaryFile(
                suffix=".png", delete=False
            ) as tmp:
                tmp.write(img_bytes)
                tmp_path = tmp.name

            try:
                result = await discord_conn.send_file(
                    tmp_path, caption="📸 Screenshot", channel_id=channel_id
                )
                if result.get("success"):
                    logger.info("Screenshot sent to Discord")
                    return True
                else:
                    logger.warning(
                        f"Failed to send screenshot to Discord: "
                        f"{result.get('message')}"
                    )
                    return False
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        except Exception as e:
            logger.error(f"Failed to send screenshot to Discord: {e}")
            return False


class _NullLock:
    """A no-op async context manager used when no lock is needed."""
    async def __aenter__(self):
        return self
    async def __aexit__(self, *_):
        pass


# Singleton bridge instance
_bridge: DiscordBridge | None = None


def get_discord_bridge() -> DiscordBridge:
    """Get or create the singleton Discord bridge."""
    global _bridge
    if _bridge is None:
        _bridge = DiscordBridge()
    return _bridge
