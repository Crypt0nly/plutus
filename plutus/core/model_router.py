"""Model Router — intelligent model selection based on task complexity.

Routes tasks to the most appropriate model:
  - Claude Opus:   Complex reasoning, multi-step planning, code architecture
  - Claude Sonnet: Balanced — good for most tasks (default)
  - Claude Haiku:  Simple tasks, fast responses, summaries, classification
  - GPT-5.2:       Alternative provider — all complexity levels

The router classifies task complexity using keyword analysis and explicit
hints from the agent, then selects the cheapest model that can handle it.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from plutus.config import SecretsStore

logger = logging.getLogger("plutus.model_router")


# ── Complexity tiers ──────────────────────────────────────────────────────────

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
    max_tokens: int = 4096
    supports_tools: bool = True
    supports_vision: bool = True
    cost_per_1k_input: float = 0.0   # For display/budgeting
    cost_per_1k_output: float = 0.0


# Available models — the user can enable/disable these in settings
AVAILABLE_MODELS: dict[str, ModelSpec] = {
    # Anthropic
    "claude-opus": ModelSpec(
        id="claude-opus-4",
        provider="anthropic",
        display_name="Claude Opus",
        complexity_tier=Complexity.COMPLEX,
        max_tokens=4096,
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.075,
    ),
    "claude-sonnet": ModelSpec(
        id="claude-sonnet-4-6",
        provider="anthropic",
        display_name="Claude Sonnet",
        complexity_tier=Complexity.MODERATE,
        max_tokens=4096,
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
    ),
    "claude-haiku": ModelSpec(
        id="claude-haiku-4",
        provider="anthropic",
        display_name="Claude Haiku",
        complexity_tier=Complexity.SIMPLE,
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
        max_tokens=4096,
        cost_per_1k_input=0.005,
        cost_per_1k_output=0.015,
    ),
}


# ── Complexity classifier ─────────────────────────────────────────────────────

# Keywords/patterns that suggest task complexity
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
    r"\b(\d{3,}\s*word)\b",  # e.g. "5000 word"
]

_SIMPLE_PATTERNS = [
    r"\b(hello|hi|hey|thanks|thank you|ok|okay|yes|no|sure)\b",
    r"\b(what time|what day|what date|weather)\b",
    r"\b(summarize this|tldr|quick question|simple)\b",
    r"\b(translate|convert|format|rename|list)\b",
    r"\b(open|close|click|scroll|navigate to)\b",
]


def classify_complexity(prompt: str, tool_count: int = 0, context_length: int = 0) -> Complexity:
    """Classify the complexity of a task based on the prompt and context.

    Args:
        prompt: The user's message or task description
        tool_count: Number of tools likely needed (hint from planner)
        context_length: Current conversation context length in messages

    Returns:
        Complexity tier (SIMPLE, MODERATE, or COMPLEX)
    """
    prompt_lower = prompt.lower().strip()

    # Very short messages are usually simple
    if len(prompt_lower) < 20:
        return Complexity.SIMPLE

    # Check for explicit complexity hints
    if any(re.search(p, prompt_lower) for p in _COMPLEX_PATTERNS):
        return Complexity.COMPLEX

    if any(re.search(p, prompt_lower) for p in _SIMPLE_PATTERNS):
        return Complexity.SIMPLE

    # Heuristics based on message characteristics
    word_count = len(prompt_lower.split())

    if word_count > 60 or tool_count > 4:
        return Complexity.COMPLEX
    elif word_count > 25 or tool_count > 2:
        return Complexity.MODERATE
    elif word_count < 15 and tool_count <= 1:
        return Complexity.SIMPLE

    # Default to moderate
    return Complexity.MODERATE


# ── Router configuration ──────────────────────────────────────────────────────

@dataclass
class ModelRoutingConfig:
    """User-configurable model routing preferences."""
    primary_provider: str = "anthropic"          # "anthropic" or "openai"
    enabled_models: list[str] = field(default_factory=lambda: [
        "claude-opus", "claude-sonnet", "claude-haiku"
    ])
    default_model: str = "claude-sonnet"         # Fallback when routing is uncertain
    auto_route: bool = True                      # Enable automatic model selection
    cost_conscious: bool = False                 # Prefer cheaper models when possible
    worker_model: str = "claude-haiku"           # Default model for worker subprocesses
    scheduler_model: str = "claude-haiku"        # Default model for scheduled tasks

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_provider": self.primary_provider,
            "enabled_models": self.enabled_models,
            "default_model": self.default_model,
            "auto_route": self.auto_route,
            "cost_conscious": self.cost_conscious,
            "worker_model": self.worker_model,
            "scheduler_model": self.scheduler_model,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelRoutingConfig:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ── Model Router ──────────────────────────────────────────────────────────────

class ModelRouter:
    """Selects the optimal model for each task based on complexity and user preferences.

    Usage:
        router = ModelRouter(config, secrets)
        model = router.route("Write a comprehensive analysis of...")
        # → ModelSpec for Claude Opus

        model = router.route("hello")
        # → ModelSpec for Claude Haiku

        model = router.route_for_worker()
        # → ModelSpec for Claude Haiku (fast + cheap for workers)
    """

    def __init__(
        self,
        config: ModelRoutingConfig | None = None,
        secrets: SecretsStore | None = None,
    ):
        self._config = config or ModelRoutingConfig()
        self._secrets = secrets or SecretsStore()
        self._usage_stats: dict[str, dict[str, int]] = {}  # model_key → {calls, tokens}

    @property
    def config(self) -> ModelRoutingConfig:
        return self._config

    def update_config(self, config: ModelRoutingConfig) -> None:
        self._config = config

    def route(
        self,
        prompt: str,
        complexity_override: Complexity | None = None,
        model_override: str | None = None,
        tool_count: int = 0,
        context_length: int = 0,
    ) -> ModelSpec:
        """Select the best model for a given task.

        Args:
            prompt: The task/message to route
            complexity_override: Explicit complexity (skips classification)
            model_override: Explicit model key (e.g. "claude-opus")
            tool_count: Estimated number of tools needed
            context_length: Current conversation length

        Returns:
            ModelSpec for the selected model
        """
        # Explicit model override — agent or user requested a specific model
        if model_override and model_override in AVAILABLE_MODELS:
            spec = AVAILABLE_MODELS[model_override]
            if self._is_available(spec):
                logger.info(f"Model override: {spec.display_name}")
                return spec

        # Auto-routing disabled — use default
        if not self._config.auto_route:
            return self._get_default()

        # Classify complexity
        complexity = complexity_override or classify_complexity(
            prompt, tool_count, context_length
        )

        # Find the best model for this complexity
        model = self._select_for_complexity(complexity)
        logger.info(
            f"Routed [{complexity.value}] → {model.display_name} "
            f"(prompt: {prompt[:50]}...)"
        )
        return model

    def route_for_worker(self, task_description: str = "") -> ModelSpec:
        """Select a model for a worker subprocess (defaults to fast/cheap)."""
        worker_key = self._config.worker_model
        if worker_key in AVAILABLE_MODELS:
            spec = AVAILABLE_MODELS[worker_key]
            if self._is_available(spec):
                return spec
        # Fallback: cheapest available
        return self._get_cheapest()

    def route_for_scheduler(self, job_description: str = "") -> ModelSpec:
        """Select a model for a scheduled job."""
        sched_key = self._config.scheduler_model
        if sched_key in AVAILABLE_MODELS:
            spec = AVAILABLE_MODELS[sched_key]
            if self._is_available(spec):
                return spec
        return self._get_cheapest()

    def get_available_models(self) -> list[dict[str, Any]]:
        """Return list of available models with their status."""
        result = []
        for key, spec in AVAILABLE_MODELS.items():
            available = self._is_available(spec)
            stats = self._usage_stats.get(key, {"calls": 0, "tokens": 0})
            result.append({
                "key": key,
                "id": spec.id,
                "provider": spec.provider,
                "display_name": spec.display_name,
                "complexity_tier": spec.complexity_tier.value,
                "enabled": key in self._config.enabled_models,
                "available": available,
                "is_default": key == self._config.default_model,
                "is_worker_model": key == self._config.worker_model,
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
        # Check if the model key is enabled
        model_key = None
        for key, s in AVAILABLE_MODELS.items():
            if s.id == spec.id:
                model_key = key
                break
        if model_key and model_key not in self._config.enabled_models:
            return False

        # Check if API key exists for the provider
        return self._secrets.has_key(spec.provider)

    def _get_default(self) -> ModelSpec:
        """Get the default model."""
        key = self._config.default_model
        if key in AVAILABLE_MODELS:
            spec = AVAILABLE_MODELS[key]
            if self._is_available(spec):
                return spec
        # Fallback to first available
        for key in self._config.enabled_models:
            if key in AVAILABLE_MODELS and self._is_available(AVAILABLE_MODELS[key]):
                return AVAILABLE_MODELS[key]
        # Last resort — return sonnet even if not available (will error at call time)
        return AVAILABLE_MODELS["claude-sonnet"]

    def _select_for_complexity(self, complexity: Complexity) -> ModelSpec:
        """Select the best model for a given complexity tier."""
        provider = self._config.primary_provider

        # Build preference order based on complexity and provider
        if provider == "openai":
            # OpenAI: only GPT-5.2 for everything
            if "gpt-5.2" in self._config.enabled_models:
                spec = AVAILABLE_MODELS["gpt-5.2"]
                if self._is_available(spec):
                    return spec

        # Anthropic model selection based on complexity
        preference_map = {
            Complexity.COMPLEX: ["claude-opus", "claude-sonnet", "gpt-5.2"],
            Complexity.MODERATE: ["claude-sonnet", "claude-haiku", "gpt-5.2"],
            Complexity.SIMPLE: ["claude-haiku", "claude-sonnet", "gpt-5.2"],
        }

        # Cost-conscious mode: always prefer cheaper
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

        return self._get_default()

    def _get_cheapest(self) -> ModelSpec:
        """Get the cheapest available model."""
        cheapest = None
        cheapest_cost = float("inf")
        for key in self._config.enabled_models:
            if key in AVAILABLE_MODELS:
                spec = AVAILABLE_MODELS[key]
                if self._is_available(spec):
                    cost = spec.cost_per_1k_input + spec.cost_per_1k_output
                    if cost < cheapest_cost:
                        cheapest = spec
                        cheapest_cost = cost
        return cheapest or self._get_default()
