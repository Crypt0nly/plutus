"""
PC Control Tool — OpenClaw-style unified interface for all machine interaction.

Architecture:
  1. SHELL: Open apps, run commands, manage processes via OS-native commands
  2. BROWSER (Accessibility Tree + Refs): Navigate web, snapshot page, interact by ref numbers
  2.5 DESKTOP UIA (Accessibility Tree + Refs): Navigate native Windows apps the same way
  3. DESKTOP FALLBACK (PyAutoGUI): Mouse/keyboard when UIA isn't available

The KEY INNOVATION is the snapshot → ref → act loop (works for BOTH web AND native apps):
  1. snapshot() / desktop_snapshot() → returns numbered accessibility tree
  2. LLM reads the tree, picks a ref number
  3. click_ref(3) / desktop_click_ref(3) → precise, deterministic interaction
"""

from __future__ import annotations

import json
import logging
from typing import Any

from plutus.pc.os_control import OSControl
from plutus.pc.browser_control import BrowserControl
from plutus.tools.base import Tool

logger = logging.getLogger("plutus.pc.control")

# Lazy-loaded skill system
_skill_engine = None
_skill_registry = None


def _ensure_skills():
    global _skill_engine, _skill_registry
    if _skill_registry is None:
        from plutus.skills.registry import create_default_registry
        _skill_registry = create_default_registry()
    return _skill_registry


def _get_skill_engine(pc_tool):
    global _skill_engine
    if _skill_engine is None:
        from plutus.skills.engine import SkillEngine
        _skill_engine = SkillEngine(pc_tool.execute)
    return _skill_engine


