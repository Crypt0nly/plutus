"""Audit logging — every tool action gets recorded for review."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from plutus.config import plutus_dir


@dataclass
class AuditEntry:
    timestamp: float
    tool_name: str
    operation: str | None
    params: dict[str, Any]
    decision: str  # "allowed", "denied", "pending_approval", "approved", "rejected"
    tier: str
    reason: str
    result_summary: str | None = None
    id: str = field(default_factory=lambda: f"{time.time_ns()}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditLogger:
    """Append-only audit log stored as newline-delimited JSON."""

    def __init__(self, path: Path | None = None):
        self._path = path or (plutus_dir() / "audit.jsonl")
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, entry: AuditEntry) -> None:
        with open(self._path, "a") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

    def recent(self, limit: int = 50, offset: int = 0) -> list[AuditEntry]:
        """Read the most recent audit entries."""
        if not self._path.exists():
            return []

        lines = self._path.read_text().strip().split("\n")
        lines = [l for l in lines if l]  # skip blanks
        lines.reverse()  # newest first

        entries = []
        for line in lines[offset : offset + limit]:
            data = json.loads(line)
            entries.append(AuditEntry(**data))
        return entries

    def count(self) -> int:
        if not self._path.exists():
            return 0
        return sum(1 for line in self._path.read_text().strip().split("\n") if line)

    def clear(self) -> None:
        """Wipe the audit log."""
        self._path.write_text("")

    def entries_for_tool(self, tool_name: str, limit: int = 20) -> list[AuditEntry]:
        entries = self.recent(limit=500)
        return [e for e in entries if e.tool_name == tool_name][:limit]

    def summary(self) -> dict[str, Any]:
        """Return a summary of audit activity."""
        entries = self.recent(limit=1000)
        by_decision: dict[str, int] = {}
        by_tool: dict[str, int] = {}
        for e in entries:
            by_decision[e.decision] = by_decision.get(e.decision, 0) + 1
            by_tool[e.tool_name] = by_tool.get(e.tool_name, 0) + 1

        return {
            "total_entries": len(entries),
            "by_decision": by_decision,
            "by_tool": by_tool,
            "latest": entries[0].to_dict() if entries else None,
        }
