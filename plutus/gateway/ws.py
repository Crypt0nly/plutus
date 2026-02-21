"""WebSocket handler for real-time chat with the agent.

Plutus uses TWO agent modes:
  1. Computer Use mode (PRIMARY): Uses Anthropic's native Computer Use Tool.
     Claude sees screenshots, clicks, types, scrolls — like a human at the keyboard.
  2. Standard mode (FALLBACK): Uses LiteLLM + function calling for code editing,
     analysis, and other non-desktop tasks.

The WebSocket handler automatically routes to the Computer Use agent for all
messages by default. If the CU agent is not available (no Anthropic key, or
non-Anthropic provider), it falls back to the standard agent.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("plutus.ws")


# ── Keywords that indicate the user wants desktop interaction ────────
# (Used as a hint, but by default ALL messages go through CU agent)
_DESKTOP_KEYWORDS = {
    "open", "click", "type", "scroll", "screenshot", "browser", "tab",
    "window", "app", "application", "desktop", "mouse", "keyboard",
    "whatsapp", "chrome", "firefox", "safari", "edge", "notepad",
    "vscode", "vs code", "terminal", "finder", "explorer", "file manager",
    "search", "google", "youtube", "spotify", "slack", "discord",
    "telegram", "signal", "email", "outlook", "gmail", "settings",
    "control panel", "system preferences", "task manager",
    "send", "message", "navigate", "go to", "visit", "download",
    "install", "uninstall", "close", "minimize", "maximize",
    "drag", "drop", "select", "copy", "paste", "cut", "undo", "redo",
    "save", "print", "zoom", "fullscreen", "switch", "move",
}

# Keywords that indicate code/file work (use standard agent)
_CODE_KEYWORDS = {
    "analyze code", "edit file", "create file", "read file", "write code",
    "python script", "javascript", "refactor", "debug", "compile",
    "git commit", "git push", "run tests", "lint", "format code",
}


def _should_use_computer_use(message: str) -> bool:
    """Determine if a message should use the Computer Use agent.

    By default, returns True for most messages. Only returns False
    for messages that are clearly about code/file operations.
    """
    lower = message.lower()

    # Check if it's clearly a code/file task
    for kw in _CODE_KEYWORDS:
        if kw in lower:
            return False

    # Default: use computer use for everything
    return True


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
    elif msg_type == "heartbeat_control":
        await _handle_heartbeat_control(ws, message)
    elif msg_type == "stop_task":
        await _handle_stop_task(ws)
    elif msg_type == "ping":
        await ws.send_json({"type": "pong"})
    else:
        await ws.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})


async def _handle_chat(ws: WebSocket, message: dict[str, Any]) -> None:
    """Process a user chat message.

    Routes to the Computer Use agent (primary) or standard agent (fallback).
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

    # Real user message — reset the heartbeat consecutive counter
    if heartbeat:
        heartbeat.reset_consecutive()

    # Decide which agent to use
    use_cu = message.get("computer_use", None)  # Explicit override from UI
    if use_cu is None:
        # Auto-detect: use CU agent if available and message seems desktop-related
        use_cu = cu_agent is not None and _should_use_computer_use(user_text)

    if use_cu and cu_agent:
        await _handle_computer_use_chat(ws, cu_agent, user_text)
    elif agent:
        await _handle_standard_chat(ws, agent, user_text)
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


async def _handle_standard_chat(ws: WebSocket, agent: Any, user_text: str) -> None:
    """Process a message through the standard LiteLLM agent."""
    logger.info(f"Standard agent handling: {user_text[:80]}")

    # Notify UI that we're using standard mode
    await ws.send_json({
        "type": "mode",
        "mode": "standard",
        "message": "Using standard mode for code and file operations",
    })

    async for event in agent.process_message(user_text):
        await ws.send_json(event.to_dict())

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


async def _handle_stop_task(ws: WebSocket) -> None:
    """Stop the currently running computer use task."""
    from plutus.gateway.server import get_state

    state = get_state()
    cu_agent = state.get("cu_agent")

    if cu_agent and cu_agent.is_running:
        cu_agent.stop()
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

    action = message.get("action")

    if action == "start":
        config.heartbeat.enabled = True
        config.save()
        heartbeat.update_config(config.heartbeat)
        if not heartbeat.running:
            heartbeat.start()
    elif action == "stop":
        config.heartbeat.enabled = False
        config.save()
        heartbeat.stop()
    elif action == "pause":
        heartbeat.pause()
    elif action == "resume":
        heartbeat.resume()
    elif action == "configure":
        if "interval_seconds" in message:
            config.heartbeat.interval_seconds = message["interval_seconds"]
        if "quiet_hours_start" in message:
            config.heartbeat.quiet_hours_start = message["quiet_hours_start"]
        if "quiet_hours_end" in message:
            config.heartbeat.quiet_hours_end = message["quiet_hours_end"]
        if "max_consecutive" in message:
            config.heartbeat.max_consecutive = message["max_consecutive"]
        if "prompt" in message:
            config.heartbeat.prompt = message["prompt"]
        config.save()
        heartbeat.update_config(config.heartbeat)
    else:
        await ws.send_json({"type": "error", "message": f"Unknown heartbeat action: {action}"})
        return

    await ws.send_json({"type": "heartbeat_status", **heartbeat.status()})
