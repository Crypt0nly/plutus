"""Subprocess Manager — orchestrates worker processes for parallel task execution.

This is the core innovation: Claude can spawn isolated subprocesses to:
  - Edit files with surgical precision
  - Analyze code (AST, dependencies, complexity)
  - Execute shell commands in sandboxed environments
  - Run dynamically-created tools

Each subprocess communicates via JSON over stdin/stdout and has resource limits.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import signal
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("plutus.subprocess")


class WorkerStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class TaskPriority(int, Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class SubprocessTask:
    """A task to be executed by a worker subprocess."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    worker_type: str = "shell"  # shell, file_edit, code_analysis, custom
    command: dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    timeout: float = 60.0
    working_dir: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "worker_type": self.worker_type,
            "command": self.command,
            "priority": self.priority.value,
            "timeout": self.timeout,
            "working_dir": self.working_dir,
            "env": self.env,
            "created_at": self.created_at,
        }


@dataclass
class SubprocessResult:
    """Result from a worker subprocess."""

    task_id: str
    status: WorkerStatus
    output: Any = None
    error: str | None = None
    duration: float = 0.0
    pid: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "duration": self.duration,
            "pid": self.pid,
        }


class WorkerProcess:
    """Manages a single worker subprocess with JSON stdin/stdout communication."""

    def __init__(
        self,
        worker_id: str,
        script_path: str,
        working_dir: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 60.0,
    ):
        self.worker_id = worker_id
        self.script_path = script_path
        self.working_dir = working_dir
        self.env = env or {}
        self.timeout = timeout
        self.process: asyncio.subprocess.Process | None = None
        self.status = WorkerStatus.IDLE
        self.start_time: float = 0.0

    async def start(self) -> None:
        """Start the worker subprocess."""
        env = {**os.environ, **self.env}
        # Use the same Python that's running Plutus — avoids "python3 not found" on Windows
        python_exe = sys.executable or shutil.which("python") or shutil.which("python3") or "python"
        self.process = await asyncio.create_subprocess_exec(
            python_exe, self.script_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.working_dir,
            env=env,
        )
        self.status = WorkerStatus.RUNNING
        self.start_time = time.time()
        logger.debug(f"Worker {self.worker_id} started (PID: {self.process.pid})")

    async def send_command(self, command: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON command to the worker and read the JSON response."""
        if not self.process or not self.process.stdin or not self.process.stdout:
            raise RuntimeError(f"Worker {self.worker_id} is not running")

        # Send command as a single JSON line
        payload = json.dumps(command) + "\n"
        self.process.stdin.write(payload.encode())
        await self.process.stdin.drain()

        # Read response line
        try:
            line = await asyncio.wait_for(
                self.process.stdout.readline(),
                timeout=self.timeout,
            )
            if not line:
                stderr_data = b""
                if self.process.stderr:
                    try:
                        stderr_data = await asyncio.wait_for(
                            self.process.stderr.read(), timeout=2.0
                        )
                    except asyncio.TimeoutError:
                        pass
                raise RuntimeError(
                    f"Worker {self.worker_id} closed stdout. "
                    f"stderr: {stderr_data.decode(errors='replace')}"
                )
            return json.loads(line.decode().strip())
        except asyncio.TimeoutError:
            self.status = WorkerStatus.TIMEOUT
            raise TimeoutError(
                f"Worker {self.worker_id} timed out after {self.timeout}s"
            )

    async def stop(self) -> None:
        """Gracefully stop the worker."""
        if self.process and self.process.returncode is None:
            try:
                # Send quit command
                if self.process.stdin:
                    quit_cmd = json.dumps({"action": "quit"}) + "\n"
                    self.process.stdin.write(quit_cmd.encode())
                    await self.process.stdin.drain()
                # Wait briefly for graceful shutdown
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except (asyncio.TimeoutError, Exception):
                # Force kill
                try:
                    self.process.kill()
                    await self.process.wait()
                except ProcessLookupError:
                    pass
            self.status = WorkerStatus.COMPLETED
            logger.debug(f"Worker {self.worker_id} stopped")

    @property
    def pid(self) -> int | None:
        return self.process.pid if self.process else None

    @property
    def elapsed(self) -> float:
        if self.start_time:
            return time.time() - self.start_time
        return 0.0


class SubprocessManager:
    """Orchestrates a pool of worker subprocesses.

    Features:
      - Priority task queue
      - Configurable max concurrent workers
      - Automatic cleanup of finished workers
      - Event callbacks for task completion
      - Resource limit enforcement
    """

    # Path to built-in worker scripts
    WORKER_SCRIPTS_DIR = Path(__file__).parent.parent / "workers"

    def __init__(
        self,
        max_workers: int = 5,
        default_timeout: float = 60.0,
        temp_dir: str | None = None,
    ):
        self.max_workers = max_workers
        self.default_timeout = default_timeout
        self.temp_dir = temp_dir or tempfile.mkdtemp(prefix="plutus_workers_")
        self._workers: dict[str, WorkerProcess] = {}
        self._results: dict[str, SubprocessResult] = {}
        self._callbacks: list[Callable[[SubprocessResult], Any]] = []
        self._task_counter = 0
        self._lock = asyncio.Lock()

    def on_result(self, callback: Callable[[SubprocessResult], Any]) -> None:
        """Register a callback for when a task completes."""
        self._callbacks.append(callback)

    async def _notify(self, result: SubprocessResult) -> None:
        for cb in self._callbacks:
            try:
                ret = cb(result)
                if asyncio.iscoroutine(ret):
                    await ret
            except Exception as e:
                logger.warning(f"Result callback error: {e}")

    async def spawn(self, task: SubprocessTask) -> SubprocessResult:
        """Spawn a worker subprocess to execute a task.

        This is the main entry point. It:
          1. Selects the appropriate worker script
          2. Starts the subprocess
          3. Sends the command
          4. Collects and returns the result
        """
        start_time = time.time()

        # Resolve worker script
        script_path = self._resolve_worker_script(task.worker_type)
        if not script_path:
            result = SubprocessResult(
                task_id=task.id,
                status=WorkerStatus.FAILED,
                error=f"Unknown worker type: {task.worker_type}",
            )
            await self._notify(result)
            return result

        # Check worker limit
        async with self._lock:
            active = sum(
                1 for w in self._workers.values()
                if w.status == WorkerStatus.RUNNING
            )
            if active >= self.max_workers:
                result = SubprocessResult(
                    task_id=task.id,
                    status=WorkerStatus.FAILED,
                    error=f"Worker limit reached ({self.max_workers}). Try again later.",
                )
                await self._notify(result)
                return result

        # Create and start worker
        worker = WorkerProcess(
            worker_id=task.id,
            script_path=str(script_path),
            working_dir=task.working_dir,
            env=task.env,
            timeout=task.timeout or self.default_timeout,
        )

        try:
            await worker.start()
            self._workers[task.id] = worker

            # Send the task command
            response = await worker.send_command(task.command)

            duration = time.time() - start_time
            status = WorkerStatus.COMPLETED if response.get("success") else WorkerStatus.FAILED

            result = SubprocessResult(
                task_id=task.id,
                status=status,
                output=response.get("result"),
                error=response.get("error"),
                duration=duration,
                pid=worker.pid,
            )

        except TimeoutError as e:
            result = SubprocessResult(
                task_id=task.id,
                status=WorkerStatus.TIMEOUT,
                error=str(e),
                duration=time.time() - start_time,
                pid=worker.pid,
            )
        except Exception as e:
            result = SubprocessResult(
                task_id=task.id,
                status=WorkerStatus.FAILED,
                error=str(e),
                duration=time.time() - start_time,
                pid=worker.pid,
            )
        finally:
            await worker.stop()
            self._results[task.id] = result
            # Trim results to prevent unbounded memory growth
            if len(self._results) > 200:
                # Keep only the 100 most recent results
                sorted_ids = sorted(
                    self._results,
                    key=lambda tid: self._results[tid].duration,
                )
                for old_id in sorted_ids[:100]:
                    del self._results[old_id]

        await self._notify(result)
        return result

    async def spawn_many(self, tasks: list[SubprocessTask]) -> list[SubprocessResult]:
        """Spawn multiple tasks concurrently and collect all results."""
        coros = [self.spawn(task) for task in tasks]
        return await asyncio.gather(*coros, return_exceptions=False)

    def _resolve_worker_script(self, worker_type: str) -> Path | None:
        """Map worker type to the appropriate Python script."""
        script_map = {
            "shell": "shell_worker.py",
            "file_edit": "file_edit_worker.py",
            "code_analysis": "code_analysis_worker.py",
            "custom": "custom_worker.py",
        }
        script_name = script_map.get(worker_type)
        if not script_name:
            return None

        script_path = self.WORKER_SCRIPTS_DIR / script_name
        if not script_path.exists():
            logger.error(
                f"Worker script not found: {script_path}. "
                f"Workers dir exists: {self.WORKER_SCRIPTS_DIR.exists()}. "
                f"Contents: {list(self.WORKER_SCRIPTS_DIR.iterdir()) if self.WORKER_SCRIPTS_DIR.exists() else 'N/A'}"
            )
            return None
        return script_path

    def get_result(self, task_id: str) -> SubprocessResult | None:
        return self._results.get(task_id)

    def list_active(self) -> list[dict[str, Any]]:
        """List currently active workers."""
        return [
            {
                "id": wid,
                "pid": w.pid,
                "status": w.status.value,
                "elapsed": round(w.elapsed, 2),
            }
            for wid, w in self._workers.items()
            if w.status == WorkerStatus.RUNNING
        ]

    def list_results(self, limit: int = 20) -> list[dict[str, Any]]:
        """List recent task results."""
        results = sorted(
            self._results.values(),
            key=lambda r: r.duration,
            reverse=True,
        )[:limit]
        return [r.to_dict() for r in results]

    async def cancel(self, task_id: str) -> bool:
        """Cancel a running task."""
        worker = self._workers.get(task_id)
        if not worker or worker.status != WorkerStatus.RUNNING:
            return False
        await worker.stop()
        worker.status = WorkerStatus.CANCELLED
        self._results[task_id] = SubprocessResult(
            task_id=task_id,
            status=WorkerStatus.CANCELLED,
            pid=worker.pid,
        )
        return True

    async def cleanup(self) -> None:
        """Stop all workers and clean up temp files."""
        for worker in self._workers.values():
            if worker.status == WorkerStatus.RUNNING:
                await worker.stop()
        self._workers.clear()
        logger.info("SubprocessManager cleaned up")
