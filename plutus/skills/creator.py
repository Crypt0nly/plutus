"""Skill Creator — allows Plutus to autonomously create new skills.

When Plutus encounters a task it doesn't have a skill for, it can:
  1. Design a new skill (name, steps, triggers, params)
  2. Validate the skill definition is correct
  3. Dry-run the steps to check for obvious errors
  4. Persist the skill to disk (~/.plutus/skills/)
  5. Hot-load it into the live registry

Skills are stored as JSON files and loaded on startup, so they survive
restarts. The agent gets smarter over time.

Improvement log tracks what skills were created, when, why, and how
they performed — enabling the agent to learn from its own history.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plutus.skills.engine import SkillDefinition, SkillStep

logger = logging.getLogger("plutus.skills.creator")

# Directory for user-created skills
SKILLS_DIR = Path.home() / ".plutus" / "skills"
IMPROVEMENT_LOG = Path.home() / ".plutus" / "improvement_log.json"


@dataclass
class SkillBlueprint:
    """A blueprint for a new skill before it's created."""
    name: str
    description: str
    app: str
    category: str
    triggers: list[str]
    required_params: list[str]
    optional_params: list[str]
    steps: list[dict[str, Any]]  # raw step dicts
    reason: str = ""  # why the agent created this skill
    version: int = 1

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "app": self.app,
            "category": self.category,
            "triggers": self.triggers,
            "required_params": self.required_params,
            "optional_params": self.optional_params,
            "steps": self.steps,
            "reason": self.reason,
            "version": self.version,
        }


@dataclass
class ImprovementEntry:
    """A log entry for a self-improvement action."""
    timestamp: str
    action: str  # "created", "updated", "deleted", "learned"
    skill_name: str
    reason: str
    details: dict[str, Any] = field(default_factory=dict)
    success: bool = True

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "action": self.action,
            "skill_name": self.skill_name,
            "reason": self.reason,
            "details": self.details,
            "success": self.success,
        }


class DynamicSkill(SkillDefinition):
    """A skill created at runtime from a JSON blueprint."""

    def __init__(self, blueprint: SkillBlueprint):
        self._blueprint = blueprint
        self.name = blueprint.name
        self.description = blueprint.description
        self.app = blueprint.app
        self.category = blueprint.category
        self.triggers = blueprint.triggers
        self.required_params = blueprint.required_params
        self.optional_params = blueprint.optional_params
        self._raw_steps = blueprint.steps

    def build_steps(self, params: dict[str, Any]) -> list[SkillStep]:
        """Build steps from the blueprint, substituting parameter values."""
        steps = []
        for raw in self._raw_steps:
            # Deep-copy and substitute params in step values
            step_params = {}
            for k, v in raw.get("params", {}).items():
                if isinstance(v, str):
                    # Replace {{param_name}} with actual values
                    for pname, pval in params.items():
                        v = v.replace(f"{{{{{pname}}}}}", str(pval))
                step_params[k] = v

            description = raw.get("description", "")
            for pname, pval in params.items():
                description = description.replace(f"{{{{{pname}}}}}", str(pval))

            steps.append(SkillStep(
                description=description,
                operation=raw.get("operation", ""),
                params=step_params,
                wait_after=raw.get("wait_after", 1.0),
                retry_on_fail=raw.get("retry_on_fail", False),
                max_retries=raw.get("max_retries", 2),
                optional=raw.get("optional", False),
            ))
        return steps

    def to_dict(self) -> dict:
        base = super().to_dict()
        base["dynamic"] = True
        base["version"] = self._blueprint.version
        base["reason"] = self._blueprint.reason
        base["steps"] = self._raw_steps
        return base


