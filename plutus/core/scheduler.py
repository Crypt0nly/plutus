"""Scheduler — persistent cron-based task scheduling for Plutus.

Enables the agent to create scheduled tasks that run automatically:
  - Cron expressions: "0 6 * * *" (every day at 6 AM)
  - Intervals: every 5 minutes, every hour, etc.
  - One-shot: run once at a specific time

Jobs are persisted to ~/.plutus/scheduler.json so they survive restarts.
Each job fires by sending a prompt to the agent (or spawning a worker).

Example:
  scheduler.add_job(ScheduledJob(
      name="morning_blog",
      schedule="0 6 * * *",
      prompt="Write a new blog post about the latest AI news",
      model_key="claude-sonnet",
      spawn_worker=True,
  ))
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Awaitable

from plutus.config import plutus_dir

logger = logging.getLogger("plutus.scheduler")


class JobType(str, Enum):
    CRON = "cron"
    INTERVAL = "interval"
    ONCE = "once"


class JobState(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"    # For one-shot jobs
    DISABLED = "disabled"


@dataclass
class ScheduledJob:
    """Definition of a scheduled job."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    name: str = ""
    description: str = ""
    job_type: JobType = JobType.CRON
    schedule: str = ""                    # Cron expression or interval string
    interval_seconds: int = 0             # For interval type
    prompt: str = ""                      # What to tell the agent when the job fires
    model_key: str | None = None          # Model to use (None = auto-route)
    spawn_worker: bool = True             # Spawn as worker (True) or main agent (False)
    state: JobState = JobState.ACTIVE
    created_at: float = field(default_factory=time.time)
    last_run: float = 0.0
    next_run: float = 0.0
    run_count: int = 0
    max_runs: int = 0                     # 0 = unlimited
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "job_type": self.job_type.value,
            "schedule": self.schedule,
            "interval_seconds": self.interval_seconds,
            "prompt": self.prompt[:300] + ("..." if len(self.prompt) > 300 else ""),
            "model_key": self.model_key,
            "spawn_worker": self.spawn_worker,
            "state": self.state.value,
            "created_at": self.created_at,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "run_count": self.run_count,
            "max_runs": self.max_runs,
            "next_run_human": _format_timestamp(self.next_run) if self.next_run else "Not scheduled",
            "last_run_human": _format_timestamp(self.last_run) if self.last_run else "Never",
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScheduledJob:
        data = dict(data)
        data.pop("next_run_human", None)
        data.pop("last_run_human", None)
        if "job_type" in data and isinstance(data["job_type"], str):
            data["job_type"] = JobType(data["job_type"])
        if "state" in data and isinstance(data["state"], str):
            data["state"] = JobState(data["state"])
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


@dataclass
class JobExecution:
    """Record of a single job execution."""
    job_id: str
    job_name: str
    started_at: float
    completed_at: float = 0.0
    duration: float = 0.0
    success: bool = False
    result: str = ""
    error: str = ""
    model_used: str = ""
    worker_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_name": self.job_name,
            "started_at": self.started_at,
            "started_at_human": _format_timestamp(self.started_at),
            "completed_at": self.completed_at,
            "duration": round(self.duration, 2),
            "success": self.success,
            "result": self.result[:200] if len(self.result) > 200 else self.result,
            "error": self.error,
            "model_used": self.model_used,
            "worker_id": self.worker_id,
        }


# ── Cron parser (minimal, no external deps) ──────────────────────────────────

class CronExpression:
    """Simple cron expression parser (5 fields: min hour dom month dow)."""

    def __init__(self, expression: str):
        self._expr = expression.strip()
        parts = self._expr.split()
        if len(parts) != 5:
            raise ValueError(
                f"Cron expression must have 5 fields (min hour dom month dow), "
                f"got {len(parts)}: '{self._expr}'"
            )
        self._minute = self._parse_field(parts[0], 0, 59)
        self._hour = self._parse_field(parts[1], 0, 23)
        self._dom = self._parse_field(parts[2], 1, 31)
        self._month = self._parse_field(parts[3], 1, 12)
        self._dow = self._parse_field(parts[4], 0, 6)  # 0=Sunday

    def matches(self, dt: datetime) -> bool:
        """Check if a datetime matches this cron expression."""
        return (
            dt.minute in self._minute
            and dt.hour in self._hour
            and dt.day in self._dom
            and dt.month in self._month
            and dt.weekday() in self._dow_adjusted()
        )

    def next_occurrence(self, after: datetime | None = None) -> datetime:
        """Find the next datetime that matches this cron expression."""
        dt = (after or datetime.now()).replace(second=0, microsecond=0) + timedelta(minutes=1)
        # Search up to 366 days ahead
        for _ in range(366 * 24 * 60):
            if self.matches(dt):
                return dt
            dt += timedelta(minutes=1)
        raise ValueError(f"No next occurrence found for cron: {self._expr}")

    def _dow_adjusted(self) -> set[int]:
        """Convert cron DOW (0=Sun) to Python DOW (0=Mon)."""
        mapping = {0: 6, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}
        return {mapping[d] for d in self._dow}

    @staticmethod
    def _parse_field(field_str: str, min_val: int, max_val: int) -> set[int]:
        """Parse a single cron field into a set of valid values."""
        values: set[int] = set()

        for part in field_str.split(","):
            part = part.strip()

            if part == "*":
                values.update(range(min_val, max_val + 1))
            elif "/" in part:
                base, step = part.split("/", 1)
                step_val = int(step)
                if base == "*":
                    start = min_val
                else:
                    start = int(base)
                values.update(range(start, max_val + 1, step_val))
            elif "-" in part:
                low, high = part.split("-", 1)
                values.update(range(int(low), int(high) + 1))
            else:
                values.add(int(part))

        return {v for v in values if min_val <= v <= max_val}


