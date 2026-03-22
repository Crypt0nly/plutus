"""WebSocket handler for real-time chat with the agent.

Plutus uses TWO agent modes:
  1. Standard mode (PRIMARY): Uses LiteLLM + function calling with the `pc` tool.
     The agent reads the screen via accessibility tree snapshots (not screenshots)
     and interacts with elements by ref number — fast, precise, token-efficient.
  2. Computer Use mode (EXPLICIT ONLY): Uses Anthropic's native Computer Use Tool.
     Screenshot-based vision — only activated when the user explicitly requests it
     via the UI toggle or by saying "use computer use" / "use screenshots".

Multi-session support: each WebSocket message includes a `session_id` field.
Each session has its own AgentRuntime instance and asyncio.Lock so that multiple
conversations (including connector sessions) can run fully in parallel.
"""

from __future__ import annotations

import asyncio
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

# Default session used when no session_id is provided (backwards-compat)
_DEFAULT_SESSION_ID = "session_main"


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

    async def broadcast_to_session(
        self, session_id: str, message: dict[str, Any]
    ) -> None:
        """Broadcast a message tagged with session_id to all connected clients."""
        payload = {**message, "session_id": session_id}
        await self.broadcast(payload)


manager = ConnectionManager()

# Track in-flight chat tasks per session so we can cancel them on stop_task.
# Maps session_id -> asyncio.Task
_active_tasks: dict[str, asyncio.Task] = {}


def create_ws_router() -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        if not await manager.connect(ws):
            return  # connection rejected (limit reached)

        # Background tasks spawned for this connection — cancelled on disconnect
        background_tasks: set[asyncio.Task] = set()

        try:
            while True:
                data = await ws.receive_text()
                message = json.loads(data)

                # Chat messages are long-running — spawn as background tasks so
                # the receive loop stays free and multiple sessions can run in
                # parallel without blocking each other.
                if message.get("type") == "chat":
                    task = asyncio.create_task(
                        _handle_chat(ws, message),
                        name=f"chat-{message.get('session_id', _DEFAULT_SESSION_ID)}",
                    )
                    sid = message.get("session_id") or _DEFAULT_SESSION_ID
                    # Cancel any previous task for this session before starting a new one
                    prev = _active_tasks.get(sid)
                    if prev and not prev.done():
                        prev.cancel()
                    _active_tasks[sid] = task
                    background_tasks.add(task)
                    task.add_done_callback(background_tasks.discard)
                    task.add_done_callback(
                        lambda t, s=sid: _active_tasks.pop(s, None) if _active_tasks.get(s) is t else None
                    )
                else:
                    await _handle_message(ws, message)

        except WebSocketDisconnect:
            manager.disconnect(ws)
            # Cancel all in-flight tasks for this connection
            for t in list(background_tasks):
                t.cancel()
        except Exception as e:
            logger.exception("WebSocket error")
            manager.disconnect(ws)
            for t in list(background_tasks):
                t.cancel()

    return router


async def _handle_message(ws: WebSocket, message: dict[str, Any]) -> None:
    """Route incoming WebSocket messages."""
    msg_type = message.get("type")

    if msg_type == "chat":
        await _handle_chat(ws, message)
    elif msg_type == "approve":
        await _handle_approval(ws, message)
    elif msg_type == "new_conversation":
        await _handle_new_conversation(ws, message)
    elif msg_type == "new_session":
        await _handle_new_session(ws, message)
    elif msg_type == "close_session":
        await _handle_close_session(ws, message)
    elif msg_type == "list_sessions":
        await _handle_list_sessions(ws)
    elif msg_type == "resume_conversation":
        await _handle_resume_conversation(ws, message)
    elif msg_type == "heartbeat_control":
        await _handle_heartbeat_control(ws, message)
    elif msg_type == "stop_task":
        await _handle_stop_task(ws, message)
    elif msg_type == "clear_session_history":
        await _handle_clear_session_history(ws, message)
    elif msg_type == "ping":
        await ws.send_json({"type": "pong"})
    else:
        await ws.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})


def _should_use_computer_use(message: str) -> bool:
    """Determine if a message should use the Computer Use agent."""
    lower = message.lower()
    for kw in _FORCE_CU_KEYWORDS:
        if kw in lower:
            return True
    return False


