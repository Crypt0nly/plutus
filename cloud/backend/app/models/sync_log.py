from sqlalchemy import JSON, Column, ForeignKey, Integer, String

from app.models.base import Base, TimestampMixin


class SyncLog(Base, TimestampMixin):
    __tablename__ = "sync_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    action = Column(String, nullable=False)  # create, update, delete
    data = Column(JSON, nullable=False)
    sync_version = Column(Integer, nullable=False)
    source = Column(String, default="cloud")  # cloud or local
