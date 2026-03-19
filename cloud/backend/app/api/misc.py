"""
Stub endpoints that the local Plutus UI expects but are not applicable
(or have simplified behaviour) in the cloud deployment.

All endpoints require a valid Clerk JWT so the frontend can call them
after sign-in without hitting 401/404 errors.
"""

from fastapi import APIRouter, Depends

from app.api.auth import get_current_user

router = APIRouter()


# ---------------------------------------------------------------------------
# Updates
# ---------------------------------------------------------------------------


@router.get("/updates/check")
async def check_updates(_user=Depends(get_current_user)):
    """Cloud is always up-to-date — no self-update mechanism."""
    return {
        "update_available": False,
        "current_version": "cloud",
        "latest_version": "cloud",
    }


@router.post("/updates/dismiss")
async def dismiss_update(_body: dict | None = None, _user=Depends(get_current_user)):
    return {"message": "ok"}


@router.post("/updates/apply")
async def apply_update(_user=Depends(get_current_user)):
    return {"success": False, "previous_version": "cloud", "error": "Not applicable in cloud mode"}


# ---------------------------------------------------------------------------
# Keep-Alive
# ---------------------------------------------------------------------------


@router.get("/keep-alive")
async def get_keep_alive(_user=Depends(get_current_user)):
    """Keep-alive is not needed in cloud (always-on service)."""
    return {"enabled": False, "interval_seconds": 0}


@router.put("/keep-alive")
async def set_keep_alive(_body: dict | None = None, _user=Depends(get_current_user)):
    return {"enabled": False, "message": "Not applicable in cloud mode"}


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


@router.get("/heartbeat")
async def get_heartbeat(_user=Depends(get_current_user)):
    """Heartbeat is not needed in cloud (always-on service)."""
    return {"enabled": False, "interval_seconds": 0, "last_beat": None}


@router.put("/heartbeat")
async def update_heartbeat(_body: dict | None = None, _user=Depends(get_current_user)):
    return {"enabled": False, "message": "Not applicable in cloud mode"}


@router.post("/heartbeat/start")
async def start_heartbeat(_user=Depends(get_current_user)):
    return {"enabled": False, "message": "Not applicable in cloud mode"}


@router.post("/heartbeat/stop")
async def stop_heartbeat(_user=Depends(get_current_user)):
    return {"enabled": False, "message": "Not applicable in cloud mode"}


# ---------------------------------------------------------------------------
# API Keys status
# ---------------------------------------------------------------------------


@router.get("/keys/status")
async def get_keys_status(_user=Depends(get_current_user)):
    """
    In cloud mode, API keys are managed server-side.
    Report all providers as configured so the UI doesn't show a setup prompt.
    """
    return {
        "providers": {
            "anthropic": True,
            "openai": True,
        },
        "current_provider": "anthropic",
        "current_provider_configured": True,
    }


@router.post("/keys")
async def set_key(_body: dict | None = None, _user=Depends(get_current_user)):
    return {"message": "Keys are managed server-side in cloud mode", "key_configured": True}


@router.delete("/keys/{provider}")
async def delete_key(provider: str, _user=Depends(get_current_user)):
    return {"message": f"Key deletion for {provider} not applicable in cloud mode"}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@router.get("/config")
async def get_config(_user=Depends(get_current_user)):
    """Return a minimal cloud config so the settings page renders correctly."""
    return {
        "mode": "cloud",
        "version": "cloud",
        "features": {
            "bridge": True,
            "connectors": True,
            "memory": True,
            "skills": True,
            "scheduled_tasks": True,
        },
    }


@router.patch("/config")
async def update_config(_body: dict | None = None, _user=Depends(get_current_user)):
    return {"message": "ok"}


# ---------------------------------------------------------------------------
# Connectors  (cloud uses the bridge — no local connectors)
# ---------------------------------------------------------------------------

