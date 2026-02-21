"""Tool registry — discovers and manages available tools."""

from __future__ import annotations

from typing import Any

from plutus.core.llm import ToolDefinition
from plutus.tools.base import Tool


class ToolRegistry:
    """Central registry of available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def get_definitions(self) -> list[ToolDefinition]:
        return [tool.get_definition() for tool in self._tools.values()]

    def get_tool_info(self) -> list[dict[str, Any]]:
        """Return serializable info about all registered tools for the UI."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in self._tools.values()
        ]


def create_default_registry() -> ToolRegistry:
    """Create a registry with all built-in tools."""
    from plutus.tools.app_manager import AppManagerTool
    from plutus.tools.browser import BrowserTool
    from plutus.tools.clipboard import ClipboardTool
    from plutus.tools.desktop import DesktopTool
    from plutus.tools.filesystem import FilesystemTool
    from plutus.tools.process import ProcessTool
    from plutus.tools.shell import ShellTool
    from plutus.tools.system_info import SystemInfoTool

    registry = ToolRegistry()
    registry.register(ShellTool())
    registry.register(FilesystemTool())
    registry.register(BrowserTool())
    registry.register(ProcessTool())
    registry.register(SystemInfoTool())
    registry.register(ClipboardTool())
    registry.register(DesktopTool())
    registry.register(AppManagerTool())
    return registry
