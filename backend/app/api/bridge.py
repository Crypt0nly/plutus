import json
import os
import tempfile
import zipfile

import jwt
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, StreamingResponse

from app.api.auth import _find_signing_key, get_clerk_jwks, get_current_user

router = APIRouter()
active_bridges: dict[str, WebSocket] = {}

# Bridge source files are bundled alongside the backend image
_BRIDGE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "bridge")

# The public cloud WebSocket URL (used in generated install scripts)
_CLOUD_WS_URL = os.getenv("BRIDGE_WS_URL", "wss://api.useplutus.ai/api/bridge/ws")
_CLOUD_API_URL = os.getenv("API_URL", "https://api.useplutus.ai")


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
        readme = (
            "# Plutus Bridge\n\n"
            "## One-command install (recommended)\n\n"
            "Visit your Plutus dashboard → Settings → Bridge and click **Install Service**.\n"
            "Copy the one-liner for your OS and paste it into a terminal.\n"
            "The bridge will start automatically on every login and restart on crash.\n\n"
            "## Manual run\n\n"
            "1. Install dependencies:\n"
            "   pip install -r requirements.txt\n\n"
            "2. Run the bridge:\n"
            f"   python plutus_bridge.py --server {_CLOUD_WS_URL} --token <your-session-token>\n"
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


@router.get("/install-script")
async def bridge_install_script(platform: str = "macos", user=Depends(get_current_user)):
    """
    Return a one-liner shell script (or batch file on Windows) that:
      1. Downloads plutus_bridge.py
      2. Installs Python dependencies
      3. Runs --install to register the OS auto-start service

    The user's Clerk session token is baked in so they only need to paste
    one command and everything configures itself automatically.

    Query params:
      platform: macos | linux | windows
    """
    # We derive the token from the Authorization header that was already
    # validated by get_current_user; re-read it from the request scope
    # is complex, so we issue a fresh bridge install token instead by
    # embedding the user's subject claim as the token payload.
    # The bridge WebSocket route already validates the full Clerk JWT,
    # so we pass the raw Clerk token that get_current_user validated.
    # Since we can't easily recover the raw token here, we instruct the
    # frontend to pass it as a query param below.
    uid = user["sub"]
    token_placeholder = "__TOKEN__"  # frontend substitutes the real token

    bridge_url = f"{_CLOUD_API_URL}/api/bridge/download"
    ws_url = _CLOUD_WS_URL

    platform = platform.lower()

    if platform in ("macos", "linux"):
        script = f"""\
#!/usr/bin/env bash
# Plutus Bridge – one-command auto-start installer
# Generated for user {uid}
set -e

BRIDGE_DIR="$HOME/.plutus"
mkdir -p "$BRIDGE_DIR"

echo "⬇️  Downloading Plutus Bridge..."
curl -fsSL "{bridge_url}" -o "$BRIDGE_DIR/plutus_bridge.zip"

echo "📦  Extracting..."
cd "$BRIDGE_DIR"
unzip -o plutus_bridge.zip plutus_bridge.py requirements.txt 2>/dev/null || unzip -o plutus_bridge.zip plutus_bridge.py
rm -f plutus_bridge.zip

echo "🐍  Installing Python dependencies..."
python3 -m pip install --quiet websockets httpx

echo "⚙️   Installing auto-start service..."
python3 "$BRIDGE_DIR/plutus_bridge.py" \\
    --install \\
    --server "{ws_url}" \\
    --token "{token_placeholder}"

echo ""
echo "✅  Done! Plutus Bridge is installed and running."
echo "    It will restart automatically if it crashes or your computer reboots."
"""
    elif platform == "windows":
        script = f"""\
@echo off
REM Plutus Bridge – one-command auto-start installer (Windows)
REM Generated for user {uid}

set BRIDGE_DIR=%USERPROFILE%\\.plutus
if not exist "%BRIDGE_DIR%" mkdir "%BRIDGE_DIR%"

echo Downloading Plutus Bridge...
curl -fsSL "{bridge_url}" -o "%BRIDGE_DIR%\\plutus_bridge.zip"

echo Extracting...
powershell -Command "Expand-Archive -Force '%BRIDGE_DIR%\\plutus_bridge.zip' '%BRIDGE_DIR%'"
del "%BRIDGE_DIR%\\plutus_bridge.zip"

echo Installing Python dependencies...
python -m pip install --quiet websockets httpx

echo Installing auto-start service...
python "%BRIDGE_DIR%\\plutus_bridge.py" --install --server "{ws_url}" --token "{token_placeholder}"

echo.
echo Done! Plutus Bridge is installed and will start automatically on login.
pause
"""
    else:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}. Use macos, linux, or windows.")

    return PlainTextResponse(script, media_type="text/plain")


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
        header = jwt.get_unverified_header(token)
        key = await _find_signing_key(jwks, header["kid"])
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
            elif msg_type in ("task_result", "tool_result"):
                # Resolved by the hybrid_executor pending futures
                pass
            elif msg_type == "sync":
                pass
    except WebSocketDisconnect:
        pass
    finally:
        active_bridges.pop(uid, None)
