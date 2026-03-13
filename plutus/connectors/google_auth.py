"""Google OAuth 2.0 PKCE flow for desktop/native apps.

Handles the full OAuth lifecycle:
  1. Generate PKCE code verifier/challenge
  2. Build authorization URL → user opens in browser
  3. Spin up a temporary localhost HTTP server to catch the callback
  4. Exchange auth code (with PKCE proof) for access + refresh tokens
  5. Persist tokens in ~/.plutus/connectors/<name>.json
  6. Auto-refresh expired access tokens

No client secret required — Google treats Desktop/Native OAuth clients as
"public clients" where PKCE replaces the secret.

Reference: https://developers.google.com/identity/protocols/oauth2/native-app
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

logger = logging.getLogger("plutus.connectors.google_auth")

# ── Defaults ─────────────────────────────────────────────────────────────────

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# Scopes per service
SCOPES = {
    "gmail": [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
    ],
    "calendar": [
        "https://www.googleapis.com/auth/calendar",
    ],
    "drive": [
        "https://www.googleapis.com/auth/drive.file",
    ],
}

TOKENS_DIR = Path.home() / ".plutus" / "connectors"


# ── PKCE helpers ─────────────────────────────────────────────────────────────

def _generate_code_verifier() -> str:
    """Generate a 64-char cryptographic random code verifier."""
    return secrets.token_urlsafe(48)[:64]


def _generate_code_challenge(verifier: str) -> str:
    """SHA-256 hash → base64url encode (S256 method)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# ── Token storage ────────────────────────────────────────────────────────────

def load_tokens(service: str) -> dict[str, Any]:
    """Load stored tokens for a Google service."""
    path = TOKENS_DIR / f"google_{service}.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return data.get("tokens", {})
    except Exception:
        return {}


def save_tokens(service: str, tokens: dict[str, Any]) -> None:
    """Persist tokens securely."""
    TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    path = TOKENS_DIR / f"google_{service}.json"
    # Read existing file to preserve non-token config
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except Exception:
            pass
    existing["tokens"] = tokens
    existing["configured"] = True
    path.write_text(json.dumps(existing, indent=2))
    # Restrict permissions (owner-only read/write)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def clear_tokens(service: str) -> None:
    """Remove stored tokens."""
    path = TOKENS_DIR / f"google_{service}.json"
    if path.exists():
        path.unlink()


# ── Token refresh ────────────────────────────────────────────────────────────

async def get_valid_access_token(
    service: str, client_id: str
) -> str | None:
    """Return a valid access token, refreshing if expired."""
    tokens = load_tokens(service)
    if not tokens:
        return None

    access_token = tokens.get("access_token")
    expires_at = tokens.get("expires_at", 0)
    refresh_token = tokens.get("refresh_token")

    # If token is still valid (with 60s buffer), use it
    if access_token and time.time() < expires_at - 60:
        return access_token

    # Need to refresh
    if not refresh_token:
        return None

    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(TOKEN_URL, data={
                "client_id": client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            })
            if resp.status_code != 200:
                logger.error(f"Token refresh failed: {resp.status_code} {resp.text}")
                return None

            data = resp.json()
            tokens["access_token"] = data["access_token"]
            tokens["expires_at"] = time.time() + data.get("expires_in", 3600)
            # Google may issue a new refresh token
            if "refresh_token" in data:
                tokens["refresh_token"] = data["refresh_token"]
            save_tokens(service, tokens)
            return tokens["access_token"]
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        return None


# ── OAuth flow ───────────────────────────────────────────────────────────────

class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Temporary HTTP handler that captures the OAuth callback."""

    auth_code: str | None = None
    error: str | None = None

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "error" in params:
            _OAuthCallbackHandler.error = params["error"][0]
            body = (
                "<html><body style='font-family:system-ui;text-align:center;padding:60px'>"
                "<h2>Authorization Failed</h2>"
                f"<p>Error: {params['error'][0]}</p>"
                "<p>You can close this tab.</p></body></html>"
            )
        elif "code" in params:
            _OAuthCallbackHandler.auth_code = params["code"][0]
            body = (
                "<html><body style='font-family:system-ui;text-align:center;padding:60px'>"
                "<h2>Authorized!</h2>"
                "<p>Plutus has been connected to your Google account.</p>"
                "<p>You can close this tab and return to Plutus.</p></body></html>"
            )
        else:
            body = (
                "<html><body style='font-family:system-ui;text-align:center;padding:60px'>"
                "<h2>Unexpected Response</h2>"
                "<p>No authorization code received.</p></body></html>"
            )

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, format, *args):
        # Suppress default HTTP log output
        pass


async def start_oauth_flow(
    service: str,
    client_id: str,
    scopes: list[str] | None = None,
    port: int = 0,
) -> dict[str, Any]:
    """Run the full OAuth PKCE flow.

    1. Generates PKCE verifier/challenge
    2. Opens the user's browser to Google consent screen
    3. Listens on localhost for the callback
    4. Exchanges the code for tokens
    5. Stores tokens and returns result

    Args:
        service: Google service name (gmail, calendar, drive)
        client_id: OAuth client ID from Google Cloud Console
        scopes: OAuth scopes (defaults to SCOPES[service])
        port: Localhost port for callback (0 = auto-assign)

    Returns:
        {"success": bool, "message": str}
    """
    if scopes is None:
        scopes = SCOPES.get(service, [])
    if not scopes:
        return {"success": False, "message": f"No scopes defined for service: {service}"}

    code_verifier = _generate_code_verifier()
    code_challenge = _generate_code_challenge(code_verifier)

    # Reset handler state
    _OAuthCallbackHandler.auth_code = None
    _OAuthCallbackHandler.error = None

    # Start temporary HTTP server
    server = HTTPServer(("127.0.0.1", port), _OAuthCallbackHandler)
    actual_port = server.server_address[1]
    redirect_uri = f"http://127.0.0.1:{actual_port}"

    # Build authorization URL
    auth_params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": secrets.token_urlsafe(16),
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"{AUTH_URL}?{urlencode(auth_params)}"

    # Open browser
    logger.info(f"Opening browser for Google {service} authorization")
    webbrowser.open(auth_url)

    # Wait for callback in a thread (so we don't block the event loop)
    def _serve_once():
        server.timeout = 120  # 2-minute timeout
        server.handle_request()
        server.server_close()

    await asyncio.to_thread(_serve_once)

    # Check result
    if _OAuthCallbackHandler.error:
        return {
            "success": False,
            "message": f"Authorization denied: {_OAuthCallbackHandler.error}",
        }

    auth_code = _OAuthCallbackHandler.auth_code
    if not auth_code:
        return {"success": False, "message": "No authorization code received (timeout?)"}

    # Exchange auth code for tokens
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(TOKEN_URL, data={
                "client_id": client_id,
                "code": auth_code,
                "code_verifier": code_verifier,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            })

            if resp.status_code != 200:
                return {
                    "success": False,
                    "message": f"Token exchange failed: {resp.status_code} — {resp.text[:200]}",
                }

            token_data = resp.json()
            tokens = {
                "access_token": token_data["access_token"],
                "refresh_token": token_data.get("refresh_token", ""),
                "expires_at": time.time() + token_data.get("expires_in", 3600),
                "scope": token_data.get("scope", ""),
            }
            save_tokens(service, tokens)

            return {
                "success": True,
                "message": f"Google {service.title()} connected successfully!",
            }
    except Exception as e:
        return {"success": False, "message": f"Token exchange error: {e}"}
