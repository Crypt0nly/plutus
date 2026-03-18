import json
import aiosqlite
from datetime import datetime, timezone
from pathlib import Path
from . import BaseSkillStore

_DEFAULT_DB = Path.home() / ".plutus" / "skills.db"
_DDL = """
CREATE TABLE IF NOT EXISTS skills (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      TEXT    NOT NULL,
    name         TEXT    NOT NULL,
    description  TEXT    NOT NULL DEFAULT '',
    skill_type   TEXT    NOT NULL DEFAULT 'simple',
    definition   TEXT    NOT NULL,
    is_shared    INTEGER NOT NULL DEFAULT 0,
    sync_version INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
)"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LocalSkillStore(BaseSkillStore):
    def __init__(self, db_path: str | Path = _DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def _conn(self):
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        await db.execute(_DDL)
        await db.commit()
        return db

    async def _next_version(self, db, user_id: str) -> int:
        cur = await db.execute(
            "SELECT COALESCE(MAX(sync_version), 0) FROM skills WHERE user_id=?",
            (user_id,),
        )
        row = await cur.fetchone()
        return row[0] + 1

    async def save_skill(
        self,
        user_id: str,
        name: str,
        definition: dict,
        description: str = "",
        skill_type: str = "simple",
    ) -> int:
        defn = json.dumps(definition)
        now = _now()
        async with await self._conn() as db:
            version = await self._next_version(db, user_id)
            cur = await db.execute(
                "INSERT INTO skills "
                "(user_id, name, description, skill_type, definition, sync_version, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, name, description, skill_type, defn, version, now, now),
            )
            await db.commit()
            return cur.lastrowid

    async def get_skill(self, user_id: str, skill_id: int) -> dict | None:
        async with await self._conn() as db:
            cur = await db.execute(
                "SELECT * FROM skills WHERE id=? AND (user_id=? OR is_shared=1)",
                (skill_id, user_id),
            )
            row = await cur.fetchone()
        return _row(row) if row else None

    async def list_skills(
        self, user_id: str, include_shared: bool = True
    ) -> list[dict]:
        async with await self._conn() as db:
            if include_shared:
                cur = await db.execute(
                    "SELECT * FROM skills WHERE user_id=? OR is_shared=1 ORDER BY id DESC",
                    (user_id,),
                )
            else:
                cur = await db.execute(
                    "SELECT * FROM skills WHERE user_id=? ORDER BY id DESC",
                    (user_id,),
                )
            rows = await cur.fetchall()
        return [_row(r) for r in rows]

    async def delete_skill(self, user_id: str, skill_id: int) -> bool:
        async with await self._conn() as db:
            cur = await db.execute(
                "DELETE FROM skills WHERE id=? AND user_id=?", (skill_id, user_id)
            )
            await db.commit()
            return cur.rowcount > 0

    async def get_sync_changes(
        self, user_id: str, since_version: int = 0
    ) -> list[dict]:
        async with await self._conn() as db:
            cur = await db.execute(
                "SELECT * FROM skills WHERE user_id=? AND sync_version>? ORDER BY sync_version",
                (user_id, since_version),
            )
            rows = await cur.fetchall()
        return [_row(r) for r in rows]


def _row(r: aiosqlite.Row) -> dict:
    d = dict(r)
    if d.get("definition"):
        try:
            d["definition"] = json.loads(d["definition"])
        except (json.JSONDecodeError, TypeError):
            pass
    # Normalise is_shared from integer to bool for consistency with cloud store
    d["is_shared"] = bool(d.get("is_shared", 0))
    return d
