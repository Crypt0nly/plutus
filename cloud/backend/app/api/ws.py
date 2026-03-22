"""
WebSocket endpoint for real-time chat with the Plutus cloud agent.

The frontend connects to /ws?token=<clerk_jwt> and exchanges JSON messages
in the same format as the local Plutus backend.

Incoming message types (sent by the frontend):
  - ping
  - list_sessions
  - new_session          { display_name?, icon? }
  - chat                 { session_id, content, attachments? }
  - send_message         { session_id?, message, conversation_id? }  (legacy alias)
  - stop_task            { session_id }
  - delete_session       { session_id }
  - load_conversation    { session_id, conversation_id }

Outgoing message types (expected by the frontend):
  - connected
  - pong
  - sessions_list        { sessions: [...] }
  - session_created      { session: { id, display_name, icon, ... } }
  - thinking             { session_id }
  - text                 { content, role, session_id }
  - done                 { session_id }
  - error                { message, session_id }
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from uuid import uuid4

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.agent.runtime import CloudAgentRuntime
from app.api.auth import get_clerk_jwks
from app.database import async_session_factory
from app.models.conversation import Conversation, Message

logger = logging.getLogger(__name__)

router = APIRouter()

# Track active WebSocket connections per user
active_connections: dict[str, WebSocket] = {}


async def _authenticate_ws(token: str) -> dict | None:
    """Verify Clerk JWT and return user claims, or None on failure."""
    try:
        jwks = await get_clerk_jwks()
        header = jwt.get_unverified_header(token)
        key = None
        for k in jwks.get("keys", []):
            if k["kid"] == header["kid"]:
                key = jwt.algorithms.RSAAlgorithm.from_jwk(k)
                break
        if not key:
            return None
        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        return {
            "sub": payload.get("sub"),
            "user_id": payload.get("sub"),
            "email": payload.get("email"),
        }
    except Exception as e:
        logger.warning(f"WS auth failed: {e}")
        return None


def _make_session_obj(sid: str, display_name: str = "Chat", icon: str = "💬") -> dict:
    """Build a session object in the format the frontend expects."""
    now = datetime.now(UTC).isoformat()
    return {
        "session_id": sid,
        "id": sid,
        "display_name": display_name,
        "icon": icon,
        "is_connector": False,
        "connector_name": None,
        "conversation_id": None,
        "is_processing": False,
        "created_at": now,
        "last_active": now,
    }


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = ""):
    """Main WebSocket endpoint."""
    # Authenticate
    if not token:
        await websocket.close(code=4001)
        return

    user = await _authenticate_ws(token)
    if not user:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    user_id = user["user_id"]
    active_connections[user_id] = websocket

    # Send connected confirmation
    await websocket.send_text(json.dumps({"type": "connected"}))

    # Per-connection session state: session_id -> conversation_id
    sessions: dict[str, str | None] = {"session_main": None}
    active_sid = "session_main"

    # Auto-start connectors that were previously configured and running.
    # This ensures connector sessions survive page refreshes.
    from app.services import connector_service

    try:
        async with async_session_factory() as db:
            from app.models.user import User

            user_row = await db.get(User, user_id)
            if user_row and user_row.connector_credentials:
                creds_map: dict = user_row.connector_credentials
                for connector_name, creds in creds_map.items():
                    if not isinstance(creds, dict):
                        continue
                    # Only auto-start connectors that were previously running
                    # (indicated by a "listening" flag we persist on start).
                    if not creds.get("listening"):
                        continue
                    if connector_service.is_running(user_id, connector_name):
                        # Already running — just push the session object
                        await connector_service._push_connector_session_created(
                            user_id, connector_name
                        )
                    else:
                        asyncio.create_task(
                            connector_service.start_connector(
                                user_id, connector_name, creds, async_session_factory
                            )
                        )
    except Exception as _e:
        logger.debug(f"Auto-start connectors error for {user_id}: {_e}")

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            # ── Ping / pong ──────────────────────────────────────
            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

            # ── Session list ─────────────────────────────────────────
            elif msg_type == "list_sessions":
                session_list = [
                    _make_session_obj(sid, "Chat" if sid == "session_main" else sid)
                    for sid in sessions
                ]
                # Append any active connector sessions
                session_list += connector_service.get_all_connector_sessions(user_id)
                await websocket.send_text(
                    json.dumps({"type": "sessions_list", "sessions": session_list})
                )

            # ── New session ──────────────────────────────────────────
            elif msg_type == "new_session":
                new_sid = f"session_{uuid4().hex[:8]}"
                display_name = msg.get("display_name", "New Chat")
                icon = msg.get("icon", "💬")
                sessions[new_sid] = None
                active_sid = new_sid
                session_obj = _make_session_obj(new_sid, display_name, icon)
                await websocket.send_text(
                    json.dumps({"type": "session_created", "session": session_obj})
                )

            # ── Chat message (primary frontend message type) ───────────
            elif msg_type in ("chat", "send_message"):
                # Normalise field names: frontend sends "content", legacy sends "message"
                message_text = (msg.get("content") or msg.get("message") or "").strip()
                if not message_text:
                    continue

                sid = msg.get("session_id") or active_sid
                if sid not in sessions:
                    sessions[sid] = None
                conv_id = msg.get("conversation_id") or sessions.get(sid)

                # Signal thinking
                await websocket.send_text(json.dumps({"type": "thinking", "session_id": sid}))

                try:
                    async with async_session_factory() as db:
                        runtime = CloudAgentRuntime(user_id=user_id, session=db)
                        result = await runtime.process_message(
                            message=message_text,
                            conversation_id=conv_id,
                        )

                    new_conv_id = result["conversation_id"]
                    sessions[sid] = new_conv_id
                    response_text = result["response"]
                    auto_title = result.get("auto_title")

                    # Send the assistant reply
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "text",
                                "content": response_text,
                                "role": "assistant",
                                "session_id": sid,
                                "conversation_id": new_conv_id,
                            }
                        )
                    )

                    # Signal completion
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "done",
                                "session_id": sid,
                                "conversation_id": new_conv_id,
                            }
                        )
                    )

                    # Notify frontend of the auto-generated title
                    if auto_title:
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "conversation_renamed",
                                    "conversation_id": new_conv_id,
                                    "title": auto_title,
                                    "session_id": sid,
                                }
                            )
                        )

                except Exception as e:
                    logger.error(f"Agent error for user {user_id}: {e}", exc_info=True)
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "error",
                                "message": f"Agent error: {str(e)}",
                                "session_id": sid,
                            }
                        )
                    )

            # ── Stop task ────────────────────────────────────────────
            elif msg_type == "stop_task":
                sid = msg.get("session_id", active_sid)
                # CloudAgentRuntime does not yet support mid-flight cancellation;
                # acknowledge so the frontend spinner clears.
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "task_stopped",
                            "message": "Task stopped.",
                            "session_id": sid,
                        }
                    )
                )

            # ── Resume conversation (load previous chat history) ──────
            elif msg_type in ("resume_conversation", "load_conversation"):
                conv_id = msg.get("conversation_id")
                sid = msg.get("session_id") or active_sid
                if not conv_id:
                    continue
                try:
                    async with async_session_factory() as db:
                        conv = await db.get(Conversation, conv_id)
                        if not conv or conv.user_id != user_id:
                            await websocket.send_text(
                                json.dumps(
                                    {
                                        "type": "error",
                                        "message": "Conversation not found.",
                                        "session_id": sid,
                                    }
                                )
                            )
                            continue
                        result = await db.execute(
                            select(Message)
                            .where(Message.conversation_id == conv_id)
                            .order_by(Message.created_at)
                        )
                        messages = result.scalars().all()
                        # Link this session to the resumed conversation
                        sessions[sid] = conv_id
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "conversation_resumed",
                                    "conversation_id": conv_id,
                                    "session_id": sid,
                                    "messages": [
                                        {
                                            "role": m.role,
                                            "content": m.content,
                                            "created_at": (
                                                m.created_at.timestamp() if m.created_at else 0
                                            ),
                                        }
                                        for m in messages
                                    ],
                                }
                            )
                        )
                except Exception as e:
                    logger.error(f"resume_conversation error: {e}", exc_info=True)
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "error",
                                "message": f"Failed to load conversation: {e}",
                                "session_id": sid,
                            }
                        )
                    )

            # ── Delete session ───────────────────────────────────────
            elif msg_type == "delete_session":
                sid = msg.get("session_id")
                if sid and sid in sessions:
                    del sessions[sid]
                    await websocket.send_text(
                        json.dumps({"type": "session_closed", "session_id": sid})
                    )

    except WebSocketDisconnect:
        logger.info(f"WS disconnected: user {user_id}")
    except Exception as e:
        logger.error(f"WS error for user {user_id}: {e}", exc_info=True)
    finally:
        active_connections.pop(user_id, None)
