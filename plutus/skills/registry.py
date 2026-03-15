"""Skill Registry — discovers, stores, and matches skills to user requests.

NOTE: Skills are for desktop/browser automation workflows where no direct API
connector exists. Services with connectors (WhatsApp, Gmail, Calendar, Telegram,
Discord, GitHub, etc.) should use their connector instead — connectors are more
reliable because they call APIs directly rather than automating browser UIs.
"""

from __future__ import annotations

import logging
from typing import Any

from plutus.skills.engine import SkillDefinition

logger = logging.getLogger("plutus.skills.registry")


class SkillRegistry:
    """Central registry for all available skills."""

    def __init__(self):
        self._skills: dict[str, SkillDefinition] = {}

    def register(self, skill: SkillDefinition) -> None:
        """Register a skill."""
        self._skills[skill.name] = skill
        logger.info(f"Registered skill: {skill.name} ({skill.category})")

    def get(self, name: str) -> SkillDefinition | None:
        """Get a skill by exact name."""
        return self._skills.get(name)

    def find_by_trigger(self, text: str) -> list[SkillDefinition]:
        """Find skills whose triggers match the given text."""
        text_lower = text.lower()
        matches = []
        for skill in self._skills.values():
            for trigger in skill.triggers:
                if trigger.lower() in text_lower:
                    matches.append(skill)
                    break
        return matches

    def find_by_category(self, category: str) -> list[SkillDefinition]:
        """Get all skills in a category."""
        return [s for s in self._skills.values() if s.category == category]

    def find_by_app(self, app: str) -> list[SkillDefinition]:
        """Get all skills for a specific app."""
        app_lower = app.lower()
        return [s for s in self._skills.values() if s.app.lower() == app_lower]

    def list_all(self) -> list[dict[str, Any]]:
        """List all registered skills with metadata."""
        return [s.to_dict() for s in self._skills.values()]

    def list_names(self) -> list[str]:
        """List all skill names."""
        return list(self._skills.keys())

    def list_categories(self) -> list[str]:
        """List all unique categories."""
        return list(set(s.category for s in self._skills.values()))


def create_default_registry() -> SkillRegistry:
    """Create a registry with all built-in skills.

    Only includes skills for apps/tasks that do NOT have a dedicated connector.
    Services like WhatsApp, Gmail, Calendar, Telegram, Discord, and GitHub
    are handled by their respective connectors (direct API calls), which are
    far more reliable than browser automation.
    """
    registry = SkillRegistry()

    # Spotify — no connector, uses web player / desktop app automation
    from plutus.skills.apps.spotify import (
        SpotifyPlaySong,
        SpotifyPlayPause,
        SpotifyNextTrack,
        SpotifySearchPlay,
    )
    # Files — local filesystem operations via shell commands
    from plutus.skills.apps.files import (
        CreateFile,
        OrganizeFolder,
        FindFiles,
        ZipFiles,
    )
    # Browser — general web navigation and downloads
    from plutus.skills.apps.browser import (
        GoogleSearch,
        OpenWebsite,
        DownloadFile,
    )

    for skill_class in [
        # Spotify
        SpotifyPlaySong,
        SpotifyPlayPause,
        SpotifyNextTrack,
        SpotifySearchPlay,
        # Files
        CreateFile,
        OrganizeFolder,
        FindFiles,
        ZipFiles,
        # Browser
        GoogleSearch,
        OpenWebsite,
        DownloadFile,
    ]:
        registry.register(skill_class())

    return registry
