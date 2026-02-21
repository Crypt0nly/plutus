"""Tests for the guardrails system — tiers, policies, and audit."""

import json
import tempfile
from pathlib import Path

import pytest

from plutus.guardrails.tiers import (
    Tier,
    ToolPermission,
    ToolPolicy,
    TIER_DEFAULTS,
    default_permission_for_tier,
    get_tier_info,
)
from plutus.guardrails.policies import PolicyEvaluator, PolicyDecision
from plutus.guardrails.audit import AuditEntry, AuditLogger


# ── Tier tests ──────────────────────────────────────────────


class TestTiers:
    def test_tier_values(self):
        assert Tier.OBSERVER.value == "observer"
        assert Tier.ASSISTANT.value == "assistant"
        assert Tier.OPERATOR.value == "operator"
        assert Tier.AUTONOMOUS.value == "autonomous"

    def test_tier_levels_are_ordered(self):
        assert Tier.OBSERVER.level < Tier.ASSISTANT.level
        assert Tier.ASSISTANT.level < Tier.OPERATOR.level
        assert Tier.OPERATOR.level < Tier.AUTONOMOUS.level

    def test_tier_labels(self):
        assert Tier.OBSERVER.label == "Observer"
        assert Tier.AUTONOMOUS.label == "Autonomous"

    def test_tier_descriptions_are_nonempty(self):
        for tier in Tier:
            assert len(tier.description) > 10

    def test_all_tiers_have_defaults(self):
        for tier in Tier:
            assert tier in TIER_DEFAULTS

    def test_default_permission_for_observer_is_denied(self):
        assert default_permission_for_tier(Tier.OBSERVER) == ToolPermission.DENIED

    def test_default_permission_for_autonomous_is_allowed(self):
        assert default_permission_for_tier(Tier.AUTONOMOUS) == ToolPermission.ALLOWED

    def test_get_tier_info_returns_all_tiers(self):
        info = get_tier_info()
        assert len(info) == 4
        ids = {t["id"] for t in info}
        assert ids == {"observer", "assistant", "operator", "autonomous"}


# ── Policy Evaluator tests ──────────────────────────────────


class TestPolicyEvaluator:
    def test_observer_denies_shell(self):
        evaluator = PolicyEvaluator(Tier.OBSERVER)
        decision = evaluator.evaluate("shell", "execute", {"command": "ls"})
        assert not decision.allowed
        assert decision.status == "denied"

    def test_observer_allows_filesystem_read(self):
        evaluator = PolicyEvaluator(Tier.OBSERVER)
        decision = evaluator.evaluate("filesystem", "read")
        assert decision.allowed
        assert not decision.requires_approval

    def test_observer_denies_filesystem_write(self):
        evaluator = PolicyEvaluator(Tier.OBSERVER)
        decision = evaluator.evaluate("filesystem", "write")
        assert not decision.allowed

    def test_assistant_requires_approval_for_shell(self):
        evaluator = PolicyEvaluator(Tier.ASSISTANT)
        decision = evaluator.evaluate("shell", "execute")
        assert decision.allowed
        assert decision.requires_approval
        assert decision.status == "pending_approval"

    def test_operator_allows_shell(self):
        evaluator = PolicyEvaluator(Tier.OPERATOR)
        decision = evaluator.evaluate("shell", "execute", {"command": "ls -la"})
        assert decision.allowed
        assert not decision.requires_approval

    def test_operator_denies_dangerous_patterns(self):
        evaluator = PolicyEvaluator(Tier.OPERATOR)
        decision = evaluator.evaluate("shell", "execute", {"command": "rm -rf /"})
        assert not decision.allowed

    def test_autonomous_allows_everything(self):
        evaluator = PolicyEvaluator(Tier.AUTONOMOUS)
        for tool in ["shell", "filesystem", "browser", "process", "system_info", "clipboard"]:
            decision = evaluator.evaluate(tool)
            assert decision.allowed
            assert not decision.requires_approval

    def test_user_override_disables_tool(self):
        overrides = {"shell": {"enabled": False}}
        evaluator = PolicyEvaluator(Tier.AUTONOMOUS, overrides=overrides)
        decision = evaluator.evaluate("shell", "execute")
        assert not decision.allowed

    def test_user_override_forces_approval(self):
        overrides = {"shell": {"enabled": True, "require_approval": True}}
        evaluator = PolicyEvaluator(Tier.AUTONOMOUS, overrides=overrides)
        decision = evaluator.evaluate("shell", "execute")
        assert decision.allowed
        assert decision.requires_approval

    def test_unknown_tool_uses_tier_default(self):
        evaluator = PolicyEvaluator(Tier.OBSERVER)
        decision = evaluator.evaluate("unknown_tool")
        assert not decision.allowed  # Observer defaults to denied

        evaluator2 = PolicyEvaluator(Tier.AUTONOMOUS)
        decision2 = evaluator2.evaluate("unknown_tool")
        assert decision2.allowed  # Autonomous defaults to allowed

    def test_decision_has_reason(self):
        evaluator = PolicyEvaluator(Tier.OBSERVER)
        decision = evaluator.evaluate("shell")
        assert len(decision.reason) > 0


# ── Audit Logger tests ──────────────────────────────────────


class TestAuditLogger:
    def test_log_and_read(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = Path(f.name)

        logger = AuditLogger(path)

        entry = AuditEntry(
            timestamp=1700000000.0,
            tool_name="shell",
            operation="execute",
            params={"command": "ls"},
            decision="allowed",
            tier="operator",
            reason="Allowed by tier policy",
        )
        logger.log(entry)

        entries = logger.recent(limit=10)
        assert len(entries) == 1
        assert entries[0].tool_name == "shell"
        assert entries[0].decision == "allowed"

        path.unlink()

    def test_recent_returns_newest_first(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = Path(f.name)

        logger = AuditLogger(path)

        for i in range(5):
            logger.log(
                AuditEntry(
                    timestamp=1700000000.0 + i,
                    tool_name=f"tool_{i}",
                    operation=None,
                    params={},
                    decision="allowed",
                    tier="operator",
                    reason="test",
                )
            )

        entries = logger.recent(limit=3)
        assert len(entries) == 3
        assert entries[0].tool_name == "tool_4"  # newest
        assert entries[2].tool_name == "tool_2"

        path.unlink()

    def test_count(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = Path(f.name)

        logger = AuditLogger(path)
        assert logger.count() == 0

        logger.log(
            AuditEntry(
                timestamp=1.0,
                tool_name="t",
                operation=None,
                params={},
                decision="allowed",
                tier="operator",
                reason="test",
            )
        )
        assert logger.count() == 1

        path.unlink()

    def test_summary(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = Path(f.name)

        logger = AuditLogger(path)

        for decision in ["allowed", "allowed", "denied"]:
            logger.log(
                AuditEntry(
                    timestamp=1.0,
                    tool_name="shell",
                    operation=None,
                    params={},
                    decision=decision,
                    tier="operator",
                    reason="test",
                )
            )

        summary = logger.summary()
        assert summary["total_entries"] == 3
        assert summary["by_decision"]["allowed"] == 2
        assert summary["by_decision"]["denied"] == 1

        path.unlink()

    def test_clear(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = Path(f.name)

        logger = AuditLogger(path)
        logger.log(
            AuditEntry(
                timestamp=1.0,
                tool_name="t",
                operation=None,
                params={},
                decision="allowed",
                tier="op",
                reason="test",
            )
        )
        assert logger.count() == 1
        logger.clear()
        assert logger.count() == 0

        path.unlink()
