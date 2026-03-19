"""
Stub endpoints that the local Plutus UI expects but are not applicable
(or have simplified behaviour) in the cloud deployment.

All endpoints require a valid Clerk JWT so the frontend can call them
after sign-in without hitting 401/404 errors.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_session

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
    return {
        "success": False,
        "previous_version": "cloud",
        "error": "Not applicable in cloud mode",
    }


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
# Connectors — full catalogue for cloud
# ---------------------------------------------------------------------------

_CLOUD_CONNECTORS = [
    # ── AI Providers ──────────────────────────────────────────────────────────
    {
        "name": "openai",
        "display_name": "OpenAI",
        "description": "Connect your own OpenAI API key to use GPT-4o and other models.",
        "icon": "Brain",
        "category": "ai",
        "configured": False,
        "connected": False,
        "auto_start": False,
        "config": {},
        "config_schema": [
            {
                "name": "api_key",
                "label": "API Key",
                "type": "password",
                "required": True,
                "placeholder": "sk-...",
                "help": "Find your key at platform.openai.com/api-keys",
            }
        ],
        "features": [],
        "docs_url": "https://platform.openai.com/docs",
    },
    {
        "name": "anthropic",
        "display_name": "Anthropic",
        "description": "Connect your own Anthropic API key to use Claude models.",
        "icon": "Sparkles",
        "category": "ai",
        "configured": False,
        "connected": False,
        "auto_start": False,
        "config": {},
        "config_schema": [
            {
                "name": "api_key",
                "label": "API Key",
                "type": "password",
                "required": True,
                "placeholder": "sk-ant-...",
                "help": "Find your key at console.anthropic.com/settings/keys",
            }
        ],
        "features": [],
        "docs_url": "https://docs.anthropic.com",
    },
    {
        "name": "gemini",
        "display_name": "Google Gemini",
        "description": "Connect your own Google Gemini API key for Gemini Pro and Flash.",
        "icon": "Wand2",
        "category": "ai",
        "configured": False,
        "connected": False,
        "auto_start": False,
        "config": {},
        "config_schema": [
            {
                "name": "api_key",
                "label": "API Key",
                "type": "password",
                "required": True,
                "placeholder": "AIza...",
                "help": "Get your key at aistudio.google.com/app/apikey",
            }
        ],
        "features": [],
        "docs_url": "https://ai.google.dev/docs",
    },
    {
        "name": "ollama",
        "display_name": "Ollama (Local)",
        "description": "Connect to a local Ollama instance to use open-source models.",
        "icon": "Server",
        "category": "ai",
        "configured": False,
        "connected": False,
        "auto_start": False,
        "config": {},
        "config_schema": [
            {
                "name": "base_url",
                "label": "Ollama URL",
                "type": "text",
                "required": True,
                "placeholder": "http://localhost:11434",
                "help": "The URL where your Ollama server is running.",
            }
        ],
        "features": [],
        "docs_url": "https://ollama.com",
    },
    # ── Google Workspace ──────────────────────────────────────────────────────
    {
        "name": "gmail",
        "display_name": "Gmail",
        "description": "Read, send and manage your Gmail messages.",
        "icon": "Mail",
        "category": "google",
        "auth_type": "oauth",
        "configured": False,
        "connected": False,
        "auto_start": False,
        "config": {},
        "config_schema": [],
        "features": [],
        "docs_url": "https://developers.google.com/gmail/api",
    },
    {
        "name": "google_calendar",
        "display_name": "Google Calendar",
        "description": "Create, read and manage your Google Calendar events.",
        "icon": "Calendar",
        "category": "google",
        "auth_type": "oauth",
        "configured": False,
        "connected": False,
        "auto_start": False,
        "config": {},
        "config_schema": [],
        "features": [],
        "docs_url": "https://developers.google.com/calendar",
    },
    {
        "name": "google_drive",
        "display_name": "Google Drive",
        "description": "Read, upload and manage files in your Google Drive.",
        "icon": "HardDrive",
        "category": "google",
        "auth_type": "oauth",
        "configured": False,
        "connected": False,
        "auto_start": False,
        "config": {},
        "config_schema": [],
        "features": [],
        "docs_url": "https://developers.google.com/drive",
    },
    # ── Web Hosting / Deployments ─────────────────────────────────────────────
    {
        "name": "vercel",
        "display_name": "Vercel",
        "description": "Deploy and manage websites on Vercel.",
        "icon": "Rocket",
        "category": "hosting",
        "configured": False,
        "connected": False,
        "auto_start": False,
        "config": {},
        "config_schema": [
            {
                "name": "api_token",
                "label": "API Token",
                "type": "password",
                "required": True,
                "placeholder": "vercel_...",
                "help": "Create a token at vercel.com/account/tokens",
            }
        ],
        "features": [],
        "docs_url": "https://vercel.com/docs/rest-api",
    },
    {
        "name": "netlify",
        "display_name": "Netlify",
        "description": "Deploy and manage sites on Netlify.",
        "icon": "Globe",
        "category": "hosting",
        "configured": False,
        "connected": False,
        "auto_start": False,
        "config": {},
        "config_schema": [
            {
                "name": "api_token",
                "label": "Personal Access Token",
                "type": "password",
                "required": True,
                "placeholder": "nfp_...",
                "help": "Create a token at app.netlify.com/user/applications",
            }
        ],
        "features": [],
        "docs_url": "https://docs.netlify.com/api/get-started/",
    },
    {
        "name": "github_pages",
        "display_name": "GitHub Pages",
        "description": "Deploy static sites via GitHub Pages.",
        "icon": "Upload",
        "category": "hosting",
        "configured": False,
        "connected": False,
        "auto_start": False,
        "config": {},
        "config_schema": [
            {
                "name": "token",
                "label": "GitHub Token",
                "type": "password",
                "required": True,
                "placeholder": "ghp_...",
                "help": "Create a token at github.com/settings/tokens",
            }
        ],
        "features": [],
        "docs_url": "https://docs.github.com/en/pages",
    },
    # ── Messaging connectors ──────────────────────────────────────────────────
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
        "name": "whatsapp",
        "display_name": "WhatsApp",
        "description": "Chat with Plutus via WhatsApp. Requires a dedicated second phone number — Plutus controls that number and you message it from your personal phone.",
        "icon": "MessageCircle",
        "category": "messaging",
        "configured": False,
        "connected": False,
        "auto_start": False,
        "config": {},
        "config_schema": [
            {
                "name": "phone_number",
                "label": "Plutus Bot Number",
                "type": "text",
                "required": True,
                "placeholder": "+49 176 1234 5678",
                "help": "The phone number of the dedicated WhatsApp account Plutus will control (your second SIM / prepaid number). This is NOT your personal number — you will message this number from your personal phone to talk to Plutus. Enter it in international format, e.g. +14155552671.",
            },
            {
                "name": "default_contact",
                "label": "Your Personal Number (optional)",
                "type": "text",
                "required": False,
                "placeholder": "e.g. +49 176 9876 5432",
                "help": "Your own personal WhatsApp number. If set, Plutus can proactively send you messages (e.g. alerts or task results) without you messaging first.",
            },
        ],
        "features": ["two_way"],
        "docs_url": "https://wwebjs.dev/",
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
    # ── GitHub ────────────────────────────────────────────────────────────────
    {
        "name": "github",
        "display_name": "GitHub",
        "description": "Clone repos, create PRs, manage issues and push code via GitHub.",
        "icon": "Globe",
        "category": "messaging",
        "configured": False,
        "connected": False,
        "auto_start": False,
        "config": {},
        "config_schema": [
            {
                "name": "token",
                "label": "Personal Access Token",
                "type": "password",
                "required": True,
                "placeholder": "ghp_...",
                "help": "Create a fine-grained token at github.com/settings/tokens",
            },
            {
                "name": "username",
                "label": "GitHub Username",
                "type": "text",
                "required": True,
                "placeholder": "your-username",
                "help": "Your GitHub username.",
            },
        ],
        "features": [],
        "docs_url": "https://docs.github.com/en/rest",
    },
]


@router.get("/connectors")
async def list_connectors(
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Return connectors with per-user configured state from DB."""
    from app.models.user import User

    user_row = await db.get(User, _user["user_id"])
    creds: dict = (user_row.connector_credentials or {}) if user_row else {}

    result = []
    for c in _CLOUD_CONNECTORS:
        entry = dict(c)
        if c["name"] in creds:
            entry["configured"] = True
            # Don't leak secrets — mask the config values
            entry["config"] = {k: "••••••••" for k in creds[c["name"]]}
        result.append(entry)
    return {"connectors": result}


