"""Persistent memory store backed by SQLite.

Stores conversation history, learned facts, conversation summaries,
goals, and memory checkpoints. This is the foundation of Plutus's
"never forget" system — all persistent state lives here.
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
    metadata TEXT DEFAULT '{}',
    last_activity REAL
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

CREATE TABLE IF NOT EXISTS conversation_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL UNIQUE,
    summary_data TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    priority INTEGER NOT NULL DEFAULT 0,
    parent_goal_id INTEGER,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    FOREIGN KEY (parent_goal_id) REFERENCES goals(id)
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    checkpoint_type TEXT NOT NULL DEFAULT 'auto',
    state_data TEXT NOT NULL DEFAULT '{}',
    message_id INTEGER,
    created_at REAL NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
CREATE INDEX IF NOT EXISTS idx_summaries_conversation ON conversation_summaries(conversation_id);
CREATE INDEX IF NOT EXISTS idx_goals_conversation ON goals(conversation_id);
CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);
CREATE INDEX IF NOT EXISTS idx_checkpoints_conversation ON checkpoints(conversation_id);
"""


class MemoryStore:
    """Async SQLite-backed memory store with summarization and goal support."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript(_SCHEMA)
        await self._db.commit()
        # Migrate: add last_activity column if missing (for existing databases)
        await self._migrate_last_activity()
        # Create index after migration ensures column exists
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_last_activity ON conversations(last_activity)"
        )
        await self._db.commit()

    async def _migrate_last_activity(self) -> None:
        """Add last_activity column to conversations table if it doesn't exist."""
        assert self._db
        try:
            cursor = await self._db.execute("PRAGMA table_info(conversations)")
            columns = [row[1] for row in await cursor.fetchall()]
            if "last_activity" not in columns:
                await self._db.execute(
                    "ALTER TABLE conversations ADD COLUMN last_activity REAL"
                )
                # Backfill: set last_activity to the latest message time or created_at
                await self._db.execute(
                    "UPDATE conversations SET last_activity = "
                    "COALESCE((SELECT MAX(created_at) FROM messages WHERE conversation_id = conversations.id), created_at)"
                )
                await self._db.commit()
        except Exception:
            pass  # Column already exists or other non-critical error

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    # -- Conversations --

    async def create_conversation(self, conv_id: str, title: str | None = None) -> None:
        assert self._db
        now = time.time()
        await self._db.execute(
            "INSERT INTO conversations (id, created_at, title, last_activity) VALUES (?, ?, ?, ?)",
            (conv_id, now, title, now),
        )
        await self._db.commit()

    async def list_conversations(self, limit: int = 50) -> list[dict[str, Any]]:
        assert self._db
        cursor = await self._db.execute(
            "SELECT c.id, c.created_at, c.title, c.metadata, c.last_activity, "
            "(SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) as msg_count "
            "FROM conversations c "
            "ORDER BY COALESCE(c.last_activity, c.created_at) DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "created_at": r[1],
                "title": r[2],
                "metadata": json.loads(r[3]) if r[3] else {},
                "last_activity": r[4] or r[1],
                "message_count": r[5],
            }
            for r in rows
        ]

    async def rename_conversation(self, conv_id: str, title: str) -> None:
        """Rename a conversation."""
        assert self._db
        await self._db.execute(
            "UPDATE conversations SET title = ? WHERE id = ?",
            (title, conv_id),
        )
        await self._db.commit()

    async def touch_conversation(self, conv_id: str) -> None:
        """Update last_activity timestamp for a conversation."""
        assert self._db
        await self._db.execute(
            "UPDATE conversations SET last_activity = ? WHERE id = ?",
            (time.time(), conv_id),
        )
        await self._db.commit()

    async def delete_conversation(self, conv_id: str) -> None:
        assert self._db
        await self._db.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
        await self._db.execute("DELETE FROM conversation_summaries WHERE conversation_id = ?", (conv_id,))
        await self._db.execute("DELETE FROM goals WHERE conversation_id = ?", (conv_id,))
        await self._db.execute("DELETE FROM checkpoints WHERE conversation_id = ?", (conv_id,))
        await self._db.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        await self._db.commit()

    async def cleanup_stale_conversations(self, max_age_days: int = 30) -> int:
        """Delete conversations with no activity for more than max_age_days.

        Returns the number of conversations deleted.
        """
        assert self._db
        cutoff = time.time() - (max_age_days * 86400)

        # Find stale conversations
        cursor = await self._db.execute(
            "SELECT id FROM conversations WHERE COALESCE(last_activity, created_at) < ?",
            (cutoff,),
        )
        stale_ids = [r[0] for r in await cursor.fetchall()]

        if not stale_ids:
            return 0

        # Delete all related data for each stale conversation
        placeholders = ",".join("?" for _ in stale_ids)
        await self._db.execute(
            f"DELETE FROM messages WHERE conversation_id IN ({placeholders})",
            stale_ids,
        )
        await self._db.execute(
            f"DELETE FROM conversation_summaries WHERE conversation_id IN ({placeholders})",
            stale_ids,
        )
        await self._db.execute(
            f"DELETE FROM goals WHERE conversation_id IN ({placeholders})",
            stale_ids,
        )
        await self._db.execute(
            f"DELETE FROM checkpoints WHERE conversation_id IN ({placeholders})",
            stale_ids,
        )
        await self._db.execute(
            f"DELETE FROM conversations WHERE id IN ({placeholders})",
            stale_ids,
        )
        await self._db.commit()
        return len(stale_ids)

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
        now = time.time()
        cursor = await self._db.execute(
            "INSERT INTO messages (conversation_id, role, content, tool_calls, tool_call_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                conversation_id,
                role,
                content,
                json.dumps(tool_calls) if tool_calls else None,
                tool_call_id,
                now,
            ),
        )
        # Update last_activity on the conversation
        await self._db.execute(
            "UPDATE conversations SET last_activity = ? WHERE id = ?",
            (now, conversation_id),
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
            query = (
                "SELECT * FROM ("
                "  SELECT id, role, content, tool_calls, tool_call_id, created_at "
                "  FROM messages WHERE conversation_id = ? "
                "  ORDER BY created_at DESC LIMIT ?"
                ") sub ORDER BY created_at ASC"
            )
            params = (conversation_id, limit)

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        results = []
        for r in rows:
            tool_calls = None
            if r[3]:
                try:
                    tool_calls = json.loads(r[3])
                except (json.JSONDecodeError, ValueError):
                    logger.warning(f"Corrupt tool_calls JSON in message {r[0]}, skipping")
            results.append({
                "id": r[0],
                "role": r[1],
                "content": r[2],
                "tool_calls": tool_calls,
                "tool_call_id": r[4],
                "created_at": r[5],
            })
        return results

    async def get_message_count(self, conversation_id: str) -> int:
        """Get the total number of messages in a conversation."""
        assert self._db
        cursor = await self._db.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    # -- Facts (persistent memory) --

    async def store_fact(self, category: str, content: str, source: str | None = None) -> int:
        assert self._db
        now = time.time()

        # Check for duplicate facts (same category + content)
        cursor = await self._db.execute(
            "SELECT id FROM facts WHERE category = ? AND content = ?",
            (category, content),
        )
        existing = await cursor.fetchone()
        if existing:
            # Update the timestamp
            await self._db.execute(
                "UPDATE facts SET updated_at = ? WHERE id = ?",
                (now, existing[0]),
            )
            await self._db.commit()
            return existing[0]

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

    async def search_facts(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search facts by content (simple LIKE query)."""
        assert self._db
        cursor = await self._db.execute(
            "SELECT id, category, content, source, created_at FROM facts "
            "WHERE content LIKE ? ORDER BY updated_at DESC LIMIT ?",
            (f"%{query}%", limit),
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

    # -- Conversation Summaries --

    async def save_conversation_summary(
        self, conversation_id: str, summary_data: dict[str, Any]
    ) -> None:
        """Save or update a conversation summary."""
        assert self._db
        now = time.time()
        summary_json = json.dumps(summary_data)

        # Upsert
        await self._db.execute(
            """INSERT INTO conversation_summaries (conversation_id, summary_data, created_at, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(conversation_id) DO UPDATE SET
                 summary_data = excluded.summary_data,
                 updated_at = excluded.updated_at""",
            (conversation_id, summary_json, now, now),
        )
        await self._db.commit()

    async def get_conversation_summary(
        self, conversation_id: str
    ) -> dict[str, Any] | None:
        """Get the summary for a conversation."""
        assert self._db
        cursor = await self._db.execute(
            "SELECT summary_data FROM conversation_summaries WHERE conversation_id = ?",
            (conversation_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return json.loads(row[0])

    # -- Goals --

    async def add_goal(
        self,
        description: str,
        conversation_id: str | None = None,
        priority: int = 0,
        parent_goal_id: int | None = None,
    ) -> int:
        """Add a new goal."""
        assert self._db
        now = time.time()
        cursor = await self._db.execute(
            "INSERT INTO goals (conversation_id, description, status, priority, parent_goal_id, created_at, updated_at) "
            "VALUES (?, ?, 'active', ?, ?, ?, ?)",
            (conversation_id, description, priority, parent_goal_id, now, now),
        )
        await self._db.commit()
        return cursor.lastrowid  # type: ignore

    async def get_active_goals(
        self, conversation_id: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Get active goals, optionally scoped to a conversation."""
        assert self._db
        if conversation_id:
            cursor = await self._db.execute(
                "SELECT id, conversation_id, description, status, priority, parent_goal_id, created_at "
                "FROM goals WHERE status = 'active' AND conversation_id = ? "
                "ORDER BY priority DESC, created_at ASC LIMIT ?",
                (conversation_id, limit),
            )
        else:
            cursor = await self._db.execute(
                "SELECT id, conversation_id, description, status, priority, parent_goal_id, created_at "
                "FROM goals WHERE status = 'active' "
                "ORDER BY priority DESC, created_at ASC LIMIT ?",
                (limit,),
            )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "conversation_id": r[1],
                "description": r[2],
                "status": r[3],
                "priority": r[4],
                "parent_goal_id": r[5],
                "created_at": r[6],
            }
            for r in rows
        ]

    async def update_goal_status(self, goal_id: int, status: str) -> None:
        """Update a goal's status (active, completed, failed, cancelled)."""
        assert self._db
        await self._db.execute(
            "UPDATE goals SET status = ?, updated_at = ? WHERE id = ?",
            (status, time.time(), goal_id),
        )
        await self._db.commit()

    async def get_all_goals(
        self, conversation_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get all goals regardless of status."""
        assert self._db
        if conversation_id:
            cursor = await self._db.execute(
                "SELECT id, conversation_id, description, status, priority, parent_goal_id, created_at "
                "FROM goals WHERE conversation_id = ? ORDER BY created_at DESC LIMIT ?",
                (conversation_id, limit),
            )
        else:
            cursor = await self._db.execute(
                "SELECT id, conversation_id, description, status, priority, parent_goal_id, created_at "
                "FROM goals ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "conversation_id": r[1],
                "description": r[2],
                "status": r[3],
                "priority": r[4],
                "parent_goal_id": r[5],
                "created_at": r[6],
            }
            for r in rows
        ]

    # -- Checkpoints --

    async def save_checkpoint(
        self,
        conversation_id: str,
        state_data: dict[str, Any],
        checkpoint_type: str = "auto",
        message_id: int | None = None,
    ) -> int:
        """Save a checkpoint of the current state."""
        assert self._db
        cursor = await self._db.execute(
            "INSERT INTO checkpoints (conversation_id, checkpoint_type, state_data, message_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (conversation_id, checkpoint_type, json.dumps(state_data), message_id, time.time()),
        )
        await self._db.commit()
        return cursor.lastrowid  # type: ignore

    async def get_latest_checkpoint(
        self, conversation_id: str
    ) -> dict[str, Any] | None:
        """Get the most recent checkpoint for a conversation."""
        assert self._db
        cursor = await self._db.execute(
            "SELECT id, checkpoint_type, state_data, message_id, created_at "
            "FROM checkpoints WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 1",
            (conversation_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "checkpoint_type": row[1],
            "state_data": json.loads(row[2]),
            "message_id": row[3],
            "created_at": row[4],
        }

    async def list_checkpoints(
        self, conversation_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """List checkpoints for a conversation."""
        assert self._db
        cursor = await self._db.execute(
            "SELECT id, checkpoint_type, state_data, message_id, created_at "
            "FROM checkpoints WHERE conversation_id = ? ORDER BY created_at DESC LIMIT ?",
            (conversation_id, limit),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "checkpoint_type": r[1],
                "state_data": json.loads(r[2]),
                "message_id": r[3],
                "created_at": r[4],
            }
            for r in rows
        ]

    # -- Memory stats --

    async def get_memory_stats(self) -> dict[str, Any]:
        """Get overall memory statistics."""
        assert self._db

        conv_count = await self._db.execute("SELECT COUNT(*) FROM conversations")
        msg_count = await self._db.execute("SELECT COUNT(*) FROM messages")
        fact_count = await self._db.execute("SELECT COUNT(*) FROM facts")
        goal_count = await self._db.execute("SELECT COUNT(*) FROM goals WHERE status = 'active'")
        summary_count = await self._db.execute("SELECT COUNT(*) FROM conversation_summaries")
        checkpoint_count = await self._db.execute("SELECT COUNT(*) FROM checkpoints")

        return {
            "conversations": (await conv_count.fetchone())[0],
            "messages": (await msg_count.fetchone())[0],
            "facts": (await fact_count.fetchone())[0],
            "active_goals": (await goal_count.fetchone())[0],
            "summaries": (await summary_count.fetchone())[0],
            "checkpoints": (await checkpoint_count.fetchone())[0],
        }
