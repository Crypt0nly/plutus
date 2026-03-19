"""Shared memory interface used by both local and cloud Plutus."""

from abc import ABC, abstractmethod
from typing import Any


class BaseMemoryStore(ABC):
    """Abstract memory store - implemented by SQLite (local) and Postgres (cloud)."""

    @abstractmethod
    async def save_fact(self, user_id: str, category: str, content: str, metadata: dict | None = None) -> int:
        ...

    @abstractmethod
    async def recall_facts(self, user_id: str, category: str | None = None, limit: int = 10) -> list[dict]:
        ...

    @abstractmethod
    async def search_facts(self, user_id: str, query: str, limit: int = 10) -> list[dict]:
        ...

    @abstractmethod
    async def delete_fact(self, user_id: str, fact_id: int) -> bool:
        ...

    @abstractmethod
    async def get_sync_changes(self, user_id: str, since_version: int) -> list[dict]:
        """Get all changes since a given sync version (for sync engine)."""
        ...
