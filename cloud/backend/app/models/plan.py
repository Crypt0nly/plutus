"""SQLAlchemy model for cloud agent plans."""
from __future__ import annotations

import time

from sqlalchemy import Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    steps: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False, default=time.time)

    __table_args__ = (
        Index("ix_plans_user_id", "user_id"),
        Index("ix_plans_status", "status"),
    )
