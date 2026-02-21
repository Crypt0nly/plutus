"""Context Awareness Engine — always knows where Plutus is.

This module solves the #1 problem with computer-use agents: acting on the wrong
window. Before every action, Plutus checks:
  1. Which window is currently active (title, app, PID)
  2. Whether that matches the intended target
  3. If not, it auto-focuses the correct window first

The context is also injected into every tool result so the LLM always knows
exactly what app/window it's looking at.

Architecture:
  ContextState  — snapshot of the current desktop state
  ContextEngine — singleton that tracks state and provides guards
  ActionGuard   — wraps every pc action with pre/post context checks
"""

from __future__ import annotations

import asyncio
import json
import logging
import platform
import re
import time
from dataclasses import dataclass, field
from typing import Any

SYSTEM = platform.system()
logger = logging.getLogger("plutus.pc.context")


# ─────────────────────────────────────────────────────────────
# Context State — a snapshot of what's happening on the desktop
# ─────────────────────────────────────────────────────────────

@dataclass
class ContextState:
    """Snapshot of the current desktop context."""

    # Active window info
    active_window_title: str = ""
    active_app_name: str = ""
    active_window_pid: int = 0

    # Derived context
    active_app_category: str = ""  # browser, editor, terminal, messenger, etc.
    active_browser_tab: str = ""   # if in a browser, what tab/URL
    active_document: str = ""      # if in an editor, what file

    # Screen state
    screen_width: int = 0
    screen_height: int = 0
    mouse_x: int = 0
    mouse_y: int = 0

    # Timestamps
    captured_at: float = 0.0
    age_seconds: float = 0.0

    # Confidence
    is_stale: bool = False  # True if context is older than threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_window": {
                "title": self.active_window_title,
                "app": self.active_app_name,
                "pid": self.active_window_pid,
                "category": self.active_app_category,
            },
            "browser_tab": self.active_browser_tab or None,
            "active_document": self.active_document or None,
            "screen": {
                "width": self.screen_width,
                "height": self.screen_height,
            },
            "mouse": {"x": self.mouse_x, "y": self.mouse_y},
            "captured_at": self.captured_at,
            "is_stale": self.is_stale,
        }

    def summary(self) -> str:
        """Human-readable one-line summary for injecting into LLM context."""
        parts = []
        if self.active_app_name:
            parts.append(f"Active app: {self.active_app_name}")
        if self.active_window_title:
            title = self.active_window_title
            if len(title) > 80:
                title = title[:77] + "..."
            parts.append(f"Window: \"{title}\"")
        if self.active_app_category:
            parts.append(f"Category: {self.active_app_category}")
        if self.active_browser_tab:
            parts.append(f"Tab: {self.active_browser_tab}")
        if self.active_document:
            parts.append(f"Document: {self.active_document}")
        return " | ".join(parts) if parts else "No active window detected"


# ─────────────────────────────────────────────────────────────
# App Category Detection — classify what kind of app is active
# ─────────────────────────────────────────────────────────────

# Map of known apps to categories
APP_CATEGORIES: dict[str, str] = {
    # Browsers
    "chrome": "browser", "firefox": "browser", "edge": "browser",
    "msedge": "browser", "safari": "browser", "brave": "browser",
    "opera": "browser", "vivaldi": "browser", "arc": "browser",
    # Messengers
    "whatsapp": "messenger", "telegram": "messenger", "signal": "messenger",
    "discord": "messenger", "slack": "messenger", "teams": "messenger",
    "skype": "messenger", "messenger": "messenger", "wechat": "messenger",
    "viber": "messenger", "line": "messenger", "imessage": "messenger",
    # Editors / IDEs
    "code": "editor", "vscode": "editor", "visual studio code": "editor",
    "sublime": "editor", "atom": "editor", "notepad": "editor",
    "notepad++": "editor", "vim": "editor", "neovim": "editor",
    "emacs": "editor", "pycharm": "editor", "intellij": "editor",
    "webstorm": "editor", "cursor": "editor",
    # Terminals
    "terminal": "terminal", "iterm": "terminal", "iterm2": "terminal",
    "cmd": "terminal", "powershell": "terminal", "windowsterminal": "terminal",
    "windows terminal": "terminal", "wt": "terminal", "alacritty": "terminal",
    "kitty": "terminal", "hyper": "terminal", "warp": "terminal",
    "gnome-terminal": "terminal", "konsole": "terminal",
    # Office
    "word": "office", "winword": "office", "excel": "office",
    "powerpoint": "office", "powerpnt": "office", "onenote": "office",
    "outlook": "office", "libreoffice": "office", "pages": "office",
    "numbers": "office", "keynote": "office", "google docs": "office",
    # File managers
    "explorer": "file_manager", "finder": "file_manager",
    "nautilus": "file_manager", "dolphin": "file_manager",
    "thunar": "file_manager", "nemo": "file_manager",
    # Media
    "spotify": "media", "vlc": "media", "itunes": "media",
    "music": "media", "photos": "media", "preview": "media",
    # AI / Chat
    "chatgpt": "ai_chat", "claude": "ai_chat", "copilot": "ai_chat",
    "bard": "ai_chat", "perplexity": "ai_chat",
    # System
    "settings": "system", "systempreferences": "system",
    "control panel": "system", "task manager": "system",
    "activity monitor": "system",
}

