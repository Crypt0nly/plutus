"""Plutus PC Control — four-layer computer interaction.

Architecture (matching OpenClaw's proven approach):
  Layer 1: OS Control (shell commands — most reliable)
  Layer 2: Browser Control (Playwright accessibility tree — for web interaction)
  Layer 2.5: Desktop UIA (pywinauto accessibility tree — for native Windows apps)
  Layer 3: Desktop Fallback (PyAutoGUI — last resort for native apps)

The OSControl is the PRIMARY interface for opening apps, running commands,
and managing processes via native OS commands.

The BrowserControl handles all web interaction via Playwright with
accessibility tree snapshots and ref-based interaction.

The DesktopControl handles native Windows app interaction via pywinauto
with UIA accessibility tree snapshots and ref-based interaction.

Desktop fallback (mouse, keyboard, screen) is a last resort.
"""

from plutus.pc.os_control import OSControl
from plutus.pc.browser_control import BrowserControl
from plutus.pc.desktop_control import DesktopControl
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
    "DesktopControl",
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
