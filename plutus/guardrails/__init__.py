"""Guardrails — configurable permission system for Plutus.

Four tiers control what the AI can do:
  - Observer:   Read-only. No writes, no execution.
  - Assistant:  Every action requires explicit user approval.
  - Operator:   Pre-approved action types run autonomously; the rest ask.
  - Autonomous: Full system control.
"""

from plutus.guardrails.engine import GuardrailEngine
from plutus.guardrails.tiers import Tier

__all__ = ["GuardrailEngine", "Tier"]