# Patterns for detecting browser tab content from window titles
BROWSER_TITLE_PATTERNS = [
    # "Page Title - Google Chrome"
    re.compile(r'^(.+?)\s*[-–—]\s*(?:Google Chrome|Mozilla Firefox|Microsoft Edge|Safari|Brave|Opera|Vivaldi|Arc)$', re.I),
    # "Page Title — Browser"
    re.compile(r'^(.+?)\s*[-–—]\s*\w+\s*Browser$', re.I),
]

# Patterns for detecting document names from editor titles
EDITOR_TITLE_PATTERNS = [
    # "file.py - Visual Studio Code"
    re.compile(r'^(.+?\.[\w]+)\s*[-–—]', re.I),
    # "file.py — Sublime Text"
    re.compile(r'^(.+?\.[\w]+)\s', re.I),
]

# Patterns for detecting messenger context from window titles
MESSENGER_TITLE_PATTERNS = [
    # "Contact Name - WhatsApp"
    re.compile(r'^(.+?)\s*[-–—]\s*(?:WhatsApp|Telegram|Signal|Discord|Slack|Teams)', re.I),
    # "Chat with Contact"
    re.compile(r'^(?:Chat with|Conversation with)\s+(.+)', re.I),
]


def classify_app(app_name: str, window_title: str = "") -> dict[str, str]:
    """Classify an app and extract context from its window title.

    Returns:
        {
            "category": "browser" | "messenger" | "editor" | etc.,
            "browser_tab": "..." (if browser),
            "document": "..." (if editor),
            "chat_context": "..." (if messenger),
        }
    """
    result: dict[str, str] = {"category": "", "browser_tab": "", "document": "", "chat_context": ""}

    app_lower = app_name.lower().strip()
    title_lower = window_title.lower().strip()

    # Direct app name match
    for key, category in APP_CATEGORIES.items():
        if key in app_lower:
            result["category"] = category
            break

    # If not found by app name, try window title
    if not result["category"]:
        for key, category in APP_CATEGORIES.items():
            if key in title_lower:
                result["category"] = category
                break

    # Extract browser tab from title
    if result["category"] == "browser":
        for pattern in BROWSER_TITLE_PATTERNS:
            match = pattern.match(window_title)
            if match:
                result["browser_tab"] = match.group(1).strip()
                break
        # Check if browser is showing a known web app
        if any(x in title_lower for x in ["chatgpt", "claude.ai", "bard.google"]):
            result["category"] = "ai_chat"
            result["browser_tab"] = window_title.split(" - ")[0].strip() if " - " in window_title else window_title
        elif any(x in title_lower for x in ["web.whatsapp", "web.telegram", "discord.com/channels"]):
            result["category"] = "messenger"
            result["browser_tab"] = window_title.split(" - ")[0].strip() if " - " in window_title else window_title

    # Extract document from editor title
    elif result["category"] == "editor":
        for pattern in EDITOR_TITLE_PATTERNS:
            match = pattern.match(window_title)
            if match:
                result["document"] = match.group(1).strip()
                break

    # Extract chat context from messenger title
    elif result["category"] == "messenger":
        for pattern in MESSENGER_TITLE_PATTERNS:
            match = pattern.match(window_title)
            if match:
                result["chat_context"] = match.group(1).strip()
                break

    return result


# ─────────────────────────────────────────────────────────────
# Context Engine — the singleton that tracks desktop state
# ─────────────────────────────────────────────────────────────

