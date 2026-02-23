"""Worker Tool — allows the Coordinator to spawn and manage agent workers.

The Coordinator (you) is the team lead. When you need to delegate tasks,
use this tool to spawn workers. YOU decide which model each worker uses
based on what the task requires:

  - "claude-haiku":  Fast & cheap. Use for simple lookups, fetching data, summaries.
  - "claude-sonnet": Balanced. Use for standard tasks that need some reasoning.
  - "claude-opus":   Smartest. Use for complex analysis, writing, architecture.
  - "gpt-5.2":      OpenAI alternative for complex tasks.
  - "auto":          Let the system auto-select based on task complexity.

Operations:
  - spawn:       Spawn a new worker with a task and model choice
  - spawn_many:  Spawn multiple workers at once for parallel execution
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
            "You are the Coordinator — the team lead. Use this to delegate tasks to workers.\n\n"
            "YOU choose which model each worker uses based on the task:\n"
            "- 'claude-haiku': Fast & cheap — fetching data, summaries, simple lookups\n"
            "- 'claude-sonnet': Balanced — standard tasks needing some reasoning\n"
            "- 'claude-opus': Smartest — complex analysis, writing, deep research\n"
            "- 'gpt-5.2': OpenAI alternative for complex tasks\n"
            "- 'auto': Let the system pick based on task complexity\n\n"
            "Operations:\n"
            "- spawn: Create a new worker. Set model_key to choose its brain.\n"
            "- spawn_many: Create multiple workers at once for parallel execution\n"
            "- list: List all active and recent workers\n"
            "- status: Get detailed status of a specific worker\n"
            "- cancel: Cancel a running worker\n"
            "- wait: Wait for a worker to complete and get its result\n"
            "- stats: Get worker pool statistics\n\n"
            "Example: To research news while writing a blog post:\n"
            "  1. worker(operation='spawn', name='News Research', prompt='Research latest AI news', model_key='claude-haiku')\n"
            "  2. You (the Coordinator) start writing the blog post using your own model\n"
            "  3. worker(operation='wait', task_id='...') to get the research results\n"
            "  4. Incorporate the results into the blog post"
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
                    "description": "Human-readable name for the worker (for 'spawn'). E.g. 'News Researcher', 'Data Analyzer'.",
                },
                "prompt": {
                    "type": "string",
                    "description": "The task instruction for the worker (for 'spawn'). Be specific about what you want.",
                },
                "model_key": {
                    "type": "string",
                    "enum": ["claude-haiku", "claude-sonnet", "claude-opus", "gpt-5.2", "auto"],
                    "description": (
                        "Which model the worker should use. YOU decide based on the task:\n"
                        "- 'claude-haiku': Simple tasks (fetching, summarizing, lookups)\n"
                        "- 'claude-sonnet': Medium tasks (browsing, standard work)\n"
                        "- 'claude-opus': Hard tasks (analysis, writing, research)\n"
                        "- 'gpt-5.2': OpenAI alternative\n"
                        "- 'auto': System picks based on task complexity"
                    ),
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
                            "name": {"type": "string", "description": "Worker name"},
                            "prompt": {"type": "string", "description": "Task instruction"},
                            "model_key": {
                                "type": "string",
                                "enum": ["claude-haiku", "claude-sonnet", "claude-opus", "gpt-5.2", "auto"],
                                "description": "Model for this worker",
                            },
                            "timeout": {"type": "number"},
                        },
                        "required": ["prompt"],
                    },
                    "description": "List of tasks for 'spawn_many' operation. Each task gets its own worker.",
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

        model_key = kwargs.get("model_key", "auto")

        task = WorkerTask(
            name=kwargs.get("name", ""),
            prompt=prompt,
            model_key=model_key,
            timeout=kwargs.get("timeout", 300.0),
        )

        status = await self._pool.submit(task)
        return json.dumps({
            "success": True,
            "message": f"Worker '{status.name}' spawned with model '{model_key}'.",
            "task_id": status.task_id,
            "state": status.state.value,
            "model": model_key,
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
                model_key=td.get("model_key", "auto"),
                timeout=td.get("timeout", 300.0),
            ))

        statuses = await self._pool.submit_many(tasks)
        return json.dumps({
            "success": True,
            "message": f"Spawned {len(statuses)} workers.",
            "workers": [
                {
                    "task_id": s.task_id,
                    "name": s.name,
                    "state": s.state.value,
                    "model": tasks[i].model_key if i < len(tasks) else "auto",
                }
                for i, s in enumerate(statuses)
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
