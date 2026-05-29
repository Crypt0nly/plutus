"""JSON-backed agent workflow manager for local Plutus.

This mirrors the cloud Agent Workflows contract closely enough for the local UI:
users can create repeatable workflows, define ordered agent steps, start runs, and
track/cancel those runs. Runtime execution delegates to the existing local
WorkerPool when available, so workflows reuse Plutus' normal agent/tool runtime.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from plutus.config import plutus_dir

TERMINAL_RUN_STATES = {"completed", "failed", "cancelled", "timeout"}


def _now() -> float:
    return time.time()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _step_sort_key(step: dict[str, Any]) -> tuple[int, str]:
    return (int(step.get("order", 0)), str(step.get("id", "")))


class AgentWorkflowManager:
    """Persist and manage reusable local agent workflows."""

    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path or (plutus_dir() / "agent_workflows.json")
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.storage_path.exists():
            return {"workflows": [], "runs": []}
        try:
            raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
            return {
                "workflows": list(raw.get("workflows") or []),
                "runs": list(raw.get("runs") or []),
            }
        except Exception:
            return {"workflows": [], "runs": []}

    def _save(self) -> None:
        tmp = self.storage_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.storage_path)

    def _find_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        return next((w for w in self._data["workflows"] if w.get("id") == workflow_id), None)

    def _find_run(self, run_id: str) -> dict[str, Any] | None:
        return next((r for r in self._data["runs"] if r.get("id") == run_id), None)

    def _serialize_workflow(self, workflow: dict[str, Any]) -> dict[str, Any]:
        item = dict(workflow)
        item["steps"] = sorted([dict(s) for s in item.get("steps", [])], key=_step_sort_key)
        return item

    def list_workflows(self) -> list[dict[str, Any]]:
        workflows = [self._serialize_workflow(w) for w in self._data["workflows"]]
        return sorted(workflows, key=lambda w: w.get("updated_at", 0), reverse=True)

    def get_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        workflow = self._find_workflow(workflow_id)
        return self._serialize_workflow(workflow) if workflow else None

    def create_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        workflow = {
            "id": _id("wf"),
            "title": (payload.get("title") or "Untitled workflow").strip(),
            "description": (payload.get("description") or "").strip(),
            "category": payload.get("category") or "General",
            "status": payload.get("status") or "draft",
            "trigger_type": payload.get("trigger_type") or "manual",
            "trigger_config": payload.get("trigger_config") or {},
            "priority": payload.get("priority") or "normal",
            "tags": list(payload.get("tags") or []),
            "steps": [],
            "created_at": now,
            "updated_at": now,
            "last_run_at": None,
            "next_run_at": None,
            "run_count": 0,
            "success_count": 0,
            "failure_count": 0,
        }
        for idx, step in enumerate(payload.get("steps") or [], start=1):
            workflow["steps"].append(self._build_step(step, idx))
        self._data["workflows"].append(workflow)
        self._save()
        return self._serialize_workflow(workflow)

    def update_workflow(self, workflow_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        workflow = self._find_workflow(workflow_id)
        if not workflow:
            return None
        allowed = {
            "title", "description", "category", "status", "trigger_type",
            "trigger_config", "priority", "tags", "next_run_at",
        }
        for key, value in patch.items():
            if key in allowed and value is not None:
                if key in {"title", "description"} and isinstance(value, str):
                    value = value.strip()
                workflow[key] = value
        workflow["updated_at"] = _now()
        self._save()
        return self._serialize_workflow(workflow)

    def delete_workflow(self, workflow_id: str) -> bool:
        before = len(self._data["workflows"])
        self._data["workflows"] = [w for w in self._data["workflows"] if w.get("id") != workflow_id]
        if len(self._data["workflows"]) == before:
            return False
        for run in self._data["runs"]:
            if run.get("workflow_id") == workflow_id and run.get("status") not in TERMINAL_RUN_STATES:
                run["status"] = "cancelled"
                run["completed_at"] = _now()
                run["error"] = "Workflow was deleted."
        self._save()
        return True

    def _build_step(self, payload: dict[str, Any], order: int) -> dict[str, Any]:
        return {
            "id": payload.get("id") or _id("step"),
            "title": (payload.get("title") or f"Step {order}").strip(),
            "description": (payload.get("description") or "").strip(),
            "instruction": (payload.get("instruction") or payload.get("description") or "").strip(),
            "agent_type": payload.get("agent_type") or "general",
            "status": payload.get("status") or "active",
            "order": int(payload.get("order") or order),
            "enabled": bool(payload.get("enabled", True)),
            "depends_on": list(payload.get("depends_on") or []),
            "expected_output": (payload.get("expected_output") or "").strip(),
            "timeout_seconds": int(payload.get("timeout_seconds") or 600),
            "created_at": payload.get("created_at") or _now(),
            "updated_at": _now(),
        }

    def add_step(self, workflow_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        workflow = self._find_workflow(workflow_id)
        if not workflow:
            return None
        next_order = max([int(s.get("order", 0)) for s in workflow.get("steps", [])] or [0]) + 1
        step = self._build_step(payload, next_order)
        workflow.setdefault("steps", []).append(step)
        workflow["updated_at"] = _now()
        self._save()
        return dict(step)

    def update_step(self, workflow_id: str, step_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        workflow = self._find_workflow(workflow_id)
        if not workflow:
            return None
        step = next((s for s in workflow.get("steps", []) if s.get("id") == step_id), None)
        if not step:
            return None
        allowed = {
            "title", "description", "instruction", "agent_type", "status", "order",
            "enabled", "depends_on", "expected_output", "timeout_seconds",
        }
        for key, value in patch.items():
            if key in allowed and value is not None:
                if key in {"title", "description", "instruction", "expected_output"} and isinstance(value, str):
                    value = value.strip()
                if key in {"order", "timeout_seconds"}:
                    value = int(value)
                step[key] = value
        step["updated_at"] = _now()
        workflow["updated_at"] = _now()
        self._save()
        return dict(step)

    def delete_step(self, workflow_id: str, step_id: str) -> bool:
        workflow = self._find_workflow(workflow_id)
        if not workflow:
            return False
        before = len(workflow.get("steps", []))
        workflow["steps"] = [s for s in workflow.get("steps", []) if s.get("id") != step_id]
        if len(workflow["steps"]) == before:
            return False
        for idx, step in enumerate(sorted(workflow["steps"], key=_step_sort_key), start=1):
            step["order"] = idx
        workflow["updated_at"] = _now()
        self._save()
        return True

    def reorder_steps(self, workflow_id: str, step_ids: list[str]) -> dict[str, Any] | None:
        workflow = self._find_workflow(workflow_id)
        if not workflow:
            return None
        order_map = {step_id: idx for idx, step_id in enumerate(step_ids, start=1)}
        for step in workflow.get("steps", []):
            if step.get("id") in order_map:
                step["order"] = order_map[step["id"]]
        workflow["updated_at"] = _now()
        self._save()
        return self._serialize_workflow(workflow)

    def _run_snapshot_steps(self, workflow: dict[str, Any]) -> list[dict[str, Any]]:
        steps = [s for s in sorted(workflow.get("steps", []), key=_step_sort_key) if s.get("enabled", True)]
        return [
            {
                "id": s.get("id"),
                "title": s.get("title"),
                "instruction": s.get("instruction") or s.get("description", ""),
                "status": "pending",
                "order": s.get("order"),
                "started_at": None,
                "completed_at": None,
                "output": None,
                "error": None,
            }
            for s in steps
        ]

    def build_worker_prompt(self, workflow: dict[str, Any]) -> str:
        steps = [s for s in sorted(workflow.get("steps", []), key=_step_sort_key) if s.get("enabled", True)]
        lines = [
            f"Run this reusable Plutus workflow: {workflow.get('title', 'Untitled workflow')}",
            "",
            workflow.get("description", ""),
            "",
            "Execute the steps in order. For each step, produce concise progress notes and a final result.",
            "",
            "Steps:",
        ]
        for idx, step in enumerate(steps, start=1):
            instruction = step.get("instruction") or step.get("description") or "Complete this step."
            expected = step.get("expected_output") or "Useful completion output."
            lines.append(f"{idx}. {step.get('title', f'Step {idx}')}: {instruction}")
            lines.append(f"   Expected output: {expected}")
        if not steps:
            lines.append("1. Review the workflow and explain that no active steps are configured yet.")
        return "\n".join(lines).strip()

    async def start_run(self, workflow_id: str, worker_pool: Any | None = None, triggered_by: str = "manual") -> dict[str, Any] | None:
        workflow = self._find_workflow(workflow_id)
        if not workflow:
            return None
        now = _now()
        run_steps = self._run_snapshot_steps(workflow)
        run = {
            "id": _id("run"),
            "workflow_id": workflow_id,
            "workflow_title": workflow.get("title", "Untitled workflow"),
            "status": "queued",
            "triggered_by": triggered_by,
            "current_step_id": run_steps[0]["id"] if run_steps else None,
            "steps": run_steps,
            "result": None,
            "error": None,
            "worker_task_id": None,
            "started_at": now,
            "completed_at": None,
            "created_at": now,
        }
        workflow["run_count"] = int(workflow.get("run_count") or 0) + 1
        workflow["last_run_at"] = now
        workflow["updated_at"] = now
        self._data["runs"].insert(0, run)
        self._data["runs"] = self._data["runs"][:200]
        self._save()

        if worker_pool is not None:
            try:
                from plutus.core.worker_pool import WorkerTask

                timeout = max(300, sum(int(s.get("timeout_seconds") or 600) for s in workflow.get("steps", [])))
                task = WorkerTask(
                    name=f"Workflow: {workflow.get('title', 'Untitled')}",
                    prompt=self.build_worker_prompt(workflow),
                    complexity="moderate",
                    timeout=float(min(timeout, 7200)),
                    metadata={"workflow_id": workflow_id, "workflow_run_id": run["id"]},
                )
                status = await worker_pool.submit(task)
                run["worker_task_id"] = status.task_id
                run["status"] = status.state.value
                if run["steps"]:
                    run["steps"][0]["status"] = "running" if run["status"] == "running" else "pending"
                    run["steps"][0]["started_at"] = now if run["status"] == "running" else None
                self._save()
            except Exception as exc:
                run["status"] = "failed"
                run["error"] = str(exc)
                run["completed_at"] = _now()
                workflow["failure_count"] = int(workflow.get("failure_count") or 0) + 1
                self._save()
        else:
            run["status"] = "failed"
            run["error"] = "Worker pool is not available."
            run["completed_at"] = _now()
            workflow["failure_count"] = int(workflow.get("failure_count") or 0) + 1
            self._save()
        return dict(run)

    def refresh_runs(self, worker_pool: Any | None = None) -> None:
        if worker_pool is None:
            return
        changed = False
        for run in self._data["runs"]:
            if run.get("status") in TERMINAL_RUN_STATES or not run.get("worker_task_id"):
                continue
            status = worker_pool.get_status(run["worker_task_id"])
            if status is None:
                continue
            status_dict = status.to_dict()
            new_state = status_dict.get("state")
            if new_state and run.get("status") != new_state:
                run["status"] = new_state
                changed = True
            if status_dict.get("result"):
                run["result"] = status_dict["result"]
                changed = True
            if status_dict.get("error"):
                run["error"] = status_dict["error"]
                changed = True
            if new_state in TERMINAL_RUN_STATES:
                run["completed_at"] = status_dict.get("completed_at") or _now()
                for step in run.get("steps", []):
                    if step.get("status") not in TERMINAL_RUN_STATES:
                        step["status"] = "completed" if new_state == "completed" else new_state
                        step["completed_at"] = run["completed_at"]
                workflow = self._find_workflow(run.get("workflow_id", ""))
                if workflow:
                    if new_state == "completed":
                        workflow["success_count"] = int(workflow.get("success_count") or 0) + 1
                    elif new_state in {"failed", "timeout"}:
                        workflow["failure_count"] = int(workflow.get("failure_count") or 0) + 1
                    workflow["updated_at"] = _now()
                changed = True
        if changed:
            self._save()

    def list_runs(self, limit: int = 50, workflow_id: str | None = None, worker_pool: Any | None = None) -> list[dict[str, Any]]:
        self.refresh_runs(worker_pool)
        runs = [dict(r) for r in self._data["runs"] if not workflow_id or r.get("workflow_id") == workflow_id]
        return sorted(runs, key=lambda r: r.get("created_at", 0), reverse=True)[:limit]

    async def cancel_run(self, run_id: str, worker_pool: Any | None = None) -> dict[str, Any] | None:
        run = self._find_run(run_id)
        if not run:
            return None
        if run.get("status") in TERMINAL_RUN_STATES:
            return dict(run)
        if worker_pool is not None and run.get("worker_task_id"):
            try:
                await worker_pool.cancel(run["worker_task_id"])
            except Exception:
                pass
        run["status"] = "cancelled"
        run["completed_at"] = _now()
        for step in run.get("steps", []):
            if step.get("status") not in TERMINAL_RUN_STATES:
                step["status"] = "cancelled"
                step["completed_at"] = run["completed_at"]
        self._save()
        return dict(run)

    def stats(self, worker_pool: Any | None = None) -> dict[str, Any]:
        self.refresh_runs(worker_pool)
        workflows = self._data["workflows"]
        runs = self._data["runs"]
        active_runs = [r for r in runs if r.get("status") not in TERMINAL_RUN_STATES]
        return {
            "workflow_count": len(workflows),
            "active_workflow_count": sum(1 for w in workflows if w.get("status") == "active"),
            "run_count": len(runs),
            "active_run_count": len(active_runs),
            "success_count": sum(1 for r in runs if r.get("status") == "completed"),
            "failure_count": sum(1 for r in runs if r.get("status") in {"failed", "timeout"}),
        }
