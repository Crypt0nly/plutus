"""Custom API Connector — generic REST API connector for user-defined services.

Users (or the agent) can create custom connectors by providing:
  - A name and description
  - A base URL
  - Authentication type and credentials
  - Optional default headers

The connector then provides a generic HTTP client that can call any endpoint
on the configured service. This is the same pattern used by Zapier, Make, n8n.

Custom connectors are stored in ~/.plutus/connectors/custom_<name>.json
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import aiohttp

from plutus.connectors.base import BaseConnector, ConnectorConfig, CONNECTORS_DIR
from plutus.utils.ssl_utils import make_aiohttp_connector

logger = logging.getLogger("plutus.connectors.custom_api")

CUSTOM_CONNECTORS_DIR = Path.home() / ".plutus" / "custom_connectors"


def _ensure_custom_dir() -> Path:
    CUSTOM_CONNECTORS_DIR.mkdir(parents=True, exist_ok=True)
    return CUSTOM_CONNECTORS_DIR


class CustomAPIConnector(BaseConnector):
    """A generic REST API connector that can be configured for any service."""

    category = "custom"

    def __init__(self, connector_id: str, display_name: str = "", description: str = ""):
        self.name = f"custom_{connector_id}"
        self.connector_id = connector_id
        self.display_name = display_name or connector_id.replace("_", " ").title()
        self.description = description or f"Custom API connector: {self.display_name}"
        self.icon = "Plug"
        super().__init__()

    def _sensitive_fields(self) -> list[str]:
        return ["api_key", "token", "password"]

    def config_schema(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "base_url",
                "label": "Base URL",
                "type": "text",
                "required": True,
                "placeholder": "https://api.example.com/v1",
                "help": "The base URL for all API requests",
            },
            {
                "name": "auth_type",
                "label": "Authentication Type",
                "type": "select",
                "required": True,
                "options": ["none", "api_key", "bearer_token", "basic_auth"],
                "placeholder": "none",
                "help": "How to authenticate with the API",
            },
            {
                "name": "api_key",
                "label": "API Key",
                "type": "password",
                "required": False,
                "placeholder": "Your API key",
                "help": "API key (for api_key auth type). Sent as X-API-Key header.",
            },
            {
                "name": "token",
                "label": "Bearer Token",
                "type": "password",
                "required": False,
                "placeholder": "Your bearer token",
                "help": "Bearer token (for bearer_token auth type)",
            },
            {
                "name": "username",
                "label": "Username",
                "type": "text",
                "required": False,
                "placeholder": "Username for basic auth",
                "help": "Username (for basic_auth type)",
            },
            {
                "name": "password",
                "label": "Password",
                "type": "password",
                "required": False,
                "placeholder": "Password for basic auth",
                "help": "Password (for basic_auth type)",
            },
            {
                "name": "default_headers",
                "label": "Default Headers (JSON)",
                "type": "text",
                "required": False,
                "placeholder": '{"Content-Type": "application/json"}',
                "help": "Additional headers to include with every request (JSON object)",
            },
        ]

    async def test_connection(self) -> dict[str, Any]:
        """Test the connection by making a simple request to the base URL."""
        base_url = self._config.get("base_url", "").rstrip("/")
        if not base_url:
            return {"success": False, "message": "No base URL configured"}

        try:
            headers = self._build_headers()
            async with aiohttp.ClientSession(connector=make_aiohttp_connector()) as session:
                async with session.get(base_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    return {
                        "success": resp.status < 500,
                        "message": f"HTTP {resp.status} — {'Connected' if resp.status < 500 else 'Server error'}",
                        "status_code": resp.status,
                    }
        except aiohttp.ClientError as e:
            return {"success": False, "message": f"Connection failed: {str(e)}"}
        except Exception as e:
            return {"success": False, "message": f"Error: {str(e)}"}

    async def send_message(self, text: str, **kwargs: Any) -> dict[str, Any]:
        """Not applicable for generic API connectors — use request() instead."""
        return {"success": False, "message": "Use the request() method for custom API connectors"}

    async def request(
        self,
        method: str = "GET",
        endpoint: str = "/",
        body: dict | None = None,
        headers: dict | None = None,
        params: dict | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request to the configured API.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE)
            endpoint: API endpoint path (appended to base_url)
            body: Request body (for POST/PUT/PATCH)
            headers: Additional headers for this request
            params: Query parameters
        """
        base_url = self._config.get("base_url", "").rstrip("/")
        if not base_url:
            return {"success": False, "error": "No base URL configured"}

        url = f"{base_url}{endpoint}" if endpoint.startswith("/") else f"{base_url}/{endpoint}"
        req_headers = self._build_headers()
        if headers:
            req_headers.update(headers)

        try:
            async with aiohttp.ClientSession(connector=make_aiohttp_connector()) as session:
                kwargs_req: dict[str, Any] = {
                    "headers": req_headers,
                    "timeout": aiohttp.ClientTimeout(total=30),
                }
                if params:
                    kwargs_req["params"] = params
                if body and method.upper() in ("POST", "PUT", "PATCH"):
                    kwargs_req["json"] = body

                async with session.request(method.upper(), url, **kwargs_req) as resp:
                    # Try to parse as JSON, fall back to text
                    try:
                        response_body = await resp.json()
                    except Exception:
                        response_body = await resp.text()

                    return {
                        "success": resp.status < 400,
                        "status_code": resp.status,
                        "body": response_body,
                        "headers": dict(resp.headers),
                    }
        except aiohttp.ClientError as e:
            return {"success": False, "error": f"Request failed: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Error: {str(e)}"}

    def _build_headers(self) -> dict[str, str]:
        """Build request headers based on auth config."""
        headers: dict[str, str] = {"Content-Type": "application/json"}

        # Parse default headers
        raw_headers = self._config.get("default_headers", "")
        if raw_headers and isinstance(raw_headers, str):
            try:
                parsed = json.loads(raw_headers)
                if isinstance(parsed, dict):
                    headers.update(parsed)
            except json.JSONDecodeError:
                pass
        elif isinstance(raw_headers, dict):
            headers.update(raw_headers)

        # Apply auth
        auth_type = self._config.get("auth_type", "none")

        if auth_type == "api_key":
            api_key = self._config.get("api_key", "")
            if api_key:
                headers["X-API-Key"] = api_key

        elif auth_type == "bearer_token":
            token = self._config.get("token", "")
            if token:
                headers["Authorization"] = f"Bearer {token}"

        elif auth_type == "basic_auth":
            import base64
            username = self._config.get("username", "")
            password = self._config.get("password", "")
            if username:
                creds = base64.b64encode(f"{username}:{password}".encode()).decode()
                headers["Authorization"] = f"Basic {creds}"

        return headers

    def status(self) -> dict[str, Any]:
        """Return status with custom connector flag."""
        s = super().status()
        s["is_custom"] = True
        s["connector_id"] = self.connector_id
        return s


