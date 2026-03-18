from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass
class SyncPayload:
    """Payload for syncing state between local and cloud.
    
    Uses last-write-wins strategy with timestamps.
    Cloud Postgres is the source of truth.
    Local SQLite mirrors cloud state.
    """
    entity_type: str  # 'memory', 'skill', 'conversation', 'scheduled_task', 'setting'
    entity_id: str
    user_id: str
    action: Literal["create", "update", "delete"]
    data: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: Literal["local", "cloud"] = "cloud"
    sync_version: int = 1

    def to_dict(self) -> dict:
        return {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "user_id": self.user_id,
            "action": self.action,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "sync_version": self.sync_version,
        }


@dataclass
class SyncConflict:
    """Represents a sync conflict between local and cloud state."""
    entity_type: str
    entity_id: str
    local_data: dict[str, Any]
    cloud_data: dict[str, Any]
    local_timestamp: datetime
    cloud_timestamp: datetime
    resolution: Literal["local_wins", "cloud_wins", "unresolved"] = "unresolved"

    def resolve_last_write_wins(self) -> "SyncConflict":
        """Resolve using last-write-wins strategy."""
        if self.local_timestamp >= self.cloud_timestamp:
            self.resolution = "local_wins"
        else:
            self.resolution = "cloud_wins"
        return self
