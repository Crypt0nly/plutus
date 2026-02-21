"""Plan manager — lets Plutus create, track, and update execution plans.

Plans keep the agent and user in sync.  Before tackling a complex task the
agent creates a plan with discrete steps.  As it works, it marks steps
in-progress / done / failed and the UI can show real-time progress.

Plans are persisted to SQLite so they survive restarts and can be reviewed
after the fact.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from enum import Enum
from typing import Any

from plutus.core.memory import MemoryStore

logger = logging.getLogger("plutus.planner")


class StepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class PlanStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PlanManager:
    """Creates and manages execution plans backed by SQLite."""

    def __init__(self, memory: MemoryStore):
        self._memory = memory

    async def initialize(self) -> None:
        """Create the plans table if it doesn't exist."""
        assert self._memory._db
        await self._memory._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS plans (
                id TEXT PRIMARY KEY,
                conversation_id TEXT,
                title TEXT NOT NULL,
                goal TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                steps TEXT NOT NULL DEFAULT '[]',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            );
            CREATE INDEX IF NOT EXISTS idx_plans_conversation ON plans(conversation_id);
            CREATE INDEX IF NOT EXISTS idx_plans_status ON plans(status);
            """
        )
        await self._memory._db.commit()

    # -- CRUD ----------------------------------------------------------------

    async def create_plan(
        self,
        title: str,
        steps: list[dict[str, str]],
        goal: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new plan.

        Each step dict should have at minimum: {"description": "..."}
        Optional fields: "details", "tool_hint".
        """
        plan_id = str(uuid.uuid4())
        now = time.time()

        enriched_steps = []
        for i, s in enumerate(steps):
            enriched_steps.append(
                {
                    "index": i,
                    "description": s.get("description", s.get("name", f"Step {i + 1}")),
                    "details": s.get("details", ""),
                    "status": StepStatus.PENDING.value,
                    "result": None,
                    "started_at": None,
                    "finished_at": None,
                }
            )

        assert self._memory._db
        await self._memory._db.execute(
            "INSERT INTO plans (id, conversation_id, title, goal, status, steps, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                plan_id,
                conversation_id,
                title,
                goal,
                PlanStatus.ACTIVE.value,
                json.dumps(enriched_steps),
                now,
                now,
            ),
        )
        await self._memory._db.commit()

        plan = {
            "id": plan_id,
            "conversation_id": conversation_id,
            "title": title,
            "goal": goal,
            "status": PlanStatus.ACTIVE.value,
            "steps": enriched_steps,
            "created_at": now,
            "updated_at": now,
        }
        logger.info("Plan created: %s (%d steps)", title, len(enriched_steps))
        return plan

    async def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        assert self._memory._db
        cursor = await self._memory._db.execute(
            "SELECT id, conversation_id, title, goal, status, steps, created_at, updated_at "
            "FROM plans WHERE id = ?",
            (plan_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return _row_to_plan(row)

    async def get_active_plan(self, conversation_id: str | None = None) -> dict[str, Any] | None:
        """Get the most recent active plan, optionally scoped to a conversation."""
        assert self._memory._db
        if conversation_id:
            cursor = await self._memory._db.execute(
                "SELECT id, conversation_id, title, goal, status, steps, created_at, updated_at "
                "FROM plans WHERE status = 'active' AND conversation_id = ? "
                "ORDER BY updated_at DESC LIMIT 1",
                (conversation_id,),
            )
        else:
            cursor = await self._memory._db.execute(
                "SELECT id, conversation_id, title, goal, status, steps, created_at, updated_at "
                "FROM plans WHERE status = 'active' ORDER BY updated_at DESC LIMIT 1",
            )
        row = await cursor.fetchone()
        if not row:
            return None
        return _row_to_plan(row)

    async def list_plans(
        self, conversation_id: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        assert self._memory._db
        if conversation_id:
            cursor = await self._memory._db.execute(
                "SELECT id, conversation_id, title, goal, status, steps, created_at, updated_at "
                "FROM plans WHERE conversation_id = ? ORDER BY updated_at DESC LIMIT ?",
                (conversation_id, limit),
            )
        else:
            cursor = await self._memory._db.execute(
                "SELECT id, conversation_id, title, goal, status, steps, created_at, updated_at "
                "FROM plans ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            )
        rows = await cursor.fetchall()
        return [_row_to_plan(r) for r in rows]

    # -- Step updates --------------------------------------------------------

    async def update_step(
        self,
        plan_id: str,
        step_index: int,
        status: str,
        result: str | None = None,
    ) -> dict[str, Any] | None:
        """Update a single step's status and optional result."""
        plan = await self.get_plan(plan_id)
        if not plan:
            return None

        steps = plan["steps"]
        if step_index < 0 or step_index >= len(steps):
            return None

        now = time.time()
        steps[step_index]["status"] = status
        if result is not None:
            steps[step_index]["result"] = result
        if status == StepStatus.IN_PROGRESS.value:
            steps[step_index]["started_at"] = now
        if status in (StepStatus.DONE.value, StepStatus.FAILED.value, StepStatus.SKIPPED.value):
            steps[step_index]["finished_at"] = now

        # Auto-detect plan completion
        plan_status = plan["status"]
        all_terminal = all(
            s["status"] in (StepStatus.DONE.value, StepStatus.SKIPPED.value, StepStatus.FAILED.value)
            for s in steps
        )
        if all_terminal:
            any_failed = any(s["status"] == StepStatus.FAILED.value for s in steps)
            plan_status = PlanStatus.FAILED.value if any_failed else PlanStatus.COMPLETED.value

        assert self._memory._db
        await self._memory._db.execute(
            "UPDATE plans SET steps = ?, status = ?, updated_at = ? WHERE id = ?",
            (json.dumps(steps), plan_status, now, plan_id),
        )
        await self._memory._db.commit()

        plan["steps"] = steps
        plan["status"] = plan_status
        plan["updated_at"] = now
        return plan

    async def set_plan_status(self, plan_id: str, status: str) -> dict[str, Any] | None:
        plan = await self.get_plan(plan_id)
        if not plan:
            return None

        now = time.time()
        assert self._memory._db
        await self._memory._db.execute(
            "UPDATE plans SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, plan_id),
        )
        await self._memory._db.commit()

        plan["status"] = status
        plan["updated_at"] = now
        return plan

    async def delete_plan(self, plan_id: str) -> bool:
        assert self._memory._db
        cursor = await self._memory._db.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
        await self._memory._db.commit()
        return cursor.rowcount > 0

    # -- Helpers for the agent -----------------------------------------------

    def format_plan_for_context(self, plan: dict[str, Any]) -> str:
        """Render a plan as readable text to inject into the system prompt."""
        lines = [
            f"## Active Plan: {plan['title']}",
        ]
        if plan.get("goal"):
            lines.append(f"**Goal:** {plan['goal']}")
        lines.append("")

        status_icons = {
            "pending": "[ ]",
            "in_progress": "[>]",
            "done": "[x]",
            "failed": "[!]",
            "skipped": "[-]",
        }

        for step in plan["steps"]:
            icon = status_icons.get(step["status"], "[ ]")
            line = f"{icon} Step {step['index'] + 1}: {step['description']}"
            if step.get("result"):
                line += f"  — {step['result']}"
            lines.append(line)

        done_count = sum(
            1 for s in plan["steps"] if s["status"] in ("done", "skipped")
        )
        total = len(plan["steps"])
        lines.append(f"\nProgress: {done_count}/{total} steps complete")
        return "\n".join(lines)


def _row_to_plan(row: tuple) -> dict[str, Any]:
    return {
        "id": row[0],
        "conversation_id": row[1],
        "title": row[2],
        "goal": row[3],
        "status": row[4],
        "steps": json.loads(row[5]),
        "created_at": row[6],
        "updated_at": row[7],
    }
