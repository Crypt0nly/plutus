"""Base connector system for Plutus.

Connectors allow Plutus to send/receive messages through external services
like Telegram, WhatsApp, and Email. Each connector stores its own config
in ~/.plutus/connectors/<name>.json and provides a unified interface.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

logger = logging.getLogger("plutus.connectors")

CONNECTORS_DIR = Path.home() / ".plutus" / "connectors"


def _ensure_dir() -> Path:
    CONNECTORS_DIR.mkdir(parents=True, exist_ok=True)
    return CONNECTORS_DIR


class ConnectorConfig:
    """Persistent config storage for a single connector."""

    def __init__(self, name: str):
        self.name = name
        self._path = _ensure_dir() / f"{name}.json"

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text())
        except Exception:
            return {}

    def save(self, data: dict[str, Any]) -> None:
        _ensure_dir()
        self._path.write_text(json.dumps(data, indent=2))

    def delete(self) -> None:
        if self._path.exists():
            self._path.unlink()


class BaseConnector(ABC):
    """Abstract base class for all connectors."""

    name: str = ""
    display_name: str = ""
    description: str = ""
    icon: str = ""  # Lucide icon name for the UI
    category: str = "messaging"  # "messaging" or "ai"

    def __init__(self):
        self._config_store = ConnectorConfig(self.name)
        self._config: dict[str, Any] = self._config_store.load()
        self._running = False

    @property
    def is_configured(self) -> bool:
        """Whether the connector has been configured with required credentials."""
        return bool(self._config.get("configured"))

    @property
    def auto_start(self) -> bool:
        """Whether this connector should auto-start when Plutus launches."""
        return bool(self._config.get("auto_start", False))

    def set_auto_start(self, enabled: bool) -> None:
        """Set whether this connector should auto-start on launch."""
        self._config["auto_start"] = enabled
        self._config_store.save(self._config)

    @property
    def is_connected(self) -> bool:
        """Whether the connector is currently active/connected."""
        return self._running

    def get_config(self) -> dict[str, Any]:
        """Return the config with sensitive fields cleared (never sent to UI)."""
        config = dict(self._config)
        # Clear sensitive fields — only send a flag so the UI knows they're set
        for key in self._sensitive_fields():
            if key in config and config[key]:
                config[f"_has_{key}"] = True
                config[key] = ""
            else:
                config[f"_has_{key}"] = False
                config[key] = ""
        return config

    def get_raw_config(self) -> dict[str, Any]:
        """Return the raw config (internal use only, not exposed via API)."""
        return dict(self._config)

    def save_config(self, data: dict[str, Any]) -> None:
        """Save connector configuration."""
        # Don't overwrite real credentials with masked values from the UI
        for field in self._sensitive_fields():
            val = data.get(field, "")
            if not val or "••" in str(val):
                data.pop(field, None)
        self._config.update(data)
        self._config["configured"] = True
        self._config_store.save(self._config)

    def clear_config(self) -> None:
        """Remove all connector configuration."""
        self._config = {}
        self._config_store.delete()
        self._running = False

    @abstractmethod
    def _sensitive_fields(self) -> list[str]:
        """Return list of field names that should be masked in API responses."""
        ...

    @abstractmethod
    def config_schema(self) -> list[dict[str, Any]]:
        """Return the configuration schema for the UI to render form fields.

        Each field: {"name": str, "label": str, "type": "text"|"password"|"number",
                     "required": bool, "placeholder": str, "help": str}
        """
        ...

    @abstractmethod
    async def test_connection(self) -> dict[str, Any]:
        """Test the connection and return {"success": bool, "message": str, ...}."""
        ...

    @abstractmethod
    async def send_message(self, text: str, **kwargs: Any) -> dict[str, Any]:
        """Send a message through this connector."""
        ...

    async def start(self) -> None:
        """Start the connector (e.g., start polling for messages)."""
        self._running = True

    async def stop(self) -> None:
        """Stop the connector."""
        self._running = False

    def status(self) -> dict[str, Any]:
        """Return the connector status for the API."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "icon": self.icon,
            "category": self.category,
            "configured": self.is_configured,
            "connected": self.is_connected,
            "auto_start": self.auto_start,
            "config": self.get_config(),
            "config_schema": self.config_schema(),
        }


class ConnectorManager:
    """Manages all registered connectors."""

    def __init__(self):
        self._connectors: dict[str, BaseConnector] = {}

    def register(self, connector: BaseConnector) -> None:
        self._connectors[connector.name] = connector
        logger.info(f"Registered connector: {connector.name}")

    def get(self, name: str) -> BaseConnector | None:
        return self._connectors.get(name)

    def list_all(self) -> list[dict[str, Any]]:
        return [c.status() for c in self._connectors.values()]

    def get_configured(self) -> list[BaseConnector]:
        return [c for c in self._connectors.values() if c.is_configured]

    async def start_all(self) -> None:
        """Start all configured connectors."""
        for c in self.get_configured():
            try:
                await c.start()
                logger.info(f"Started connector: {c.name}")
            except Exception as e:
                logger.error(f"Failed to start connector {c.name}: {e}")

    async def stop_all(self) -> None:
        """Stop all running connectors."""
        for c in self._connectors.values():
            if c.is_connected:
                try:
                    await c.stop()
                except Exception:
                    pass
