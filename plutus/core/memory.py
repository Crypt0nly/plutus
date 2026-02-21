"""Persistent memory store backed by SQLite.

Stores conversation history, learned facts, and project context.
"""

from __future__ import annotations

import json
import time
from typing import Any

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    title TEXT,
    metadata TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT,
    tool_calls TEXT,
    tool_call_id TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
"""


class MemoryStore:
    """Async SQLite-backed memory store."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    # -- Conversations --

    async def create_conversation(self, conv_id: str, title: str | None = None) -> None:
        assert self._db
        await self._db.execute(
            "INSERT INTO conversations (id, created_at, title) VALUES (?, ?, ?)",
            (conv_id, time.time(), title),
        )
        await self._db.commit()

    async def list_conversations(self, limit: int = 20) -> list[dict[str, Any]]:
        assert self._db
        cursor = await self._db.execute(
            "SELECT id, created_at, title, metadata FROM conversations "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "created_at": r[1],
                "title": r[2],
                "metadata": json.loads(r[3]),
            }
            for r in rows
        ]

    async def delete_conversation(self, conv_id: str) -> None:
        assert self._db
        await self._db.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
        await self._db.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        await self._db.commit()

    # -- Messages --

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str | None = None,
        tool_calls: list[dict] | None = None,
        tool_call_id: str | None = None,
    ) -> int:
        assert self._db
        cursor = await self._db.execute(
            "INSERT INTO messages (conversation_id, role, content, tool_calls, tool_call_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                conversation_id,
                role,
                content,
                json.dumps(tool_calls) if tool_calls else None,
                tool_call_id,
                time.time(),
            ),
        )
        await self._db.commit()
        return cursor.lastrowid  # type: ignore

    async def get_messages(
        self, conversation_id: str, limit: int | None = None
    ) -> list[dict[str, Any]]:
        assert self._db
        query = (
            "SELECT id, role, content, tool_calls, tool_call_id, created_at "
            "FROM messages WHERE conversation_id = ? ORDER BY created_at ASC"
        )
        params: tuple = (conversation_id,)
        if limit:
            query += " LIMIT ?"
            params = (conversation_id, limit)
            # Get last N messages
            query = (
                "SELECT * FROM ("
                "  SELECT id, role, content, tool_calls, tool_call_id, created_at "
                "  FROM messages WHERE conversation_id = ? "
                "  ORDER BY created_at DESC LIMIT ?"
                ") sub ORDER BY created_at ASC"
            )

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "role": r[1],
                "content": r[2],
                "tool_calls": json.loads(r[3]) if r[3] else None,
                "tool_call_id": r[4],
                "created_at": r[5],
            }
            for r in rows
        ]

    # -- Facts (persistent memory) --

    async def store_fact(self, category: str, content: str, source: str | None = None) -> int:
        assert self._db
        now = time.time()
        cursor = await self._db.execute(
            "INSERT INTO facts (category, content, source, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (category, content, source, now, now),
        )
        await self._db.commit()
        return cursor.lastrowid  # type: ignore

    async def get_facts(self, category: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        assert self._db
        if category:
            cursor = await self._db.execute(
                "SELECT id, category, content, source, created_at FROM facts "
                "WHERE category = ? ORDER BY updated_at DESC LIMIT ?",
                (category, limit),
            )
        else:
            cursor = await self._db.execute(
                "SELECT id, category, content, source, created_at FROM facts "
                "ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "category": r[1],
                "content": r[2],
                "source": r[3],
                "created_at": r[4],
            }
            for r in rows
        ]

    async def delete_fact(self, fact_id: int) -> None:
        assert self._db
        await self._db.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        await self._db.commit()
