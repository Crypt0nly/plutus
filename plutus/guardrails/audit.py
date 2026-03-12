"""Audit logging — every tool action gets recorded for review."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from plutus.config import plutus_dir

# Maximum audit log file size before rotation (10 MB)
_MAX_AUDIT_SIZE = 10 * 1024 * 1024


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
        # Rotate if file exceeds size limit
        self._maybe_rotate()

    def _maybe_rotate(self) -> None:
        """Rotate audit log if it exceeds the max size."""
        try:
            if self._path.exists() and self._path.stat().st_size > _MAX_AUDIT_SIZE:
                rotated = self._path.with_suffix(".jsonl.old")
                # Remove previous rotation if it exists
                if rotated.exists():
                    rotated.unlink()
                self._path.rename(rotated)
        except OSError:
            pass

    def recent(self, limit: int = 50, offset: int = 0) -> list[AuditEntry]:
        """Read the most recent audit entries without loading the entire file."""
        if not self._path.exists():
            return []

        lines = _tail_lines(self._path, limit + offset)
        lines.reverse()  # newest first

        entries = []
        for line in lines[offset : offset + limit]:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                entries.append(AuditEntry(**data))
            except (json.JSONDecodeError, TypeError):
                continue
        return entries

    def count(self) -> int:
        if not self._path.exists():
            return 0
        count = 0
        with open(self._path) as f:
            for line in f:
                if line.strip():
                    count += 1
        return count

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


def _tail_lines(path: Path, n: int) -> list[str]:
    """Read the last n lines from a file efficiently without loading the whole file."""
    if n <= 0:
        return []
    try:
        file_size = path.stat().st_size
        if file_size == 0:
            return []
        # For small files, just read the whole thing
        if file_size < 1024 * 1024:  # < 1 MB
            with open(path) as f:
                lines = f.readlines()
            return [line.rstrip("\n") for line in lines[-n:]]
        # For large files, read from the end in chunks
        chunk_size = 8192
        lines: list[str] = []
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            remaining = f.tell()
            buffer = b""
            while remaining > 0 and len(lines) <= n:
                read_size = min(chunk_size, remaining)
                remaining -= read_size
                f.seek(remaining)
                buffer = f.read(read_size) + buffer
                lines = buffer.decode(errors="replace").splitlines()
            return lines[-n:]
    except OSError:
        return []
