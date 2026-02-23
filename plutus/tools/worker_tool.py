"""Worker Tool — allows the agent to spawn and manage agent workers.

This replaces the old SubprocessTool for most use cases. Workers are
lightweight agents that can call the LLM and use tools, running in
parallel with the main agent.

Operations:
  - spawn:       Spawn a new worker with a task
  - spawn_many:  Spawn multiple workers at once
  - list:        List all active and recent workers
  - status:      Get status of a specific worker
  - cancel:      Cancel a running worker
  - wait:        Wait for a worker to complete and get its result
  - stats:       Get worker pool statistics
"""

from __future__ import annotations

import json
from typing import Any

from plutus.core.worker_pool import WorkerPool, WorkerTask
from plutus.tools.base import Tool


class WorkerTool(Tool):
    """Spawn and manage agent workers for parallel task execution."""

    def __init__(self, pool: WorkerPool):
        self._pool = pool

    @property
    def name(self) -> str:
        return "worker"

    @property
    def description(self) -> str:
        return (
            "Spawn and manage agent workers for parallel task execution. "
            "Workers are lightweight agents that can think, plan, and use tools independently. "
            "Use this to delegate tasks, run things in parallel, or offload simple work.\n\n"
            "Operations:\n"
            "- spawn: Create a new worker with a task prompt\n"
            "- spawn_many: Create multiple workers at once for parallel execution\n"
            "- list: List all active and recent workers\n"
            "- status: Get detailed status of a specific worker\n"
            "- cancel: Cancel a running worker\n"
            "- wait: Wait for a worker to complete and get its result\n"
            "- stats: Get worker pool statistics\n\n"
            "Model selection: Set model_key to choose which model the worker uses:\n"
            "- 'claude-haiku': Fast and cheap — summaries, simple lookups, classification\n"
            "- 'claude-sonnet': Balanced — most tasks (default)\n"
            "- 'claude-opus': Complex reasoning, architecture, deep analysis\n"
            "- 'gpt-5.2': OpenAI alternative\n"
            "- null: Auto-select based on task complexity"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["spawn", "spawn_many", "list", "status", "cancel", "wait", "stats"],
                    "description": "The worker operation to perform.",
                },
                "name": {
                    "type": "string",
                    "description": "Human-readable name for the worker (for 'spawn').",
                },
                "prompt": {
                    "type": "string",
                    "description": "The task instruction for the worker (for 'spawn').",
                },
                "model_key": {
                    "type": "string",
                    "enum": ["claude-haiku", "claude-sonnet", "claude-opus", "gpt-5.2"],
                    "description": "Which model the worker should use. Omit for auto-selection.",
                },
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds (default: 300).",
                },
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "prompt": {"type": "string"},
                            "model_key": {"type": "string"},
                            "timeout": {"type": "number"},
                        },
                        "required": ["prompt"],
                    },
                    "description": "List of tasks for 'spawn_many' operation.",
                },
                "task_id": {
                    "type": "string",
                    "description": "Worker task ID (for 'status', 'cancel', 'wait').",
                },
            },
            "required": ["operation"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        operation = kwargs.get("operation", "list")

        try:
            if operation == "spawn":
                return await self._spawn(kwargs)
            elif operation == "spawn_many":
                return await self._spawn_many(kwargs)
            elif operation == "list":
                return self._list()
            elif operation == "status":
                return self._status(kwargs)
            elif operation == "cancel":
                return await self._cancel(kwargs)
            elif operation == "wait":
                return await self._wait(kwargs)
            elif operation == "stats":
                return self._stats()
            else:
                return f"[ERROR] Unknown operation: {operation}"
        except Exception as e:
            return f"[ERROR] Worker operation failed: {e}"

    async def _spawn(self, kwargs: dict) -> str:
        prompt = kwargs.get("prompt", "")
        if not prompt:
            return "[ERROR] 'prompt' is required for spawn operation."

        task = WorkerTask(
            name=kwargs.get("name", ""),
            prompt=prompt,
            model_key=kwargs.get("model_key"),
            timeout=kwargs.get("timeout", 300.0),
        )

        status = await self._pool.submit(task)
        return json.dumps({
            "success": True,
            "message": f"Worker '{status.name}' spawned successfully.",
            "task_id": status.task_id,
            "state": status.state.value,
            "tip": "Use worker(operation='wait', task_id='...') to get the result when done.",
        }, indent=2)

    async def _spawn_many(self, kwargs: dict) -> str:
        tasks_data = kwargs.get("tasks", [])
        if not tasks_data:
            return "[ERROR] 'tasks' array is required for spawn_many."

        tasks = []
        for td in tasks_data:
            tasks.append(WorkerTask(
                name=td.get("name", ""),
                prompt=td.get("prompt", ""),
                model_key=td.get("model_key"),
                timeout=td.get("timeout", 300.0),
            ))

        statuses = await self._pool.submit_many(tasks)
        return json.dumps({
            "success": True,
            "message": f"Spawned {len(statuses)} workers.",
            "workers": [
                {"task_id": s.task_id, "name": s.name, "state": s.state.value}
                for s in statuses
            ],
        }, indent=2)

    def _list(self) -> str:
        all_workers = self._pool.list_all()
        if not all_workers:
            return json.dumps({"workers": [], "message": "No workers active or recent."})
        return json.dumps({"workers": all_workers}, indent=2)

    def _status(self, kwargs: dict) -> str:
        task_id = kwargs.get("task_id", "")
        if not task_id:
            return "[ERROR] 'task_id' is required."
        status = self._pool.get_status(task_id)
        if not status:
            return f"[ERROR] Worker '{task_id}' not found."
        return json.dumps(status.to_dict(), indent=2)

    async def _cancel(self, kwargs: dict) -> str:
        task_id = kwargs.get("task_id", "")
        if not task_id:
            return "[ERROR] 'task_id' is required."
        success = await self._pool.cancel(task_id)
        if success:
            return f"Worker '{task_id}' cancelled."
        return f"Worker '{task_id}' not found or already completed."

    async def _wait(self, kwargs: dict) -> str:
        task_id = kwargs.get("task_id", "")
        if not task_id:
            return "[ERROR] 'task_id' is required."
        timeout = kwargs.get("timeout", 300.0)
        status = await self._pool.wait_for(task_id, timeout=timeout)
        if not status:
            return f"[ERROR] Worker '{task_id}' not found."
        return json.dumps(status.to_dict(), indent=2)

    def _stats(self) -> str:
        return json.dumps(self._pool.stats(), indent=2)
