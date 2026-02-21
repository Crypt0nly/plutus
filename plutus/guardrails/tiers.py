"""Tier definitions for the guardrails system.

Each tier specifies default permissions for every tool category.
Users can override individual tool permissions within any tier.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


class Tier(str, Enum):
    OBSERVER = "observer"
    ASSISTANT = "assistant"
    OPERATOR = "operator"
    AUTONOMOUS = "autonomous"

    @property
    def label(self) -> str:
        return {
            Tier.OBSERVER: "Observer",
            Tier.ASSISTANT: "Assistant",
            Tier.OPERATOR: "Operator",
            Tier.AUTONOMOUS: "Autonomous",
        }[self]

    @property
    def description(self) -> str:
        return {
            Tier.OBSERVER: "Read-only access. The AI can observe but never modify.",
            Tier.ASSISTANT: "Every action requires your explicit approval before executing.",
            Tier.OPERATOR: "Pre-approved actions run automatically; everything else asks first.",
            Tier.AUTONOMOUS: "Full system control. The AI handles everything independently.",
        }[self]

    @property
    def level(self) -> int:
        """Numeric level for comparison. Higher = more permissive."""
        return {Tier.OBSERVER: 0, Tier.ASSISTANT: 1, Tier.OPERATOR: 2, Tier.AUTONOMOUS: 3}[self]


class ToolPermission(str, Enum):
    DENIED = "denied"
    REQUIRES_APPROVAL = "requires_approval"
    ALLOWED = "allowed"


class ToolPolicy(BaseModel):
    """Permission policy for a single tool within a given tier."""

    tool_name: str
    permission: ToolPermission
    allowed_operations: list[str] | None = None  # granular op filtering (e.g. ["read"] for fs)
    denied_patterns: list[str] | None = None  # blocklist patterns (e.g. ["rm -rf /"])


# Default policies per tier. Keys are tool names.
# Tools not listed inherit the tier's default permission.

TIER_DEFAULTS: dict[Tier, dict[str, ToolPolicy]] = {
    Tier.OBSERVER: {
        "shell": ToolPolicy(tool_name="shell", permission=ToolPermission.DENIED),
        "filesystem": ToolPolicy(
            tool_name="filesystem",
            permission=ToolPermission.ALLOWED,
            allowed_operations=["read", "search", "list"],
        ),
        "browser": ToolPolicy(
            tool_name="browser",
            permission=ToolPermission.ALLOWED,
            allowed_operations=["navigate", "screenshot", "extract", "wait"],
        ),
        "process": ToolPolicy(
            tool_name="process",
            permission=ToolPermission.ALLOWED,
            allowed_operations=["list"],
        ),
        "system_info": ToolPolicy(tool_name="system_info", permission=ToolPermission.ALLOWED),
        "clipboard": ToolPolicy(
            tool_name="clipboard",
            permission=ToolPermission.ALLOWED,
            allowed_operations=["read"],
        ),
        "desktop": ToolPolicy(
            tool_name="desktop",
            permission=ToolPermission.ALLOWED,
            allowed_operations=["screenshot", "get_mouse_position", "get_screen_size"],
        ),
        "app_manager": ToolPolicy(
            tool_name="app_manager",
            permission=ToolPermission.ALLOWED,
            allowed_operations=["list_windows"],
        ),
    },
    Tier.ASSISTANT: {
        "shell": ToolPolicy(tool_name="shell", permission=ToolPermission.REQUIRES_APPROVAL),
        "filesystem": ToolPolicy(
            tool_name="filesystem", permission=ToolPermission.REQUIRES_APPROVAL
        ),
        "browser": ToolPolicy(tool_name="browser", permission=ToolPermission.REQUIRES_APPROVAL),
        "process": ToolPolicy(tool_name="process", permission=ToolPermission.REQUIRES_APPROVAL),
        "system_info": ToolPolicy(tool_name="system_info", permission=ToolPermission.ALLOWED),
        "clipboard": ToolPolicy(tool_name="clipboard", permission=ToolPermission.REQUIRES_APPROVAL),
        "desktop": ToolPolicy(tool_name="desktop", permission=ToolPermission.REQUIRES_APPROVAL),
        "app_manager": ToolPolicy(
            tool_name="app_manager", permission=ToolPermission.REQUIRES_APPROVAL
        ),
    },
    Tier.OPERATOR: {
        "shell": ToolPolicy(
            tool_name="shell",
            permission=ToolPermission.ALLOWED,
            denied_patterns=["rm -rf /", "mkfs", "dd if=", "> /dev/"],
        ),
        "filesystem": ToolPolicy(tool_name="filesystem", permission=ToolPermission.ALLOWED),
        "browser": ToolPolicy(tool_name="browser", permission=ToolPermission.ALLOWED),
        "process": ToolPolicy(
            tool_name="process",
            permission=ToolPermission.ALLOWED,
            allowed_operations=["list", "start"],
        ),
        "system_info": ToolPolicy(tool_name="system_info", permission=ToolPermission.ALLOWED),
        "clipboard": ToolPolicy(tool_name="clipboard", permission=ToolPermission.ALLOWED),
        "desktop": ToolPolicy(tool_name="desktop", permission=ToolPermission.ALLOWED),
        "app_manager": ToolPolicy(
            tool_name="app_manager",
            permission=ToolPermission.ALLOWED,
            allowed_operations=["launch", "list_windows", "focus_window", "minimize_window", "maximize_window"],
        ),
    },
    Tier.AUTONOMOUS: {
        "shell": ToolPolicy(tool_name="shell", permission=ToolPermission.ALLOWED),
        "filesystem": ToolPolicy(tool_name="filesystem", permission=ToolPermission.ALLOWED),
        "browser": ToolPolicy(tool_name="browser", permission=ToolPermission.ALLOWED),
        "process": ToolPolicy(tool_name="process", permission=ToolPermission.ALLOWED),
        "system_info": ToolPolicy(tool_name="system_info", permission=ToolPermission.ALLOWED),
        "clipboard": ToolPolicy(tool_name="clipboard", permission=ToolPermission.ALLOWED),
        "desktop": ToolPolicy(tool_name="desktop", permission=ToolPermission.ALLOWED),
        "app_manager": ToolPolicy(tool_name="app_manager", permission=ToolPermission.ALLOWED),
    },
}


def default_permission_for_tier(tier: Tier) -> ToolPermission:
    """Fallback permission for tools not explicitly listed in a tier."""
    return {
        Tier.OBSERVER: ToolPermission.DENIED,
        Tier.ASSISTANT: ToolPermission.REQUIRES_APPROVAL,
        Tier.OPERATOR: ToolPermission.ALLOWED,
        Tier.AUTONOMOUS: ToolPermission.ALLOWED,
    }[tier]


def get_tier_info() -> list[dict[str, Any]]:
    """Return serializable tier information for the UI."""
    result = []
    for tier in Tier:
        policies = TIER_DEFAULTS.get(tier, {})
        result.append(
            {
                "id": tier.value,
                "label": tier.label,
                "description": tier.description,
                "level": tier.level,
                "tools": {
                    name: {
                        "permission": policy.permission.value,
                        "allowed_operations": policy.allowed_operations,
                        "denied_patterns": policy.denied_patterns,
                    }
                    for name, policy in policies.items()
                },
            }
        )
    return result
