import json
import aiosqlite
from datetime import datetime, timezone
from pathlib import Path
from . import BaseMemoryStore

_DEFAULT_DB = Path.home() / ".plutus" / "memory.db"
_DDL = """
CREATE TABLE IF NOT EXISTS memories (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      TEXT    NOT NULL,
    category     TEXT    NOT NULL DEFAULT '',
    content      TEXT    NOT NULL,
    metadata     TEXT,
    sync_version INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
)"""

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

class LocalMemoryStore(BaseMemoryStore):
    def __init__(self, db_path: str | Path = _DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def _conn(self):
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        await db.execute(_DDL)
        await db.commit()
        return db

    async def save_fact(self, user_id: str, category: str, content: str, metadata: dict | None = None) -> int:
        meta = json.dumps(metadata) if metadata else None
        now = _now()
        async with await self._conn() as db:
            cur = await db.execute(
                "INSERT INTO memories (user_id, category, content, metadata, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, category, content, meta, now, now),
            )
            await db.commit()
            return cur.lastrowid

    async def recall_facts(self, user_id: str, category: str | None = None, limit: int = 10) -> list[dict]:
        async with await self._conn() as db:
            if category:
                cur = await db.execute(
                    "SELECT * FROM memories WHERE user_id=? AND category=? ORDER BY id DESC LIMIT ?",
                    (user_id, category, limit),
                )
            else:
                cur = await db.execute(
                    "SELECT * FROM memories WHERE user_id=? ORDER BY id DESC LIMIT ?",
                    (user_id, limit),
                )
            rows = await cur.fetchall()
        return [_row(r) for r in rows]

    async def search_facts(self, user_id: str, query: str, limit: int = 10) -> list[dict]:
        pattern = f"%{query}%"
        async with await self._conn() as db:
            cur = await db.execute(
                "SELECT * FROM memories WHERE user_id=? AND (content LIKE ? OR category LIKE ?)"
                " ORDER BY id DESC LIMIT ?",
                (user_id, pattern, pattern, limit),
            )
            rows = await cur.fetchall()
        return [_row(r) for r in rows]

    async def delete_fact(self, user_id: str, fact_id: int) -> bool:
        async with await self._conn() as db:
            cur = await db.execute(
                "DELETE FROM memories WHERE id=? AND user_id=?", (fact_id, user_id)
            )
            await db.commit()
            return cur.rowcount > 0

    async def get_sync_changes(self, user_id: str, since_version: int) -> list[dict]:
        async with await self._conn() as db:
            cur = await db.execute(
                "SELECT * FROM memories WHERE user_id=? AND sync_version>? ORDER BY sync_version",
                (user_id, since_version),
            )
            rows = await cur.fetchall()
        return [_row(r) for r in rows]

def _row(r: aiosqlite.Row) -> dict:
    d = dict(r)
    if d.get("metadata"):
        try:
            d["metadata"] = json.loads(d["metadata"])
        except (json.JSONDecodeError, TypeError):
            pass
    return d
