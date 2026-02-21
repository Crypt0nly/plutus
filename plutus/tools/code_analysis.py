"""Code Analysis Tool — provides AST-based code analysis capabilities.

This tool allows the agent to deeply understand code structure:
  - Parse and analyze Python files
  - Find functions, classes, imports
  - Calculate complexity metrics
  - Build call graphs
  - Search for patterns and TODOs

All analysis runs in a subprocess for isolation.
"""

from __future__ import annotations

import json
from typing import Any

from plutus.core.subprocess_manager import SubprocessManager, SubprocessTask
from plutus.tools.base import Tool


class CodeAnalysisTool(Tool):
    """Analyze code structure, complexity, and dependencies."""

    def __init__(self, subprocess_manager: SubprocessManager | None = None):
        self._manager = subprocess_manager or SubprocessManager()

    @property
    def name(self) -> str:
        return "code_analysis"

    @property
    def description(self) -> str:
        return (
            "Analyze Python code files — extract functions, classes, imports, "
            "calculate complexity, build call graphs, find TODOs, and generate summaries. "
            "All analysis is AST-based for accuracy."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "analyze",
                        "find_functions",
                        "find_classes",
                        "find_imports",
                        "find_todos",
                        "complexity",
                        "symbols",
                        "call_graph",
                        "summarize",
                    ],
                    "description": (
                        "The analysis operation:\n"
                        "- analyze: Full analysis (functions, classes, imports, complexity, etc.)\n"
                        "- find_functions: List all function/method definitions\n"
                        "- find_classes: List all class definitions\n"
                        "- find_imports: Extract all import statements\n"
                        "- find_todos: Find TODO/FIXME/HACK comments\n"
                        "- complexity: Calculate cyclomatic complexity per function\n"
                        "- symbols: Extract all top-level symbols\n"
                        "- call_graph: Build function call graph\n"
                        "- summarize: Generate human-readable summary"
                    ),
                },
                "path": {
                    "type": "string",
                    "description": "Path to the Python file to analyze.",
                },
            },
            "required": ["operation", "path"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        operation = kwargs.get("operation", "analyze")
        path = kwargs.get("path", "")

        if not path:
            return "[ERROR] No file path provided."

        task = SubprocessTask(
            worker_type="code_analysis",
            command={"action": operation, "path": path},
            timeout=30.0,
        )

        result = await self._manager.spawn(task)

        if result.error:
            return f"[ERROR] {result.error}"

        return json.dumps(result.output, indent=2)
