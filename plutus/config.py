"""Configuration management for Plutus.

Config is stored at ~/.plutus/config.json and managed via the CLI or web UI.
API keys are stored separately in ~/.plutus/.secrets.json with restricted permissions.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


def plutus_dir() -> Path:
    """Return the Plutus home directory, creating it if needed."""
    p = Path.home() / ".plutus"
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_path() -> Path:
    return plutus_dir() / "config.json"


class ModelConfig(BaseModel):
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-6"
    api_key_env: str = "ANTHROPIC_API_KEY"
    base_url: str | None = None
    temperature: float = 0.7
    max_tokens: int = 4096


class ToolOverride(BaseModel):
    enabled: bool = True
    require_approval: bool = False


class GuardrailsConfig(BaseModel):
    tier: str = "assistant"
    tool_overrides: dict[str, ToolOverride] = Field(default_factory=dict)
    audit_enabled: bool = True
    max_concurrent_tools: int = 3


class GatewayConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 7777
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


class MemoryConfig(BaseModel):
    db_path: str = ""  # empty = ~/.plutus/memory.db
    max_conversation_history: int = 100
    context_window_messages: int = 20


class HeartbeatConfig(BaseModel):
    enabled: bool = False
    interval_seconds: int = 300  # default: 5 minutes
    quiet_hours_start: str | None = None  # e.g. "23:00" — pause heartbeats
    quiet_hours_end: str | None = None  # e.g. "07:00" — resume heartbeats
    max_consecutive: int = 50  # stop after N heartbeats with no user interaction
    prompt: str = ""  # custom heartbeat prompt; empty = use default


class WorkerConfig(BaseModel):
    max_concurrent_workers: int = 3  # max simultaneous agent workers
    default_timeout: int = 300  # default worker timeout in seconds
    worker_model: str = "claude-haiku"  # default model for workers


class ModelRoutingConfig(BaseModel):
    primary_provider: str = "anthropic"
    enabled_models: list[str] = Field(default_factory=lambda: [
        "claude-opus", "claude-sonnet", "claude-haiku"
    ])
    default_model: str = "claude-sonnet"
    auto_route: bool = True  # auto-select model based on task complexity
    cost_conscious: bool = False  # prefer cheaper models when possible
    worker_model: str = "claude-haiku"  # default model for workers
    scheduler_model: str = "claude-haiku"  # default model for scheduled jobs


class SchedulerConfig(BaseModel):
    enabled: bool = True  # enable the scheduler on startup
    max_concurrent_jobs: int = 3  # max jobs running simultaneously


class AgentConfig(BaseModel):
    max_tool_rounds: int = 25  # max external tool rounds per message (plan calls don't count)


class PlannerConfig(BaseModel):
    enabled: bool = True
    auto_plan: bool = True  # agent creates a plan automatically for complex tasks
    show_progress: bool = True  # emit plan progress events to UI


class PlutusConfig(BaseSettings):
    model: ModelConfig = Field(default_factory=ModelConfig)
    guardrails: GuardrailsConfig = Field(default_factory=GuardrailsConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)
    planner: PlannerConfig = Field(default_factory=PlannerConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    workers: WorkerConfig = Field(default_factory=WorkerConfig)
    model_routing: ModelRoutingConfig = Field(default_factory=ModelRoutingConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    skills_dir: str = ""  # empty = ~/.plutus/skills

    @classmethod
    def load(cls) -> PlutusConfig:
        """Load config from disk, or return defaults."""
        path = config_path()
        if path.exists():
            data = json.loads(path.read_text())
            return cls(**data)
        return cls()

    def save(self) -> None:
        """Persist config to disk."""
        path = config_path()
        path.write_text(json.dumps(self.model_dump(), indent=2))

    def resolve_skills_dir(self) -> Path:
        if self.skills_dir:
            return Path(self.skills_dir)
        p = plutus_dir() / "skills"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def resolve_memory_db(self) -> str:
        if self.memory.db_path:
            return self.memory.db_path
        return str(plutus_dir() / "memory.db")

    def update(self, patch: dict[str, Any]) -> None:
        """Merge a partial config dict and save."""
        current = self.model_dump()
        _deep_merge(current, patch)
        new_cfg = PlutusConfig(**current)
        # Copy merged values back
        for field in self.model_fields:
            setattr(self, field, getattr(new_cfg, field))
        self.save()


def _deep_merge(base: dict, override: dict) -> None:
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


# Provider name → environment variable name mapping
PROVIDER_ENV_VARS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "custom": "API_KEY",
}


class SecretsStore:
    """Secure storage for API keys in ~/.plutus/.secrets.json (chmod 600).

    Keys are never stored in the main config.json and never returned via the API.
    On set, keys are also injected into os.environ so LiteLLM picks them up.
    """

    def __init__(self, path: Path | None = None):
        self._path = path or (plutus_dir() / ".secrets.json")

    def _read(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text())

    def _write(self, data: dict[str, str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2))
        # Restrict to owner read/write only
        self._path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def get_key(self, provider: str) -> str | None:
        """Get the API key for a provider. Checks env var first, then secrets file."""
        env_var = PROVIDER_ENV_VARS.get(provider, f"{provider.upper()}_API_KEY")
        # Environment variable takes priority
        env_key = os.environ.get(env_var)
        if env_key:
            return env_key
        # Fall back to secrets file
        data = self._read()
        return data.get(provider)

    def set_key(self, provider: str, key: str) -> None:
        """Store a key and inject it into os.environ for the current process."""
        data = self._read()
        data[provider] = key
        self._write(data)
        # Inject into environment so LiteLLM picks it up immediately
        env_var = PROVIDER_ENV_VARS.get(provider, f"{provider.upper()}_API_KEY")
        os.environ[env_var] = key

    def has_key(self, provider: str) -> bool:
        """Check if a key is available (from env or secrets file)."""
        return self.get_key(provider) is not None

    def delete_key(self, provider: str) -> None:
        """Remove a key from the secrets file (does not unset env vars)."""
        data = self._read()
        data.pop(provider, None)
        self._write(data)

    def key_status(self) -> dict[str, bool]:
        """Return which providers have keys configured."""
        all_providers = list(PROVIDER_ENV_VARS.keys())
        # Also include any providers in the secrets file
        data = self._read()
        for p in data:
            if p not in all_providers:
                all_providers.append(p)
        return {p: self.has_key(p) for p in all_providers}

    def inject_all(self) -> None:
        """Inject all stored keys into os.environ (called at startup)."""
        data = self._read()
        for provider, key in data.items():
            env_var = PROVIDER_ENV_VARS.get(provider, f"{provider.upper()}_API_KEY")
            # Don't overwrite existing env vars
            if not os.environ.get(env_var):
                os.environ[env_var] = key
