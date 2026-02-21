"""Plutus PC Control — deep OS integration for seamless machine interaction.

This package provides the "friendly ghost" layer: smooth mouse movement,
natural typing, intelligent screen reading, window orchestration, and
workflow automation across Windows, macOS, and Linux.
"""

from plutus.pc.mouse import MouseController
from plutus.pc.keyboard import KeyboardController
from plutus.pc.screen import ScreenReader
from plutus.pc.windows import WindowManager
from plutus.pc.workflow import WorkflowEngine

__all__ = [
    "MouseController",
    "KeyboardController",
    "ScreenReader",
    "WindowManager",
    "WorkflowEngine",
]
