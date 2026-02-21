"""Subprocess Tool — allows the agent to spawn worker subprocesses.

This is the key tool that gives Claude the ability to:
  - Spawn isolated subprocesses for file editing, code analysis, shell commands
  - Run multiple tasks in parallel
  - Execute dynamically-created tools
  - Manage running workers
"""

from __future__ import annotations

import json
from typing import Any

from plutus.core.subprocess_manager import (
    SubprocessManager,
    SubprocessTask,
    TaskPriority,
)
from plutus.tools.base import Tool


class SubprocessTool(Tool):
    """Spawn and manage worker subprocesses for parallel task execution."""

    def __init__(self, manager: SubprocessManager | None = None):
        self._manager = manager or SubprocessManager()

    @property
    def name(self) -> str:
        return "subprocess"

    @property
    def description(self) -> str:
        return (
            "Spawn worker subprocesses for parallel task execution. "
            "Supports shell commands, file editing, code analysis, and custom scripts. "
            "Use this to run isolated tasks that won't block the main agent. "
            "Worker types: 'shell' (run commands), 'file_edit' (create/edit/read files), "
            "'code_analysis' (analyze Python code), 'custom' (run custom scripts)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["spawn", "spawn_many", "list_active", "list_results", "cancel"],
                    "description": "The subprocess operation to perform.",
                },
                "worker_type": {
                    "type": "string",
                    "enum": ["shell", "file_edit", "code_analysis", "custom"],
                    "description": "Type of worker to spawn (for 'spawn' operation).",
                },
                "command": {
                    "type": "object",
                    "description": (
                        "The command to send to the worker. Structure depends on worker_type:\n"
                        "- shell: {action: 'exec', command: 'ls -la', timeout: 30, cwd: '/path'}\n"
                        "- file_edit: {action: 'read|write|edit|delete|list|find|grep|...', path: '...', ...}\n"
                        "- code_analysis: {action: 'analyze|find_functions|complexity|...', path: '...'}\n"
                        "- custom: {action: 'run_script|run_inline|run_function', path: '...', code: '...', args: {}}"
                    ),
                },
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "worker_type": {"type": "string"},
                            "command": {"type": "object"},
                            "timeout": {"type": "number"},
                        },
                    },
                    "description": "List of tasks for 'spawn_many' operation.",
                },
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds (default: 60).",
                },
                "working_dir": {
                    "type": "string",
                    "description": "Working directory for the subprocess.",
                },
                "task_id": {
                    "type": "string",
                    "description": "Task ID (for 'cancel' operation).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (for 'list_results').",
                },
            },
            "required": ["operation"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        operation = kwargs.get("operation", "spawn")

        if operation == "spawn":
            return await self._spawn(kwargs)
        elif operation == "spawn_many":
            return await self._spawn_many(kwargs)
        elif operation == "list_active":
            return json.dumps(self._manager.list_active(), indent=2)
        elif operation == "list_results":
            limit = kwargs.get("limit", 20)
            return json.dumps(self._manager.list_results(limit), indent=2)
        elif operation == "cancel":
            task_id = kwargs.get("task_id", "")
            success = await self._manager.cancel(task_id)
            return f"Task {task_id} cancelled." if success else f"Task {task_id} not found or not running."
        else:
            return f"[ERROR] Unknown operation: {operation}"

    async def _spawn(self, kwargs: dict) -> str:
        worker_type = kwargs.get("worker_type", "shell")
        command = kwargs.get("command", {})
        timeout = kwargs.get("timeout", 60.0)
        working_dir = kwargs.get("working_dir")

        task = SubprocessTask(
            worker_type=worker_type,
            command=command,
            timeout=timeout,
            working_dir=working_dir,
        )

        result = await self._manager.spawn(task)
        return json.dumps(result.to_dict(), indent=2)

    async def _spawn_many(self, kwargs: dict) -> str:
        tasks_data = kwargs.get("tasks", [])
        if not tasks_data:
            return "[ERROR] No tasks provided for spawn_many."

        tasks = []
        for td in tasks_data:
            tasks.append(SubprocessTask(
                worker_type=td.get("worker_type", "shell"),
                command=td.get("command", {}),
                timeout=td.get("timeout", 60.0),
                working_dir=td.get("working_dir"),
            ))

        results = await self._manager.spawn_many(tasks)
        return json.dumps([r.to_dict() for r in results], indent=2)
