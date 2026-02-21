"""Plutus Skills — pre-built, reliable workflows for common apps.

A skill is a structured set of instructions that tells the agent exactly
how to accomplish a task in a specific app. Instead of guessing how to
navigate WhatsApp or Google Calendar, the agent follows a proven recipe.

Skills are defined as Python classes with:
  - A name and description (for the LLM to match against user requests)
  - A list of app triggers (e.g., "whatsapp", "calendar")
  - Required parameters (e.g., contact_name, message)
  - A step-by-step execute() method that uses the pc tool
"""

from plutus.skills.engine import SkillEngine, SkillDefinition, SkillStep, SkillResult
from plutus.skills.registry import SkillRegistry, create_default_registry

__all__ = [
    "SkillEngine",
    "SkillDefinition",
    "SkillStep",
    "SkillResult",
    "SkillRegistry",
    "create_default_registry",
]
