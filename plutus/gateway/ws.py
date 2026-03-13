"""WebSocket handler for real-time chat with the agent.

Plutus uses TWO agent modes:
  1. Standard mode (PRIMARY): Uses LiteLLM + function calling with the `pc` tool.
     The agent reads the screen via accessibility tree snapshots (not screenshots)
     and interacts with elements by ref number — fast, precise, token-efficient.
  2. Computer Use mode (EXPLICIT ONLY): Uses Anthropic's native Computer Use Tool.
     Screenshot-based vision — only activated when the user explicitly requests it
     via the UI toggle or by saying "use computer use" / "use screenshots".

The Standard agent handles ALL messages by default, including desktop interaction.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("plutus.ws")


# ── Keywords that FORCE Computer Use mode (explicit user request) ────
_FORCE_CU_KEYWORDS = {
    "use computer use", "computer use mode", "use screenshots",
    "screenshot mode", "vision mode", "use vision",
    "switch to computer use", "enable computer use",
}


_MAX_WS_CONNECTIONS = 50  # safety limit to prevent FD/memory exhaustion


class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> bool:
        """Accept a WebSocket connection. Returns False if limit is reached."""
        if len(self._connections) >= _MAX_WS_CONNECTIONS:
            await ws.accept()
            await ws.close(code=1013, reason="Too many connections")
            logger.warning(
                f"Rejected WebSocket — limit of {_MAX_WS_CONNECTIONS} reached"
            )
            return False
        await ws.accept()
        self._connections.append(ws)
        logger.info(f"Client connected ({len(self._connections)} total)")
        return True

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
        if not await manager.connect(ws):
            return  # connection rejected (limit reached)

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
    elif msg_type == "heartbeat_control":
        await _handle_heartbeat_control(ws, message)
    elif msg_type == "stop_task":
        await _handle_stop_task(ws)
    elif msg_type == "ping":
        await ws.send_json({"type": "pong"})
    else:
        await ws.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})


def _should_use_computer_use(message: str) -> bool:
    """Determine if a message should use the Computer Use agent.

    Returns True ONLY if the user explicitly requests Computer Use mode.
    The Standard agent (with accessibility tree snapshots) is the default
    for ALL messages, including desktop interaction.
    """
    lower = message.lower()

    # Only use CU if the user explicitly asks for it
    for kw in _FORCE_CU_KEYWORDS:
        if kw in lower:
            return True

    # Default: use Standard agent (accessibility tree, not screenshots)
    return False


async def _handle_chat(ws: WebSocket, message: dict[str, Any]) -> None:
    """Process a user chat message.

    Routes to the Standard agent (primary) or Computer Use agent (explicit only).
    """
    from plutus.gateway.server import get_state

    state = get_state()
    agent = state.get("agent")
    cu_agent = state.get("cu_agent")
    heartbeat = state.get("heartbeat")

    if not agent and not cu_agent:
        await ws.send_json({"type": "error", "message": "Agent not initialized"})
        return

    user_text = message.get("content", "").strip()
    if not user_text:
        return

    # Extract file attachments (base64-encoded)
    attachments = message.get("attachments")  # list of {name, type, data}

    # Real user message — reset the heartbeat consecutive counter
    if heartbeat:
        heartbeat.reset_consecutive()

    # Decide which agent to use
    # Priority: explicit UI override > explicit keyword > default (standard)
    use_cu = message.get("computer_use", None)  # Explicit override from UI toggle
    if use_cu is None:
        # Only use CU if user explicitly asks for it AND the CU agent is available
        use_cu = cu_agent is not None and _should_use_computer_use(user_text)

    if use_cu and cu_agent:
        await _handle_computer_use_chat(ws, cu_agent, user_text)
    elif agent:
        await _handle_standard_chat(ws, agent, user_text, attachments=attachments)
    else:
        await ws.send_json({"type": "error", "message": "No suitable agent available"})


async def _handle_computer_use_chat(ws: WebSocket, cu_agent: Any, user_text: str) -> None:
    """Process a message through the Anthropic Computer Use agent."""
    from plutus.core.computer_use_agent import ComputerUseEvent

    logger.info(f"Computer Use agent handling: {user_text[:80]}")

    # Notify UI that we're using computer use mode
    await ws.send_json({
        "type": "mode",
        "mode": "computer_use",
        "message": "Using Computer Use mode — I can see and control your screen",
    })

    try:
        async for event in cu_agent.run_task(user_text):
            event_dict = event.to_dict()

            # Transform computer use events to match the UI's expected format
            if event.type == "tool_call":
                # Include screenshot indicator for the UI
                tool_name = event.data.get("tool", "")
                tool_input = event.data.get("input", {})
                action = tool_input.get("action", "") if isinstance(tool_input, dict) else ""

                await ws.send_json({
                    "type": "tool_call",
                    "id": event.data.get("id", ""),
                    "tool": f"computer.{action}" if tool_name == "computer" else tool_name,
                    "arguments": tool_input,
                })

            elif event.type == "tool_result":
                result = event.data.get("result", {})
                result_data: dict[str, Any] = {
                    "type": "tool_result",
                    "id": event.data.get("id", ""),
                    "tool": event.data.get("tool", ""),
                }

                if isinstance(result, dict):
                    if result.get("type") == "image":
                        # Screenshot result — send base64 to UI
                        result_data["screenshot"] = True
                        result_data["image_base64"] = result.get("base64", "")
                        result_data["result"] = "Screenshot captured"
                    elif result.get("type") == "error":
                        result_data["result"] = result.get("error", "Unknown error")
                        result_data["error"] = True
                    else:
                        result_data["result"] = result.get("text", str(result))
                else:
                    result_data["result"] = str(result)

                await ws.send_json(result_data)

            elif event.type == "text":
                await ws.send_json({
                    "type": "text",
                    "content": event.data.get("content", ""),
                })

            elif event.type == "thinking":
                await ws.send_json({
                    "type": "thinking",
                    "message": event.data.get("message", ""),
                })

            elif event.type == "iteration":
                await ws.send_json({
                    "type": "iteration",
                    "number": event.data.get("number", 0),
                    "max": event.data.get("max", 50),
                })

            elif event.type == "done":
                await ws.send_json({
                    "type": "done",
                    "iterations": event.data.get("iterations", 0),
                })

            elif event.type == "error":
                await ws.send_json({
                    "type": "error",
                    "message": event.data.get("message", "Unknown error"),
                })

            elif event.type == "cancelled":
                await ws.send_json({
                    "type": "cancelled",
                    "message": event.data.get("message", "Task cancelled"),
                })

    except Exception as e:
        logger.exception("Computer Use agent error")
        await ws.send_json({
            "type": "error",
            "message": f"Computer Use error: {str(e)}",
        })


async def _handle_standard_chat(
    ws: WebSocket,
    agent: Any,
    user_text: str,
    attachments: list[dict[str, str]] | None = None,
) -> None:
    """Process a message through the standard LiteLLM agent."""
    from plutus.gateway.server import _agent_lock

    logger.info(f"Standard agent handling: {user_text[:80]}")

    # Notify UI that we're using standard mode
    await ws.send_json({
        "type": "mode",
        "mode": "standard",
        "message": "🖥️ Computer Use mode — I can see and control your screen",
    })

    disconnected = False
    try:
        async with _agent_lock:
            async for event in agent.process_message(user_text, attachments=attachments):
                if disconnected:
                    # Client disconnected — keep draining the generator so the
                    # agent finishes cleanly (tool_use / tool_result stay paired).
                    continue
                try:
                    await ws.send_json(event.to_dict())
                except (WebSocketDisconnect, RuntimeError, Exception) as send_err:
                    logger.warning(f"Client disconnected during processing: {send_err}")
                    disconnected = True
                    continue

                if event.type == "tool_approval_needed":
                    try:
                        await manager.broadcast(event.to_dict())
                    except Exception:
                        pass
    except Exception as e:
        logger.exception("Standard agent error")
        if not disconnected:
            try:
                await ws.send_json({
                    "type": "error",
                    "message": f"Agent error: {str(e)}",
                })
            except Exception:
                pass


async def _handle_approval(ws: WebSocket, message: dict[str, Any]) -> None:
    """Handle user's approval/rejection of a pending tool action."""
    from plutus.gateway.server import get_state

    state = get_state()
    guardrails = state.get("guardrails")

    approval_id = message.get("approval_id")
    approved = message.get("approved", False)

    if not guardrails:
        await ws.send_json({"type": "error", "message": "Guardrails not initialized"})
        return

    if not approval_id:
        await ws.send_json({"type": "error", "message": "Missing approval_id"})
        return

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
        # Limit messages sent over WebSocket to prevent OOM on large conversations
        messages = await state["memory"].get_messages(conv_id, limit=200)
        await ws.send_json(
            {
                "type": "conversation_resumed",
                "conversation_id": conv_id,
                "messages": messages,
            }
        )