def _get_session(session_id: str | None) -> Any | None:
    """Look up a session from the registry. Falls back to default session."""
    from plutus.gateway.server import get_state
    from plutus.core.session_registry import get_registry

    registry = get_registry()
    sid = session_id or _DEFAULT_SESSION_ID
    session = registry.get(sid)
    if session is None:
        # Fall back to the legacy single-agent state for backwards compatibility
        state = get_state()
        return None
    return session


async def _handle_chat(ws: WebSocket, message: dict[str, Any]) -> None:
    """Process a user chat message, routed to the correct session's agent."""
    from plutus.gateway.server import get_state
    from plutus.core.session_registry import get_registry

    state = get_state()
    cu_agent = state.get("cu_agent")
    heartbeat = state.get("heartbeat")

    user_text = message.get("content", "").strip()
    if not user_text:
        return

    session_id = message.get("session_id") or _DEFAULT_SESSION_ID
    attachments = message.get("attachments")

    # Real user message — reset the heartbeat consecutive counter
    if heartbeat:
        heartbeat.reset_consecutive()

    # Resolve the agent for this session
    registry = get_registry()
    session = registry.get(session_id)

    if session is None:
        # Fall back to the global agent for backwards compatibility
        agent = state.get("agent")
        if not agent:
            await ws.send_json({"type": "error", "message": "Agent not initialized", "session_id": session_id})
            return
        session_lock = state.get("_agent_lock_fallback")
        if session_lock is None:
            from plutus.gateway.server import _agent_lock
            session_lock = _agent_lock
    else:
        agent = session.agent
        session_lock = session.lock

    # Decide which agent to use
    use_cu = message.get("computer_use", None)
    if use_cu is None:
        use_cu = cu_agent is not None and _should_use_computer_use(user_text)

    if use_cu and cu_agent:
        await _handle_computer_use_chat(ws, cu_agent, user_text, session_id=session_id)
    elif agent:
        await _handle_standard_chat(
            ws, agent, user_text,
            attachments=attachments,
            session_lock=session_lock,
            session_id=session_id,
        )
    else:
        await ws.send_json({"type": "error", "message": "No suitable agent available", "session_id": session_id})


async def _handle_computer_use_chat(
    ws: WebSocket,
    cu_agent: Any,
    user_text: str,
    session_id: str = _DEFAULT_SESSION_ID,
) -> None:
    """Process a message through the Anthropic Computer Use agent."""
    from plutus.core.computer_use_agent import ComputerUseEvent
    from plutus.core.session_registry import get_registry

    logger.info(f"Computer Use agent handling [{session_id}]: {user_text[:80]}")

    await ws.send_json({
        "type": "mode",
        "mode": "computer_use",
        "message": "Using Computer Use mode — I can see and control your screen",
        "session_id": session_id,
    })

    # Auto-name the session from the first user message
    registry = get_registry()
    cu_session = registry.get(session_id)
    if cu_session and cu_session.display_name in ("New Chat", "Chat") and not cu_session.is_connector:
        auto_title = user_text[:60].strip()
        if auto_title:
            cu_session.display_name = auto_title
            await manager.broadcast({
                "type": "session_renamed",
                "session_id": session_id,
                "display_name": auto_title,
            })

    try:
        async for event in cu_agent.run_task(user_text):
            event_dict = event.to_dict()
            event_dict["session_id"] = session_id

            if event.type == "tool_call":
                tool_name = event.data.get("tool", "")
                tool_input = event.data.get("input", {})
                action = tool_input.get("action", "") if isinstance(tool_input, dict) else ""
                await ws.send_json({
                    "type": "tool_call",
                    "id": event.data.get("id", ""),
                    "tool": f"computer.{action}" if tool_name == "computer" else tool_name,
                    "arguments": tool_input,
                    "session_id": session_id,
                })
            elif event.type == "tool_result":
                result = event.data.get("result", {})
                result_data: dict[str, Any] = {
                    "type": "tool_result",
                    "id": event.data.get("id", ""),
                    "tool": event.data.get("tool", ""),
                    "session_id": session_id,
                }
                if isinstance(result, dict):
                    if result.get("type") == "image":
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
                    "session_id": session_id,
                })
            elif event.type == "thinking":
                await ws.send_json({
                    "type": "thinking",
                    "message": event.data.get("message", ""),
                    "session_id": session_id,
                })
            elif event.type == "done":
                await ws.send_json({
                    "type": "done",
                    "iterations": event.data.get("iterations", 0),
                    "session_id": session_id,
                })
            elif event.type == "error":
                await ws.send_json({
                    "type": "error",
                    "message": event.data.get("message", "Unknown error"),
                    "session_id": session_id,
                })
            elif event.type == "cancelled":
                await ws.send_json({
                    "type": "cancelled",
                    "message": event.data.get("message", "Task cancelled"),
                    "session_id": session_id,
                })
    except Exception as e:
        logger.exception("Computer Use agent error")
        await ws.send_json({
            "type": "error",
            "message": f"Computer Use error: {str(e)}",
            "session_id": session_id,
        })


