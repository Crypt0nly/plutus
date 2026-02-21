"""Plutus PC Control — deep OS integration for seamless machine interaction.

This package provides the "friendly ghost" layer: smooth mouse movement,
natural typing, intelligent screen reading, window orchestration, context
awareness, and workflow automation across Windows, macOS, and Linux.

The ContextEngine is the brain — it always knows which app/window is active
and prevents the agent from acting on the wrong window.
"""

from plutus.pc.mouse import MouseController
from plutus.pc.keyboard import KeyboardController
from plutus.pc.screen import ScreenReader
from plutus.pc.windows import WindowManager
from plutus.pc.workflow import WorkflowEngine
from plutus.pc.context import ContextEngine, ActionGuard, get_context_engine

__all__ = [
    "MouseController",
    "KeyboardController",
    "ScreenReader",
    "WindowManager",
    "WorkflowEngine",
    "ContextEngine",
    "ActionGuard",
    "get_context_engine",
]