# ── Scheduler ─────────────────────────────────────────────────────────────────

# Callback type: async def on_fire(job) -> str (result)
JobFireCallback = Callable[[ScheduledJob], Awaitable[str]]


class Scheduler:
    """Persistent cron-based task scheduler.

    Usage:
        scheduler = Scheduler(on_fire=my_callback)
        scheduler.add_job(ScheduledJob(
            name="daily_news",
            schedule="0 6 * * *",
            prompt="Research and summarize today's AI news",
        ))
        await scheduler.start()
    """

    def __init__(
        self,
        on_fire: JobFireCallback | None = None,
        on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        storage_path: Path | None = None,
    ):
        self._on_fire = on_fire
        self._on_event = on_event
        self._storage_path = storage_path or (plutus_dir() / "scheduler.json")
        self._jobs: dict[str, ScheduledJob] = {}
        self._executions: list[JobExecution] = []
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

        # Load persisted jobs
        self._load()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    # ── Job management ────────────────────────────────────────────────────

    def add_job(self, job: ScheduledJob) -> ScheduledJob:
        """Add a new scheduled job."""
        # Calculate next run time
        job.next_run = self._calc_next_run(job)
        self._jobs[job.id] = job
        self._save()
        logger.info(f"Job added: {job.name} ({job.id}) — next run: {_format_timestamp(job.next_run)}")
        return job

    def update_job(self, job_id: str, updates: dict[str, Any]) -> ScheduledJob | None:
        """Update an existing job."""
        job = self._jobs.get(job_id)
        if not job:
            return None
        for key, value in updates.items():
            if hasattr(job, key):
                setattr(job, key, value)
        # Recalculate next run if schedule changed
        if "schedule" in updates or "interval_seconds" in updates:
            job.next_run = self._calc_next_run(job)
        self._save()
        return job

    def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job."""
        if job_id in self._jobs:
            del self._jobs[job_id]
            self._save()
            logger.info(f"Job removed: {job_id}")
            return True
        return False

    def pause_job(self, job_id: str) -> bool:
        """Pause a job."""
        job = self._jobs.get(job_id)
        if job:
            job.state = JobState.PAUSED
            self._save()
            return True
        return False

    def resume_job(self, job_id: str) -> bool:
        """Resume a paused job."""
        job = self._jobs.get(job_id)
        if job:
            job.state = JobState.ACTIVE
            job.next_run = self._calc_next_run(job)
            self._save()
            return True
        return False

    def get_job(self, job_id: str) -> ScheduledJob | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[dict[str, Any]]:
        """List all jobs with their status."""
        return [j.to_dict() for j in sorted(
            self._jobs.values(),
            key=lambda j: j.next_run or float("inf")
        )]

    def list_executions(self, limit: int = 50, job_id: str | None = None) -> list[dict[str, Any]]:
        """List recent job executions."""
        execs = self._executions
        if job_id:
            execs = [e for e in execs if e.job_id == job_id]
        return [e.to_dict() for e in execs[-limit:]]

    def stats(self) -> dict[str, Any]:
        """Get scheduler statistics."""
        active = sum(1 for j in self._jobs.values() if j.state == JobState.ACTIVE)
        paused = sum(1 for j in self._jobs.values() if j.state == JobState.PAUSED)
        total_runs = sum(j.run_count for j in self._jobs.values())
        return {
            "running": self.running,
            "total_jobs": len(self._jobs),
            "active_jobs": active,
            "paused_jobs": paused,
            "total_executions": total_runs,
            "recent_executions": len(self._executions),
        }

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the scheduler loop."""
        if self.running:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop(), name="scheduler")
        logger.info(f"Scheduler started with {len(self._jobs)} jobs")

    async def stop(self) -> None:
        """Stop the scheduler loop."""
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Scheduler stopped")

    # ── Main loop ─────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        """Main scheduler loop — checks every 30 seconds for due jobs."""
        try:
            while not self._stop_event.is_set():
                now = time.time()

                for job in list(self._jobs.values()):
                    if job.state != JobState.ACTIVE:
                        continue
                    if job.next_run and now >= job.next_run:
                        # Advance next_run immediately to prevent re-firing
                        # on the next loop iteration while _fire_job runs
                        if job.max_runs > 0 and job.run_count + 1 >= job.max_runs:
                            job.next_run = 0
                        elif job.job_type == JobType.ONCE:
                            job.next_run = 0
                        else:
                            job.next_run = self._calc_next_run(job)

                        asyncio.create_task(
                            self._fire_job(job),
                            name=f"job-{job.id}"
                        )

                # Sleep 30 seconds between checks
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=30.0,
                    )
                    break  # stop_event was set
                except asyncio.TimeoutError:
                    pass  # Normal — just loop again

        except asyncio.CancelledError:
            logger.debug("Scheduler loop cancelled")

    async def _fire_job(self, job: ScheduledJob) -> None:
        """Execute a scheduled job."""
        logger.info(f"Firing job: {job.name} ({job.id})")

        execution = JobExecution(
            job_id=job.id,
            job_name=job.name,
            started_at=time.time(),
        )

        # Emit event
        if self._on_event:
            await self._on_event({
                "type": "scheduler_job_fired",
                "job": job.to_dict(),
            })

        try:
            result = ""
            if self._on_fire:
                result = await self._on_fire(job)

            execution.success = True
            execution.result = result or "Completed"

        except Exception as e:
            execution.success = False
            execution.error = str(e)
            logger.exception(f"Job {job.id} failed: {e}")

        finally:
            execution.completed_at = time.time()
            execution.duration = execution.completed_at - execution.started_at

            # Update job state
            job.last_run = execution.started_at
            job.run_count += 1

            # Calculate next run
            if job.max_runs > 0 and job.run_count >= job.max_runs:
                job.state = JobState.COMPLETED
                job.next_run = 0
            elif job.job_type == JobType.ONCE:
                job.state = JobState.COMPLETED
                job.next_run = 0
            else:
                job.next_run = self._calc_next_run(job)

            self._executions.append(execution)
            # Keep history bounded
            if len(self._executions) > 500:
                self._executions = self._executions[-250:]

            self._save()

            if self._on_event:
                await self._on_event({
                    "type": "scheduler_job_completed",
                    "execution": execution.to_dict(),
                })

    # ── Persistence ───────────────────────────────────────────────────────

    def _save(self) -> None:
        """Save jobs to disk."""
        try:
            data = {
                "jobs": {jid: j.to_dict() for jid, j in self._jobs.items()},
                "executions": [e.to_dict() for e in self._executions[-100:]],
            }
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._storage_path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.error(f"Failed to save scheduler state: {e}")

    def _load(self) -> None:
        """Load jobs from disk."""
        if not self._storage_path.exists():
            return
        try:
            data = json.loads(self._storage_path.read_text())
            for jid, jdata in data.get("jobs", {}).items():
                job = ScheduledJob.from_dict(jdata)
                self._jobs[job.id] = job
            logger.info(f"Loaded {len(self._jobs)} scheduled jobs")
        except Exception as e:
            logger.error(f"Failed to load scheduler state: {e}")

    # ── Helpers ───────────────────────────────────────────────────────────

    def _calc_next_run(self, job: ScheduledJob) -> float:
        """Calculate the next run time for a job."""
        now = datetime.now()

        if job.job_type == JobType.CRON:
            try:
                cron = CronExpression(job.schedule)
                next_dt = cron.next_occurrence(now)
                return next_dt.timestamp()
            except ValueError as e:
                logger.error(f"Invalid cron expression for job {job.id}: {e}")
                return 0

        elif job.job_type == JobType.INTERVAL:
            if job.interval_seconds <= 0:
                return 0
            if job.last_run:
                return job.last_run + job.interval_seconds
            return time.time() + job.interval_seconds

        elif job.job_type == JobType.ONCE:
            # For one-shot jobs, next_run should be set explicitly
            return job.next_run or 0

        return 0


def _format_timestamp(ts: float) -> str:
    """Format a Unix timestamp as a human-readable string."""
    if not ts:
        return "Never"
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, ValueError):
        return "Invalid"
