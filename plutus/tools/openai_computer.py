"""OpenAI Computer Use Tool — delegate desktop tasks to GPT-5.4.

This tool allows the Coordinator (regardless of its own provider) to spawn
a GPT-5.4 computer use session for autonomous desktop control. It acts as a
bridge: the Coordinator describes what needs to be done, and GPT-5.4 drives
the desktop via screenshots and actions.

The tool respects the guardrails system — in autonomous mode it runs without
approval; in lower tiers the guardrail engine will prompt the user first.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from plutus.config import SecretsStore
from plutus.tools.base import Tool

logger = logging.getLogger("plutus.tools.openai_computer")


class OpenAIComputerTool(Tool):
    """Delegate desktop tasks to GPT-5.4's native computer use capability."""

    def __init__(self, secrets: SecretsStore | None = None):
        self._secrets = secrets or SecretsStore()

    @property
    def name(self) -> str:
        return "openai_computer"

    @property
    def description(self) -> str:
        return (
            "Delegate a desktop task to OpenAI GPT-5.4's native computer use.\n\n"
            "GPT-5.4 can see the screen and autonomously click, type, scroll, "
            "and navigate to complete tasks. Use this when you need fast, "
            "vision-based desktop automation.\n\n"
            "The task runs as an autonomous loop: GPT-5.4 takes screenshots, "
            "decides what to do, executes actions, and repeats until done.\n\n"
            "Examples:\n"
            "  openai_computer(task='Open Chrome and search for Python tutorials')\n"
            "  openai_computer(task='Fill out the form with name John Doe')\n"
            "  openai_computer(task='Take a screenshot of the current desktop')\n\n"
            "Requirements: OpenAI API key must be configured in Settings."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "The desktop task for GPT-5.4 to complete. "
                        "Be specific about what you want done."
                    ),
                },
                "max_iterations": {
                    "type": "integer",
                    "description": (
                        "Maximum action-screenshot loops (default 50). "
                        "Lower for simple tasks, higher for complex ones."
                    ),
                    "default": 50,
                },
            },
            "required": ["task"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        task = kwargs.get("task", "")
        if not task:
            return "[ERROR] 'task' is required."

        max_iterations = min(int(kwargs.get("max_iterations", 50)), 100)

        # Check for OpenAI API key
        api_key = self._secrets.get_key("openai")
        if not api_key:
            return json.dumps({
                "success": False,
                "error": "OpenAI API key not configured. "
                         "Add it in Settings → API Key (select OpenAI provider).",
            })

        try:
            from plutus.core.openai_computer_use import OpenAIComputerUseAgent
        except ImportError:
            return json.dumps({
                "success": False,
                "error": "Failed to import OpenAI computer use agent.",
            })

        agent = OpenAIComputerUseAgent(
            api_key=api_key,
            model="gpt-5.4",
            max_iterations=max_iterations,
        )

        # Collect events as the agent runs
        events: list[dict[str, Any]] = []
        final_text_parts: list[str] = []
        iterations_used = 0

        async for event in agent.run_task(task):
            events.append(event.to_dict())

            if event.type == "text":
                final_text_parts.append(event.data.get("content", ""))
            elif event.type == "iteration":
                iterations_used = event.data.get("number", 0)
            elif event.type == "error":
                return json.dumps({
                    "success": False,
                    "error": event.data.get("message", "Unknown error"),
                    "iterations": iterations_used,
                })
            elif event.type == "cancelled":
                return json.dumps({
                    "success": False,
                    "error": "Task cancelled",
                    "iterations": iterations_used,
                })

        return json.dumps({
            "success": True,
            "task": task,
            "result": "\n".join(final_text_parts) if final_text_parts else "Task completed.",
            "iterations": iterations_used,
            "model": "gpt-5.4",
        }, indent=2)
