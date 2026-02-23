"""Worker Pool — manages concurrent agent workers for parallel task execution.

Unlike the old SubprocessManager (which spawns Python scripts communicating via
stdin/stdout), the WorkerPool manages **agent workers** — lightweight agents that
can call the LLM, use tools, and report status back to the main agent.

This enables patterns like:
  - "Research AI news" (worker 1) while "Write blog post" (worker 2)
  - Spawn a worker to monitor something in the background
  - Delegate simple subtasks to cheaper models (Haiku) while main agent uses Sonnet

Each worker:
  - Has its own LLM client (model chosen by the router)
  - Can use a subset of tools
  - Reports status updates in real-time
  - Has a timeout and can be cancelled
  - Runs as an asyncio task (not a subprocess)
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable

logger = logging.getLogger("plutus.worker_pool")


class WorkerState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class WorkerTask:
    """A task to be executed by an agent worker."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""                        # Human-readable name
    prompt: str = ""                      # The instruction for the worker
    model_key: str | None = None          # Explicit model choice (None = auto-route)
    complexity: str | None = None         # "simple", "moderate", "complex" (hint)
    timeout: float = 300.0                # 5 min default
    tools: list[str] | None = None        # Tool names the worker can use (None = all)
    parent_task_id: str | None = None     # If spawned by another worker
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "prompt": self.prompt[:200] + ("..." if len(self.prompt) > 200 else ""),
            "model_key": self.model_key,
            "complexity": self.complexity,
            "timeout": self.timeout,
            "tools": self.tools,
            "parent_task_id": self.parent_task_id,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


@dataclass
class WorkerStatus:
    """Real-time status of a worker."""
    task_id: str
    state: WorkerState
    name: str = ""
    model_used: str = ""                  # Display name of the model being used
    current_step: str = ""                # What the worker is doing right now
    steps_completed: int = 0
    progress_pct: float = 0.0             # 0-100
    result: str | None = None
    error: str | None = None
    started_at: float = 0.0
    completed_at: float = 0.0
    duration: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "state": self.state.value,
            "name": self.name,
            "model_used": self.model_used,
            "current_step": self.current_step,
            "steps_completed": self.steps_completed,
            "progress_pct": round(self.progress_pct, 1),
            "result": self.result[:500] if self.result and len(self.result) > 500 else self.result,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration": round(self.duration, 2),
        }


# Type for the worker execution function
# Signature: async def execute(task, on_status_update) -> str
WorkerExecutor = Callable[
    ["WorkerTask", Callable[[WorkerStatus], Awaitable[None]]],
    Awaitable[str]
]


