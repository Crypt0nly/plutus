"""Plutus Cloud Bridge — WebSocket tunnel between local Plutus and Plutus Cloud."""

import time
from typing import Any

from plutus.bridge import bridge as _bridge_module
from plutus.bridge.bridge import extract_server_url


class PlutusBridge(_bridge_module.PlutusBridge):
    async def send_to_cloud(
        self,
        content: str,
        sender: str = "local_agent",
        reply_to: str | None = None,
    ) -> bool:
        """Send an agent message using the documented bridge payload schema.

        The cloud receiver reads agent replies from ``msg.get("content")``.
        Keep fire-and-forget replies aligned with send_to_cloud_and_wait and
        the Bridge Protocol Spec so replies do not arrive as empty messages.
        """
        if not self._ws or not self._connected:
            _bridge_module.log.warning("Bridge: cannot send to cloud — not connected")
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
            _bridge_module.log.info("Bridge: sent agent_message to cloud (%d chars)", len(content))
            return True
        except Exception as exc:
            _bridge_module.log.warning("Bridge: failed to send agent_message: %s", exc)
            return False


_bridge_module.PlutusBridge = PlutusBridge

__all__ = ["PlutusBridge", "extract_server_url"]
