"""AI provider connectors — manage API keys for LLM and generative AI services.

These connectors don't send messages like messaging connectors. Instead they
manage API keys, inject them into the environment, and validate connectivity.
Keys are stored via SecretsStore (~/.plutus/.secrets.json, chmod 600).
"""

from __future__ import annotations

import os
from typing import Any

from plutus.connectors.base import BaseConnector


class AIProviderConnector(BaseConnector):
    """Base class for AI provider connectors.

    Overrides the default file-based config to use SecretsStore for API keys
    while keeping the connector config file for non-secret metadata.
    """

    category = "ai"
    env_var: str = ""  # e.g. "OPENAI_API_KEY"
    provider_key: str = ""  # key name in SecretsStore, e.g. "openai"
    docs_url: str = ""
    features: list[str] = []  # e.g. ["Chat", "Vision", "Image Generation"]

    @property
    def is_configured(self) -> bool:
        """Check if API key is available (env var or secrets store)."""
        if os.environ.get(self.env_var):
            return True
        try:
            from plutus.config import SecretsStore
            secrets = SecretsStore()
            return secrets.has_key(self.provider_key)
        except Exception:
            return False

    def _sensitive_fields(self) -> list[str]:
        return ["api_key"]

    def get_config(self) -> dict[str, Any]:
        """Return config with key cleared (never sent to UI)."""
        config = dict(self._config)
        # Never send the actual key — only a flag so the UI knows it's set
        key = self._get_key()
        config["_has_api_key"] = bool(key)
        config["api_key"] = ""
        return config

    def _get_key(self) -> str | None:
        """Get the actual API key."""
        env_key = os.environ.get(self.env_var)
        if env_key:
            return env_key
        try:
            from plutus.config import SecretsStore
            secrets = SecretsStore()
            return secrets.get_key(self.provider_key)
        except Exception:
            return None

    def save_config(self, data: dict[str, Any]) -> None:
        """Save API key via SecretsStore, other config normally."""
        api_key = data.pop("api_key", None)
        if api_key and not api_key.startswith("••"):
            # Store via SecretsStore (secure, chmod 600)
            from plutus.config import SecretsStore
            secrets = SecretsStore()
            secrets.set_key(self.provider_key, api_key)
        # Save non-secret config normally
        self._config.update(data)
        self._config["configured"] = True
        self._config_store.save(self._config)

    def clear_config(self) -> None:
        """Remove API key and config."""
        try:
            from plutus.config import SecretsStore
            secrets = SecretsStore()
            secrets.delete_key(self.provider_key)
        except Exception:
            pass
        # Also unset env var for current process
        os.environ.pop(self.env_var, None)
        super().clear_config()

    def config_schema(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "api_key",
                "label": "API Key",
                "type": "password",
                "required": True,
                "placeholder": f"Enter your {self.display_name} API key",
                "help": f"Get your key from {self.docs_url}" if self.docs_url else "",
            },
        ]

    async def test_connection(self) -> dict[str, Any]:
        """Test connectivity by making a lightweight API call."""
        key = self._get_key()
        if not key:
            return {
                "success": False,
                "message": f"No API key configured. Set {self.env_var} or enter it above.",
            }
        return await self._test_with_key(key)

    async def _test_with_key(self, key: str) -> dict[str, Any]:
        """Override in subclasses to test the specific provider."""
        return {"success": True, "message": "API key is set"}

    async def send_message(self, text: str, **kwargs: Any) -> dict[str, Any]:
        """AI connectors don't send messages — they provide API access."""
        return {"success": False, "message": "AI providers don't support direct messaging"}

    def status(self) -> dict[str, Any]:
        """Return status with additional AI-specific fields."""
        base = super().status()
        base["features"] = self.features
        base["docs_url"] = self.docs_url
        return base


class OpenAIConnector(AIProviderConnector):
    name = "openai"
    display_name = "OpenAI"
    description = "GPT-4o, o1, DALL-E, and more"
    icon = "Brain"
    env_var = "OPENAI_API_KEY"
    provider_key = "openai"
    docs_url = "https://platform.openai.com/api-keys"
    features = ["Chat", "Vision", "Image Generation", "TTS", "STT"]

    async def _test_with_key(self, key: str) -> dict[str, Any]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
                if resp.status_code == 200:
                    return {"success": True, "message": "Connected to OpenAI API"}
                elif resp.status_code == 401:
                    return {"success": False, "message": "Invalid API key"}
                else:
                    return {"success": False, "message": f"API returned status {resp.status_code}"}
        except Exception as e:
            return {"success": False, "message": f"Connection failed: {e}"}