class SkillCreator:
    """Creates, validates, persists, and manages dynamic skills."""

    # Valid operations that skills can use
    VALID_OPERATIONS = {
        # OS
        "open_app", "close_app", "open_url", "open_file", "open_folder",
        "run_command", "list_processes", "kill_process",
        "get_clipboard", "set_clipboard", "send_notification",
        "list_apps", "system_info", "active_window",
        # Browser
        "navigate", "browser_click", "browser_type", "browser_press",
        "fill_form", "select_option", "browser_hover", "browser_scroll",
        "get_page", "get_elements", "browser_screenshot",
        "new_tab", "close_tab", "switch_tab", "list_tabs",
        "evaluate_js", "wait_for_text",
        # Desktop
        "mouse_click", "mouse_move", "mouse_scroll",
        "keyboard_type", "keyboard_press", "keyboard_hotkey", "keyboard_shortcut",
        "screenshot", "read_screen", "find_text_on_screen",
    }

    VALID_CATEGORIES = {
        "messaging", "calendar", "email", "music", "files", "browser",
        "productivity", "social", "shopping", "finance", "development",
        "system", "media", "education", "health", "travel", "food",
        "gaming", "communication", "utility", "custom",
    }

    def __init__(self):
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        self._improvement_log: list[ImprovementEntry] = []
        self._load_improvement_log()

    # ── Validation ──────────────────────────────────────────

    def validate_blueprint(self, blueprint: SkillBlueprint) -> tuple[bool, list[str]]:
        """Validate a skill blueprint before creation.
        
        Returns (is_valid, list_of_errors).
        """
        errors = []

        # Name validation
        if not blueprint.name:
            errors.append("Skill name is required")
        elif not blueprint.name.replace("_", "").isalnum():
            errors.append("Skill name must be alphanumeric with underscores only")
        elif len(blueprint.name) > 64:
            errors.append("Skill name must be 64 characters or less")

        # Description
        if not blueprint.description:
            errors.append("Description is required")

        # App
        if not blueprint.app:
            errors.append("App name is required")

        # Category
        if blueprint.category and blueprint.category not in self.VALID_CATEGORIES:
            errors.append(
                f"Invalid category: {blueprint.category}. "
                f"Valid: {', '.join(sorted(self.VALID_CATEGORIES))}"
            )

        # Triggers
        if not blueprint.triggers:
            errors.append("At least one trigger keyword is required")

        # Steps
        if not blueprint.steps:
            errors.append("At least one step is required")
        else:
            for i, step in enumerate(blueprint.steps):
                if not step.get("operation"):
                    errors.append(f"Step {i+1}: operation is required")
                elif step["operation"] not in self.VALID_OPERATIONS:
                    errors.append(
                        f"Step {i+1}: unknown operation '{step['operation']}'. "
                        f"See pc tool for valid operations."
                    )
                if not step.get("description"):
                    errors.append(f"Step {i+1}: description is required")

        # Check for param placeholders in steps
        all_params = set(blueprint.required_params + blueprint.optional_params)
        for i, step in enumerate(blueprint.steps):
            for v in step.get("params", {}).values():
                if isinstance(v, str) and "{{" in v:
                    # Extract param names from {{param_name}}
                    import re
                    placeholders = re.findall(r"\{\{(\w+)\}\}", v)
                    for ph in placeholders:
                        if ph not in all_params:
                            errors.append(
                                f"Step {i+1}: placeholder '{{{{{ph}}}}}' not in "
                                f"required_params or optional_params"
                            )

        return len(errors) == 0, errors

    # ── Creation ────────────────────────────────────────────

    def create_skill(
        self,
        blueprint: SkillBlueprint,
        registry=None,
    ) -> tuple[bool, str, DynamicSkill | None]:
        """Create a new skill from a blueprint.
        
        Returns (success, message, skill_or_none).
        """
        # Validate
        valid, errors = self.validate_blueprint(blueprint)
        if not valid:
            return False, f"Validation failed:\n" + "\n".join(f"  - {e}" for e in errors), None

        # Check for name conflicts
        skill_path = SKILLS_DIR / f"{blueprint.name}.json"
        if skill_path.exists():
            # Load existing to check version
            try:
                existing = json.loads(skill_path.read_text())
                blueprint.version = existing.get("version", 1) + 1
                logger.info(f"Updating existing skill {blueprint.name} to v{blueprint.version}")
            except Exception:
                pass

        # Create the dynamic skill
        skill = DynamicSkill(blueprint)

        # Persist to disk
        try:
            skill_path.write_text(json.dumps(blueprint.to_dict(), indent=2))
            logger.info(f"Saved skill to {skill_path}")
        except Exception as e:
            return False, f"Failed to save skill: {e}", None

        # Register in live registry if provided
        if registry is not None:
            registry.register(skill)
            logger.info(f"Hot-loaded skill {blueprint.name} into live registry")

        # Log the improvement
        self._log_improvement(ImprovementEntry(
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            action="created" if blueprint.version == 1 else "updated",
            skill_name=blueprint.name,
            reason=blueprint.reason or "Agent decided to create this skill",
            details={
                "version": blueprint.version,
                "steps": len(blueprint.steps),
                "category": blueprint.category,
                "app": blueprint.app,
                "triggers": blueprint.triggers,
            },
        ))

        action = "Updated" if blueprint.version > 1 else "Created"
        return True, (
            f"{action} skill '{blueprint.name}' v{blueprint.version} "
            f"({len(blueprint.steps)} steps, category: {blueprint.category}). "
            f"It's now available for use."
        ), skill

    def create_from_dict(self, data: dict, registry=None) -> tuple[bool, str, DynamicSkill | None]:
        """Create a skill from a raw dictionary (from LLM output)."""
        try:
            blueprint = SkillBlueprint(
                name=data.get("name", ""),
                description=data.get("description", ""),
                app=data.get("app", ""),
                category=data.get("category", "custom"),
                triggers=data.get("triggers", []),
                required_params=data.get("required_params", []),
                optional_params=data.get("optional_params", []),
                steps=data.get("steps", []),
                reason=data.get("reason", ""),
            )
            return self.create_skill(blueprint, registry)
        except Exception as e:
            return False, f"Invalid skill data: {e}", None

    # ── Loading ─────────────────────────────────────────────

    def load_saved_skills(self) -> list[DynamicSkill]:
        """Load all saved skills from disk."""
        skills = []
        if not SKILLS_DIR.exists():
            return skills

        for path in sorted(SKILLS_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text())
                blueprint = SkillBlueprint(
                    name=data.get("name", path.stem),
                    description=data.get("description", ""),
                    app=data.get("app", ""),
                    category=data.get("category", "custom"),
                    triggers=data.get("triggers", []),
                    required_params=data.get("required_params", []),
                    optional_params=data.get("optional_params", []),
                    steps=data.get("steps", []),
                    reason=data.get("reason", ""),
                    version=data.get("version", 1),
                )
                skills.append(DynamicSkill(blueprint))
                logger.info(f"Loaded saved skill: {blueprint.name} v{blueprint.version}")
            except Exception as e:
                logger.warning(f"Failed to load skill from {path}: {e}")

        return skills

    def load_into_registry(self, registry) -> int:
        """Load all saved skills into a registry. Returns count loaded."""
        skills = self.load_saved_skills()
        for skill in skills:
            registry.register(skill)
        return len(skills)

    # ── Management ──────────────────────────────────────────

    def delete_skill(self, name: str, registry=None) -> tuple[bool, str]:
        """Delete a saved skill."""
        path = SKILLS_DIR / f"{name}.json"
        if not path.exists():
            return False, f"Skill '{name}' not found"

        try:
            path.unlink()
        except Exception as e:
            return False, f"Failed to delete: {e}"

        # Unregister from live registry
        if registry is not None and hasattr(registry, '_skills'):
            registry._skills.pop(name, None)

        self._log_improvement(ImprovementEntry(
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            action="deleted",
            skill_name=name,
            reason="Skill deleted by agent or user",
        ))

        return True, f"Deleted skill '{name}'"

    def list_saved_skills(self) -> list[dict]:
        """List all saved skills with metadata."""
        skills = []
        if not SKILLS_DIR.exists():
            return skills

        for path in sorted(SKILLS_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text())
                skills.append({
                    "name": data.get("name", path.stem),
                    "description": data.get("description", ""),
                    "app": data.get("app", ""),
                    "category": data.get("category", "custom"),
                    "version": data.get("version", 1),
                    "triggers": data.get("triggers", []),
                    "steps_count": len(data.get("steps", [])),
                    "reason": data.get("reason", ""),
                    "file": str(path),
                })
            except Exception:
                pass

        return skills

    def get_skill_source(self, name: str) -> dict | None:
        """Get the full source JSON of a saved skill."""
        path = SKILLS_DIR / f"{name}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except Exception:
            return None

    # ── Improvement Log ─────────────────────────────────────

    def _log_improvement(self, entry: ImprovementEntry):
        """Add an entry to the improvement log."""
        self._improvement_log.append(entry)
        self._save_improvement_log()

    def log_learning(self, skill_name: str, reason: str, details: dict | None = None):
        """Log a learning event (e.g., skill worked well, or needs improvement)."""
        self._log_improvement(ImprovementEntry(
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            action="learned",
            skill_name=skill_name,
            reason=reason,
            details=details or {},
        ))

    def get_improvement_log(self, limit: int = 50) -> list[dict]:
        """Get recent improvement log entries."""
        entries = self._improvement_log[-limit:]
        return [e.to_dict() for e in entries]

    def get_improvement_stats(self) -> dict:
        """Get statistics about self-improvement."""
        total = len(self._improvement_log)
        created = sum(1 for e in self._improvement_log if e.action == "created")
        updated = sum(1 for e in self._improvement_log if e.action == "updated")
        deleted = sum(1 for e in self._improvement_log if e.action == "deleted")
        learned = sum(1 for e in self._improvement_log if e.action == "learned")
        saved = self.list_saved_skills()

        return {
            "total_improvements": total,
            "skills_created": created,
            "skills_updated": updated,
            "skills_deleted": deleted,
            "learnings_recorded": learned,
            "active_custom_skills": len(saved),
            "categories_covered": list(set(s["category"] for s in saved)),
        }

    def _load_improvement_log(self):
        """Load the improvement log from disk."""
        if IMPROVEMENT_LOG.exists():
            try:
                data = json.loads(IMPROVEMENT_LOG.read_text())
                self._improvement_log = [
                    ImprovementEntry(**entry) for entry in data
                ]
            except Exception as e:
                logger.warning(f"Failed to load improvement log: {e}")
                self._improvement_log = []

    def _save_improvement_log(self):
        """Save the improvement log to disk."""
        try:
            IMPROVEMENT_LOG.parent.mkdir(parents=True, exist_ok=True)
            IMPROVEMENT_LOG.write_text(
                json.dumps([e.to_dict() for e in self._improvement_log], indent=2)
            )
        except Exception as e:
            logger.warning(f"Failed to save improvement log: {e}")


# ── Convenience ─────────────────────────────────────────────

_creator_instance: SkillCreator | None = None


def get_skill_creator() -> SkillCreator:
    """Get the singleton SkillCreator instance."""
    global _creator_instance
    if _creator_instance is None:
        _creator_instance = SkillCreator()
    return _creator_instance
