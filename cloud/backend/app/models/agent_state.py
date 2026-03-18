from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func

from app.models.base import Base, TimestampMixin


class AgentState(Base, TimestampMixin):
    """Per-user agent runtime state."""

    __tablename__ = "agent_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String, default="idle")  # idle, busy, offline
    current_task = Column(Text, nullable=True)
    execution_context = Column(String, default="cloud")  # cloud, local, auto
    bridge_connected = Column(Boolean, default=False)
    last_heartbeat = Column(DateTime(timezone=True), nullable=True)


class Memory(Base, TimestampMixin):
    """Per-user persistent memory/facts."""

    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    category = Column(String, nullable=False, index=True)
    content = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSON, default=dict)
    sync_version = Column(Integer, default=1)
    synced_at = Column(DateTime(timezone=True), server_default=func.now())


class Skill(Base, TimestampMixin):
    """Per-user custom skills (shared base skills are loaded separately)."""

    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    skill_type = Column(String, default="simple")  # simple, python
    definition = Column(JSON, nullable=False)
    is_shared = Column(Boolean, default=False)  # Base skill available to all users
    sync_version = Column(Integer, default=1)


class ScheduledTask(Base, TimestampMixin):
    """Per-user scheduled/recurring tasks."""

    __tablename__ = "scheduled_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    schedule = Column(String, nullable=False)  # Cron expression
    prompt = Column(Text, nullable=False)  # What to execute
    is_active = Column(Boolean, default=True)
    last_run = Column(DateTime(timezone=True), nullable=True)
    next_run = Column(DateTime(timezone=True), nullable=True)
