"""Cloud ↔ Agent bridge — makes Plutus Cloud a two-way interface to local Plutus.

Flow:
  1. Cloud agent sends a message via the bridge WebSocket
  2. The PlutusBridge client receives it and calls the on_agent_message callback
  3. This bridge queues the message for sequential processing
  4. Routes it through the dedicated Cloud session agent
     (session_id = "session_cloud") — isolated from the main UI chat
  5. Collects the agent's text response events
  6. Sends the response back to the cloud via bridge.send_to_cloud()
  7. Broadcasts events to WebSocket tagged with session_id="session_cloud"
     so the Sessions panel in the local UI stays in sync

The bridge processes messages sequentially via a queue to prevent
concurrent agent calls from interfering with each other.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("plutus.connectors.cloud_bridge")

# The session_id used for all Cloud traffic — must match the value in
# session_registry.CONNECTOR_SESSIONS.
_CLOUD_SESSION_ID = "session_cloud"


class CloudBridge:
    """Routes cloud agent messages through the local Plutus agent and sends responses back."""

    _instance: CloudBridge | None = None

    def __init__(self) -> None:
        self._running = False
        self._processing = False
        self._queue: asyncio.Queue[tuple[str, str, str | None]] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    @classmethod
    def get_instance(cls) -> CloudBridge:
        """Get or create the singleton CloudBridge instance."""
        if cls._instance is None:
            cls._instance = CloudBridge()
        return cls._instance

    async def start(self) -> None:
        """Start the bridge — begins processing incoming cloud messages."""
        if self._running:
            logger.info("Cloud bridge already running")
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._process_queue())
        logger.info("Cloud bridge started — two-way messaging active")

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
        logger.info("Cloud bridge stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def _get_agent(self):
        """Get the dedicated Cloud session agent from the session registry.

        Falls back to the global main agent if the session registry is not
        available (e.g. during early startup).
        """
        try:
            from plutus.core.session_registry import get_registry

            registry = get_registry()
            session = registry.get(_CLOUD_SESSION_ID)
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

    def _get_bridge_instance(self):
        """Get the PlutusBridge instance from the gateway state."""
        try:
            from plutus.gateway.server import get_state

            state = get_state()
            return state.get("bridge_instance")
        except Exception as e:
            logger.error(f"Failed to get bridge instance: {e}")
            return None

    async def _broadcast(self, payload: dict[str, Any]) -> None:
        """Broadcast a WebSocket event tagged with the Cloud session_id."""
        try:
            from plutus.gateway.ws import manager as ws_manager

            await ws_manager.broadcast_to_session(_CLOUD_SESSION_ID, payload)
        except Exception as e:
            logger.debug(f"Could not broadcast to WebSocket: {e}")

    async def handle_cloud_message(
        self,
        content: str,
        sender: str = "cloud_agent",
        reply_to: str | None = None,
        ws=None,
    ) -> None:
        """Callback when a cloud agent message arrives — queue it for processing.

        This is called by the PlutusBridge's on_agent_message callback.
        The ``ws`` parameter is the raw websocket (not used directly here —
        we use bridge.send_to_cloud() instead).
        """
        logger.info(
            f"Queuing cloud message from {sender}: {content[:80]}"
        )
        await self._queue.put((content, sender, reply_to))

    async def _process_queue(self) -> None:
        """Worker that processes queued cloud messages one at a time."""
        logger.info("Cloud bridge queue processor started")
        while self._running:
            try:
                content, sender, reply_to = await asyncio.wait_for(
                    self._queue.get(), timeout=2.0
                )
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            logger.info(f"Processing cloud message: {content[:80]}")
            try:
                self._processing = True
                await self._handle_message(content, sender, reply_to)
            except Exception as e:
                logger.exception(f"Error processing cloud message: {e}")
                # Send error back to cloud
                bridge = self._get_bridge_instance()
                if bridge:
                    await bridge.send_to_cloud(
                        f"Error processing your message: {str(e)[:500]}",
                        sender="local_agent",
                        reply_to=reply_to,
                    )
            finally:
                self._processing = False

    async def _handle_message(
        self,
        content: str,
        sender: str,
        reply_to: str | None,
    ) -> None:
        """Route a cloud message through the local agent and send the response back."""
        agent, agent_lock = self._get_agent()
        bridge = self._get_bridge_instance()

        if not agent:
            logger.error("Agent not available for cloud message processing")
            if bridge:
                await bridge.send_to_cloud(
                    "Local Plutus agent is not initialized. "
                    "Please check the local app and ensure it's fully started.",
                    sender="local_agent",
                    reply_to=reply_to,
                )
            return

        # Broadcast the incoming cloud message to the Sessions panel in the UI
        await self._broadcast({
            "type": "text",
            "content": f"☁️ **Cloud Agent**: {content}",
            "role": "user",
        })
        await self._broadcast({"type": "thinking"})

        # Process through the dedicated Cloud session agent
        response_parts: list[str] = []
        tool_summaries: list[str] = []

        try:
            logger.info("Sending message to Cloud session agent...")

            class _NullLock:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

            lock_ctx = agent_lock if agent_lock else _NullLock()
            async with lock_ctx:
                async for event in agent.process_message(content):
                    # Broadcast every event to the Sessions panel
                    await self._broadcast(event.to_dict())

                    if event.type == "text" and event.data.get("content"):
                        evt_content = event.data["content"]
                        response_parts.append(evt_content)
                        logger.debug(f"Agent text: {evt_content[:100]}")

                    elif event.type == "tool_call":
                        tool_name = event.data.get("tool", "")
                        if tool_name not in ("plan", "memory"):
                            operation = (
                                event.data.get("arguments", {}).get(
                                    "operation", ""
                                )
                            )
                            summary = (
                                f"{tool_name}.{operation}"
                                if operation
                                else f"{tool_name}"
                            )
                            tool_summaries.append(summary)
                            logger.debug(f"Agent tool call: {summary}")

                    elif event.type == "error":
                        error_msg = event.data.get("message", "Unknown error")
                        response_parts.append(f"Error: {error_msg}")
                        logger.warning(f"Agent error event: {error_msg}")

                    elif event.type == "done":
                        logger.info("Agent processing complete")

        except Exception as e:
            logger.exception("Agent processing failed for cloud message")
            response_parts.append(f"Processing error: {str(e)[:300]}")
            await self._broadcast({
                "type": "error",
                "message": str(e)[:300],
            })

        await self._broadcast({"type": "done"})

        # Build the final response
        final_response = "\n".join(response_parts).strip()

        if not final_response:
            if tool_summaries:
                final_response = "Done!"
            else:
                final_response = (
                    "I received your message but had no response to give. "
                    "Could you try rephrasing?"
                )

        # Append tool call summary if there were any
        if tool_summaries:
            shown = tool_summaries[:10]
            actions_str = ", ".join(shown)
            if len(tool_summaries) > 10:
                actions_str += f" ... and {len(tool_summaries) - 10} more"
            final_response = f"{final_response}\n\n[Actions: {actions_str}]"

        logger.info(
            f"Sending reply to cloud ({len(final_response)} chars)"
        )

        # Send the response back to the cloud agent via the bridge
        if bridge:
            sent = await bridge.send_to_cloud(
                final_response,
                sender="local_agent",
                reply_to=reply_to,
            )
            if sent:
                logger.info("Reply sent to cloud successfully")
            else:
                logger.warning("Failed to send reply to cloud")
        else:
            logger.warning(
                "Bridge instance not available — reply not sent to cloud"
            )


# Module-level singleton accessor
def get_cloud_bridge() -> CloudBridge:
    """Get the singleton CloudBridge instance."""
    return CloudBridge.get_instance()
