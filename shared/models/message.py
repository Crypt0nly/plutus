from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Message:
    """A chat message exchanged between user and agent."""
    role: str  # 'user', 'assistant', 'system'
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)
    execution_context: str = "cloud"  # 'cloud' or 'local'

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "execution_context": self.execution_context,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.utcnow().isoformat())),
            metadata=data.get("metadata", {}),
            execution_context=data.get("execution_context", "cloud"),
        )


@dataclass
class Conversation:
    """A conversation thread."""
    id: str
    user_id: str
    messages: list[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    title: str = ""
    sync_version: int = 1