class ContextEngine:
    """Tracks the current desktop context and provides pre-action guards.

    Usage:
        ctx = ContextEngine()
        state = await ctx.get_context()       # get current state
        await ctx.ensure_app("WhatsApp")      # focus WhatsApp if not active
        result = await ctx.guarded_action(     # run action with context check
            target_app="WhatsApp",
            action_fn=some_async_fn,
        )
    """

    # How old context can be before it's considered stale
    STALE_THRESHOLD = 3.0  # seconds

    # How long to wait after focusing a window before acting
    FOCUS_SETTLE_TIME = 0.5  # seconds

    def __init__(self):
        self._last_state: ContextState | None = None
        self._state_lock = asyncio.Lock()
        self._focus_history: list[dict[str, Any]] = []  # track recent focus changes
        self._action_log: list[dict[str, Any]] = []     # track recent actions + their context

    async def _run_cmd(self, cmd: str, timeout: float = 5) -> str:
        """Run a shell command and return stdout."""
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return stdout.decode("utf-8", errors="replace").strip()
        except Exception:
            return ""

    # ─── Get Active Window (cross-platform) ───

    async def _get_active_window_windows(self) -> dict[str, Any]:
        """Get the active window on Windows using PowerShell."""
        cmd = (
            'powershell -NoProfile -Command "'
            '$fw = [System.Diagnostics.Process]::GetProcesses() | '
            'Where-Object { $_.MainWindowHandle -eq '
            '(Add-Type -MemberDefinition \'[DllImport(\"user32.dll\")] '
            'public static extern IntPtr GetForegroundWindow();\' '
            '-Name Win32 -PassThru)::GetForegroundWindow() }; '
            'if ($fw) { @{Title=$fw.MainWindowTitle; App=$fw.ProcessName; PID=$fw.Id} | ConvertTo-Json } '
            'else { \'{\"Title\":\"\",\"App\":\"\",\"PID\":0}\' }"'
        )
        out = await self._run_cmd(cmd)
        try:
            data = json.loads(out)
            return {
                "title": data.get("Title", ""),
                "app": data.get("App", ""),
                "pid": data.get("PID", 0),
            }
        except Exception:
            return {"title": "", "app": "", "pid": 0}

    async def _get_active_window_macos(self) -> dict[str, Any]:
        """Get the active window on macOS using AppleScript."""
        script = '''osascript -e '
        tell application "System Events"
            set frontApp to first application process whose frontmost is true
            set appName to name of frontApp
            try
                set winTitle to name of front window of frontApp
            on error
                set winTitle to ""
            end try
            set appPID to unix id of frontApp
        end tell
        return appName & "|" & winTitle & "|" & appPID'
        '''
        out = await self._run_cmd(script)
        parts = out.split("|")
        if len(parts) >= 3:
            return {
                "title": parts[1].strip(),
                "app": parts[0].strip(),
                "pid": int(parts[2].strip()) if parts[2].strip().isdigit() else 0,
            }
        return {"title": "", "app": "", "pid": 0}

    async def _get_active_window_linux(self) -> dict[str, Any]:
        """Get the active window on Linux using xdotool/xprop."""
        # Try xdotool first
        wid = await self._run_cmd("xdotool getactivewindow 2>/dev/null")
        if wid:
            title = await self._run_cmd(f"xdotool getwindowname {wid} 2>/dev/null")
            pid = await self._run_cmd(f"xdotool getwindowpid {wid} 2>/dev/null")
            # Try to get app name from PID
            app = ""
            if pid and pid.isdigit():
                app = await self._run_cmd(f"ps -p {pid} -o comm= 2>/dev/null")
            return {
                "title": title,
                "app": app,
                "pid": int(pid) if pid and pid.isdigit() else 0,
            }

        # Fallback: xprop
        out = await self._run_cmd(
            "xprop -root _NET_ACTIVE_WINDOW 2>/dev/null | grep -oP '0x[0-9a-f]+'"
        )
        if out:
            title = await self._run_cmd(f"xprop -id {out} WM_NAME 2>/dev/null")
            match = re.search(r'"(.+)"', title)
            return {
                "title": match.group(1) if match else "",
                "app": "",
                "pid": 0,
            }

        return {"title": "", "app": "", "pid": 0}

    async def get_active_window(self) -> dict[str, Any]:
        """Get the currently active/foreground window (cross-platform)."""
        if SYSTEM == "Windows":
            return await self._get_active_window_windows()
        elif SYSTEM == "Darwin":
            return await self._get_active_window_macos()
        else:
            return await self._get_active_window_linux()

    # ─── Get Full Context ───

    async def get_context(self, force_refresh: bool = False) -> ContextState:
        """Get the current desktop context.

        Returns a cached state if it's fresh enough, otherwise refreshes.
        """
        async with self._state_lock:
            now = time.time()

            # Return cached if fresh
            if (
                not force_refresh
                and self._last_state
                and (now - self._last_state.captured_at) < self.STALE_THRESHOLD
            ):
                self._last_state.age_seconds = now - self._last_state.captured_at
                return self._last_state

            # Refresh
            window = await self.get_active_window()
            classification = classify_app(
                window.get("app", ""),
                window.get("title", ""),
            )

            # Get mouse position
            mouse_x, mouse_y = 0, 0
            try:
                import pyautogui
                pos = pyautogui.position()
                mouse_x, mouse_y = pos.x, pos.y
                size = pyautogui.size()
                screen_w, screen_h = size.width, size.height
            except Exception:
                screen_w, screen_h = 1920, 1080

            state = ContextState(
                active_window_title=window.get("title", ""),
                active_app_name=window.get("app", ""),
                active_window_pid=window.get("pid", 0),
                active_app_category=classification["category"],
                active_browser_tab=classification["browser_tab"],
                active_document=classification["document"],
                screen_width=screen_w,
                screen_height=screen_h,
                mouse_x=mouse_x,
                mouse_y=mouse_y,
                captured_at=now,
                age_seconds=0.0,
                is_stale=False,
            )

            self._last_state = state
            return state

    # ─── Focus Verification & Auto-Focus ───

    async def is_app_active(self, target: str) -> bool:
        """Check if a specific app/window is currently in the foreground.

        Matches against app name, window title, and category.
        Uses fuzzy matching for convenience.
        """
        state = await self.get_context(force_refresh=True)
        target_lower = target.lower().strip()

        # Check app name
        if target_lower in state.active_app_name.lower():
            return True

        # Check window title
        if target_lower in state.active_window_title.lower():
            return True

        # Check category
        if target_lower == state.active_app_category:
            return True

        # Check browser tab (for web apps)
        if state.active_browser_tab and target_lower in state.active_browser_tab.lower():
            return True

        return False

    async def ensure_app(self, target: str, timeout: float = 5.0) -> dict[str, Any]:
        """Ensure a specific app is in the foreground. Focus it if not.

        This is the KEY method that prevents wrong-window actions.
        Call this before any action that targets a specific app.

        Returns:
            {
                "already_active": bool,
                "focused": bool,
                "app": str,
                "title": str,
                "error": str | None,
            }
        """
        # Check if already active
        if await self.is_app_active(target):
            state = await self.get_context()
            return {
                "already_active": True,
                "focused": True,
                "app": state.active_app_name,
                "title": state.active_window_title,
                "error": None,
            }

        # Need to focus — import WindowManager
        from plutus.pc.windows import WindowManager
        wm = WindowManager()

        result = await wm.focus(target)

        if result.get("success"):
            # Wait for the window to settle
            await asyncio.sleep(self.FOCUS_SETTLE_TIME)

            # Verify focus actually changed
            state = await self.get_context(force_refresh=True)

            # Log the focus change
            self._focus_history.append({
                "target": target,
                "result_app": state.active_app_name,
                "result_title": state.active_window_title,
                "timestamp": time.time(),
                "success": True,
            })

            logger.info(
                f"Focused window: {state.active_app_name} - {state.active_window_title}"
            )

            return {
                "already_active": False,
                "focused": True,
                "app": state.active_app_name,
                "title": state.active_window_title,
                "error": None,
            }
        else:
            self._focus_history.append({
                "target": target,
                "result_app": "",
                "result_title": "",
                "timestamp": time.time(),
                "success": False,
                "error": result.get("error", "Unknown error"),
            })

            return {
                "already_active": False,
                "focused": False,
                "app": "",
                "title": "",
                "error": result.get("error", f"Could not focus: {target}"),
            }

    # ─── Context-Enriched Results ───

    def enrich_result(self, result: dict[str, Any], operation: str) -> dict[str, Any]:
        """Add current context info to a tool result.

        This is injected into EVERY pc tool result so the LLM always knows
        what window/app it's looking at.
        """
        if self._last_state:
            result["_context"] = {
                "active_app": self._last_state.active_app_name,
                "active_window": self._last_state.active_window_title[:100],
                "category": self._last_state.active_app_category,
                "mouse_at": f"({self._last_state.mouse_x}, {self._last_state.mouse_y})",
            }
            if self._last_state.active_browser_tab:
                result["_context"]["browser_tab"] = self._last_state.active_browser_tab
            if self._last_state.active_document:
                result["_context"]["document"] = self._last_state.active_document
        return result

    # ─── Action Logging ───

    def log_action(self, operation: str, params: dict[str, Any], result: Any) -> None:
        """Log an action with its context for debugging and learning."""
        entry = {
            "operation": operation,
            "params": {k: v for k, v in params.items() if k != "include_base64"},
            "context": self._last_state.summary() if self._last_state else "unknown",
            "timestamp": time.time(),
        }
        self._action_log.append(entry)

        # Keep only last 100 actions
        if len(self._action_log) > 100:
            self._action_log = self._action_log[-100:]

    # ─── Status / Debug ───

    def get_status(self) -> dict[str, Any]:
        """Get the context engine status for the UI/API."""
        return {
            "last_state": self._last_state.to_dict() if self._last_state else None,
            "focus_history": self._focus_history[-10:],
            "recent_actions": self._action_log[-10:],
            "stale_threshold": self.STALE_THRESHOLD,
            "focus_settle_time": self.FOCUS_SETTLE_TIME,
        }