class PCControlTool(Tool):
    """
    Unified PC control — the primary way the AI interacts with the computer.

    Three clean layers:
    1. OS Control: shell commands for apps, files, processes
    2. Browser Control: accessibility tree snapshots + ref-based interaction for web
    2.5 Desktop UIA: accessibility tree snapshots + ref-based interaction for native Windows apps
    3. Desktop Fallback: PyAutoGUI mouse/keyboard when UIA isn't available
    """

    def __init__(self):
        self._os = OSControl()
        self._browser = BrowserControl()
        self._desktop = None  # Lazy-loaded DesktopControl (UIA)
        self._mouse = None
        self._keyboard = None
        self._screen = None

    def _ensure_desktop_uia(self):
        """Lazy-load the Windows UIA desktop controller."""
        if self._desktop is None:
            try:
                from plutus.pc.desktop_control import DesktopControl
                self._desktop = DesktopControl()
                logger.info("Desktop UIA controller loaded")
            except Exception as e:
                logger.warning(f"Desktop UIA not available: {e}")

    def _ensure_desktop_fallback(self):
        """Lazy-load PyAutoGUI fallback controllers."""
        if self._mouse is None:
            try:
                from plutus.pc.mouse import MouseController
                from plutus.pc.keyboard import KeyboardController
                from plutus.pc.screen import ScreenReader
                self._mouse = MouseController("normal")
                self._keyboard = KeyboardController("natural")
                self._screen = ScreenReader()
            except Exception as e:
                logger.warning(f"Desktop fallback control not available: {e}")

    # Keep backward compat
    def _ensure_desktop(self):
        self._ensure_desktop_fallback()

    @property
    def name(self) -> str:
        return "pc"

    @property
    def description(self) -> str:
        return (
            "Control the computer — open apps, browse the web, navigate native Windows apps, run commands.\n\n"
            "=== OS OPERATIONS (always use for opening apps and system tasks) ===\n"
            "• open_app: Open any app by name (WhatsApp, Chrome, Spotify, etc.)\n"
            "• close_app, open_url, open_file, open_folder, run_command\n"
            "• list_processes, kill_process, get_clipboard, set_clipboard\n"
            "• send_notification, list_apps, system_info, active_window\n\n"
            "=== BROWSER OPERATIONS (snapshot → ref → act loop for WEB PAGES) ===\n"
            "MANDATORY for ALL web interaction — NEVER use desktop ops for web pages:\n"
            "  1. navigate(url) → opens page AND returns accessibility tree snapshot\n"
            "  2. snapshot() → refreshes the accessibility tree with numbered [ref] elements\n"
            "  3. click_ref(ref=5) → clicks element [5] from the snapshot\n"
            "  4. type_ref(ref=3, text='hello') → types into element [3]\n"
            "  5. select_ref(ref=7, value='option') → selects dropdown option\n"
            "  6. check_ref(ref=9, checked=true) → toggles checkbox\n"
            "  7. browser_scroll(direction='down') → scrolls the page, then call snapshot()\n"
            "  8. snapshot() → verify the result after ANY action\n\n"
            "=== DESKTOP UIA OPERATIONS (snapshot → ref → act loop for NATIVE WINDOWS APPS) ===\n"
            "Same pattern as browser, but for native apps (File Explorer, Notepad, Word, etc.):\n"
            "  1. desktop_snapshot() → accessibility tree of the focused native window\n"
            "  2. desktop_click_ref(ref=3) → clicks element [3] in the native app\n"
            "  3. desktop_type_ref(ref=2, text='hello') → types into element [2]\n"
            "  4. desktop_select_ref(ref=5, value='option') → selects an option\n"
            "  5. desktop_toggle_ref(ref=4) → toggles a checkbox/radio button\n"
            "  6. desktop_scroll(direction='down') → scrolls the focused window\n"
            "  7. desktop_key(key='ctrl+s') → sends a keyboard shortcut\n"
            "  8. desktop_list_windows() → lists all visible windows\n"
            "  9. desktop_focus_window(window_title='Notepad') → brings a window to front\n"
            "  10. desktop_snapshot() → verify the result after ANY action\n\n"
            "Desktop UIA snapshot example:\n"
            "  Window: Untitled - Notepad [Notepad]\n"
            "  [1] menubar 'Application'\n"
            "  [2] menuitem 'File'\n"
            "  [3] menuitem 'Edit'\n"
            "  [4] edit 'Text Editor' value='Hello world'\n"
            "  [5] statusbar: Ln 1, Col 12\n\n"
            "Then: desktop_type_ref(ref=4, text='New content', clear_first=true)\n\n"
            "IMPORTANT: Use desktop_snapshot (NOT screenshot) to see native app content.\n"
            "IMPORTANT: Use desktop_click_ref (NOT mouse_click) to interact with native apps.\n\n"
            "Other browser ops: new_tab, close_tab, switch_tab, list_tabs,\n"
            "  fill_form, evaluate_js, wait_for_text, wait_for_navigation\n\n"
            "=== DESKTOP FALLBACK (ONLY when UIA is not available) ===\n"
            "• keyboard_type, keyboard_press, keyboard_hotkey, keyboard_shortcut\n"
            "• mouse_click, mouse_move, mouse_scroll, screenshot\n"
            "• These are ONLY for when UIA-based desktop control doesn't work\n\n"
            "=== SKILLS (pre-built app workflows) ===\n"
            "• run_skill, list_skills, create_skill, update_skill, delete_skill\n"
            "• Two skill types: 'simple' (JSON step sequences) and 'python' (full Python scripts)\n\n"
            "=== STRATEGY ===\n"
            "1. Open apps → ALWAYS use open_app\n"
            "2. Web tasks → navigate + snapshot + click_ref/type_ref\n"
            "3. Native apps → open_app + desktop_snapshot + desktop_click_ref/desktop_type_ref\n"
            "4. NEVER guess coordinates — use snapshot/desktop_snapshot to see what's available\n"
            "5. NEVER use screenshot/mouse_click when snapshot/click_ref can do the job"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        # OS operations
                        "open_app", "close_app", "open_url", "open_file", "open_folder",
                        "run_command", "list_processes", "kill_process",
                        "get_clipboard", "set_clipboard", "send_notification",
                        "list_apps", "system_info", "active_window",
                        # Browser operations — snapshot + ref-based
                        "navigate", "snapshot",
                        "click_ref", "type_ref", "select_ref", "check_ref",
                        # Browser operations — legacy (selector/text-based)
                        "browser_click", "browser_type", "browser_press",
                        "fill_form", "select_option", "browser_hover", "browser_scroll",
                        "browser_screenshot",
                        "new_tab", "close_tab", "switch_tab", "list_tabs",
                        "evaluate_js", "wait_for_text", "wait_for_navigation",
                        # Desktop UIA operations — snapshot + ref-based (for native apps)
                        "desktop_snapshot", "desktop_click_ref", "desktop_type_ref",
                        "desktop_select_ref", "desktop_toggle_ref",
                        "desktop_scroll", "desktop_key",
                        "desktop_list_windows", "desktop_focus_window",
                        # Desktop fallback operations (PyAutoGUI)
                        "mouse_click", "mouse_move", "mouse_scroll",
                        "keyboard_type", "keyboard_press", "keyboard_hotkey", "keyboard_shortcut",
                        "screenshot",
                        # Skills
                        "run_skill", "list_skills",
                        "create_skill", "update_skill", "delete_skill",
                        "improvement_log", "improvement_stats",
                    ],
                    "description": "The operation to perform",
                },
                # OS params
                "app_name": {"type": "string", "description": "App name for open_app/close_app"},
                "url": {"type": "string", "description": "URL for navigate/open_url"},
                "command": {"type": "string", "description": "Shell command for run_command"},
                "file_path": {"type": "string", "description": "File or folder path"},
                "process_name": {"type": "string", "description": "Process name"},
                "pid": {"type": "integer", "description": "Process ID"},
                "notification_title": {"type": "string", "description": "Notification title"},
                "notification_message": {"type": "string", "description": "Notification message"},
                # Ref-based params (shared by browser AND desktop UIA)
                "ref": {"type": "integer", "description": "Element ref number from snapshot (e.g., 5 to click [5])"},
                "text": {"type": "string", "description": "Text to type, find, or match"},
                "press_enter": {"type": "boolean", "description": "Press Enter after typing"},
                "clear_first": {"type": "boolean", "description": "Clear field before typing (default: true)"},
                "checked": {"type": "boolean", "description": "Check state for check_ref"},
                "value": {"type": "string", "description": "Value for select_ref/desktop_select_ref"},
                # Desktop UIA params
                "window_title": {"type": "string", "description": "Window title for desktop_snapshot/desktop_focus_window"},
                "max_depth": {"type": "integer", "description": "Max tree depth for desktop_snapshot (default: 8)"},
                "double_click": {"type": "boolean", "description": "Double-click for click_ref/desktop_click_ref"},
                # Legacy browser params
                "selector": {"type": "string", "description": "CSS selector (prefer ref-based ops instead)"},
                "label": {"type": "string", "description": "Input field label"},
                "placeholder": {"type": "string", "description": "Input field placeholder"},
                "role": {"type": "string", "description": "ARIA role"},
                "role_name": {"type": "string", "description": "ARIA role name"},
                "tab_id": {"type": "string", "description": "Tab ID for tab operations"},
                "js_code": {"type": "string", "description": "JavaScript code for evaluate_js"},
                "fields": {
                    "type": "array",
                    "description": "Form fields: [{ref?, selector?, label?, value}]",
                    "items": {"type": "object"},
                },
                "direction": {"type": "string", "enum": ["up", "down"], "description": "Scroll direction"},
                "amount": {"type": "integer", "description": "Scroll amount in pixels"},
                "full_page": {"type": "boolean", "description": "Full page screenshot"},
                "browser": {"type": "string", "description": "Specific browser for open_url"},
                "right_click": {"type": "boolean", "description": "Right-click"},
                # Desktop fallback params
                "x": {"type": "integer", "description": "X coordinate for mouse"},
                "y": {"type": "integer", "description": "Y coordinate for mouse"},
                "button": {"type": "string", "description": "Mouse button (left/right/middle)"},
                "key": {"type": "string", "description": "Key name for keyboard_press/desktop_key"},
                "hotkey": {"type": "string", "description": "Key combo for keyboard_hotkey (ctrl+c, alt+tab)"},
                "shortcut_name": {"type": "string", "description": "Named shortcut (copy, paste, save, undo)"},
                "timeout": {"type": "integer", "description": "Timeout in milliseconds"},
                "cwd": {"type": "string", "description": "Working directory for run_command"},
                # Skill params
                "skill_name": {"type": "string", "description": "Skill name for run_skill"},
                "skill_params": {"type": "object", "description": "Parameters for the skill"},
                "category": {"type": "string", "description": "Filter skills by category"},
                "skill_definition": {"type": "object", "description": "Full skill definition for create_skill/update_skill"},
                "reason": {"type": "string", "description": "Why this skill is being created"},
                "limit": {"type": "integer", "description": "Limit for improvement_log entries"},
            },
            "required": ["operation"],
        }

    async def execute(self, **kwargs: Any) -> str:
        op = kwargs.get("operation", "")
        try:
            result = await self._dispatch(op, kwargs)
            return json.dumps(result, default=str)
        except Exception as e:
            logger.error(f"PC control error in {op}: {e}")
            return json.dumps({"error": str(e), "operation": op}, default=str)

    async def _dispatch(self, op: str, kwargs: dict) -> dict:

        # ═══════════════════════════════════════════════
        # AUTO-REDIRECT: Fix common LLM operation mistakes
        # ═══════════════════════════════════════════════
        _redirects = {
            # Browser scroll redirects
            "scroll": "browser_scroll",
            "scroll_down": "browser_scroll",
            "scroll_up": "browser_scroll",
            "page_down": "browser_scroll",
            "page_up": "browser_scroll",
            # Snapshot redirects
            "take_screenshot": "snapshot",
            "get_screenshot": "snapshot",
            "capture": "snapshot",
            "get_page": "snapshot",
            "read_page": "snapshot",
            "view_page": "snapshot",
            # Ref-based redirects
            "click": "click_ref",
            "type": "type_ref",
            "select": "select_ref",
            "check": "check_ref",
            # Desktop UIA redirects (common mistakes)
            "win_snapshot": "desktop_snapshot",
            "window_snapshot": "desktop_snapshot",
            "app_snapshot": "desktop_snapshot",
            "desktop_click": "desktop_click_ref",
            "desktop_type": "desktop_type_ref",
            "desktop_select": "desktop_select_ref",
            "desktop_toggle": "desktop_toggle_ref",
            "win_click": "desktop_click_ref",
            "win_type": "desktop_type_ref",
            "list_windows": "desktop_list_windows",
            "focus_window": "desktop_focus_window",
        }
        if op in _redirects:
            old_op = op
            op = _redirects[op]
            logger.info(f"Auto-redirected '{old_op}' → '{op}'")
            # Fix direction for scroll_up/scroll_down
            if old_op == "scroll_up":
                kwargs["direction"] = "up"
            elif old_op in ("scroll_down", "scroll", "page_down"):
                kwargs["direction"] = "down"
            elif old_op == "page_up":
                kwargs["direction"] = "up"

        # If the LLM calls 'screenshot' while a browser is active, redirect to snapshot
        if op == "screenshot" and self._browser and self._browser._initialized:
            op = "snapshot"
            logger.info("Auto-redirected 'screenshot' → 'snapshot' (browser is active)")

        # If the LLM calls 'mouse_scroll' while a browser is active, redirect to browser_scroll
        if op == "mouse_scroll" and self._browser and self._browser._initialized:
            op = "browser_scroll"
            logger.info("Auto-redirected 'mouse_scroll' → 'browser_scroll' (browser is active)")

        # If the LLM calls mouse_click/keyboard_type on a native app, suggest desktop UIA instead
        if op in ("mouse_click", "keyboard_type") and self._desktop and self._desktop._uia_available:
            logger.info(f"Hint: Consider using desktop_snapshot + desktop_click_ref/desktop_type_ref instead of {op}")

        # ═══════════════════════════════════════════════
        # LAYER 1: OS Operations (shell commands)
        # ═══════════════════════════════════════════════

        if op == "open_app":
            app = kwargs.get("app_name") or kwargs.get("text", "")
            if not app:
                return {"error": "Provide app_name (e.g., 'WhatsApp', 'Chrome')"}
            return await self._os.open_app(app)

        elif op == "close_app":
            app = kwargs.get("app_name") or kwargs.get("text", "")
            if not app:
                return {"error": "Provide app_name"}
            return await self._os.close_app(app)

        elif op == "open_url":
            url = kwargs.get("url", "")
            if not url:
                return {"error": "Provide url"}
            return await self._os.open_url(url, browser=kwargs.get("browser"))

        elif op == "open_file":
            path = kwargs.get("file_path") or kwargs.get("text", "")
            if not path:
                return {"error": "Provide file_path"}
            return await self._os.open_file(path)

        elif op == "open_folder":
            path = kwargs.get("file_path") or kwargs.get("text", "")
            if not path:
                return {"error": "Provide file_path"}
            return await self._os.open_folder(path)

        elif op == "run_command":
            cmd = kwargs.get("command") or kwargs.get("text", "")
            if not cmd:
                return {"error": "Provide command"}
            return await self._os.run_command(cmd, timeout=kwargs.get("timeout", 30), cwd=kwargs.get("cwd"))

        elif op == "list_processes":
            return await self._os.list_processes(filter_name=kwargs.get("process_name"))

        elif op == "kill_process":
            return await self._os.kill_process(pid=kwargs.get("pid"), name=kwargs.get("process_name") or kwargs.get("text"))

        elif op == "get_clipboard":
            return await self._os.get_clipboard()

        elif op == "set_clipboard":
            return await self._os.set_clipboard(kwargs.get("text", ""))

        elif op == "send_notification":
            return await self._os.send_notification(
                title=kwargs.get("notification_title", "Plutus"),
                message=kwargs.get("notification_message") or kwargs.get("text", ""),
            )

        elif op == "list_apps":
            return await self._os.list_available_apps()

        elif op == "system_info":
            return await self._os.get_system_info()

        elif op == "active_window":
            return await self._os.get_active_window()

        # ═══════════════════════════════════════════════
        # LAYER 2: Browser — Snapshot + Ref-Based (PRIMARY)
        # ═══════════════════════════════════════════════

        elif op == "navigate":
            url = kwargs.get("url", "")
            if not url:
                return {"error": "Provide url"}
            return await self._browser.navigate(url, tab_id=kwargs.get("tab_id"))

        elif op == "snapshot":
            return await self._browser.snapshot()

        elif op == "click_ref":
            ref = kwargs.get("ref")
            if ref is None:
                return {"error": "Provide ref number from snapshot (e.g., ref=5 to click [5])"}
            return await self._browser.click_ref(
                int(ref),
                double_click=kwargs.get("double_click", False),
                right_click=kwargs.get("right_click", False),
            )

        elif op == "type_ref":
            ref = kwargs.get("ref")
            text = kwargs.get("text", "")
            if ref is None:
                return {"error": "Provide ref number from snapshot (e.g., ref=3)"}
            if not text:
                return {"error": "Provide text to type"}
            return await self._browser.type_ref(
                int(ref),
                text,
                press_enter=kwargs.get("press_enter", False),
                clear_first=kwargs.get("clear_first", True),
            )

        elif op == "select_ref":
            ref = kwargs.get("ref")
            value = kwargs.get("value") or kwargs.get("text", "")
            if ref is None:
                return {"error": "Provide ref number"}
            return await self._browser.select_ref(int(ref), value)

        elif op == "check_ref":
            ref = kwargs.get("ref")
            if ref is None:
                return {"error": "Provide ref number"}
            return await self._browser.check_ref(int(ref), checked=kwargs.get("checked", True))

        # ═══════════════════════════════════════════════
        # LAYER 2: Browser — Legacy (selector/text-based)
        # ═══════════════════════════════════════════════

        elif op == "browser_click":
            return await self._browser.click(
                selector=kwargs.get("selector"), text=kwargs.get("text"),
                role=kwargs.get("role"), role_name=kwargs.get("role_name"),
                double_click=kwargs.get("double_click", False),
                right_click=kwargs.get("right_click", False),
                timeout=kwargs.get("timeout", 5000),
            )

        elif op == "browser_type":
            text = kwargs.get("text", "")
            if not text:
                return {"error": "Provide text to type"}
            return await self._browser.type_text(
                text=text, selector=kwargs.get("selector"),
                label=kwargs.get("label"), placeholder=kwargs.get("placeholder"),
                press_enter=kwargs.get("press_enter", False),
                timeout=kwargs.get("timeout", 5000),
            )

        elif op == "browser_press":
            key = kwargs.get("key") or kwargs.get("text", "Enter")
            return await self._browser.press_key(key)

        elif op == "fill_form":
            fields = kwargs.get("fields", [])
            if not fields:
                return {"error": "Provide fields array"}
            return await self._browser.fill_form(fields)

        elif op == "select_option":
            ref = kwargs.get("ref")
            if ref:
                return await self._browser.select_ref(int(ref), kwargs.get("text", ""))
            # Fallback for legacy selector-based select
            page = self._browser._get_active_page()
            if page:
                try:
                    selector = kwargs.get("selector") or kwargs.get("label", "select")
                    await page.locator(selector).first.select_option(kwargs.get("text", ""), timeout=5000)
                    return {"success": True, "action": "select_option"}
                except Exception as e:
                    return {"success": False, "error": str(e)}
            return {"success": False, "error": "No active page"}

        elif op == "browser_hover":
            return await self._browser.hover(
                selector=kwargs.get("selector"), text=kwargs.get("text"),
                ref=kwargs.get("ref"),
            )

        elif op == "browser_scroll":
            return await self._browser.scroll(
                direction=kwargs.get("direction", "down"),
                amount=kwargs.get("amount", 500),
            )

        elif op == "browser_screenshot":
            return await self._browser.screenshot(full_page=kwargs.get("full_page", False))

        elif op == "new_tab":
            return await self._browser.new_tab(url=kwargs.get("url"))

        elif op == "close_tab":
            return await self._browser.close_tab(tab_id=kwargs.get("tab_id"))

        elif op == "switch_tab":
            tab_id = kwargs.get("tab_id", "")
            if not tab_id:
                return {"error": "Provide tab_id"}
            return await self._browser.switch_tab(tab_id)

        elif op == "list_tabs":
            return await self._browser.list_tabs()

        elif op == "evaluate_js":
            code = kwargs.get("js_code") or kwargs.get("text", "")
            if not code:
                return {"error": "Provide js_code"}
            return await self._browser.evaluate(code)

        elif op == "wait_for_text":
            text = kwargs.get("text", "")
            if not text:
                return {"error": "Provide text to wait for"}
            return await self._browser.wait_for_text(text, timeout=kwargs.get("timeout", 10000))

        elif op == "wait_for_navigation":
            return await self._browser.wait_for_navigation(timeout=kwargs.get("timeout", 30000))

        # ═══════════════════════════════════════════════
        # LAYER 2.5: Desktop UIA — Snapshot + Ref-Based
        # (Same pattern as browser, but for native Windows apps)
        # ═══════════════════════════════════════════════

        elif op == "desktop_snapshot":
            self._ensure_desktop_uia()
            if not self._desktop:
                return {
                    "error": "Desktop UIA not available. Install pywinauto: pip install pywinauto",
                    "hint": "Use keyboard_type/keyboard_press as fallback for native apps.",
                }
            return await self._desktop.snapshot(
                window_title=kwargs.get("window_title"),
                max_depth=kwargs.get("max_depth", 8),
            )

        elif op == "desktop_click_ref":
            self._ensure_desktop_uia()
            if not self._desktop:
                return {"error": "Desktop UIA not available"}
            ref = kwargs.get("ref")
            if ref is None:
                return {"error": "Provide ref number from desktop_snapshot (e.g., ref=3)"}
            return await self._desktop.click_ref(
                int(ref),
                double_click=kwargs.get("double_click", False),
            )

        elif op == "desktop_type_ref":
            self._ensure_desktop_uia()
            if not self._desktop:
                return {"error": "Desktop UIA not available"}
            ref = kwargs.get("ref")
            text = kwargs.get("text", "")
            if ref is None:
                return {"error": "Provide ref number from desktop_snapshot (e.g., ref=2)"}
            if not text:
                return {"error": "Provide text to type"}
            return await self._desktop.type_ref(
                int(ref),
                text,
                clear_first=kwargs.get("clear_first", True),
                press_enter=kwargs.get("press_enter", False),
            )

        elif op == "desktop_select_ref":
            self._ensure_desktop_uia()
            if not self._desktop:
                return {"error": "Desktop UIA not available"}
            ref = kwargs.get("ref")
            value = kwargs.get("value") or kwargs.get("text", "")
            if ref is None:
                return {"error": "Provide ref number"}
            return await self._desktop.select_ref(int(ref), value)

        elif op == "desktop_toggle_ref":
            self._ensure_desktop_uia()
            if not self._desktop:
                return {"error": "Desktop UIA not available"}
            ref = kwargs.get("ref")
            if ref is None:
                return {"error": "Provide ref number"}
            return await self._desktop.toggle_ref(int(ref))

        elif op == "desktop_scroll":
            self._ensure_desktop_uia()
            if not self._desktop:
                return {"error": "Desktop UIA not available"}
            return await self._desktop.scroll_window(
                direction=kwargs.get("direction", "down"),
                amount=kwargs.get("amount", 3),
            )

        elif op == "desktop_key":
            self._ensure_desktop_uia()
            if not self._desktop:
                return {"error": "Desktop UIA not available"}
            key = kwargs.get("key") or kwargs.get("hotkey") or kwargs.get("text", "")
            if not key:
                return {"error": "Provide key (e.g., 'enter', 'ctrl+s', 'alt+f4')"}
            return await self._desktop.press_key(key)

        elif op == "desktop_list_windows":
            self._ensure_desktop_uia()
            if not self._desktop:
                return {"error": "Desktop UIA not available"}
            return await self._desktop.list_windows()

        elif op == "desktop_focus_window":
            self._ensure_desktop_uia()
            if not self._desktop:
                return {"error": "Desktop UIA not available"}
            title = kwargs.get("window_title") or kwargs.get("text", "")
            if not title:
                return {"error": "Provide window_title (e.g., 'Notepad', 'File Explorer')"}
            return await self._desktop.focus_window(title)

        # ═══════════════════════════════════════════════
        # LAYER 3: Desktop Fallback (PyAutoGUI — native apps only)
        # ═══════════════════════════════════════════════

        elif op == "mouse_click":
            self._ensure_desktop()
            if not self._mouse:
                return {"error": "Desktop control not available (PyAutoGUI not installed)"}
            return await self._mouse.click(kwargs.get("x"), kwargs.get("y"), button=kwargs.get("button", "left"))

        elif op == "mouse_move":
            self._ensure_desktop()
            if not self._mouse:
                return {"error": "Desktop control not available"}
            return await self._mouse.move_to(kwargs.get("x", 0), kwargs.get("y", 0))

        elif op == "mouse_scroll":
            self._ensure_desktop()
            if not self._mouse:
                return {"error": "Desktop control not available"}
            return await self._mouse.scroll(kwargs.get("amount", 0), kwargs.get("x"), kwargs.get("y"))

        elif op == "keyboard_type":
            self._ensure_desktop()
            if not self._keyboard:
                return {"error": "Desktop control not available"}
            return await self._keyboard.type_text(kwargs.get("text", ""))

        elif op == "keyboard_press":
            self._ensure_desktop()
            if not self._keyboard:
                return {"error": "Desktop control not available"}
            return await self._keyboard.press(kwargs.get("key") or kwargs.get("text", "enter"))

        elif op == "keyboard_hotkey":
            self._ensure_desktop()
            if not self._keyboard:
                return {"error": "Desktop control not available"}
            return await self._keyboard.hotkey(kwargs.get("hotkey") or kwargs.get("text", ""))

        elif op == "keyboard_shortcut":
            self._ensure_desktop()
            if not self._keyboard:
                return {"error": "Desktop control not available"}
            return await self._keyboard.shortcut(kwargs.get("shortcut_name") or kwargs.get("text", ""))

        elif op == "screenshot":
            self._ensure_desktop()
            if not self._screen:
                return {"error": "Desktop control not available"}
            return await self._screen.capture(path=kwargs.get("file_path"))

        # ═══════════════════════════════════════════════
        # SKILLS
        # ═══════════════════════════════════════════════

        elif op == "run_skill":
            skill_name = kwargs.get("skill_name", "")
            skill_params = kwargs.get("skill_params", {})
            if not skill_name:
                return {"error": "Provide skill_name. Use list_skills to see available skills."}

            # Check if it's a Python skill first
            from pathlib import Path
            skills_dir = Path.home() / ".plutus" / "skills"
            meta_path = skills_dir / f"{skill_name}.json"
            if meta_path.exists():
                import json as _json
                try:
                    meta = _json.loads(meta_path.read_text())
                    if meta.get("type") == "python":
                        from plutus.skills.python_runner import PythonSkillRunner
                        runner = PythonSkillRunner()
                        result = await runner.run(skill_name, skill_params)
                        return result.to_dict()
                except Exception:
                    pass

            # Fall back to simple skill engine
            registry = _ensure_skills()
            skill = registry.get(skill_name)
            if not skill:
                # Also check if Python skill exists without metadata
                script_path = skills_dir / f"{skill_name}.py"
                if script_path.exists():
                    from plutus.skills.python_runner import PythonSkillRunner
                    runner = PythonSkillRunner()
                    result = await runner.run(skill_name, skill_params)
                    return result.to_dict()
                available = registry.list_names()
                return {"error": f"Unknown skill: {skill_name}", "available_skills": available}
            engine = _get_skill_engine(self)
            result = await engine.run(skill, skill_params)
            return result.to_dict()

        elif op == "list_skills":
            registry = _ensure_skills()
            category = kwargs.get("category")
            
            # Get simple skills
            if category:
                skills = registry.find_by_category(category)
                simple_skills = [s.to_dict() for s in skills]
            else:
                simple_skills = registry.list_all()
            
            # Also list Python skills
            from pathlib import Path
            import json as _json
            skills_dir = Path.home() / ".plutus" / "skills"
            python_skills = []
            if skills_dir.exists():
                for meta_path in sorted(skills_dir.glob("*.json")):
                    try:
                        meta = _json.loads(meta_path.read_text())
                        if meta.get("type") == "python":
                            if category and meta.get("category") != category:
                                continue
                            python_skills.append({
                                "name": meta.get("name", meta_path.stem),
                                "type": "python",
                                "description": meta.get("description", ""),
                                "category": meta.get("category", "custom"),
                                "triggers": meta.get("triggers", []),
                                "required_params": meta.get("required_params", []),
                                "version": meta.get("version", 1),
                            })
                    except Exception:
                        pass
            
            all_skills = simple_skills + python_skills
            categories = list(set(
                (registry.list_categories() if not category else [category])
                + [s.get("category", "custom") for s in python_skills]
            ))
            return {"skills": all_skills, "categories": categories}

        # ═══════════════════════════════════════════════
        # SELF-IMPROVEMENT
        # ═══════════════════════════════════════════════

        elif op == "create_skill":
            skill_def = kwargs.get("skill_definition", {})
            if not skill_def:
                return {
                    "error": "Provide skill_definition with 'type' field ('simple' or 'python')",
                    "simple_example": {
                        "type": "simple",
                        "name": "twitter_post_tweet",
                        "description": "Post a tweet on Twitter/X",
                        "app": "Twitter",
                        "category": "social",
                        "triggers": ["tweet", "post on twitter"],
                        "required_params": ["tweet_text"],
                        "steps": [
                            {"description": "Open Twitter", "operation": "open_url", "params": {"url": "https://twitter.com/compose/tweet"}, "wait_after": 3.0},
                            {"description": "Type the tweet", "operation": "browser_type", "params": {"text": "{{tweet_text}}"}, "wait_after": 1.0},
                        ],
                    },
                    "python_example": {
                        "type": "python",
                        "name": "stock_checker",
                        "description": "Check stock prices and send a summary",
                        "category": "finance",
                        "triggers": ["stock", "stock price", "portfolio"],
                        "required_params": ["symbols"],
                        "code": (
                            'async def run(ctx, params):\n'
                            '    """Check stock prices for given symbols."""\n'
                            '    symbols = params.get("symbols", [])\n'
                            '    results = []\n'
                            '    for symbol in symbols:\n'
                            '        await ctx.browser_navigate(f"https://finance.yahoo.com/quote/{symbol}")\n'
                            '        text = await ctx.browser_get_text()\n'
                            '        price = await ctx.llm_ask(f"Extract the current price from: {text[:500]}")\n'
                            '        results.append({"symbol": symbol, "price": price})\n'
                            '        ctx.log(f"{symbol}: {price}")\n'
                            '    ctx.save_state("last_check", results)\n'
                            '    return {"success": True, "result": results}\n'
                        ),
                    },
                }
            skill_def["reason"] = kwargs.get("reason", "Agent created this skill")
            from plutus.skills.creator import get_skill_creator
            creator = get_skill_creator()
            registry = _ensure_skills()
            success, message, skill = creator.create_from_dict(skill_def, registry=registry)
            return {"success": success, "message": message}

        elif op == "update_skill":
            skill_def = kwargs.get("skill_definition", {})
            if not skill_def:
                return {"error": "Provide skill_definition"}
            skill_def["reason"] = kwargs.get("reason", "Agent updated this skill")
            from plutus.skills.creator import get_skill_creator
            creator = get_skill_creator()
            registry = _ensure_skills()
            success, message, skill = creator.create_from_dict(skill_def, registry=registry)
            return {"success": success, "message": message}

        elif op == "delete_skill":
            skill_name = kwargs.get("skill_name", "")
            if not skill_name:
                return {"error": "Provide skill_name"}
            from plutus.skills.creator import get_skill_creator
            creator = get_skill_creator()
            registry = _ensure_skills()
            success, message = creator.delete_skill(skill_name, registry=registry)
            return {"success": success, "message": message}

        elif op == "improvement_log":
            from plutus.skills.creator import get_skill_creator
            creator = get_skill_creator()
            return {"log": creator.get_improvement_log(limit=kwargs.get("limit", 50))}

        elif op == "improvement_stats":
            from plutus.skills.creator import get_skill_creator
            creator = get_skill_creator()
            return creator.get_improvement_stats()

        else:
            return {
                "error": f"Unknown operation: {op}",
                "available_operations": {
                    "os": ["open_app", "close_app", "open_url", "open_file", "open_folder",
                           "run_command", "list_processes", "kill_process",
                           "get_clipboard", "set_clipboard", "send_notification",
                           "list_apps", "system_info", "active_window"],
                    "browser_ref": ["navigate", "snapshot", "click_ref", "type_ref",
                                    "select_ref", "check_ref"],
                    "browser_legacy": ["browser_click", "browser_type", "browser_press",
                                       "fill_form", "select_option", "browser_hover",
                                       "browser_scroll", "browser_screenshot",
                                       "new_tab", "close_tab", "switch_tab", "list_tabs",
                                       "evaluate_js", "wait_for_text", "wait_for_navigation"],
                    "desktop_uia": ["desktop_snapshot", "desktop_click_ref", "desktop_type_ref",
                                    "desktop_select_ref", "desktop_toggle_ref",
                                    "desktop_scroll", "desktop_key",
                                    "desktop_list_windows", "desktop_focus_window"],
                    "desktop_fallback": ["mouse_click", "mouse_move", "mouse_scroll",
                               "keyboard_type", "keyboard_press", "keyboard_hotkey",
                               "keyboard_shortcut", "screenshot"],
                    "skills": ["run_skill", "list_skills"],
                    "self_improvement": ["create_skill", "update_skill", "delete_skill",
                                         "improvement_log", "improvement_stats"],
                },
            }