class AnthropicConnector(AIProviderConnector):
    name = "anthropic"
    display_name = "Anthropic"
    description = "Claude Opus, Sonnet, and Haiku models"
    icon = "Sparkles"
    env_var = "ANTHROPIC_API_KEY"
    provider_key = "anthropic"
    docs_url = "https://console.anthropic.com/settings/keys"
    features = ["Chat", "Vision", "Tool Use", "Computer Use"]

    async def _test_with_key(self, key: str) -> dict[str, Any]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": key,
                        "anthropic-version": "2023-06-01",
                    },
                )
                if resp.status_code == 200:
                    return {"success": True, "message": "Connected to Anthropic API"}
                elif resp.status_code == 401:
                    return {"success": False, "message": "Invalid API key"}
                else:
                    return {"success": False, "message": f"API returned status {resp.status_code}"}
        except Exception as e:
            return {"success": False, "message": f"Connection failed: {e}"}


class GeminiConnector(AIProviderConnector):
    name = "gemini"
    display_name = "Google Gemini"
    description = "Gemini models, Nano Banana image gen, and Veo video gen"
    icon = "Wand2"
    env_var = "GEMINI_API_KEY"
    provider_key = "gemini"
    docs_url = "https://aistudio.google.com/apikey"
    features = ["Chat", "Vision", "Image Generation", "Video Generation"]

    def save_config(self, data: dict[str, Any]) -> None:
        """Also set GOOGLE_API_KEY since google-genai checks both."""
        super().save_config(data)
        # Ensure GOOGLE_API_KEY is also set for google-genai SDK
        key = self._get_key()
        if key and not os.environ.get("GOOGLE_API_KEY"):
            os.environ["GOOGLE_API_KEY"] = key

    async def _test_with_key(self, key: str) -> dict[str, Any]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
                )
                if resp.status_code == 200:
                    return {"success": True, "message": "Connected to Google Gemini API"}
                elif resp.status_code == 400 or resp.status_code == 403:
                    return {"success": False, "message": "Invalid API key"}
                else:
                    return {"success": False, "message": f"API returned status {resp.status_code}"}
        except Exception as e:
            return {"success": False, "message": f"Connection failed: {e}"}


class OllamaConnector(AIProviderConnector):
    name = "ollama"
    display_name = "Ollama"
    description = "Run local models — Llama, Mistral, Qwen, and more"
    icon = "Server"
    env_var = "OLLAMA_HOST"
    provider_key = "ollama"
    docs_url = "https://ollama.ai"
    features = ["Chat", "Vision", "Local"]

    @property
    def is_configured(self) -> bool:
        """Ollama is configured if the host is reachable (no API key needed)."""
        return bool(self._config.get("configured"))

    def config_schema(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "host",
                "label": "Ollama Host",
                "type": "text",
                "required": False,
                "placeholder": "http://localhost:11434",
                "help": "Leave blank for default (localhost:11434). Change if running remotely.",
            },
        ]

    def _sensitive_fields(self) -> list[str]:
        return []

    def get_config(self) -> dict[str, Any]:
        return dict(self._config)

    def save_config(self, data: dict[str, Any]) -> None:
        host = data.get("host", "").strip()
        if host:
            os.environ["OLLAMA_HOST"] = host
        self._config.update(data)
        self._config["configured"] = True
        self._config_store.save(self._config)

    def clear_config(self) -> None:
        os.environ.pop("OLLAMA_HOST", None)
        super().clear_config()

    async def _test_with_key(self, key: str) -> dict[str, Any]:
        host = self._config.get("host", "").strip() or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{host}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("models", [])
                    count = len(models)
                    if count:
                        names = ", ".join(
                            m.get("name", "?") for m in models[:5]
                        )
                        extra = f" (+{count - 5} more)" if count > 5 else ""
                        msg = f"Connected — {count} models: {names}{extra}"
                    else:
                        msg = "Connected — no models pulled yet"
                    return {"success": True, "message": msg}
                else:
                    return {
                        "success": False,
                        "message": f"Ollama returned status {resp.status_code}",
                    }
        except Exception as e:
            return {"success": False, "message": f"Cannot reach Ollama at {host}: {e}"}

    async def test_connection(self) -> dict[str, Any]:
        return await self._test_with_key("")