# ─────────────────────────────────────────────────────────────
# Action Guard — wraps pc actions with context verification
# ─────────────────────────────────────────────────────────────

class ActionGuard:
    """Pre-action guard that ensures context is correct before acting.

    Wraps around the PCControlTool to intercept actions and:
    1. Refresh context before the action
    2. If a target app is specified, ensure it's focused
    3. Enrich the result with current context
    4. Log the action

    Usage:
        guard = ActionGuard(context_engine)
        result = await guard.check_before_action(
            operation="type",
            params={"text": "hello"},
            target_app="WhatsApp",  # optional
        )
    """

    # Operations that modify state (need context verification)
    WRITE_OPERATIONS = {
        "click", "double_click", "right_click", "drag",
        "type", "press", "hotkey", "shortcut", "key_down",
        "scroll",
    }

    # Operations that only read state (less critical)
    READ_OPERATIONS = {
        "screenshot", "read_screen", "find_text", "find_elements",
        "get_pixel_color", "find_color", "wait_for_text", "wait_for_change",
        "screen_info", "list_windows", "find_window", "active_window",
        "list_shortcuts", "list_workflows", "list_templates", "get_template",
    }

    def __init__(self, context_engine: ContextEngine):
        self._ctx = context_engine

    async def check_before_action(
        self,
        operation: str,
        params: dict[str, Any],
        target_app: str | None = None,
    ) -> dict[str, Any]:
        """Run pre-action checks and return context info.

        Returns:
            {
                "proceed": bool,         # whether to proceed with the action
                "context": ContextState,  # current context
                "focus_result": dict,     # if focus was needed
                "warning": str | None,    # any warnings
            }
        """
        # Always refresh context for write operations
        force_refresh = operation in self.WRITE_OPERATIONS
        context = await self._ctx.get_context(force_refresh=force_refresh)

        result: dict[str, Any] = {
            "proceed": True,
            "context": context,
            "focus_result": None,
            "warning": None,
        }

        # If a target app is specified, ensure it's focused
        if target_app and operation in self.WRITE_OPERATIONS:
            if not await self._ctx.is_app_active(target_app):
                focus_result = await self._ctx.ensure_app(target_app)
                result["focus_result"] = focus_result

                if not focus_result.get("focused"):
                    result["proceed"] = False
                    result["warning"] = (
                        f"Cannot focus {target_app}: {focus_result.get('error')}. "
                        f"Currently active: {context.active_app_name} - {context.active_window_title}"
                    )
                    return result

                # Re-get context after focus change
                result["context"] = await self._ctx.get_context(force_refresh=True)

        return result

    async def post_action(
        self,
        operation: str,
        params: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """Enrich the result with context after an action."""
        # Refresh context after write operations
        if operation in self.WRITE_OPERATIONS:
            await self._ctx.get_context(force_refresh=True)

        # Enrich result with context
        enriched = self._ctx.enrich_result(result, operation)

        # Log the action
        self._ctx.log_action(operation, params, result)

        return enriched


# ─────────────────────────────────────────────────────────────
# Singleton — global context engine instance
# ─────────────────────────────────────────────────────────────

_global_context_engine: ContextEngine | None = None


def get_context_engine() -> ContextEngine:
    """Get or create the global context engine."""
    global _global_context_engine
    if _global_context_engine is None:
        _global_context_engine = ContextEngine()
    return _global_context_engine

