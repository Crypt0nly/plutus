"""Google OAuth 2.0 server-side flow for cloud connector authentication.

Flow:
1. User clicks "Connect with Google" in the connector settings
2. Frontend calls GET /api/connectors/google/authorize?service=gmail&user_id=...
3. Backend redirects to Google consent screen
4. Google redirects back to /api/connectors/google/callback?code=...&state=...
5. Backend exchanges code for tokens, stores in user.connector_credentials
6. Backend redirects user back to the frontend settings page
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import settings

logger = logging.getLogger("plutus.google_oauth")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

SCOPES: dict[str, list[str]] = {
    "gmail": [
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.labels",
    ],
    "google_calendar": [
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.events",
    ],
    "google_drive": [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/documents.readonly",
    ],
}

# ---------------------------------------------------------------------------
# State token helpers (CSRF protection)
# ---------------------------------------------------------------------------


def _make_state(user_id: str, service: str) -> str:
    """Create a signed state token encoding user_id and service."""
    payload = json.dumps({"user_id": user_id, "service": service, "ts": int(time.time())})
    sig = hmac.new(
        settings.secret_key.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()[:16]  # noqa: S324 — HMAC-SHA256 is intentional here
    import base64

    b64 = base64.urlsafe_b64encode(payload.encode()).decode()
    return f"{b64}.{sig}"


def _verify_state(state: str) -> dict[str, str] | None:
    """Verify and decode a state token. Returns None if invalid/expired."""
    try:
        import base64

        b64, sig = state.rsplit(".", 1)
        payload = base64.urlsafe_b64decode(b64 + "==").decode()
        expected_sig = hmac.new(
            settings.secret_key.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected_sig):
            return None
        data = json.loads(payload)
        # Expire after 10 minutes
        if time.time() - data.get("ts", 0) > 600:
            return None
        return data
    except Exception:
        return None


# ---------------------------------------------------------------------------
# OAuth URL builder
# ---------------------------------------------------------------------------


def build_authorize_url(
    user_id: str,
    service: str,
    client_id: str | None = None,
) -> str:
    """Build the Google OAuth authorization URL for a given service.

    ``client_id`` overrides the server-level ``settings.google_client_id`` so
    that users who have stored their own OAuth app credentials can use them.
    """
    scopes = SCOPES.get(service, [])
    if not scopes:
        raise ValueError(f"Unknown Google service: {service}")

    effective_client_id = client_id or settings.google_client_id
    if not effective_client_id:
        raise ValueError(
            "No Google Client ID available. "
            "Please save your Google Client ID in the connector settings first."
        )

    redirect_uri = f"{settings.server_base_url}/api/connectors/google/callback"
    state = _make_state(user_id, service)

    params = {
        "client_id": effective_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        # access_type=online: we only need a short-lived access token.
        # No refresh token is stored or required — the user simply re-authorizes
        # when the token expires (same behaviour as the local version).
        "access_type": "online",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


# ---------------------------------------------------------------------------
# Token exchange
# ---------------------------------------------------------------------------


async def exchange_code_for_tokens(
    code: str,
    service: str,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> dict[str, Any]:
    """Exchange an authorization code for an access token (online flow, no refresh token).

    ``client_id`` and ``client_secret`` override the server-level settings so
    that users who have stored their own OAuth app credentials can use them.
    """
    effective_client_id = client_id or settings.google_client_id
    effective_client_secret = client_secret or settings.google_client_secret

    if not effective_client_id or not effective_client_secret:
        raise RuntimeError(
            "No Google OAuth credentials available for token exchange. "
            "Please save your Google Client ID and Secret in the connector settings."
        )

    redirect_uri = f"{settings.server_base_url}/api/connectors/google/callback"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "client_id": effective_client_id,
                "client_secret": effective_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Token exchange failed: {resp.status_code} — {resp.text[:200]}")
        data = resp.json()
        # We use access_type=online so Google won't return a refresh_token.
        # We only store the access_token and its expiry; the user re-authorizes
        # when it expires (same behaviour as the local version).
        return {
            "access_token": data["access_token"],
            "expires_at": time.time() + data.get("expires_in", 3600),
            "scope": data.get("scope", ""),
        }


# ---------------------------------------------------------------------------
# Get a valid access token
# ---------------------------------------------------------------------------


async def get_valid_access_token(tokens: dict[str, Any]) -> str:
    """Return a valid access token.

    Since we use access_type=online (no refresh token), we simply return the
    stored access token.  If it has expired the caller will receive a 401 from
    Google and should prompt the user to re-authorize via the Connectors tab.
    """
    if not tokens:
        raise RuntimeError("No Google OAuth tokens found. Please reconnect via the Connectors tab.")

    access_token = tokens.get("access_token", "")
    if not access_token:
        raise RuntimeError("No access token stored. Please reconnect via the Connectors tab.")

    # Warn if the token looks expired, but still return it — the Google API
    # will reject it with a 401 which the caller can surface to the user.
    expires_at = tokens.get("expires_at", 0)
    if expires_at and time.time() > expires_at:
        logger.warning(
            "Google access token appears expired (expires_at=%s). "
            "User should re-authorize via the Connectors tab.",
            expires_at,
        )

    return access_token
