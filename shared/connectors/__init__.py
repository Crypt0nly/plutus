from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime


@dataclass
class ConnectorConfig:
    """Configuration for a connector instance."""
    service: str  # telegram, github, gmail, discord, slack, etc.
    credentials: dict = field(default_factory=dict)
    is_enabled: bool = True
    settings: dict = field(default_factory=dict)
    last_connected: Optional[datetime] = None


@dataclass 
class ConnectorResult:
    """Result from a connector action."""
    success: bool
    data: Any = None
    error: Optional[str] = None


class BaseConnector(ABC):
    """Abstract base for all service connectors."""
    
    def __init__(self, config: ConnectorConfig):
        self.config = config
        self.service = config.service
    
    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection / verify credentials."""
        ...
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Clean up connection."""
        ...
    
    @abstractmethod
    async def execute(self, action: str, params: dict = None) -> ConnectorResult:
        """Execute a connector action (send message, list repos, etc.)."""
        ...
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the connector is working."""
        ...
    
    @property
    def is_configured(self) -> bool:
        return bool(self.config.credentials)


class ConnectorRegistry:
    """Registry for managing multiple connectors per user."""
    
    def __init__(self):
        self._connectors: dict[str, BaseConnector] = {}
    
    def register(self, connector: BaseConnector) -> None:
        self._connectors[connector.service] = connector
    
    def get(self, service: str) -> Optional[BaseConnector]:
        return self._connectors.get(service)
    
    def list_services(self) -> list[str]:
        return list(self._connectors.keys())
    
    def list_configured(self) -> list[str]:
        return [s for s, c in self._connectors.items() if c.is_configured]
    
    async def disconnect_all(self) -> None:
        for c in self._connectors.values():
            await c.disconnect()