@router.get("/connectors/{name}")
async def get_connector(
    name: str,
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    from app.models.user import User

    user_row = await db.get(User, _user["user_id"])
    creds: dict = (user_row.connector_credentials or {}) if user_row else {}

    for c in _CLOUD_CONNECTORS:
        if c["name"] == name:
            entry = dict(c)
            if name in creds:
                entry["configured"] = True
                entry["config"] = {k: "••••••••" for k in creds[name]}
            return entry
    return {}


@router.put("/connectors/{name}/config")
async def update_connector_config(
    name: str,
    body: dict | None = None,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Persist connector credentials in the user's encrypted JSON column."""
    from app.models.user import User

    user_row = await db.get(User, user["user_id"])
    if not user_row:
        return {"message": "ok"}
    creds = dict(user_row.connector_credentials or {})
    if body:
        creds[name] = body
    else:
        creds.pop(name, None)
    user_row.connector_credentials = creds
    await db.commit()
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
async def disconnect_connector(
    name: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    from app.models.user import User

    user_row = await db.get(User, user["user_id"])
    if user_row:
        creds = dict(user_row.connector_credentials or {})
        creds.pop(name, None)
        user_row.connector_credentials = creds
        await db.commit()
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
# Setup / Onboarding — per-user tracking
# ---------------------------------------------------------------------------


@router.post("/setup/complete")
async def complete_setup(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Mark onboarding as completed for this user."""
    from app.models.user import User

    user_row = await db.get(User, user["user_id"])
    if user_row:
        settings = dict(user_row.settings or {})
        settings["onboarding_completed"] = True
        user_row.settings = settings
        await db.commit()
    return {"message": "ok"}
