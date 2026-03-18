from typing import Any
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.agent_state import Memory
from . import BaseMemoryStore


class CloudMemoryStore(BaseMemoryStore):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save_fact(
        self,
        user_id: str,
        category: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        version_result = await self.session.execute(
            select(func.coalesce(func.max(Memory.sync_version), 0)).where(
                Memory.user_id == user_id
            )
        )
        next_version = version_result.scalar() + 1

        fact = Memory(
            user_id=user_id,
            category=category,
            content=content,
            metadata_=metadata or {},
            sync_version=next_version,
        )
        self.session.add(fact)
        await self.session.flush()
        return fact.id

    async def recall_facts(
        self,
        user_id: str,
        category: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        stmt = select(Memory).where(Memory.user_id == user_id)
        if category is not None:
            stmt = stmt.where(Memory.category == category)
        stmt = stmt.order_by(Memory.sync_version.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return [_row(m) for m in result.scalars().all()]

    async def search_facts(
        self,
        user_id: str,
        query: str,
        limit: int = 10,
    ) -> list[dict]:
        stmt = (
            select(Memory)
            .where(Memory.user_id == user_id)
            .where(Memory.content.ilike(f"%{query}%"))
            .order_by(Memory.sync_version.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [_row(m) for m in result.scalars().all()]

    async def delete_fact(self, user_id: str, fact_id: int) -> bool:
        stmt = (
            delete(Memory)
            .where(Memory.user_id == user_id)
            .where(Memory.id == fact_id)
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def get_sync_changes(
        self, user_id: str, since_version: int
    ) -> list[dict]:
        stmt = (
            select(Memory)
            .where(Memory.user_id == user_id)
            .where(Memory.sync_version > since_version)
            .order_by(Memory.sync_version.asc())
        )
        result = await self.session.execute(stmt)
        return [_row(m) for m in result.scalars().all()]


def _row(m: Memory) -> dict:
    return {
        "id": m.id,
        "user_id": m.user_id,
        "category": m.category,
        "content": m.content,
        "metadata": m.metadata_,
        "sync_version": m.sync_version,
    }