async def _handle_stop_task(ws: WebSocket) -> None:
    """Stop the currently running agent task (standard or computer use)."""
    from plutus.gateway.server import get_state

    state = get_state()
    agent = state.get("agent")
    cu_agent = state.get("cu_agent")
    stopped = False

    if cu_agent and cu_agent.is_running:
        cu_agent.stop()
        stopped = True

    if agent:
        agent.cancel()
        stopped = True

    if stopped:
        await ws.send_json({"type": "task_stopped", "message": "Task stopped"})
    else:
        await ws.send_json({"type": "info", "message": "No task is currently running"})


async def _handle_heartbeat_control(ws: WebSocket, message: dict[str, Any]) -> None:
    """Start, stop, pause, or resume the heartbeat from the UI."""
    from plutus.gateway.server import get_state

    state = get_state()
    heartbeat = state.get("heartbeat")
    config = state.get("config")

    if not heartbeat:
        await ws.send_json({"type": "error", "message": "Heartbeat not initialized"})
        return

    action = message.get("action", "")

    if action == "start":
        interval = message.get("interval") or (config.heartbeat.interval if config else 300)
        heartbeat.start(interval)
        await ws.send_json({"type": "heartbeat_status", "status": "running", "interval": interval})
    elif action == "stop":
        heartbeat.stop()
        await ws.send_json({"type": "heartbeat_status", "status": "stopped"})
    elif action == "pause":
        heartbeat.pause()
        await ws.send_json({"type": "heartbeat_status", "status": "paused"})
    elif action == "resume":
        heartbeat.resume()
        await ws.send_json({"type": "heartbeat_status", "status": "running"})
    elif action == "status":
        await ws.send_json({
            "type": "heartbeat_status",
            "status": "running" if heartbeat.is_running else "stopped",
            "paused": heartbeat.is_paused,
            "interval": heartbeat.interval,
        })
    else:
        await ws.send_json({"type": "error", "message": f"Unknown heartbeat action: {action}"})
