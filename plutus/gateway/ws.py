"""WebSocket handler for real-time chat with the agent."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("plutus.ws")


class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        logger.info(f"Client connected ({len(self._connections)} total)")

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)
        logger.info(f"Client disconnected ({len(self._connections)} total)")

    async def broadcast(self, message: dict[str, Any]) -> None:
        dead = []
        for ws in self._connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)


manager = ConnectionManager()


def create_ws_router() -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await manager.connect(ws)

        try:
            while True:
                data = await ws.receive_text()
                message = json.loads(data)
                await _handle_message(ws, message)
        except WebSocketDisconnect:
            manager.disconnect(ws)
        except Exception as e:
            logger.exception("WebSocket error")
            manager.disconnect(ws)

    return router


async def _handle_message(ws: WebSocket, message: dict[str, Any]) -> None:
    """Route incoming WebSocket messages."""
    msg_type = message.get("type")

    if msg_type == "chat":
        await _handle_chat(ws, message)
    elif msg_type == "approve":
        await _handle_approval(ws, message)
    elif msg_type == "new_conversation":
        await _handle_new_conversation(ws)
    elif msg_type == "resume_conversation":
        await _handle_resume_conversation(ws, message)
    elif msg_type == "ping":
        await ws.send_json({"type": "pong"})
    else:
        await ws.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})


async def _handle_chat(ws: WebSocket, message: dict[str, Any]) -> None:
    """Process a user chat message through the agent."""
    from plutus.gateway.server import get_state

    state = get_state()
    agent = state.get("agent")

    if not agent:
        await ws.send_json({"type": "error", "message": "Agent not initialized"})
        return

    user_text = message.get("content", "").strip()
    if not user_text:
        return

    # Stream agent events to the WebSocket
    async for event in agent.process_message(user_text):
        await ws.send_json(event.to_dict())

        # Also broadcast approval requests so other UI tabs see them
        if event.type == "tool_approval_needed":
            await manager.broadcast(event.to_dict())


async def _handle_approval(ws: WebSocket, message: dict[str, Any]) -> None:
    """Handle user's approval/rejection of a pending tool action."""
    from plutus.gateway.server import get_state

    state = get_state()
    guardrails = state.get("guardrails")

    approval_id = message.get("approval_id")
    approved = message.get("approved", False)

    if guardrails and approval_id:
        success = guardrails.resolve_approval(approval_id, approved)
        await ws.send_json(
            {
                "type": "approval_resolved",
                "approval_id": approval_id,
                "approved": approved,
                "success": success,
            }
        )


async def _handle_new_conversation(ws: WebSocket) -> None:
    from plutus.gateway.server import get_state

    state = get_state()
    agent = state.get("agent")

    if agent:
        conv_id = await agent.conversation.start_conversation()
        await ws.send_json({"type": "conversation_started", "conversation_id": conv_id})


async def _handle_resume_conversation(ws: WebSocket, message: dict[str, Any]) -> None:
    from plutus.gateway.server import get_state

    state = get_state()
    agent = state.get("agent")
    conv_id = message.get("conversation_id")

    if agent and conv_id:
        await agent.conversation.resume_conversation(conv_id)
        messages = await state["memory"].get_messages(conv_id)
        await ws.send_json(
            {
                "type": "conversation_resumed",
                "conversation_id": conv_id,
                "messages": messages,
            }
        )
