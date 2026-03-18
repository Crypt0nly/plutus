from sqlalchemy import JSON, Boolean, Column, ForeignKey, Integer, String, Text

from app.models.base import Base, TimestampMixin


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True)  # UUID
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    metadata_ = Column("metadata", JSON, default=dict)


class Message(Base, TimestampMixin):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    tool_calls = Column(JSON, nullable=True)
    token_count = Column(Integer, nullable=True)
