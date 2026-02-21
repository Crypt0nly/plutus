"""Base tool interface — all tools implement this."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from plutus.core.llm import ToolDefinition


class Tool(ABC):
    """Base class for all Plutus tools.

    Each tool has:
      - A unique name (used in guardrails and LLM function calling)
      - A description
      - A parameter schema (JSON Schema)
      - An async execute method
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier (e.g. 'shell', 'filesystem')."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description shown to the LLM."""

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for the tool's parameters."""

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Execute the tool action. Returns a result string or structured data."""

    def get_definition(self) -> ToolDefinition:
        """Convert to an LLM tool definition."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )
