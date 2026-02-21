"""Configuration management for Plutus.

Config is stored at ~/.plutus/config.json and managed via the CLI or web UI.
"""

from __future__ import annotations

import json
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
    model: str = "claude-sonnet-4-20250514"
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


class PlutusConfig(BaseSettings):
    model: ModelConfig = Field(default_factory=ModelConfig)
    guardrails: GuardrailsConfig = Field(default_factory=GuardrailsConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
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
