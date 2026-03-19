"""Shared skills interface used by both local and cloud Plutus."""

from abc import ABC, abstractmethod


class BaseSkillStore(ABC):
    """Abstract skill store - implemented by SQLite (local) and Postgres (cloud)."""

    @abstractmethod
    async def save_skill(
        self,
        user_id: str,
        name: str,
        definition: dict,
        description: str = "",
        skill_type: str = "simple",
    ) -> int:
        ...

    @abstractmethod
    async def get_skill(self, user_id: str, skill_id: int) -> dict | None:
        ...

    @abstractmethod
    async def list_skills(
        self, user_id: str, include_shared: bool = True
    ) -> list[dict]:
        ...

    @abstractmethod
    async def delete_skill(self, user_id: str, skill_id: int) -> bool:
        ...

    @abstractmethod
    async def get_sync_changes(
        self, user_id: str, since_version: int = 0
    ) -> list[dict]:
        """Get all changes since a given sync version (for sync engine)."""
        ...
