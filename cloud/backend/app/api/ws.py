"""
WebSocket endpoint for real-time chat with the Plutus cloud agent.

The frontend connects to /ws?token=<clerk_jwt> and exchanges JSON messages
in the same format as the local Plutus backend, so the existing UI works
without modification.
"""

import json
import logging
from uuid import uuid4

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agent.runtime import CloudAgentRuntime
from app.api.auth import get_clerk_jwks
from app.database import async_session_factory

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


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = ""):
    """
    Main WebSocket endpoint. The frontend passes the Clerk JWT as ?token=...

    Supported incoming message types (matching local backend protocol):
      - ping
      - list_sessions
      - send_message  { session_id?, message, conversation_id? }
      - new_session
      - delete_session { session_id }

    Outgoing message types (matching local backend protocol):
      - connected
      - thinking
      - text { content, role }
      - done
      - error { message }
      - sessions { sessions }
      - pong
    """
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

    # Default session state
    session_id = "session_main"
    conversation_id: str | None = None

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

            elif msg_type == "list_sessions":
                # Return a single default session for cloud users
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "sessions",
                            "sessions": [
                                {
                                    "id": "session_main",
                                    "display_name": "Cloud Session",
                                    "icon": "cloud",
                                    "is_connector": False,
                                    "is_processing": False,
                                    "created_at": "",
                                    "last_active": "",
                                }
                            ],
                        }
                    )
                )

            elif msg_type == "new_session":
                # Create a new session (just a new conversation)
                new_sid = f"session_{uuid4().hex[:8]}"
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "sessions",
                            "sessions": [
                                {
                                    "id": new_sid,
                                    "display_name": "New Session",
                                    "icon": "cloud",
                                    "is_connector": False,
                                    "is_processing": False,
                                    "created_at": "",
                                    "last_active": "",
                                }
                            ],
                        }
                    )
                )

            elif msg_type == "send_message":
                message_text = msg.get("message", "").strip()
                if not message_text:
                    continue

                # Use session_id and conversation_id from message if provided
                sid = msg.get("session_id", session_id)
                conv_id = msg.get("conversation_id") or conversation_id

                # Indicate thinking
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "thinking",
                            "session_id": sid,
                        }
                    )
                )

                try:
                    async with async_session_factory() as db:
                        runtime = CloudAgentRuntime(user_id=user_id, session=db)
                        result = await runtime.process_message(
                            message=message_text,
                            conversation_id=conv_id,
                        )

                    conversation_id = result["conversation_id"]
                    response_text = result["response"]

                    # Send the response as a text message
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "text",
                                "content": response_text,
                                "role": "assistant",
                                "session_id": sid,
                                "conversation_id": conversation_id,
                            }
                        )
                    )

                    # Signal completion
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "done",
                                "session_id": sid,
                                "conversation_id": conversation_id,
                            }
                        )
                    )

                except Exception as e:
                    logger.error(f"Agent error for user {user_id}: {e}")
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "error",
                                "message": f"Agent error: {str(e)}",
                                "session_id": sid,
                            }
                        )
                    )

            elif msg_type == "delete_session":
                # Acknowledge deletion (no persistent sessions in basic cloud mode)
                pass

    except WebSocketDisconnect:
        logger.info(f"WS disconnected: user {user_id}")
    except Exception as e:
        logger.error(f"WS error for user {user_id}: {e}")
    finally:
        active_connections.pop(user_id, None)
