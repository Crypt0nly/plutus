"""Policy evaluation — decides whether a tool action is allowed, denied, or needs approval."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from plutus.guardrails.tiers import (
    TIER_DEFAULTS,
    Tier,
    ToolPermission,
    ToolPolicy,
    default_permission_for_tier,
)


@dataclass
class PolicyDecision:
    """Result of evaluating a tool action against the current policy."""

    allowed: bool
    requires_approval: bool
    reason: str
    tool_name: str
    operation: str | None = None

    @property
    def status(self) -> str:
        if self.allowed and not self.requires_approval:
            return "allowed"
        if self.requires_approval:
            return "pending_approval"
        return "denied"


class PolicyEvaluator:
    """Evaluates tool actions against the current tier and any user overrides."""

    def __init__(self, tier: Tier, overrides: dict[str, dict[str, Any]] | None = None):
        self.tier = tier
        self._overrides = overrides or {}

    def evaluate(
        self,
        tool_name: str,
        operation: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        """Check whether a tool action is allowed under the current policy.

        Args:
            tool_name: The tool being invoked (e.g. "shell", "filesystem").
            operation: The specific operation (e.g. "read", "write", "execute").
            params: Action parameters for pattern matching (e.g. {"command": "ls -la"}).
        """
        # Check user-level overrides first
        if tool_name in self._overrides:
            override = self._overrides[tool_name]
            if not override.get("enabled", True):
                return PolicyDecision(
                    allowed=False,
                    requires_approval=False,
                    reason=f"Tool '{tool_name}' is disabled by user configuration",
                    tool_name=tool_name,
                    operation=operation,
                )
            if override.get("require_approval"):
                return PolicyDecision(
                    allowed=True,
                    requires_approval=True,
                    reason=f"Tool '{tool_name}' requires approval per user override",
                    tool_name=tool_name,
                    operation=operation,
                )

        # Look up tier defaults
        tier_policies = TIER_DEFAULTS.get(self.tier, {})
        policy = tier_policies.get(tool_name)

        if policy is None:
            # Tool not explicitly listed — use tier default
            fallback = default_permission_for_tier(self.tier)
            return self._decision_from_permission(fallback, tool_name, operation, "tier default")

        # Check denied patterns (blocklist)
        if policy.denied_patterns and params:
            for pattern in policy.denied_patterns:
                for val in params.values():
                    if isinstance(val, str) and re.search(re.escape(pattern), val):
                        return PolicyDecision(
                            allowed=False,
                            requires_approval=False,
                            reason=f"Action matches denied pattern: '{pattern}'",
                            tool_name=tool_name,
                            operation=operation,
                        )

        # Check operation allowlist
        if policy.allowed_operations and operation:
            if operation not in policy.allowed_operations:
                return PolicyDecision(
                    allowed=False,
                    requires_approval=False,
                    reason=(
                        f"Operation '{operation}' not in allowed list: "
                        f"{policy.allowed_operations}"
                    ),
                    tool_name=tool_name,
                    operation=operation,
                )

        return self._decision_from_permission(policy.permission, tool_name, operation, "tier policy")

    def _decision_from_permission(
        self,
        permission: ToolPermission,
        tool_name: str,
        operation: str | None,
        source: str,
    ) -> PolicyDecision:
        if permission == ToolPermission.ALLOWED:
            return PolicyDecision(
                allowed=True,
                requires_approval=False,
                reason=f"Allowed by {source}",
                tool_name=tool_name,
                operation=operation,
            )
        if permission == ToolPermission.REQUIRES_APPROVAL:
            return PolicyDecision(
                allowed=True,
                requires_approval=True,
                reason=f"Requires approval per {source}",
                tool_name=tool_name,
                operation=operation,
            )
        return PolicyDecision(
            allowed=False,
            requires_approval=False,
            reason=f"Denied by {source}",
            tool_name=tool_name,
            operation=operation,
        )
