import json
import os
import zipfile
import tempfile

import jwt
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.api.auth import get_clerk_jwks, get_current_user

router = APIRouter()
active_bridges: dict[str, WebSocket] = {}

# Bridge source files are bundled alongside the backend image
_BRIDGE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "bridge")


@router.get("/download")
async def download_bridge(user=Depends(get_current_user)):
    """Return a zip archive containing plutus_bridge.py and requirements.txt."""
    bridge_script = os.path.join(_BRIDGE_DIR, "plutus_bridge.py")
    requirements = os.path.join(_BRIDGE_DIR, "requirements.txt")

    if not os.path.exists(bridge_script):
        raise HTTPException(status_code=404, detail="Bridge files not found")

    # Build zip in memory
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(bridge_script, "plutus_bridge.py")
        if os.path.exists(requirements):
            zf.write(requirements, "requirements.txt")
        # Add a quick-start README
        readme = (
            "# Plutus Bridge\n\n"
            "1. Install dependencies:\n"
            "   pip install -r requirements.txt\n\n"
            "2. Run the bridge (replace TOKEN with your Clerk session token):\n"
            "   python plutus_bridge.py --server wss://api.useplutus.ai/api/bridge/ws/TOKEN\n"
        )
        zf.writestr("README.md", readme)
    tmp.close()

    def iter_file():
        with open(tmp.name, "rb") as f:
            yield from f
        os.unlink(tmp.name)

    return StreamingResponse(
        iter_file(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=plutus_bridge.zip"},
    )


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
