"""
Cloud Plan Manager
==================
Persists execution plans in the cloud database (plans table).
Mirrors the local PlanManager API so the cloud agent runtime can create,
track, and resume multi-step plans across sessions and heartbeats.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    goal TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    steps TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plans_user ON plans(user_id);
CREATE INDEX IF NOT EXISTS idx_plans_status ON plans(status);
"""

_STATUS_ICONS = {
    "pending": "[ ]",
    "in_progress": "[>]",
    "done": "[x]",
    "failed": "[!]",
    "skipped": "[-]",
    "interrupted": "[~]",
}


class CloudPlanManager:
    """Async plan manager backed by the cloud Postgres/SQLite database."""

    def __init__(self, user_id: str, session: AsyncSession) -> None:
        self.user_id = user_id
        self._session = session

    # ── CRUD ──────────────────────────────────────────────────────────────────

    async def create_plan(
        self,
        title: str,
        steps: list[dict],
        goal: str | None = None,
    ) -> dict[str, Any]:
        """Create a new active plan, cancelling any previous active plan first."""
        # Cancel any existing active plan so there is only ever one at a time.
        await self._session.execute(
            text(
                "UPDATE plans SET status = 'cancelled', updated_at = :now "
                "WHERE user_id = :uid AND status = 'active'"
            ),
            {"now": time.time(), "uid": self.user_id},
        )

        plan_id = str(uuid.uuid4())
        now = time.time()
        enriched: list[dict] = []
        for i, s in enumerate(steps):
            enriched.append(
                {
                    "index": i,
                    "description": s.get("description", s.get("name", f"Step {i + 1}")),
                    "details": s.get("details", ""),
                    "status": "pending",
                    "result": None,
                    "started_at": None,
                    "finished_at": None,
                }
            )

        await self._session.execute(
            text(
                "INSERT INTO plans (id, user_id, title, goal, status, steps, created_at, updated_at) "
                "VALUES (:id, :uid, :title, :goal, 'active', :steps, :now, :now)"
            ),
            {
                "id": plan_id,
                "uid": self.user_id,
                "title": title,
                "goal": goal,
                "steps": json.dumps(enriched),
                "now": now,
            },
        )
        await self._session.commit()
        logger.info(
            "[Plan] Created plan '%s' (%d steps) for user %s",
            title,
            len(enriched),
            self.user_id[:8],
        )
        return {
            "id": plan_id,
            "user_id": self.user_id,
            "title": title,
            "goal": goal,
            "status": "active",
            "steps": enriched,
            "created_at": now,
            "updated_at": now,
        }

    async def get_active_plan(self) -> dict[str, Any] | None:
        """Return the most recent active plan for this user, or None."""
        result = await self._session.execute(
            text(
                "SELECT id, user_id, title, goal, status, steps, created_at, updated_at "
                "FROM plans WHERE user_id = :uid AND status = 'active' "
                "ORDER BY updated_at DESC LIMIT 1"
            ),
            {"uid": self.user_id},
        )
        row = result.fetchone()
        return _row_to_plan(row) if row else None

    async def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        result = await self._session.execute(
            text(
                "SELECT id, user_id, title, goal, status, steps, created_at, updated_at "
                "FROM plans WHERE id = :id AND user_id = :uid"
            ),
            {"id": plan_id, "uid": self.user_id},
        )
        row = result.fetchone()
        return _row_to_plan(row) if row else None

    async def update_step(
        self,
        step_index: int,
        status: str,
        result_note: str | None = None,
    ) -> dict[str, Any] | None:
        """Update a single step in the active plan."""
        plan = await self.get_active_plan()
        if not plan:
            return None

        steps = plan["steps"]
        if step_index < 0 or step_index >= len(steps):
            return None

        now = time.time()
        steps[step_index]["status"] = status
        if result_note is not None:
            steps[step_index]["result"] = result_note
        if status == "in_progress":
            steps[step_index]["started_at"] = now
        if status in ("done", "failed", "skipped"):
            steps[step_index]["finished_at"] = now

        # Auto-complete the plan when all steps are terminal
        plan_status = "active"
        all_terminal = all(s["status"] in ("done", "failed", "skipped") for s in steps)
        if all_terminal:
            any_failed = any(s["status"] == "failed" for s in steps)
            plan_status = "failed" if any_failed else "completed"

        await self._session.execute(
            text(
                "UPDATE plans SET steps = :steps, status = :status, updated_at = :now "
                "WHERE id = :id"
            ),
            {"steps": json.dumps(steps), "status": plan_status, "now": now, "id": plan["id"]},
        )
        await self._session.commit()
        plan["steps"] = steps
        plan["status"] = plan_status
        plan["updated_at"] = now
        return plan

    async def set_plan_status(self, status: str) -> dict[str, Any] | None:
        plan = await self.get_active_plan()
        if not plan:
            return None
        now = time.time()
        await self._session.execute(
            text("UPDATE plans SET status = :status, updated_at = :now WHERE id = :id"),
            {"status": status, "now": now, "id": plan["id"]},
        )
        await self._session.commit()
        plan["status"] = status
        plan["updated_at"] = now
        return plan

    # ── Formatting ────────────────────────────────────────────────────────────

    def format_plan(self, plan: dict[str, Any]) -> str:
        """Render a plan as readable text for the LLM context."""
        lines = [f"## Active Plan: {plan['title']}"]
        if plan.get("goal"):
            lines.append(f"**Goal:** {plan['goal']}")
        lines.append("")
        for step in plan["steps"]:
            icon = _STATUS_ICONS.get(step["status"], "[ ]")
            line = f"{icon} Step {step['index'] + 1}: {step['description']}"
            if step.get("result"):
                line += f"  — {step['result']}"
            lines.append(line)
        done = sum(1 for s in plan["steps"] if s["status"] in ("done", "skipped"))
        total = len(plan["steps"])
        lines.append(f"\nProgress: {done}/{total} steps complete")
        return "\n".join(lines)

    async def reset_interrupted_steps(self) -> None:
        """On startup, mark any in_progress steps as interrupted."""
        result = await self._session.execute(
            text("SELECT id, steps FROM plans WHERE user_id = :uid AND status = 'active'"),
            {"uid": self.user_id},
        )
        rows = result.fetchall()
        for row in rows:
            plan_id, steps_json = row[0], row[1]
            try:
                steps = json.loads(steps_json)
                changed = False
                for step in steps:
                    if step.get("status") == "in_progress":
                        step["status"] = "interrupted"
                        prev = step.get("result") or ""
                        step["result"] = (
                            (prev + " " if prev else "")
                            + "[interrupted by server restart — ask Plutus to continue]"
                        ).strip()
                        changed = True
                if changed:
                    await self._session.execute(
                        text("UPDATE plans SET steps = :steps, updated_at = :now WHERE id = :id"),
                        {"steps": json.dumps(steps), "now": time.time(), "id": plan_id},
                    )
            except Exception:
                pass
        if rows:
            await self._session.commit()


def _row_to_plan(row) -> dict[str, Any]:
    return {
        "id": row[0],
        "user_id": row[1],
        "title": row[2],
        "goal": row[3],
        "status": row[4],
        "steps": json.loads(row[5]),
        "created_at": row[6],
        "updated_at": row[7],
    }
