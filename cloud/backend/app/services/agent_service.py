from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_state import AgentState, Memory, ScheduledTask, Skill


class AgentService:
    """Service for managing per-user agent state in the cloud."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # --- Agent State ---

    async def get_agent_state(self, user_id: str) -> AgentState | None:
        result = await self.session.execute(select(AgentState).where(AgentState.user_id == user_id))
        return result.scalar_one_or_none()

    async def ensure_agent_state(self, user_id: str) -> AgentState:
        """Get or create agent state for a user."""
        state = await self.get_agent_state(user_id)
        if not state:
            state = AgentState(user_id=user_id, status="idle")
            self.session.add(state)
            await self.session.commit()
            await self.session.refresh(state)
        return state

    # --- Memory ---

    async def save_memory(
        self,
        user_id: str,
        category: str,
        content: str,
        metadata: dict | None = None,
    ) -> Memory:
        mem = Memory(
            user_id=user_id,
            category=category,
            content=content,
            metadata_=metadata or {},
        )
        self.session.add(mem)
        await self.session.commit()
        await self.session.refresh(mem)
        return mem

    async def recall_memories(
        self,
        user_id: str,
        category: str | None = None,
        limit: int = 20,
    ) -> list[Memory]:
        query = select(Memory).where(Memory.user_id == user_id)
        if category:
            query = query.where(Memory.category == category)
        query = query.order_by(Memory.created_at.desc()).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    # --- Skills ---

    async def list_skills(self, user_id: str) -> list[Skill]:
        """Get user's custom skills + shared base skills."""
        query = select(Skill).where((Skill.user_id == user_id) | Skill.is_shared)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def save_skill(
        self,
        user_id: str,
        name: str,
        definition: dict,
        description: str = "",
        skill_type: str = "simple",
    ) -> Skill:
        skill = Skill(
            user_id=user_id,
            name=name,
            description=description,
            skill_type=skill_type,
            definition=definition,
        )
        self.session.add(skill)
        await self.session.commit()
        await self.session.refresh(skill)
        return skill

    # --- Scheduled Tasks ---

    async def list_scheduled_tasks(self, user_id: str) -> list[ScheduledTask]:
        query = select(ScheduledTask).where(ScheduledTask.user_id == user_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create_scheduled_task(
        self,
        user_id: str,
        name: str,
        schedule: str,
        prompt: str,
        description: str = "",
    ) -> ScheduledTask:
        task = ScheduledTask(
            user_id=user_id,
            name=name,
            description=description,
            schedule=schedule,
            prompt=prompt,
        )
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        return task

    # --- Conversations & Messages (used by CloudAgentRuntime) ---

    async def create_conversation(self, conversation_id: str, user_id: str) -> None:
        from app.models.conversation import Conversation

        conv = Conversation(
            id=conversation_id,
            user_id=user_id,
            title="New Conversation",
            is_active=True,
        )
        self.session.add(conv)
        await self.session.commit()

    async def get_messages(self, conversation_id: str):
        from app.models.conversation import Message

        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        return list(result.scalars().all())

    async def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        user_id: str | None = None,
    ) -> None:
        from app.models.conversation import Message

        msg = Message(
            conversation_id=conversation_id,
            user_id=user_id or "",
            role=role,
            content=content,
        )
        self.session.add(msg)
        await self.session.commit()

    async def get_memory_facts(self, user_id: str) -> list[str]:
        """Return memory content strings for system prompt."""
        memories = await self.recall_memories(user_id, limit=50)
        return [m.content for m in memories]

    async def get_available_tools(self, user_id: str) -> str:
        """Return a formatted string of available tools for system prompt."""
        skills = await self.list_skills(user_id)
        if not skills:
            return "No custom tools configured."
        return "\n".join(f"- {s.name}: {s.description}" for s in skills)
