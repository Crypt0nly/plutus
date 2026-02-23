"""Scheduler Tool — allows the agent to create and manage scheduled tasks.

Operations:
  - create:      Create a new scheduled job (cron, interval, or one-shot)
  - list:        List all scheduled jobs
  - get:         Get details of a specific job
  - update:      Update a job's settings
  - delete:      Delete a scheduled job
  - pause:       Pause a job
  - resume:      Resume a paused job
  - history:     View recent job execution history
  - stats:       Get scheduler statistics
"""

from __future__ import annotations

import json
import time
from typing import Any

from plutus.core.scheduler import (
    Scheduler,
    ScheduledJob,
    JobType,
    JobState,
)
from plutus.tools.base import Tool


class SchedulerTool(Tool):
    """Create and manage scheduled tasks (cron jobs, intervals, one-shots)."""

    def __init__(self, scheduler: Scheduler):
        self._scheduler = scheduler

    @property
    def name(self) -> str:
        return "scheduler"

    @property
    def description(self) -> str:
        return (
            "Create and manage scheduled tasks. Supports cron expressions, intervals, and one-shot timers.\n\n"
            "Operations:\n"
            "- create: Create a new scheduled job\n"
            "- list: List all scheduled jobs\n"
            "- get: Get details of a specific job\n"
            "- update: Update a job's settings\n"
            "- delete: Delete a scheduled job\n"
            "- pause/resume: Pause or resume a job\n"
            "- history: View recent execution history\n"
            "- stats: Get scheduler statistics\n\n"
            "Schedule types:\n"
            "- cron: Standard 5-field cron expression (min hour dom month dow)\n"
            "  Examples: '0 6 * * *' (daily 6AM), '*/5 * * * *' (every 5 min), '0 9 * * 1-5' (weekdays 9AM)\n"
            "- interval: Run every N seconds (e.g., 300 for every 5 minutes)\n"
            "- once: Run once at a specific time\n\n"
            "Each job can spawn a worker (default) or run on the main agent. "
            "Set model_key to choose which model handles the job."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["create", "list", "get", "update", "delete", "pause", "resume", "history", "stats"],
                    "description": "The scheduler operation to perform.",
                },
                "name": {
                    "type": "string",
                    "description": "Human-readable name for the job (for 'create').",
                },
                "description": {
                    "type": "string",
                    "description": "Description of what the job does (for 'create').",
                },
                "job_type": {
                    "type": "string",
                    "enum": ["cron", "interval", "once"],
                    "description": "Type of schedule (for 'create'). Default: 'cron'.",
                },
                "schedule": {
                    "type": "string",
                    "description": "Cron expression for 'cron' type (e.g., '0 6 * * *' for daily at 6AM).",
                },
                "interval_seconds": {
                    "type": "integer",
                    "description": "Interval in seconds for 'interval' type (e.g., 300 for every 5 minutes).",
                },
                "prompt": {
                    "type": "string",
                    "description": "The instruction to execute when the job fires.",
                },
                "model_key": {
                    "type": "string",
                    "enum": ["claude-haiku", "claude-sonnet", "claude-opus", "gpt-5.2"],
                    "description": "Which model to use for this job. Omit for auto-selection.",
                },
                "spawn_worker": {
                    "type": "boolean",
                    "description": "Whether to spawn a worker (true, default) or run on main agent (false).",
                },
                "max_runs": {
                    "type": "integer",
                    "description": "Maximum number of times to run (0 = unlimited). Default: 0.",
                },
                "job_id": {
                    "type": "string",
                    "description": "Job ID (for 'get', 'update', 'delete', 'pause', 'resume', 'history').",
                },
                "updates": {
                    "type": "object",
                    "description": "Fields to update (for 'update' operation).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (for 'history'). Default: 20.",
                },
            },
            "required": ["operation"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        operation = kwargs.get("operation", "list")

        try:
            if operation == "create":
                return self._create(kwargs)
            elif operation == "list":
                return self._list()
            elif operation == "get":
                return self._get(kwargs)
            elif operation == "update":
                return self._update(kwargs)
            elif operation == "delete":
                return self._delete(kwargs)
            elif operation == "pause":
                return self._pause(kwargs)
            elif operation == "resume":
                return self._resume(kwargs)
            elif operation == "history":
                return self._history(kwargs)
            elif operation == "stats":
                return self._stats()
            else:
                return f"[ERROR] Unknown operation: {operation}"
        except Exception as e:
            return f"[ERROR] Scheduler operation failed: {e}"

    def _create(self, kwargs: dict) -> str:
        prompt = kwargs.get("prompt", "")
        if not prompt:
            return "[ERROR] 'prompt' is required — what should the job do?"

        job_type_str = kwargs.get("job_type", "cron")
        try:
            job_type = JobType(job_type_str)
        except ValueError:
            return f"[ERROR] Invalid job_type: {job_type_str}. Use 'cron', 'interval', or 'once'."

        schedule = kwargs.get("schedule", "")
        interval_seconds = kwargs.get("interval_seconds", 0)

        if job_type == JobType.CRON and not schedule:
            return "[ERROR] 'schedule' (cron expression) is required for cron jobs."
        if job_type == JobType.INTERVAL and not interval_seconds:
            return "[ERROR] 'interval_seconds' is required for interval jobs."

        job = ScheduledJob(
            name=kwargs.get("name", "Unnamed Job"),
            description=kwargs.get("description", ""),
            job_type=job_type,
            schedule=schedule,
            interval_seconds=interval_seconds,
            prompt=prompt,
            model_key=kwargs.get("model_key"),
            spawn_worker=kwargs.get("spawn_worker", True),
            max_runs=kwargs.get("max_runs", 0),
        )

        created = self._scheduler.add_job(job)
        return json.dumps({
            "success": True,
            "message": f"Job '{created.name}' created successfully.",
            "job": created.to_dict(),
        }, indent=2)

    def _list(self) -> str:
        jobs = self._scheduler.list_jobs()
        if not jobs:
            return json.dumps({"jobs": [], "message": "No scheduled jobs."})
        return json.dumps({"jobs": jobs, "total": len(jobs)}, indent=2)

    def _get(self, kwargs: dict) -> str:
        job_id = kwargs.get("job_id", "")
        if not job_id:
            return "[ERROR] 'job_id' is required."
        job = self._scheduler.get_job(job_id)
        if not job:
            return f"[ERROR] Job '{job_id}' not found."
        return json.dumps(job.to_dict(), indent=2)

    def _update(self, kwargs: dict) -> str:
        job_id = kwargs.get("job_id", "")
        updates = kwargs.get("updates", {})
        if not job_id:
            return "[ERROR] 'job_id' is required."
        if not updates:
            return "[ERROR] 'updates' dict is required."
        job = self._scheduler.update_job(job_id, updates)
        if not job:
            return f"[ERROR] Job '{job_id}' not found."
        return json.dumps({
            "success": True,
            "message": f"Job '{job.name}' updated.",
            "job": job.to_dict(),
        }, indent=2)

    def _delete(self, kwargs: dict) -> str:
        job_id = kwargs.get("job_id", "")
        if not job_id:
            return "[ERROR] 'job_id' is required."
        success = self._scheduler.remove_job(job_id)
        if success:
            return f"Job '{job_id}' deleted."
        return f"[ERROR] Job '{job_id}' not found."

    def _pause(self, kwargs: dict) -> str:
        job_id = kwargs.get("job_id", "")
        if not job_id:
            return "[ERROR] 'job_id' is required."
        success = self._scheduler.pause_job(job_id)
        if success:
            return f"Job '{job_id}' paused."
        return f"[ERROR] Job '{job_id}' not found."

    def _resume(self, kwargs: dict) -> str:
        job_id = kwargs.get("job_id", "")
        if not job_id:
            return "[ERROR] 'job_id' is required."
        success = self._scheduler.resume_job(job_id)
        if success:
            return f"Job '{job_id}' resumed."
        return f"[ERROR] Job '{job_id}' not found."

    def _history(self, kwargs: dict) -> str:
        job_id = kwargs.get("job_id")
        limit = kwargs.get("limit", 20)
        execs = self._scheduler.list_executions(limit=limit, job_id=job_id)
        return json.dumps({"executions": execs, "total": len(execs)}, indent=2)

    def _stats(self) -> str:
        return json.dumps(self._scheduler.stats(), indent=2)
