from sqlalchemy import select, delete, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.agent_state import Skill
from . import BaseSkillStore


class CloudSkillStore(BaseSkillStore):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save_skill(
        self,
        user_id: str,
        name: str,
        definition: dict,
        description: str = "",
        skill_type: str = "simple",
    ) -> int:
        version_result = await self.session.execute(
            select(func.coalesce(func.max(Skill.sync_version), 0)).where(
                Skill.user_id == user_id
            )
        )
        next_version = version_result.scalar() + 1

        skill = Skill(
            user_id=user_id,
            name=name,
            description=description,
            skill_type=skill_type,
            definition=definition,
            sync_version=next_version,
        )
        self.session.add(skill)
        await self.session.flush()
        return skill.id

    async def get_skill(self, user_id: str, skill_id: int) -> dict | None:
        stmt = (
            select(Skill)
            .where(Skill.id == skill_id)
            .where(or_(Skill.user_id == user_id, Skill.is_shared.is_(True)))
        )
        result = await self.session.execute(stmt)
        skill = result.scalars().first()
        return _row(skill) if skill else None

    async def list_skills(
        self, user_id: str, include_shared: bool = True
    ) -> list[dict]:
        if include_shared:
            stmt = (
                select(Skill)
                .where(or_(Skill.user_id == user_id, Skill.is_shared.is_(True)))
                .order_by(Skill.sync_version.desc())
            )
        else:
            stmt = (
                select(Skill)
                .where(Skill.user_id == user_id)
                .order_by(Skill.sync_version.desc())
            )
        result = await self.session.execute(stmt)
        return [_row(s) for s in result.scalars().all()]

    async def delete_skill(self, user_id: str, skill_id: int) -> bool:
        stmt = (
            delete(Skill)
            .where(Skill.user_id == user_id)
            .where(Skill.id == skill_id)
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def get_sync_changes(
        self, user_id: str, since_version: int = 0
    ) -> list[dict]:
        stmt = (
            select(Skill)
            .where(Skill.user_id == user_id)
            .where(Skill.sync_version > since_version)
            .order_by(Skill.sync_version.asc())
        )
        result = await self.session.execute(stmt)
        return [_row(s) for s in result.scalars().all()]


def _row(s: Skill) -> dict:
    return {
        "id": s.id,
        "user_id": s.user_id,
        "name": s.name,
        "description": s.description,
        "skill_type": s.skill_type,
        "definition": s.definition,
        "is_shared": s.is_shared,
        "sync_version": s.sync_version,
    }
