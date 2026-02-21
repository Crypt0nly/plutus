"""Memory tool — lets the agent explicitly save and recall persistent information.

This gives the agent a way to proactively store important information that
should survive context window boundaries. The agent can:
  - Save facts, decisions, and progress notes
  - Recall facts by category or search
  - Set and track goals
  - Create checkpoints of current state
"""

from __future__ import annotations

import json
import logging
from typing import Any

from plutus.tools.base import Tool

logger = logging.getLogger("plutus.tools.memory")


class MemoryTool(Tool):
    """Tool for persistent memory operations."""

    name = "memory"
    description = (
        "Save and recall persistent information across conversation boundaries. "
        "Use this to remember important facts, track goals, and create checkpoints. "
        "Information saved here survives even when the conversation gets very long."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "save_fact",
                    "recall_facts",
                    "search_facts",
                    "delete_fact",
                    "add_goal",
                    "list_goals",
                    "complete_goal",
                    "fail_goal",
                    "checkpoint",
                    "get_checkpoint",
                    "stats",
                ],
                "description": "The memory action to perform.",
            },
            "category": {
                "type": "string",
                "description": (
                    "Category for the fact. Suggested categories: "
                    "'user_preference', 'technical', 'decision', 'progress', "
                    "'file_path', 'credential', 'environment', 'task_context'."
                ),
            },
            "content": {
                "type": "string",
                "description": "The content to save (for save_fact) or search query (for search_facts).",
            },
            "goal_description": {
                "type": "string",
                "description": "Description of the goal (for add_goal).",
            },
            "goal_id": {
                "type": "integer",
                "description": "ID of the goal to update (for complete_goal, fail_goal).",
            },
            "fact_id": {
                "type": "integer",
                "description": "ID of the fact to delete (for delete_fact).",
            },
            "checkpoint_data": {
                "type": "object",
                "description": (
                    "State data to save in a checkpoint. Should include: "
                    "what you were doing, what's done, what's next."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return.",
                "default": 10,
            },
        },
        "required": ["action"],
    }

    def __init__(self, memory_store: Any, conversation_manager: Any = None):
        self._memory = memory_store
        self._conversation = conversation_manager

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "stats")

        try:
            if action == "save_fact":
                return await self._save_fact(kwargs)
            elif action == "recall_facts":
                return await self._recall_facts(kwargs)
            elif action == "search_facts":
                return await self._search_facts(kwargs)
            elif action == "delete_fact":
                return await self._delete_fact(kwargs)
            elif action == "add_goal":
                return await self._add_goal(kwargs)
            elif action == "list_goals":
                return await self._list_goals(kwargs)
            elif action == "complete_goal":
                return await self._update_goal(kwargs, "completed")
            elif action == "fail_goal":
                return await self._update_goal(kwargs, "failed")
            elif action == "checkpoint":
                return await self._save_checkpoint(kwargs)
            elif action == "get_checkpoint":
                return await self._get_checkpoint(kwargs)
            elif action == "stats":
                return await self._get_stats()
            else:
                return f"[ERROR] Unknown memory action: {action}"
        except Exception as e:
            logger.error(f"Memory tool error: {e}", exc_info=True)
            return f"[ERROR] Memory operation failed: {e}"

    async def _save_fact(self, kwargs: dict) -> str:
        category = kwargs.get("category", "general")
        content = kwargs.get("content", "")
        if not content:
            return "[ERROR] Content is required for save_fact."

        fact_id = await self._memory.store_fact(
            category=category,
            content=content,
            source="agent",
        )
        return json.dumps({
            "saved": True,
            "fact_id": fact_id,
            "category": category,
            "message": f"Fact saved to persistent memory (id={fact_id}).",
        })

    async def _recall_facts(self, kwargs: dict) -> str:
        category = kwargs.get("category")
        limit = kwargs.get("limit", 10)
        facts = await self._memory.get_facts(category=category, limit=limit)

        if not facts:
            return json.dumps({"facts": [], "message": "No facts found."})

        return json.dumps({
            "facts": facts,
            "count": len(facts),
        })

    async def _search_facts(self, kwargs: dict) -> str:
        query = kwargs.get("content", "")
        if not query:
            return "[ERROR] Content (search query) is required for search_facts."

        limit = kwargs.get("limit", 10)
        facts = await self._memory.search_facts(query=query, limit=limit)

        return json.dumps({
            "facts": facts,
            "count": len(facts),
            "query": query,
        })

    async def _delete_fact(self, kwargs: dict) -> str:
        fact_id = kwargs.get("fact_id")
        if fact_id is None:
            return "[ERROR] fact_id is required for delete_fact."

        await self._memory.delete_fact(fact_id)
        return json.dumps({"deleted": True, "fact_id": fact_id})

    async def _add_goal(self, kwargs: dict) -> str:
        description = kwargs.get("goal_description", "")
        if not description:
            return "[ERROR] goal_description is required for add_goal."

        conv_id = None
        if self._conversation:
            conv_id = self._conversation.conversation_id

        goal_id = await self._memory.add_goal(
            description=description,
            conversation_id=conv_id,
        )
        return json.dumps({
            "created": True,
            "goal_id": goal_id,
            "description": description,
            "message": f"Goal tracked (id={goal_id}).",
        })

    async def _list_goals(self, kwargs: dict) -> str:
        conv_id = None
        if self._conversation:
            conv_id = self._conversation.conversation_id

        limit = kwargs.get("limit", 20)
        goals = await self._memory.get_active_goals(
            conversation_id=conv_id, limit=limit
        )

        return json.dumps({
            "goals": goals,
            "count": len(goals),
        })

    async def _update_goal(self, kwargs: dict, status: str) -> str:
        goal_id = kwargs.get("goal_id")
        if goal_id is None:
            return f"[ERROR] goal_id is required for {status} goal."

        await self._memory.update_goal_status(goal_id, status)
        return json.dumps({
            "updated": True,
            "goal_id": goal_id,
            "status": status,
        })

    async def _save_checkpoint(self, kwargs: dict) -> str:
        conv_id = None
        if self._conversation:
            conv_id = self._conversation.conversation_id

        if not conv_id:
            return "[ERROR] No active conversation for checkpoint."

        checkpoint_data = kwargs.get("checkpoint_data", {})
        if not checkpoint_data:
            return "[ERROR] checkpoint_data is required."

        cp_id = await self._memory.save_checkpoint(
            conversation_id=conv_id,
            state_data=checkpoint_data,
            checkpoint_type="manual",
        )
        return json.dumps({
            "saved": True,
            "checkpoint_id": cp_id,
            "message": "Checkpoint saved to persistent memory.",
        })

    async def _get_checkpoint(self, kwargs: dict) -> str:
        conv_id = None
        if self._conversation:
            conv_id = self._conversation.conversation_id

        if not conv_id:
            return "[ERROR] No active conversation."

        checkpoint = await self._memory.get_latest_checkpoint(conv_id)
        if not checkpoint:
            return json.dumps({"checkpoint": None, "message": "No checkpoints found."})

        return json.dumps({
            "checkpoint": checkpoint,
        })

    async def _get_stats(self) -> str:
        stats = await self._memory.get_memory_stats()
        return json.dumps(stats)