async def _handle_standard_chat(
    ws: WebSocket,
    agent: Any,
    user_text: str,
    attachments: list[dict[str, str]] | None = None,
    session_lock: asyncio.Lock | None = None,
    session_id: str = _DEFAULT_SESSION_ID,
) -> None:
    """Process a message through the standard LiteLLM agent."""
    from plutus.gateway.server import _agent_lock
    from plutus.core.session_registry import get_registry

    lock = session_lock or _agent_lock
    logger.info(f"Standard agent handling [{session_id}]: {user_text[:80]}")

    await ws.send_json({
        "type": "mode",
        "mode": "standard",
        "message": "🖥️ Computer Use mode — I can see and control your screen",
        "session_id": session_id,
    })

    # Auto-name the session from the first user message
    registry = get_registry()
    session = registry.get(session_id)
    if session and session.display_name in ("New Chat", "Chat") and not session.is_connector:
        auto_title = user_text[:60].strip()
        if auto_title:
            session.display_name = auto_title
            await manager.broadcast({
                "type": "session_renamed",
                "session_id": session_id,
                "display_name": auto_title,
            })

    disconnected = False
    try:
        async with lock:
            async for event in agent.process_message(user_text, attachments=attachments):
                if disconnected:
                    continue
                try:
                    payload = event.to_dict()
                    payload["session_id"] = session_id
                    await ws.send_json(payload)
                except (WebSocketDisconnect, RuntimeError, Exception) as send_err:
                    logger.warning(f"Client disconnected during processing [{session_id}]: {send_err}")
                    disconnected = True
                    continue

                if event.type == "tool_approval_needed":
                    try:
                        payload = event.to_dict()
                        payload["session_id"] = session_id
                        await manager.broadcast(payload)
                    except Exception:
                        pass
    except Exception as e:
        logger.exception(f"Standard agent error [{session_id}]")
        if not disconnected:
            try:
                await ws.send_json({
                    "type": "error",
                    "message": f"Agent error: {str(e)}",
                    "session_id": session_id,
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
    await ws.send_json({
        "type": "approval_resolved",
        "approval_id": approval_id,
        "approved": approved,
        "success": success,
    })


async def _handle_new_conversation(ws: WebSocket, message: dict[str, Any]) -> None:
    """Start a new conversation within a session (clears chat history for that session)."""
    from plutus.core.session_registry import get_registry

    session_id = message.get("session_id") or _DEFAULT_SESSION_ID
    registry = get_registry()
    session = registry.get(session_id)

    if session:
        conv_id = await registry.new_conversation_in_session(session_id)
        await ws.send_json({
            "type": "conversation_started",
            "conversation_id": conv_id,
            "session_id": session_id,
        })
    else:
        # Fallback to legacy behaviour
        from plutus.gateway.server import get_state
        state = get_state()
        agent = state.get("agent")
        if agent:
            conv_id = await agent.conversation.start_conversation()
            await ws.send_json({
                "type": "conversation_started",
                "conversation_id": conv_id,
                "session_id": session_id,
            })


async def _handle_new_session(ws: WebSocket, message: dict[str, Any]) -> None:
    """Create a new user session (a new independent chat tab)."""
    from plutus.core.session_registry import get_registry

    registry = get_registry()
    display_name = message.get("display_name", "New Chat")
    icon = message.get("icon", "💬")

    session = await registry.create_session(
        display_name=display_name,
        icon=icon,
        is_connector=False,
    )
    await ws.send_json({
        "type": "session_created",
        "session": session.to_dict(),
    })


async def _handle_close_session(ws: WebSocket, message: dict[str, Any]) -> None:
    """Close a user session."""
    from plutus.core.session_registry import get_registry

    session_id = message.get("session_id")
    if not session_id:
        await ws.send_json({"type": "error", "message": "Missing session_id"})
        return

    registry = get_registry()
    removed = await registry.close_session(session_id)
    await ws.send_json({
        "type": "session_closed",
        "session_id": session_id,
        "success": removed,
    })


async def _handle_list_sessions(ws: WebSocket) -> None:
    """Return all active sessions."""
    from plutus.core.session_registry import get_registry

    registry = get_registry()
    sessions = registry.list_sessions()
    await ws.send_json({
        "type": "sessions_list",
        "sessions": sessions,
    })


async def _handle_resume_conversation(ws: WebSocket, message: dict[str, Any]) -> None:
    from plutus.gateway.server import get_state
    from plutus.core.session_registry import get_registry

    state = get_state()
    session_id = message.get("session_id") or _DEFAULT_SESSION_ID
    conv_id = message.get("conversation_id")

    registry = get_registry()
    session = registry.get(session_id)
    agent = session.agent if session else state.get("agent")

    if agent and conv_id:
        await agent.conversation.resume_conversation(conv_id)
        messages = await state["memory"].get_messages(conv_id, limit=200)
        await ws.send_json({
            "type": "conversation_resumed",
            "conversation_id": conv_id,
            "session_id": session_id,
            "messages": messages,
        })


async def _handle_stop_task(ws: WebSocket, message: dict[str, Any]) -> None:
    """Stop the currently running agent task in a session."""
    from plutus.gateway.server import get_state
    from plutus.core.session_registry import get_registry

    state = get_state()
    session_id = message.get("session_id") or _DEFAULT_SESSION_ID
    cu_agent = state.get("cu_agent")

    registry = get_registry()
    session = registry.get(session_id)

    stopped = False

    # Cancel the asyncio background task for this session if one is running
    bg_task = _active_tasks.get(session_id)
    if bg_task and not bg_task.done():
        bg_task.cancel()
        stopped = True

    if cu_agent and getattr(cu_agent, "is_running", False):
        cu_agent.stop()
        stopped = True

    if session and session.agent:
        session.agent.cancel()
        stopped = True
    elif not session:
        agent = state.get("agent")
        if agent:
            agent.cancel()
            stopped = True

    if stopped:
        await ws.send_json({"type": "task_stopped", "message": "Task stopped", "session_id": session_id})
    else:
        await ws.send_json({"type": "info", "message": "No task is currently running", "session_id": session_id})


async def _handle_clear_session_history(ws: WebSocket, message: dict[str, Any]) -> None:
    """Clear all stored messages for a connector session and start a fresh conversation.

    Only allowed for connector sessions (is_connector=True).  Deletes every
    message in the current conversation from the database, resets the
    conversation summary, and starts a brand-new conversation so the agent
    has a clean context on the next message.
    """
    from plutus.core.session_registry import get_registry

    session_id = message.get("session_id") or _DEFAULT_SESSION_ID
    registry = get_registry()
    session = registry.get(session_id)

    if not session:
        await ws.send_json({"type": "error", "message": "Session not found", "session_id": session_id})
        return

    if not session.is_connector:
        await ws.send_json({
            "type": "error",
            "message": "clear_session_history is only allowed for connector sessions",
            "session_id": session_id,
        })
        return

    agent = session.agent
    if not agent:
        await ws.send_json({"type": "error", "message": "No agent for session", "session_id": session_id})
        return

    conv = agent.conversation
    # Delete all messages for the current conversation from the database
    if conv.conversation_id:
        await agent._memory.clear_conversation_messages(conv.conversation_id)

    # Start a fresh conversation so the agent has a clean context
    new_conv_id = await conv.start_conversation()
    session.conversation_id = new_conv_id

    logger.info(
        "Cleared history for connector session %r, new conversation %r",
        session_id, new_conv_id,
    )
    await ws.send_json({
        "type": "session_history_cleared",
        "session_id": session_id,
        "message": "Chat history cleared. Starting fresh.",
    })


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