_CLOUD_CONNECTORS = [
    # ── Messaging connectors ──────────────────────────────────────────────
    {
        "name": "telegram",
        "display_name": "Telegram",
        "description": "Receive and respond to messages via your Telegram bot.",
        "icon": "Send",
        "category": "messaging",
        "configured": False,
        "connected": False,
        "auto_start": False,
        "config": {},
        "config_schema": [
            {
                "name": "bot_token",
                "label": "Bot Token",
                "type": "password",
                "required": True,
                "placeholder": "123456:ABC-DEF...",
                "help": "Create a bot via @BotFather and paste the token here.",
            }
        ],
        "features": ["two_way"],
        "docs_url": "https://core.telegram.org/bots",
    },
    {
        "name": "discord",
        "display_name": "Discord",
        "description": "Interact with your Plutus agent via a Discord bot.",
        "icon": "MessageCircle",
        "category": "messaging",
        "configured": False,
        "connected": False,
        "auto_start": False,
        "config": {},
        "config_schema": [
            {
                "name": "bot_token",
                "label": "Bot Token",
                "type": "password",
                "required": True,
                "placeholder": "Your Discord bot token",
                "help": "Create a bot in the Discord Developer Portal.",
            }
        ],
        "features": ["two_way"],
        "docs_url": "https://discord.com/developers/docs",
    },
    {
        "name": "slack",
        "display_name": "Slack",
        "description": "Interact with your Plutus agent via a Slack app.",
        "icon": "MessageSquare",
        "category": "messaging",
        "configured": False,
        "connected": False,
        "auto_start": False,
        "config": {},
        "config_schema": [
            {
                "name": "bot_token",
                "label": "Bot Token",
                "type": "password",
                "required": True,
                "placeholder": "xoxb-...",
                "help": "Create a Slack app and add a bot token.",
            }
        ],
        "features": [],
        "docs_url": "https://api.slack.com/",
    },
    {
        "name": "email",
        "display_name": "Email",
        "description": "Send and receive tasks via email.",
        "icon": "Mail",
        "category": "messaging",
        "configured": False,
        "connected": False,
        "auto_start": False,
        "config": {},
        "config_schema": [
            {
                "name": "smtp_host",
                "label": "SMTP Host",
                "type": "text",
                "required": True,
                "placeholder": "smtp.gmail.com",
                "help": "SMTP server hostname.",
            },
            {
                "name": "smtp_port",
                "label": "SMTP Port",
                "type": "number",
                "required": True,
                "placeholder": "587",
                "help": "SMTP server port.",
            },
            {
                "name": "username",
                "label": "Username",
                "type": "text",
                "required": True,
                "placeholder": "you@example.com",
                "help": "Email address or username.",
            },
            {
                "name": "password",
                "label": "Password / App Password",
                "type": "password",
                "required": True,
                "placeholder": "••••••••",
                "help": "Your email password or app-specific password.",
            },
        ],
        "features": [],
        "docs_url": None,
    },
]


@router.get("/connectors")
async def list_connectors(_user=Depends(get_current_user)):
    return {"connectors": _CLOUD_CONNECTORS}


@router.get("/connectors/{name}")
async def get_connector(name: str, _user=Depends(get_current_user)):
    for c in _CLOUD_CONNECTORS:
        if c["name"] == name:
            return c
    return {}


@router.put("/connectors/{name}/config")
async def update_connector_config(
    name: str, _body: dict | None = None, _user=Depends(get_current_user)
):
    return {"message": "ok"}


@router.post("/connectors/{name}/test")
async def test_connector(name: str, _user=Depends(get_current_user)):
    return {"success": False, "message": "Not yet implemented"}


@router.post("/connectors/{name}/start")
async def start_connector(name: str, _user=Depends(get_current_user)):
    return {"status": "starting", "message": "Not yet implemented"}


@router.post("/connectors/{name}/stop")
async def stop_connector(name: str, _user=Depends(get_current_user)):
    return {"status": "stopped"}


@router.delete("/connectors/{name}")
async def disconnect_connector(name: str, _user=Depends(get_current_user)):
    return {"message": "disconnected"}


@router.put("/connectors/{name}/auto-start")
async def set_connector_auto_start(
    name: str, _body: dict | None = None, _user=Depends(get_current_user)
):
    return {"message": "ok"}


@router.post("/connectors/{name}/authorize")
async def authorize_connector(name: str, _user=Depends(get_current_user)):
    return {"message": "Not yet implemented"}


@router.post("/connectors/{name}/send")
async def send_connector_message(
    name: str, _body: dict | None = None, _user=Depends(get_current_user)
):
    return {"message": "Not yet implemented"}


@router.post("/connectors/custom")
async def create_custom_connector(_body: dict | None = None, _user=Depends(get_current_user)):
    return {"message": "Custom connectors not yet supported in cloud mode"}


# ---------------------------------------------------------------------------
# Setup / Onboarding — always complete in cloud
# ---------------------------------------------------------------------------


@router.post("/setup/complete")
async def complete_setup(_user=Depends(get_current_user)):
    return {"message": "ok"}