class CustomConnectorManager:
    """Manages creation, loading, and deletion of custom API connectors.

    Custom connectors are persisted as JSON files in ~/.plutus/custom_connectors/
    and loaded into the main ConnectorManager at startup.
    """

    @staticmethod
    def list_custom_connectors() -> list[dict[str, Any]]:
        """List all saved custom connector definitions."""
        _ensure_custom_dir()
        connectors = []
        for f in sorted(CUSTOM_CONNECTORS_DIR.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                connectors.append(data)
            except Exception:
                continue
        return connectors

    @staticmethod
    def create_custom_connector(
        connector_id: str,
        display_name: str = "",
        description: str = "",
        base_url: str = "",
        auth_type: str = "none",
        credentials: dict[str, str] | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> tuple[bool, str, CustomAPIConnector | None]:
        """Create and persist a new custom connector.

        Returns (success, message, connector_instance).
        """
        # Sanitize connector_id
        connector_id = connector_id.lower().replace(" ", "_").replace("-", "_")
        connector_id = "".join(c for c in connector_id if c.isalnum() or c == "_")

        if not connector_id:
            return False, "Invalid connector ID", None

        if not base_url:
            return False, "Base URL is required", None

        # Save the definition
        _ensure_custom_dir()
        definition = {
            "connector_id": connector_id,
            "display_name": display_name or connector_id.replace("_", " ").title(),
            "description": description or f"Custom API connector for {display_name or connector_id}",
            "base_url": base_url,
            "auth_type": auth_type,
        }
        def_path = CUSTOM_CONNECTORS_DIR / f"{connector_id}.json"
        def_path.write_text(json.dumps(definition, indent=2))

        # Create the connector instance
        connector = CustomAPIConnector(
            connector_id=connector_id,
            display_name=definition["display_name"],
            description=definition["description"],
        )

        # Save the connector config (base_url, auth, credentials)
        config_data = {
            "base_url": base_url,
            "auth_type": auth_type,
        }
        if credentials:
            config_data.update(credentials)
        if default_headers:
            config_data["default_headers"] = json.dumps(default_headers)

        connector.save_config(config_data)

        return True, f"Custom connector '{definition['display_name']}' created", connector

    @staticmethod
    def delete_custom_connector(connector_id: str) -> tuple[bool, str]:
        """Delete a custom connector and its config."""
        def_path = CUSTOM_CONNECTORS_DIR / f"{connector_id}.json"
        config_path = CONNECTORS_DIR / f"custom_{connector_id}.json"

        if not def_path.exists():
            return False, f"Custom connector not found: {connector_id}"

        def_path.unlink(missing_ok=True)
        config_path.unlink(missing_ok=True)
        return True, f"Custom connector '{connector_id}' deleted"

    @staticmethod
    def load_all_custom_connectors() -> list[CustomAPIConnector]:
        """Load all persisted custom connectors and return instances."""
        _ensure_custom_dir()
        connectors = []
        for f in sorted(CUSTOM_CONNECTORS_DIR.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                connector = CustomAPIConnector(
                    connector_id=data["connector_id"],
                    display_name=data.get("display_name", ""),
                    description=data.get("description", ""),
                )
                connectors.append(connector)
            except Exception as e:
                logger.warning(f"Failed to load custom connector from {f}: {e}")
                continue
        return connectors
