"""Tool Creator — allows the agent to dynamically create new tools at runtime.

This is one of the most powerful features: Claude can write new Python tools,
validate them, register them, and use them immediately. This enables:
  - Self-extending capabilities
  - Task-specific tool creation
  - Custom automation scripts
  - One-off utilities

Created tools are saved to ~/.plutus/custom_tools/ and can be persisted
across sessions.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from plutus.core.subprocess_manager import SubprocessManager, SubprocessTask
from plutus.tools.base import Tool

logger = logging.getLogger("plutus.tool_creator")


def _get_custom_tools_dir() -> Path:
    """Get the directory for custom tools."""
    p = Path.home() / ".plutus" / "custom_tools"
    p.mkdir(parents=True, exist_ok=True)
    return p


class ToolCreatorTool(Tool):
    """Create, validate, and manage custom tools at runtime."""

    def __init__(
        self,
        subprocess_manager: SubprocessManager | None = None,
        tool_registry: Any = None,
    ):
        self._manager = subprocess_manager or SubprocessManager()
        self._registry = tool_registry
        self._custom_tools_dir = _get_custom_tools_dir()

    def set_registry(self, registry: Any) -> None:
        """Set the tool registry (called after initialization)."""
        self._registry = registry

    @property
    def name(self) -> str:
        return "tool_creator"

    @property
    def description(self) -> str:
        return (
            "Create new tools at runtime. Write Python code that extends the agent's capabilities. "
            "Created tools are validated, saved, and can be immediately registered for use. "
            "Use this when you need a specialized tool that doesn't exist yet."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["create", "validate", "list", "delete", "run", "info"],
                    "description": (
                        "The operation to perform:\n"
                        "- create: Create and save a new custom tool\n"
                        "- validate: Check if tool code is valid\n"
                        "- list: List all custom tools\n"
                        "- delete: Delete a custom tool\n"
                        "- run: Execute a custom tool directly\n"
                        "- info: Get details about a custom tool"
                    ),
                },
                "tool_name": {
                    "type": "string",
                    "description": "Name for the custom tool (snake_case).",
                },
                "description": {
                    "type": "string",
                    "description": "Description of what the tool does.",
                },
                "code": {
                    "type": "string",
                    "description": (
                        "Python code for the tool. Must define a 'main(args: dict) -> dict' function "
                        "that accepts a dict of arguments and returns a dict with 'success' and 'result' keys."
                    ),
                },
                "args": {
                    "type": "object",
                    "description": "Arguments to pass when running the tool.",
                },
                "register": {
                    "type": "boolean",
                    "description": "Whether to register the tool for LLM use (default: true).",
                },
            },
            "required": ["operation"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        operation = kwargs.get("operation", "list")

        if operation == "create":
            return await self._create_tool(kwargs)
        elif operation == "validate":
            return await self._validate_tool(kwargs)
        elif operation == "list":
            return self._list_tools()
        elif operation == "delete":
            return self._delete_tool(kwargs)
        elif operation == "run":
            return await self._run_tool(kwargs)
        elif operation == "info":
            return self._tool_info(kwargs)
        else:
            return f"[ERROR] Unknown operation: {operation}"

    async def _create_tool(self, kwargs: dict) -> str:
        tool_name = kwargs.get("tool_name", "")
        description = kwargs.get("description", "")
        code = kwargs.get("code", "")
        should_register = kwargs.get("register", True)

        if not tool_name:
            return "[ERROR] tool_name is required."
        if not code:
            return "[ERROR] code is required."

        # Validate the code first
        validation = await self._validate_code(code)
        if not validation.get("valid"):
            return f"[ERROR] Invalid code: {validation.get('message', 'Unknown error')}"

        # Save the tool
        tool_dir = self._custom_tools_dir / tool_name
        tool_dir.mkdir(parents=True, exist_ok=True)

        # Save the code
        script_path = tool_dir / "tool.py"
        script_path.write_text(code, encoding="utf-8")

        # Save metadata
        metadata = {
            "name": tool_name,
            "description": description,
            "script": str(script_path),
            "created_by": "agent",
        }
        meta_path = tool_dir / "metadata.json"
        meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        # Register if requested
        if should_register and self._registry:
            try:
                dynamic_tool = DynamicTool(
                    tool_name=tool_name,
                    tool_description=description,
                    script_path=str(script_path),
                    subprocess_manager=self._manager,
                )
                self._registry.register(dynamic_tool)
                logger.info(f"Registered custom tool: {tool_name}")
            except Exception as e:
                logger.warning(f"Failed to register tool {tool_name}: {e}")
                return (
                    f"Tool saved to {script_path} but registration failed: {e}. "
                    f"You can still run it with tool_creator run."
                )

        return json.dumps({
            "created": tool_name,
            "path": str(script_path),
            "registered": should_register,
            "description": description,
        }, indent=2)

    async def _validate_tool(self, kwargs: dict) -> str:
        code = kwargs.get("code", "")
        if not code:
            return "[ERROR] code is required."

        result = await self._validate_code(code)
        return json.dumps(result, indent=2)

    async def _validate_code(self, code: str) -> dict:
        """Validate code using the custom worker."""
        task = SubprocessTask(
            worker_type="custom",
            command={"action": "validate", "code": code},
            timeout=10.0,
        )
        result = await self._manager.spawn(task)
        if result.error:
            return {"valid": False, "message": result.error}
        return result.output or {"valid": False, "message": "No validation result"}

    def _list_tools(self) -> str:
        """List all custom tools."""
        tools = []
        if self._custom_tools_dir.exists():
            for tool_dir in sorted(self._custom_tools_dir.iterdir()):
                if tool_dir.is_dir():
                    meta_path = tool_dir / "metadata.json"
                    if meta_path.exists():
                        meta = json.loads(meta_path.read_text())
                        tools.append({
                            "name": meta.get("name", tool_dir.name),
                            "description": meta.get("description", ""),
                            "path": str(tool_dir / "tool.py"),
                        })
                    else:
                        tools.append({
                            "name": tool_dir.name,
                            "description": "(no metadata)",
                            "path": str(tool_dir / "tool.py"),
                        })

        if not tools:
            return "No custom tools found. Use 'create' to make one."

        return json.dumps({"tools": tools, "count": len(tools)}, indent=2)

    def _delete_tool(self, kwargs: dict) -> str:
        tool_name = kwargs.get("tool_name", "")
        if not tool_name:
            return "[ERROR] tool_name is required."

        tool_dir = self._custom_tools_dir / tool_name
        if not tool_dir.exists():
            return f"[ERROR] Tool not found: {tool_name}"

        import shutil
        shutil.rmtree(tool_dir)

        # Unregister if possible
        if self._registry and self._registry.get(f"custom_{tool_name}"):
            # Remove from registry
            if hasattr(self._registry, "_tools"):
                self._registry._tools.pop(f"custom_{tool_name}", None)

        return f"Deleted custom tool: {tool_name}"

    async def _run_tool(self, kwargs: dict) -> str:
        tool_name = kwargs.get("tool_name", "")
        args = kwargs.get("args", {})

        if not tool_name:
            return "[ERROR] tool_name is required."

        tool_dir = self._custom_tools_dir / tool_name
        script_path = tool_dir / "tool.py"

        if not script_path.exists():
            return f"[ERROR] Tool script not found: {script_path}"

        task = SubprocessTask(
            worker_type="custom",
            command={
                "action": "run_function",
                "path": str(script_path),
                "function": "main",
                "args": args,
            },
            timeout=60.0,
        )

        result = await self._manager.spawn(task)

        if result.error:
            return f"[ERROR] {result.error}"

        return json.dumps(result.output, indent=2)

    def _tool_info(self, kwargs: dict) -> str:
        tool_name = kwargs.get("tool_name", "")
        if not tool_name:
            return "[ERROR] tool_name is required."

        tool_dir = self._custom_tools_dir / tool_name
        if not tool_dir.exists():
            return f"[ERROR] Tool not found: {tool_name}"

        meta_path = tool_dir / "metadata.json"
        script_path = tool_dir / "tool.py"

        info: dict[str, Any] = {"name": tool_name}

        if meta_path.exists():
            info.update(json.loads(meta_path.read_text()))

        if script_path.exists():
            code = script_path.read_text()
            info["code_lines"] = len(code.splitlines())
            info["code_size"] = len(code)
            # Show first 50 lines
            info["code_preview"] = "\n".join(code.splitlines()[:50])

        return json.dumps(info, indent=2)


class DynamicTool(Tool):
    """A dynamically-created tool that runs via subprocess."""

    def __init__(
        self,
        tool_name: str,
        tool_description: str,
        script_path: str,
        subprocess_manager: SubprocessManager,
    ):
        self._name = f"custom_{tool_name}"
        self._description = tool_description
        self._script_path = script_path
        self._manager = subprocess_manager

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "args": {
                    "type": "object",
                    "description": "Arguments to pass to the tool's main() function.",
                },
            },
        }

    async def execute(self, **kwargs: Any) -> Any:
        args = kwargs.get("args", {})

        task = SubprocessTask(
            worker_type="custom",
            command={
                "action": "run_function",
                "path": self._script_path,
                "function": "main",
                "args": args,
            },
            timeout=60.0,
        )

        result = await self._manager.spawn(task)

        if result.error:
            return f"[ERROR] {result.error}"

        return json.dumps(result.output, indent=2)
