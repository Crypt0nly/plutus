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
async def get_keys_status(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Return which providers the user has configured an API key for."""
    from app.models.user import User

    user_row = await db.get(User, user["user_id"])
    creds: dict = (user_row.connector_credentials or {}) if user_row else {}

    has_anthropic = bool(creds.get("anthropic", {}).get("api_key"))
    has_openai = bool(creds.get("openai", {}).get("api_key"))
    has_gemini = bool(creds.get("gemini", {}).get("api_key"))

    current = "anthropic" if has_anthropic else ("openai" if has_openai else "")
    return {
        "providers": {
            "anthropic": has_anthropic,
            "openai": has_openai,
            "gemini": has_gemini,
        },
        "current_provider": current,
        "current_provider_configured": bool(current),
    }


@router.post("/keys")
async def set_key(
    body: dict | None = None,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Save a provider API key to the user's connector_credentials."""
    from app.models.user import User

    if not body:
        return {"message": "ok", "key_configured": False}

    provider = body.get("provider", "")
    key = body.get("key", "")
    if not provider or not key:
        return {"message": "ok", "key_configured": False}

    user_row = await db.get(User, user["user_id"])
    if not user_row:
        user_row = User(
            id=user["user_id"],
            email=user.get("email", ""),
            connector_credentials={},
        )
        db.add(user_row)

    creds = dict(user_row.connector_credentials or {})
    creds[provider] = {"api_key": key}
    user_row.connector_credentials = creds
    await db.commit()
    return {"message": "ok", "key_configured": True}


@router.delete("/keys/{provider}")
async def delete_key(provider: str, _user=Depends(get_current_user)):
    return {"message": f"Key deletion for {provider} not applicable in cloud mode"}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@router.get("/config")
async def get_config(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Return cloud config including persisted user preferences (model, agent, etc.)."""
    from app.models.user import User

    user_row = await db.get(User, user["user_id"])
    saved = (user_row.settings or {}).get("agent_config", {}) if user_row else {}
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
        # Merge in any user-saved preferences so the settings page pre-populates
        **saved,
    }


@router.patch("/config")
async def update_config(
    body: dict | None = None,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Persist user agent config preferences (model, provider, system prompt, etc.)."""
    from app.models.user import User

    if body:
        patch = body.get("patch", body)  # frontend sends {patch: {...}} or bare dict
        user_row = await db.get(User, user["user_id"])
        if user_row:
            existing = dict(user_row.settings or {})
            existing_cfg = dict(existing.get("agent_config", {}))
            # Deep-merge top-level keys (model, agent, heartbeat, etc.)
            for k, v in patch.items():
                if isinstance(v, dict) and isinstance(existing_cfg.get(k), dict):
                    existing_cfg[k] = {**existing_cfg[k], **v}
                else:
                    existing_cfg[k] = v
            existing["agent_config"] = existing_cfg
            user_row.settings = existing
            await db.commit()
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
        "description": (
            "Chat with Plutus via WhatsApp. Works with your existing number "
            "(Plutus links as a secondary device, like WhatsApp Web) "
            "or a dedicated second number."
        ),
        "icon": "MessageCircle",
        "category": "messaging",
        "configured": False,
        "connected": False,
        "auto_start": False,
        "config": {},
        "config_schema": [
            {
                "name": "phone_number",
                "label": "WhatsApp Phone Number",
                "type": "text",
                "required": True,
                "placeholder": "+49 176 1234 5678",
                "help": (
                    "The WhatsApp number Plutus will link to as a secondary device "
                    "(like WhatsApp Web). "
                    "Option A \u2014 Your own number: Plutus links to your account; "
                    "message yourself or use \u2018Message yourself\u2019 in WhatsApp "
                    "to talk to Plutus. "
                    "Option B \u2014 A second/dedicated number: Plutus controls that number; "
                    "message it from your personal phone. "
                    "Enter in international format, e.g. +14155552671."
                ),
            },
            {
                "name": "default_contact",
                "label": "Your Personal Number (optional)",
                "type": "text",
                "required": False,
                "placeholder": "e.g. +49 176 9876 5432",
                "help": (
                    "Your own personal WhatsApp number. If set, Plutus can proactively "
                    "send you messages (e.g. alerts or task results) without you messaging first."
                ),
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
        # Create user row on the fly
        user_row = User(
            id=user["user_id"],
            email=user.get("email", ""),
            connector_credentials={},
        )
        db.add(user_row)

    creds = dict(user_row.connector_credentials or {})
    if body:
        # The frontend wraps fields in a { "config": { ... } } envelope.
        # Unwrap it so we store the flat field dict directly.
        config_data = body.get("config", body)
        creds[name] = config_data
    else:
        creds.pop(name, None)
    user_row.connector_credentials = creds
    await db.commit()
    return {"message": "Configuration saved", "configured": True}


@router.post("/connectors/{name}/test")
async def test_connector(
    name: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Test a connector by validating its stored credentials."""
    import httpx

    from app.models.user import User

    user_row = await db.get(User, user["user_id"])
    creds: dict = (user_row.connector_credentials or {}) if user_row else {}
    cfg: dict = creds.get(name, {})

    if not cfg:
        return {
            "success": False,
            "message": "No credentials saved. Please fill in the fields and click Save first.",
        }

    # ── Per-connector validation ──────────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if name == "anthropic":
                key = cfg.get("api_key", "")
                if not key:
                    return {"success": False, "message": "API key is required"}
                resp = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                )
                if resp.status_code == 200:
                    return {"success": True, "message": "Anthropic API key is valid"}
                return {"success": False, "message": f"Invalid API key (HTTP {resp.status_code})"}

            elif name == "openai":
                key = cfg.get("api_key", "")
                if not key:
                    return {"success": False, "message": "API key is required"}
                resp = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
                if resp.status_code == 200:
                    return {"success": True, "message": "OpenAI API key is valid"}
                return {"success": False, "message": f"Invalid API key (HTTP {resp.status_code})"}

            elif name == "gemini":
                key = cfg.get("api_key", "")
                if not key:
                    return {"success": False, "message": "API key is required"}
                resp = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
                )
                if resp.status_code == 200:
                    return {"success": True, "message": "Gemini API key is valid"}
                return {"success": False, "message": f"Invalid API key (HTTP {resp.status_code})"}

            elif name == "telegram":
                token = cfg.get("bot_token", "")
                if not token:
                    return {"success": False, "message": "Bot token is required"}
                resp = await client.get(f"https://api.telegram.org/bot{token}/getMe")
                data = resp.json()
                if data.get("ok"):
                    bot = data["result"]
                    return {
                        "success": True,
                        "message": (
                            f"Connected to @{bot.get('username', '')} ({bot.get('first_name', '')})"
                        ),
                    }
                return {"success": False, "message": data.get("description", "Invalid token")}

            elif name == "discord":
                token = cfg.get("bot_token", "")
                if not token:
                    return {"success": False, "message": "Bot token is required"}
                resp = await client.get(
                    "https://discord.com/api/v10/users/@me",
                    headers={"Authorization": f"Bot {token}"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    uname = data.get("username", "bot")
                    disc = data.get("discriminator", "0")
                    return {
                        "success": True,
                        "message": f"Connected as {uname}#{disc}",
                    }
                return {"success": False, "message": f"Invalid bot token (HTTP {resp.status_code})"}

            elif name == "github_pages":
                token = cfg.get("token", "")
                if not token:
                    return {"success": False, "message": "Personal access token is required"}
                resp = await client.get(
                    "https://api.github.com/user",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    login = data.get("login", "user")
                    return {"success": True, "message": f"Authenticated as {login}"}
                return {"success": False, "message": f"Invalid token (HTTP {resp.status_code})"}

            elif name in ("vercel", "netlify"):
                token = cfg.get("api_token", "")
                if not token:
                    return {"success": False, "message": "API token is required"}
                if name == "vercel":
                    resp = await client.get(
                        "https://api.vercel.com/v2/user",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        return {
                            "success": True,
                            "message": (
                                "Authenticated as " + data.get("user", {}).get("username", "user")
                            ),
                        }
                    return {"success": False, "message": f"Invalid token (HTTP {resp.status_code})"}
                else:  # netlify
                    resp = await client.get(
                        "https://api.netlify.com/api/v1/user",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        return {
                            "success": True,
                            "message": f"Authenticated as {data.get('email', 'user')}",
                        }
                    return {"success": False, "message": f"Invalid token (HTTP {resp.status_code})"}

            else:
                # Generic: just confirm credentials are saved
                return {
                    "success": True,
                    "message": (
                        "Credentials saved. Connection test not available for this connector."
                    ),
                }
    except httpx.TimeoutException:
        return {
            "success": False,
            "message": "Connection timed out. Check your internet connection.",
        }
    except Exception as exc:
        return {"success": False, "message": f"Test failed: {exc}"}


@router.get("/connectors/{name}/status")
async def connector_status(
    name: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Return the current running state of a connector bridge."""
    from app.models.user import User
    from app.services.connector_service import is_running

    user_id = user["user_id"]
    listening = is_running(user_id, name)

    # For WhatsApp, also return pairing_code and ready flag from DB
    extra: dict = {}
    if name == "whatsapp":
        user_row = await db.get(User, user_id)
        if user_row:
            creds = (user_row.connector_credentials or {}).get(name, {})
            extra["pairing_code"] = creds.get("pairing_code")
            extra["whatsapp_ready"] = creds.get("ready", False)

    return {"listening": listening, **extra}


@router.post("/connectors/{name}/start")
async def start_connector(
    name: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Start a server-side bridge for a communication connector."""
    from app.database import async_session_factory
    from app.models.user import User
    from app.services.connector_service import start_connector as svc_start

    user_id = user["user_id"]
    user_row = await db.get(User, user_id)
    creds: dict = {}
    if user_row:
        all_creds = user_row.connector_credentials or {}
        creds = all_creds.get(name, {})

    if not creds:
        return {
            "status": "error",
            "listening": False,
            "message": (f"No credentials found for {name}. Please configure the connector first."),
        }

    result = await svc_start(user_id, name, creds, async_session_factory)

    # Persist the listening flag so the connector auto-restarts on reconnect.
    if result.get("listening"):
        if user_row:
            all_creds = dict(user_row.connector_credentials or {})
            connector_creds = dict(all_creds.get(name, {}))
            connector_creds["listening"] = True
            all_creds[name] = connector_creds
            user_row.connector_credentials = all_creds
            await db.commit()

    return result


@router.post("/connectors/{name}/stop")
async def stop_connector(
    name: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Stop the server-side bridge for a communication connector."""
    from app.models.user import User
    from app.services.connector_service import stop_connector as svc_stop

    user_id = user["user_id"]
    result = await svc_stop(user_id, name)

    # Clear the listening flag so the connector does not auto-restart.
    user_row = await db.get(User, user_id)
    if user_row:
        all_creds = dict(user_row.connector_credentials or {})
        connector_creds = dict(all_creds.get(name, {}))
        connector_creds["listening"] = False
        all_creds[name] = connector_creds
        user_row.connector_credentials = all_creds
        await db.commit()

    return result


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
    """Mark onboarding as completed for this user.

    Creates the user row if it does not exist yet (first-time users complete
    onboarding before sending their first message, so the row may not exist).
    """
    from app.models.user import User

    user_row = await db.get(User, user["user_id"])
    if user_row:
        settings = dict(user_row.settings or {})
        settings["onboarding_completed"] = True
        user_row.settings = settings
    else:
        # First-time user: create the row with onboarding already marked done
        user_row = User(
            id=user["user_id"],
            email=user.get("email") or f"{user['user_id']}@clerk.local",
            plan="free",
            settings={"onboarding_completed": True},
            connector_credentials={},
        )
        db.add(user_row)
    await db.commit()
    return {"message": "ok"}
