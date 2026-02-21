"""Guardrail engine — the central authority for all permission decisions.

This is the single entry point that the agent runtime calls before executing
any tool action. It combines tier policies, user overrides, audit logging,
and the approval queue.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from plutus.config import PlutusConfig
from plutus.guardrails.audit import AuditEntry, AuditLogger
from plutus.guardrails.policies import PolicyDecision, PolicyEvaluator
from plutus.guardrails.tiers import Tier


class ApprovalRequest:
    """A pending action waiting for user approval via the UI."""

    def __init__(self, tool_name: str, operation: str | None, params: dict[str, Any], reason: str):
        self.id = f"approval-{time.time_ns()}"
        self.tool_name = tool_name
        self.operation = operation
        self.params = params
        self.reason = reason
        self.created_at = time.time()
        self._event = asyncio.Event()
        self._approved: bool | None = None

    async def wait(self, timeout: float = 300.0) -> bool:
        """Block until the user approves or rejects, or timeout expires."""
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            self._approved = False
        return self._approved or False

    def resolve(self, approved: bool) -> None:
        self._approved = approved
        self._event.set()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "operation": self.operation,
            "params": self.params,
            "reason": self.reason,
            "created_at": self.created_at,
        }


class GuardrailEngine:
    """Central guardrail authority.

    Usage:
        engine = GuardrailEngine(config)
        decision = engine.check("shell", "execute", {"command": "ls"})
        if decision.requires_approval:
            approved = await engine.request_approval(decision, ...)
    """

    def __init__(self, config: PlutusConfig):
        self._config = config
        self._tier = Tier(config.guardrails.tier)
        self._evaluator = PolicyEvaluator(
            tier=self._tier,
            overrides={
                k: v.model_dump() for k, v in config.guardrails.tool_overrides.items()
            },
        )
        self._audit = AuditLogger()
        self._pending_approvals: dict[str, ApprovalRequest] = {}

    @property
    def tier(self) -> Tier:
        return self._tier

    @property
    def audit(self) -> AuditLogger:
        return self._audit

    def set_tier(self, tier: Tier) -> None:
        """Change the active tier (persists to config)."""
        self._tier = tier
        self._config.guardrails.tier = tier.value
        self._evaluator = PolicyEvaluator(
            tier=tier,
            overrides={
                k: v.model_dump() for k, v in self._config.guardrails.tool_overrides.items()
            },
        )
        self._config.save()

    def check(
        self,
        tool_name: str,
        operation: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        """Evaluate whether a tool action is permitted."""
        decision = self._evaluator.evaluate(tool_name, operation, params)

        self._audit.log(
            AuditEntry(
                timestamp=time.time(),
                tool_name=tool_name,
                operation=operation,
                params=params or {},
                decision=decision.status,
                tier=self._tier.value,
                reason=decision.reason,
            )
        )

        return decision

    async def request_approval(
        self,
        tool_name: str,
        operation: str | None,
        params: dict[str, Any],
        reason: str,
    ) -> bool:
        """Create an approval request and wait for the user to respond via the UI."""
        request = ApprovalRequest(tool_name, operation, params, reason)
        self._pending_approvals[request.id] = request

        approved = await request.wait()

        # Log the resolution
        self._audit.log(
            AuditEntry(
                timestamp=time.time(),
                tool_name=tool_name,
                operation=operation,
                params=params,
                decision="approved" if approved else "rejected",
                tier=self._tier.value,
                reason=f"User {'approved' if approved else 'rejected'} the action",
            )
        )

        del self._pending_approvals[request.id]
        return approved

    def resolve_approval(self, approval_id: str, approved: bool) -> bool:
        """Called by the UI/API when the user approves or rejects a pending action."""
        request = self._pending_approvals.get(approval_id)
        if not request:
            return False
        request.resolve(approved)
        return True

    def pending_approvals(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self._pending_approvals.values()]

    def get_status(self) -> dict[str, Any]:
        return {
            "tier": self._tier.value,
            "tier_label": self._tier.label,
            "tier_description": self._tier.description,
            "pending_approvals": len(self._pending_approvals),
            "audit_summary": self._audit.summary(),
        }
