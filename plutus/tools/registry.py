"""Tool registry — discovers and manages available tools, including dynamic hot-reload."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from plutus.core.llm import ToolDefinition
from plutus.tools.base import Tool

logger = logging.getLogger("plutus.tools.registry")


class ToolRegistry:
    """Central registry of available tools with hot-reload support."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool (or replace an existing one with the same name)."""
        if tool.name in self._tools:
            logger.info(f"Replacing tool: {tool.name}")
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def unregister(self, name: str) -> bool:
        """Remove a tool from the registry."""
        if name in self._tools:
            del self._tools[name]
            logger.info(f"Unregistered tool: {name}")
            return True
        return False

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

    def load_custom_tools(self, custom_tools_dir: Path | None = None) -> int:
        """Load persisted custom tools from disk.

        Returns the number of tools loaded.
        """
        from plutus.core.subprocess_manager import SubprocessManager
        from plutus.tools.tool_creator import DynamicTool

        tools_dir = custom_tools_dir or (Path.home() / ".plutus" / "custom_tools")
        if not tools_dir.exists():
            return 0

        loaded = 0
        manager = SubprocessManager()

        for tool_dir in sorted(tools_dir.iterdir()):
            if not tool_dir.is_dir():
                continue

            meta_path = tool_dir / "metadata.json"
            script_path = tool_dir / "tool.py"

            if not script_path.exists():
                continue

            try:
                if meta_path.exists():
                    meta = json.loads(meta_path.read_text())
                    tool_name = meta.get("name", tool_dir.name)
                    description = meta.get("description", "Custom tool")
                else:
                    tool_name = tool_dir.name
                    description = "Custom tool"

                dynamic_tool = DynamicTool(
                    tool_name=tool_name,
                    tool_description=description,
                    script_path=str(script_path),
                    subprocess_manager=manager,
                )
                self.register(dynamic_tool)
                loaded += 1
                logger.info(f"Loaded custom tool: {tool_name}")
            except Exception as e:
                logger.warning(f"Failed to load custom tool from {tool_dir}: {e}")

        return loaded


def create_default_registry() -> ToolRegistry:
    """Create a registry with all built-in tools, including new subprocess-based tools."""
    from plutus.core.subprocess_manager import SubprocessManager
    from plutus.tools.app_manager import AppManagerTool
    from plutus.tools.browser import BrowserTool
    from plutus.tools.clipboard import ClipboardTool
    from plutus.tools.code_analysis import CodeAnalysisTool
    from plutus.tools.code_editor import CodeEditorTool
    from plutus.tools.desktop import DesktopTool
    from plutus.tools.filesystem import FilesystemTool
    from plutus.tools.process import ProcessTool
    from plutus.tools.shell import ShellTool
    from plutus.tools.subprocess_tool import SubprocessTool
    from plutus.tools.system_info import SystemInfoTool
    from plutus.tools.tool_creator import ToolCreatorTool

    # Shared subprocess manager for all subprocess-based tools
    subprocess_mgr = SubprocessManager(max_workers=8, default_timeout=60.0)

    registry = ToolRegistry()

    # Core tools
    registry.register(ShellTool())
    registry.register(FilesystemTool())
    registry.register(ProcessTool())
    registry.register(SystemInfoTool())

    # New subprocess-powered tools
    registry.register(CodeEditorTool(subprocess_mgr))
    registry.register(CodeAnalysisTool(subprocess_mgr))
    registry.register(SubprocessTool(subprocess_mgr))

    # Tool creator (needs registry reference for dynamic registration)
    tool_creator = ToolCreatorTool(subprocess_mgr, registry)
    registry.register(tool_creator)

    # Desktop/GUI tools (may not work in all environments)
    registry.register(BrowserTool())
    registry.register(ClipboardTool())
    registry.register(DesktopTool())
    registry.register(AppManagerTool())

    # Load any persisted custom tools
    loaded = registry.load_custom_tools()
    if loaded:
        logger.info(f"Loaded {loaded} custom tools from disk")

    return registry