class WorkerPool:
    """Manages a pool of concurrent agent workers.

    The pool enforces a configurable max concurrency limit. Tasks beyond the
    limit are queued and executed as slots become available.

    Usage:
        pool = WorkerPool(max_workers=3, executor=my_executor_fn)

        # Submit a task
        status = await pool.submit(WorkerTask(name="Research", prompt="..."))

        # Check status
        all_workers = pool.list_all()

        # Cancel a worker
        await pool.cancel("task_id")
    """

    def __init__(
        self,
        max_workers: int = 3,
        executor: WorkerExecutor | None = None,
        on_status_change: Callable[[WorkerStatus], Awaitable[None]] | None = None,
    ):
        self._max_workers = max_workers
        self._executor = executor
        self._on_status_change = on_status_change

        # State tracking
        self._queue: asyncio.Queue[WorkerTask] = asyncio.Queue()
        self._active: dict[str, WorkerStatus] = {}
        self._completed: list[WorkerStatus] = []
        self._tasks: dict[str, asyncio.Task] = {}  # asyncio tasks
        self._all_tasks: dict[str, WorkerTask] = {}  # task definitions

        # Stats
        self._total_submitted = 0
        self._total_completed = 0
        self._total_failed = 0

        # Semaphore for concurrency control
        self._semaphore = asyncio.Semaphore(max_workers)
        self._running = False

    @property
    def max_workers(self) -> int:
        return self._max_workers

    @max_workers.setter
    def max_workers(self, value: int) -> None:
        self._max_workers = max(1, min(value, 20))
        # Recreate semaphore (active tasks will finish, new ones use new limit)
        self._semaphore = asyncio.Semaphore(self._max_workers)

    def set_executor(self, executor: WorkerExecutor) -> None:
        """Set the worker executor function (called after init when agent is ready)."""
        self._executor = executor

    async def submit(self, task: WorkerTask) -> WorkerStatus:
        """Submit a task for execution. Returns immediately with queued status."""
        if not self._executor:
            raise RuntimeError("No executor set — call set_executor() first")

        self._total_submitted += 1
        self._all_tasks[task.id] = task

        # Create initial status
        status = WorkerStatus(
            task_id=task.id,
            state=WorkerState.QUEUED,
            name=task.name or f"Worker-{task.id[:6]}",
        )
        self._active[task.id] = status

        if self._on_status_change:
            await self._on_status_change(status)

        # Launch the worker as an asyncio task
        async_task = asyncio.create_task(
            self._run_worker(task),
            name=f"worker-{task.id}"
        )
        self._tasks[task.id] = async_task

        logger.info(f"Worker submitted: {task.name} ({task.id})")
        return status

    async def submit_many(self, tasks: list[WorkerTask]) -> list[WorkerStatus]:
        """Submit multiple tasks at once."""
        return [await self.submit(t) for t in tasks]

    async def cancel(self, task_id: str) -> bool:
        """Cancel a running or queued worker."""
        if task_id in self._tasks:
            self._tasks[task_id].cancel()
            if task_id in self._active:
                self._active[task_id].state = WorkerState.CANCELLED
                self._active[task_id].completed_at = time.time()
                if self._on_status_change:
                    await self._on_status_change(self._active[task_id])
                self._move_to_completed(task_id)
            logger.info(f"Worker cancelled: {task_id}")
            return True
        return False

    async def cancel_all(self) -> int:
        """Cancel all active workers. Returns count of cancelled tasks."""
        count = 0
        for task_id in list(self._tasks.keys()):
            if await self.cancel(task_id):
                count += 1
        return count

    def get_status(self, task_id: str) -> WorkerStatus | None:
        """Get the status of a specific worker."""
        if task_id in self._active:
            return self._active[task_id]
        for s in self._completed:
            if s.task_id == task_id:
                return s
        return None

    def list_active(self) -> list[dict[str, Any]]:
        """List all active (queued + running) workers."""
        return [s.to_dict() for s in self._active.values()]

    def list_completed(self, limit: int = 50) -> list[dict[str, Any]]:
        """List recently completed workers."""
        return [s.to_dict() for s in self._completed[-limit:]]

    def list_all(self) -> list[dict[str, Any]]:
        """List all workers (active + recent completed)."""
        active = self.list_active()
        completed = self.list_completed(20)
        return active + completed

    def stats(self) -> dict[str, Any]:
        """Get pool statistics."""
        active_count = sum(
            1 for s in self._active.values()
            if s.state == WorkerState.RUNNING
        )
        queued_count = sum(
            1 for s in self._active.values()
            if s.state == WorkerState.QUEUED
        )
        return {
            "max_workers": self._max_workers,
            "active_count": active_count,
            "queued_count": queued_count,
            "total_submitted": self._total_submitted,
            "total_completed": self._total_completed,
            "total_failed": self._total_failed,
            "completed_history": len(self._completed),
        }

    async def wait_for(self, task_id: str, timeout: float = 300.0) -> WorkerStatus | None:
        """Wait for a specific worker to complete."""
        if task_id in self._tasks:
            try:
                await asyncio.wait_for(self._tasks[task_id], timeout=timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        return self.get_status(task_id)

    async def wait_all(self, task_ids: list[str] | None = None, timeout: float = 600.0) -> list[WorkerStatus]:
        """Wait for multiple workers to complete."""
        ids = task_ids or list(self._tasks.keys())
        tasks = [self._tasks[tid] for tid in ids if tid in self._tasks]
        if tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                pass
        return [self.get_status(tid) for tid in ids if self.get_status(tid)]

    async def cleanup(self) -> None:
        """Cancel all workers and clean up."""
        await self.cancel_all()
        self._active.clear()
        self._tasks.clear()
        logger.info("WorkerPool cleaned up")

    # ── Internal ──────────────────────────────────────────────────────────

    async def _run_worker(self, task: WorkerTask) -> None:
        """Execute a worker task with concurrency control."""
        status = self._active.get(task.id)
        if not status:
            return

        # Wait for a slot
        async with self._semaphore:
            status.state = WorkerState.RUNNING
            status.started_at = time.time()

            if self._on_status_change:
                await self._on_status_change(status)

            try:
                # Execute with timeout
                result = await asyncio.wait_for(
                    self._executor(task, self._update_status),
                    timeout=task.timeout,
                )

                status.state = WorkerState.COMPLETED
                status.result = result
                self._total_completed += 1

            except asyncio.TimeoutError:
                status.state = WorkerState.TIMEOUT
                status.error = f"Timed out after {task.timeout}s"
                self._total_failed += 1

            except asyncio.CancelledError:
                status.state = WorkerState.CANCELLED
                self._total_failed += 1

            except Exception as e:
                status.state = WorkerState.FAILED
                status.error = str(e)
                self._total_failed += 1
                logger.exception(f"Worker {task.id} failed: {e}")

            finally:
                status.completed_at = time.time()
                status.duration = status.completed_at - status.started_at

                if self._on_status_change:
                    await self._on_status_change(status)

                self._move_to_completed(task.id)

    async def _update_status(self, status: WorkerStatus) -> None:
        """Callback for workers to report status updates."""
        if status.task_id in self._active:
            self._active[status.task_id] = status
        if self._on_status_change:
            await self._on_status_change(status)

    def _move_to_completed(self, task_id: str) -> None:
        """Move a worker from active to completed history."""
        if task_id in self._active:
            self._completed.append(self._active.pop(task_id))
            # Keep history bounded
            if len(self._completed) > 200:
                self._completed = self._completed[-100:]
        self._tasks.pop(task_id, None)
