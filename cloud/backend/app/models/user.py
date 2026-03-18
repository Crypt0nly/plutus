from sqlalchemy import Column, String, Boolean, JSON, DateTime, func
from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """Multi-tenant user. clerk_id is the primary identifier from Clerk."""

    __tablename__ = "users"

    id = Column(String, primary_key=True)  # Clerk user ID (user_xxx)
    email = Column(String, unique=True, nullable=False, index=True)
    display_name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    plan = Column(String, default="free")  # free, pro, enterprise
    is_active = Column(Boolean, default=True)
    settings = Column(JSON, default=dict)  # User-specific agent settings
    connector_credentials = Column(JSON, default=dict)  # Encrypted connector creds
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now())
