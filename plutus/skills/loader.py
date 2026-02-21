"""Skill loader — discovers and loads skills from the skills directory."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from plutus.skills.base import Skill, SkillStep

logger = logging.getLogger("plutus.skills")


def _try_import_yaml():
    """Try to import yaml, return None if not available."""
    try:
        import yaml as _yaml
        return _yaml
    except ImportError:
        return None


class SkillLoader:
    """Load skills from YAML files in the skills directory."""

    def __init__(self, skills_dir: Path):
        self._dir = skills_dir
        self._skills: dict[str, Skill] = {}

    def load_all(self) -> dict[str, Skill]:
        """Scan the skills directory and load all valid skill files."""
        if not self._dir.exists():
            return {}

        for path in self._dir.glob("**/*.yaml"):
            try:
                skill = self._load_file(path)
                if skill:
                    self._skills[skill.name] = skill
                    logger.info(f"Loaded skill: {skill.name}")
            except Exception as e:
                logger.warning(f"Failed to load skill from {path}: {e}")

        for path in self._dir.glob("**/*.yml"):
            try:
                skill = self._load_file(path)
                if skill:
                    self._skills[skill.name] = skill
                    logger.info(f"Loaded skill: {skill.name}")
            except Exception as e:
                logger.warning(f"Failed to load skill from {path}: {e}")

        return self._skills

    def _load_file(self, path: Path) -> Skill | None:
        """Parse a YAML skill file into a Skill object."""
        _yaml = _try_import_yaml()
        if not _yaml:
            logger.warning("PyYAML not installed — skipping skill loading")
            return None

        data = _yaml.safe_load(path.read_text())
        if not data or not isinstance(data, dict):
            return None

        steps = []
        for step_data in data.get("steps", []):
            if isinstance(step_data, str):
                steps.append(SkillStep(run=step_data))
            elif isinstance(step_data, dict):
                if "run" in step_data:
                    steps.append(SkillStep(run=step_data["run"]))
                else:
                    steps.append(SkillStep(**step_data))

        return Skill(
            name=data.get("name", path.stem),
            description=data.get("description", ""),
            tools_required=data.get("tools_required", []),
            tier_minimum=data.get("tier_minimum", "operator"),
            tags=data.get("tags", []),
            steps=steps,
            prompt=data.get("prompt"),
        )

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def list_skills(self) -> list[dict[str, Any]]:
        return [
            {
                "name": s.name,
                "description": s.description,
                "tools_required": s.tools_required,
                "tier_minimum": s.tier_minimum,
                "tags": s.tags,
                "step_count": len(s.steps),
            }
            for s in self._skills.values()
        ]


# Make yaml import optional — only needed for skills
try:
    import yaml
except ImportError:
    yaml = None  # type: ignore
