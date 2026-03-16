"""Web Hosting Connectors — Vercel and Netlify.

These connectors store deployment tokens (not API keys) and expose
them to the web_deploy tool so Plutus can publish websites publicly.
Tokens are stored via SecretsStore (~/.plutus/.secrets.json, chmod 600).
"""

from __future__ import annotations

import os
from typing import Any

from plutus.connectors.base import BaseConnector


class WebHostingConnector(BaseConnector):
    """Base class for web hosting connectors (Vercel, Netlify).

    Stores a deployment token securely and validates it by hitting the
    provider's API to confirm it's valid.
    """

    category = "hosting"
    env_var: str = ""          # e.g. "VERCEL_TOKEN"
    token_key: str = ""        # SecretsStore key, e.g. "vercel_token"
    docs_url: str = ""
    features: list[str] = []

    @property
    def is_configured(self) -> bool:
        if os.environ.get(self.env_var):
            return True
        try:
            from plutus.config import SecretsStore
            return SecretsStore().has_key(self.token_key)
        except Exception:
            return False

    def _sensitive_fields(self) -> list[str]:
        return ["token"]

    def get_config(self) -> dict[str, Any]:
        config = dict(self._config)
        token = self._get_token()
        config["_has_token"] = bool(token)
        config["token"] = ""
        return config

    def _get_token(self) -> str | None:
        env_token = os.environ.get(self.env_var)
        if env_token:
            return env_token
        try:
            from plutus.config import SecretsStore
            return SecretsStore().get_key(self.token_key)
        except Exception:
            return None

    def save_config(self, data: dict[str, Any]) -> None:
        token = data.pop("token", None)
        if token and not token.startswith("••"):
            from plutus.config import SecretsStore
            SecretsStore().set_key(self.token_key, token)
            os.environ[self.env_var] = token
        self._config.update(data)
        self._config["configured"] = True
        self._config_store.save(self._config)

    def clear_config(self) -> None:
        try:
            from plutus.config import SecretsStore
            SecretsStore().delete_key(self.token_key)
        except Exception:
            pass
        os.environ.pop(self.env_var, None)
        super().clear_config()

    def config_schema(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "token",
                "label": "Deploy Token",
                "type": "password",
                "required": True,
                "placeholder": f"Paste your {self.display_name} token here",
                "help": f"Create a token at {self.docs_url}" if self.docs_url else "",
            },
        ]

    async def test_connection(self) -> dict[str, Any]:
        token = self._get_token()
        if not token:
            return {
                "success": False,
                "message": f"No token configured. Get one from {self.docs_url}",
            }
        return await self._test_with_token(token)

    async def _test_with_token(self, token: str) -> dict[str, Any]:
        """Override in subclasses to validate the token."""
        return {"success": True, "message": "Token is set"}

    async def send_message(self, text: str, **kwargs: Any) -> dict[str, Any]:
        return {"success": False, "message": "Hosting connectors don't support messaging"}

    def status(self) -> dict[str, Any]:
        configured = self.is_configured
        return {
            "name": self.name,
            "configured": configured,
            "connected": configured,
            "listening": False,
        }


class VercelConnector(WebHostingConnector):
    """Vercel hosting connector — stores a Vercel deploy token."""

    name = "vercel"
    display_name = "Vercel"
    description = (
        "Deploy websites and web apps to Vercel's global edge network. "
        "Supports React, Next.js, Vue, Svelte, Astro, and static HTML/CSS/JS."
    )
    icon = "Globe"
    category = "hosting"
    env_var = "VERCEL_TOKEN"
    token_key = "vercel_token"
    docs_url = "https://vercel.com/account/tokens"
    features = ["React", "Next.js", "Vue", "Svelte", "Astro", "Static", "Node.js"]

    async def _test_with_token(self, token: str) -> dict[str, Any]:
        """Validate the Vercel token by calling the /v2/user endpoint."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.vercel.com/v2/user",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    username = data.get("user", {}).get("username", "unknown")
                    return {
                        "success": True,
                        "message": f"Connected as @{username} on Vercel",
                    }
                elif resp.status_code == 401:
                    return {"success": False, "message": "Invalid token — please check and re-enter it"}
                else:
                    return {"success": False, "message": f"Vercel API returned {resp.status_code}"}
        except Exception as e:
            return {"success": False, "message": f"Connection test failed: {e}"}


class NetlifyConnector(WebHostingConnector):
    """Netlify hosting connector — stores a Netlify personal access token."""

    name = "netlify"
    display_name = "Netlify"
    description = (
        "Deploy websites to Netlify's global CDN with instant rollbacks. "
        "Great for static sites, Gatsby, Hugo, and JAMstack apps."
    )
    icon = "Globe"
    category = "hosting"
    env_var = "NETLIFY_TOKEN"
    token_key = "netlify_token"
    docs_url = "https://app.netlify.com/user/applications/personal"
    features = ["Static", "Gatsby", "Hugo", "Astro", "React", "Vue", "JAMstack"]

    async def _test_with_token(self, token: str) -> dict[str, Any]:
        """Validate the Netlify token by calling the /api/v1/user endpoint."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.netlify.com/api/v1/user",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    email = data.get("email", "unknown")
                    return {
                        "success": True,
                        "message": f"Connected as {email} on Netlify",
                    }
                elif resp.status_code == 401:
                    return {"success": False, "message": "Invalid token — please check and re-enter it"}
                else:
                    return {"success": False, "message": f"Netlify API returned {resp.status_code}"}
        except Exception as e:
            return {"success": False, "message": f"Connection test failed: {e}"}
