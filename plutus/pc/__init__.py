"""Plutus PC Control — three-layer computer interaction.

Architecture (matching OpenClaw's proven approach):
  Layer 1: OS Control (shell commands — most reliable)
  Layer 2: Browser Control (Playwright/CDP — for web interaction)
  Layer 3: Desktop Control (PyAutoGUI — fallback for native apps)

The OSControl is the PRIMARY interface for opening apps, running commands,
and managing processes via native OS commands.

The BrowserControl handles all web interaction via Playwright/CDP with
DOM element references (not pixel coordinates).

Desktop control (mouse, keyboard, screen) is a fallback for native apps.
"""

from plutus.pc.os_control import OSControl
from plutus.pc.browser_control import BrowserControl
from plutus.pc.mouse import MouseController
from plutus.pc.keyboard import KeyboardController
from plutus.pc.screen import ScreenReader
from plutus.pc.windows import WindowManager
from plutus.pc.workflow import WorkflowEngine
from plutus.pc.context import ContextEngine, ActionGuard, get_context_engine
from plutus.pc.computer_use import ComputerUseExecutor

__all__ = [
    "OSControl",
    "BrowserControl",
    "ComputerUseExecutor",
    "MouseController",
    "KeyboardController",
    "ScreenReader",
    "WindowManager",
    "WorkflowEngine",
    "ContextEngine",
    "ActionGuard",
    "get_context_engine",
]
