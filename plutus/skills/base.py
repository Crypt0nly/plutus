"""Base skill definition — skills extend the agent's capabilities."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SkillStep(BaseModel):
    """A single step in a skill execution."""

    tool: str = "shell"
    operation: str | None = None
    params: dict[str, Any] = {}
    run: str | None = None  # shorthand for shell commands

    def to_tool_call(self) -> tuple[str, dict[str, Any]]:
        if self.run:
            return "shell", {"command": self.run}
        return self.tool, {"operation": self.operation, **self.params}


class Skill(BaseModel):
    """A reusable skill that the agent can invoke."""

    name: str
    description: str
    tools_required: list[str] = []
    tier_minimum: str = "operator"
    tags: list[str] = []
    steps: list[SkillStep] = []
    prompt: str | None = None  # optional LLM prompt for complex skills

    def validate_tier(self, current_tier_level: int) -> bool:
        """Check if the current tier meets the minimum for this skill."""
        from plutus.guardrails.tiers import Tier

        try:
            min_tier = Tier(self.tier_minimum)
            return current_tier_level >= min_tier.level
        except ValueError:
            return False
