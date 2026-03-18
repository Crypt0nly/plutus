from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from app.api.auth import get_current_user, get_clerk_jwks
import jwt, json

router = APIRouter()
active_bridges: dict[str, WebSocket] = {}


@router.get("/status")
async def bridge_status(user=Depends(get_current_user)):
    uid = user["sub"]
    return {"connected": uid in active_bridges}


@router.post("/send-task")
async def send_task(body: dict, user=Depends(get_current_user)):
    uid = user["sub"]
    if uid not in active_bridges:
        raise HTTPException(status_code=503, detail="Bridge not connected")
    task_type = body.get("task_type")
    payload = body.get("payload", {})
    await active_bridges[uid].send_text(
        json.dumps({"type": "task", "task_type": task_type, "payload": payload})
    )
    return {"status": "sent"}


@router.websocket("/ws/{token}")
async def bridge_ws(websocket: WebSocket, token: str):
    try:
        jwks = await get_clerk_jwks()
        # Build RSA public key from JWKS
        header = jwt.get_unverified_header(token)
        key = None
        for k in jwks.get("keys", []):
            if k["kid"] == header["kid"]:
                key = jwt.algorithms.RSAAlgorithm.from_jwk(k)
                break
        if not key:
            await websocket.close(code=4001)
            return
        claims = jwt.decode(token, key, algorithms=["RS256"], options={"verify_aud": False})
        uid = claims["sub"]
    except Exception:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    active_bridges[uid] = websocket
    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")
            if msg_type == "heartbeat":
                await websocket.send_text(json.dumps({"type": "heartbeat_ack"}))
            elif msg_type == "task_result":
                pass  # handled by caller polling or webhooks
            elif msg_type == "sync":
                pass  # forward to sync service (extend here)
    except WebSocketDisconnect:
        pass
    finally:
        active_bridges.pop(uid, None)
