"""Model Router — Coordinator-centric model selection for workers.

Architecture:
  - The COORDINATOR (main agent) always uses the model chosen by the user
    in Settings. This never changes automatically.
  - When the Coordinator spawns WORKERS, it decides which model each worker
    should use based on the task it's delegating.
  - The Coordinator can either:
    (a) Explicitly pick a model: worker(model_key="claude-haiku", ...)
    (b) Let the router auto-select: worker(model_key="auto", ...)

Available models:
  - Claude Opus:   Complex reasoning, multi-step planning, deep analysis
  - Claude Sonnet: Balanced — good for most tasks
  - Claude Haiku:  Fast & cheap — summaries, lookups, simple tasks
  - GPT-5.2:       OpenAI alternative for complex tasks
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from plutus.config import SecretsStore

logger = logging.getLogger("plutus.model_router")


# ── Complexity tiers (used for worker model selection) ───────────────────────

class Complexity(str, Enum):
    SIMPLE = "simple"      # Quick lookups, summaries, classification, chat
    MODERATE = "moderate"   # Standard tasks, browsing, file ops, tool use
    COMPLEX = "complex"     # Multi-step planning, code architecture, deep analysis


# ── Model definitions ─────────────────────────────────────────────────────────

@dataclass
class ModelSpec:
    """Specification for a single model."""
    id: str                          # e.g. "claude-sonnet-4-6"
    provider: str                    # "anthropic" or "openai"
    display_name: str                # "Claude Sonnet"
    complexity_tier: Complexity      # What it's best at
    description: str = ""            # Human-readable description of strengths
    max_tokens: int = 4096
    supports_tools: bool = True
    supports_vision: bool = True
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0


# Available models — the user can enable/disable these in settings
AVAILABLE_MODELS: dict[str, ModelSpec] = {
    # Anthropic
    "claude-opus": ModelSpec(
        id="claude-opus-4-6",
        provider="anthropic",
        display_name="Claude Opus",
        complexity_tier=Complexity.COMPLEX,
        description="Most intelligent. Best for complex reasoning, architecture, deep analysis, long-form writing.",
        max_tokens=4096,
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.075,
    ),
    "claude-sonnet": ModelSpec(
        id="claude-sonnet-4-6",
        provider="anthropic",
        display_name="Claude Sonnet",
        complexity_tier=Complexity.MODERATE,
        description="Balanced intelligence and speed. Good for most tasks.",
        max_tokens=4096,
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
    ),
    "claude-haiku": ModelSpec(
        id="claude-haiku-4-5",
        provider="anthropic",
        display_name="Claude Haiku",
        complexity_tier=Complexity.SIMPLE,
        description="Fastest and cheapest. Great for summaries, lookups, classification, simple tasks.",
        max_tokens=4096,
        cost_per_1k_input=0.00025,
        cost_per_1k_output=0.00125,
    ),
    # OpenAI
    "gpt-5.2": ModelSpec(
        id="gpt-5.2",
        provider="openai",
        display_name="GPT-5.2",
        complexity_tier=Complexity.COMPLEX,
        description="OpenAI's most capable model. Alternative for complex tasks.",
        max_tokens=4096,
        cost_per_1k_input=0.005,
        cost_per_1k_output=0.015,
    ),
}


# ── Complexity classifier (for auto worker model selection) ──────────────────

_COMPLEX_PATTERNS = [
    r"\b(architect|design system|refactor|multi.?step|comprehensive|in.?depth)\b",
    r"\b(analyze|debug.*complex|plan.*project|write.*report)\b",
    r"\b(research|compare.*and.*contrast|investigate)\b",
    r"\b(create.*application|build.*system|implement.*feature)\b",
    r"\b(strategy|optimization|trade.?off|deep.*analysis)\b",
    r"\b(blog.?post|article|essay|paper|thesis|dissertation)\b",
    r"\b(every.*day|daily|weekly|schedule|cron|automat)\b",
    r"\b(while.*also|simultaneously|parallel|worker)\b",
    r"\b(financial|market|stock|crypto|investment)\b",
    r"\b(\d{3,}\s*word)\b",
]

_SIMPLE_PATTERNS = [
    r"\b(hello|hi|hey|thanks|thank you|ok|okay|yes|no|sure)\b",
    r"\b(what time|what day|what date|weather)\b",
    r"\b(summarize this|tldr|quick question|simple)\b",
    r"\b(translate|convert|format|rename|list)\b",
    r"\b(open|close|click|scroll|navigate to)\b",
    r"\b(fetch|get|check|look up|find)\b",
]


def classify_complexity(prompt: str, tool_count: int = 0) -> Complexity:
    """Classify the complexity of a worker task based on its description.

    This is used when the Coordinator sets model_key="auto" for a worker.
    """
    prompt_lower = prompt.lower().strip()

    if len(prompt_lower) < 20:
        return Complexity.SIMPLE

    if any(re.search(p, prompt_lower) for p in _COMPLEX_PATTERNS):
        return Complexity.COMPLEX

    if any(re.search(p, prompt_lower) for p in _SIMPLE_PATTERNS):
        return Complexity.SIMPLE

    word_count = len(prompt_lower.split())

    if word_count > 60 or tool_count > 4:
        return Complexity.COMPLEX
    elif word_count > 25 or tool_count > 2:
        return Complexity.MODERATE
    elif word_count < 15 and tool_count <= 1:
        return Complexity.SIMPLE

    return Complexity.MODERATE


# ── Router configuration ──────────────────────────────────────────────────────

@dataclass
class ModelRoutingConfig:
    """User-configurable model routing preferences.

    Note: The coordinator_model is set separately in the main Settings
    (ModelConfig component). This config is only for worker/scheduler defaults.
    """
    enabled_models: list[str] = field(default_factory=lambda: [
        "claude-opus", "claude-sonnet", "claude-haiku", "gpt-5.2"
    ])
    cost_conscious: bool = False                 # Prefer cheaper worker models
    default_worker_model: str = "auto"           # "auto" or a specific model key
    default_scheduler_model: str = "auto"        # "auto" or a specific model key

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled_models": self.enabled_models,
            "cost_conscious": self.cost_conscious,
            "default_worker_model": self.default_worker_model,
            "default_scheduler_model": self.default_scheduler_model,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelRoutingConfig:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ── Model Router ──────────────────────────────────────────────────────────────

class ModelRouter:
    """Helps the Coordinator select models for workers and scheduled jobs.

    The Coordinator (main agent) always uses the user's chosen model.
    This router is ONLY used for worker model selection.

    Usage:
        router = ModelRouter(config, secrets)

        # Coordinator picks explicitly
        model = router.get_model("claude-haiku")

        # Coordinator says "auto" — router picks based on task
        model = router.select_for_worker("Research AI trends and write a summary")
        # → Claude Sonnet or Opus depending on complexity

        model = router.select_for_worker("Fetch the headlines from HackerNews")
        # → Claude Haiku (simple task)
    """

    def __init__(
        self,
        config: ModelRoutingConfig | None = None,
        secrets: SecretsStore | None = None,
    ):
        self._config = config or ModelRoutingConfig()
        self._secrets = secrets or SecretsStore()
        self._usage_stats: dict[str, dict[str, int]] = {}

    @property
    def config(self) -> ModelRoutingConfig:
        return self._config

    def update_config(self, config: ModelRoutingConfig) -> None:
        self._config = config

    def get_model(self, model_key: str) -> ModelSpec | None:
        """Get a specific model by key. Returns None if not available."""
        if model_key in AVAILABLE_MODELS:
            spec = AVAILABLE_MODELS[model_key]
            if self._is_available(spec):
                return spec
        return None

    def select_for_worker(
        self,
        task_description: str,
        model_key: str | None = None,
    ) -> ModelSpec:
        """Select a model for a worker task.

        Args:
            task_description: What the worker will do
            model_key: Explicit model choice from the Coordinator.
                       "auto" or None = auto-select based on task complexity.
                       Any other value = use that specific model.

        Returns:
            ModelSpec for the selected model
        """
        # Explicit model choice from the Coordinator
        if model_key and model_key != "auto":
            spec = self.get_model(model_key)
            if spec:
                logger.info(f"Worker model (explicit): {spec.display_name} for '{task_description[:50]}'")
                return spec
            logger.warning(f"Requested model '{model_key}' not available, falling back to auto")

        # Check if there's a default worker model set (not "auto")
        default_key = self._config.default_worker_model
        if default_key and default_key != "auto":
            spec = self.get_model(default_key)
            if spec:
                logger.info(f"Worker model (default): {spec.display_name} for '{task_description[:50]}'")
                return spec

        # Auto-select based on task complexity
        complexity = classify_complexity(task_description)
        model = self._select_for_complexity(complexity)
        logger.info(
            f"Worker model (auto [{complexity.value}]): {model.display_name} "
            f"for '{task_description[:50]}'"
        )
        return model

    def select_for_scheduler(
        self,
        job_description: str,
        model_key: str | None = None,
    ) -> ModelSpec:
        """Select a model for a scheduled job."""
        if model_key and model_key != "auto":
            spec = self.get_model(model_key)
            if spec:
                return spec

        default_key = self._config.default_scheduler_model
        if default_key and default_key != "auto":
            spec = self.get_model(default_key)
            if spec:
                return spec

        # Auto-select based on job complexity
        complexity = classify_complexity(job_description)
        return self._select_for_complexity(complexity)

    def get_available_models(self) -> list[dict[str, Any]]:
        """Return list of all models with their status and usage."""
        result = []
        for key, spec in AVAILABLE_MODELS.items():
            available = self._is_available(spec)
            stats = self._usage_stats.get(key, {"calls": 0, "tokens": 0})
            result.append({
                "key": key,
                "id": spec.id,
                "provider": spec.provider,
                "display_name": spec.display_name,
                "description": spec.description,
                "complexity_tier": spec.complexity_tier.value,
                "enabled": key in self._config.enabled_models,
                "available": available,
                "cost_per_1k_input": spec.cost_per_1k_input,
                "cost_per_1k_output": spec.cost_per_1k_output,
                "calls": stats["calls"],
                "tokens": stats["tokens"],
            })
        return result

    def record_usage(self, model_key: str, tokens: int = 0) -> None:
        """Record usage statistics for a model."""
        if model_key not in self._usage_stats:
            self._usage_stats[model_key] = {"calls": 0, "tokens": 0}
        self._usage_stats[model_key]["calls"] += 1
        self._usage_stats[model_key]["tokens"] += tokens

    def get_usage_stats(self) -> dict[str, dict[str, int]]:
        return dict(self._usage_stats)

    def get_litellm_model_string(self, spec: ModelSpec) -> str:
        """Convert a ModelSpec to the litellm model string format."""
        if spec.provider == "anthropic":
            return f"anthropic/{spec.id}"
        elif spec.provider == "openai":
            return f"openai/{spec.id}"
        return spec.id

    # ── Internal helpers ──────────────────────────────────────────────────

    def _is_available(self, spec: ModelSpec) -> bool:
        """Check if a model is available (API key exists + enabled)."""
        model_key = None
        for key, s in AVAILABLE_MODELS.items():
            if s.id == spec.id:
                model_key = key
                break
        if model_key and model_key not in self._config.enabled_models:
            return False
        return self._secrets.has_key(spec.provider)

    def _select_for_complexity(self, complexity: Complexity) -> ModelSpec:
        """Select the best available model for a given complexity tier."""
        # Normal preference order
        preference_map = {
            Complexity.COMPLEX: ["claude-opus", "claude-sonnet", "gpt-5.2"],
            Complexity.MODERATE: ["claude-sonnet", "claude-haiku", "gpt-5.2"],
            Complexity.SIMPLE: ["claude-haiku", "claude-sonnet", "gpt-5.2"],
        }

        # Cost-conscious: always prefer cheaper
        if self._config.cost_conscious:
            preference_map = {
                Complexity.COMPLEX: ["claude-sonnet", "claude-haiku", "gpt-5.2"],
                Complexity.MODERATE: ["claude-haiku", "claude-sonnet", "gpt-5.2"],
                Complexity.SIMPLE: ["claude-haiku", "claude-sonnet", "gpt-5.2"],
            }

        for model_key in preference_map.get(complexity, ["claude-sonnet"]):
            if model_key in AVAILABLE_MODELS and model_key in self._config.enabled_models:
                spec = AVAILABLE_MODELS[model_key]
                if self._is_available(spec):
                    return spec

        return self._get_fallback()

    def _get_fallback(self) -> ModelSpec:
        """Get any available model as a last resort."""
        for key in self._config.enabled_models:
            if key in AVAILABLE_MODELS and self._is_available(AVAILABLE_MODELS[key]):
                return AVAILABLE_MODELS[key]
        # Absolute fallback
        return AVAILABLE_MODELS["claude-sonnet"]
