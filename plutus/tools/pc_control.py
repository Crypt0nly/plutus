"""
PC Control Tool — OpenClaw-style unified interface for all machine interaction.

Architecture (matching OpenClaw's proven approach):
  1. SHELL-FIRST: Open apps, run commands, manage processes via OS-native commands
  2. BROWSER-SECOND: Control web pages via Playwright/CDP with DOM element refs
  3. VISION-FALLBACK: Screenshot + Anthropic Computer Use only when needed

This replaces the old PyAutoGUI/OCR approach with reliable, structured control.
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
    """Lazy-load the skill system."""
    global _skill_engine, _skill_registry
    if _skill_registry is None:
        from plutus.skills.registry import create_default_registry
        _skill_registry = create_default_registry()
    return _skill_registry


def _get_skill_engine(pc_tool):
    """Get or create the skill engine with the pc tool as executor."""
    global _skill_engine
    if _skill_engine is None:
        from plutus.skills.engine import SkillEngine
        _skill_engine = SkillEngine(pc_tool.execute)
    return _skill_engine


class PCControlTool(Tool):
    """
    Unified PC control tool — the primary way the AI interacts with the computer.
    
    Three layers (tried in order):
    1. OS Control: open_app, close_app, open_url, run_command, open_file, clipboard, etc.
    2. Browser Control: navigate, click, type, fill_form, get_page_snapshot, tabs, etc.
    3. Desktop Control: mouse, keyboard, screenshot (PyAutoGUI fallback for native apps)
    """

    def __init__(self):
        self._os = OSControl()
        self._browser = BrowserControl()
        # Lazy-load desktop control (PyAutoGUI) only when needed
        self._mouse = None
        self._keyboard = None
        self._screen = None

    def _ensure_desktop(self):
        """Lazy-load PyAutoGUI desktop control only when needed."""
        if self._mouse is None:
            try:
                from plutus.pc.mouse import MouseController
                from plutus.pc.keyboard import KeyboardController
                from plutus.pc.screen import ScreenReader
                self._mouse = MouseController("normal")
                self._keyboard = KeyboardController("natural")
                self._screen = ScreenReader()
            except Exception as e:
                logger.warning(f"Desktop control not available: {e}")

    @property
    def name(self) -> str:
        return "pc"

    @property
    def description(self) -> str:
        return (
            "Control the computer — open apps, browse the web, run commands, manage files.\n\n"
            "=== OS OPERATIONS (most reliable, use first) ===\n"
            "• open_app: Open any app by name (e.g., 'WhatsApp', 'Chrome', 'VS Code')\n"
            "• close_app: Close an app by name\n"
            "• open_url: Open a URL in the browser\n"
            "• open_file: Open a file with its default app\n"
            "• open_folder: Open a folder in file explorer\n"
            "• run_command: Execute a shell command\n"
            "• list_processes: List running processes\n"
            "• kill_process: Kill a process by name or PID\n"
            "• get_clipboard / set_clipboard: Read/write clipboard\n"
            "• send_notification: Send a desktop notification\n"
            "• list_apps: List apps Plutus can open\n"
            "• system_info: Get OS and system information\n"
            "• active_window: Get the currently focused window\n\n"
            "=== BROWSER OPERATIONS (for web interaction) ===\n"
            "• navigate: Go to a URL in the browser\n"
            "• browser_click: Click an element by CSS selector or text content\n"
            "• browser_type: Type into an input field by selector, label, or placeholder\n"
            "• browser_press: Press a key (Enter, Tab, Escape, etc.)\n"
            "• fill_form: Fill multiple form fields at once\n"
            "• select_option: Select from a dropdown\n"
            "• browser_hover: Hover over an element\n"
            "• browser_scroll: Scroll the page\n"
            "• get_page: Get structured page content (text, links, buttons, inputs)\n"
            "• get_elements: Get interactive elements on the page\n"
            "• browser_screenshot: Take a screenshot of the browser page\n"
            "• new_tab / close_tab / switch_tab / list_tabs: Manage browser tabs\n"
            "• evaluate_js: Run JavaScript on the page\n"
            "• wait_for_text: Wait for text to appear on the page\n\n"
            "=== DESKTOP OPERATIONS (fallback for native apps) ===\n"
            "• mouse_click: Click at screen coordinates\n"
            "• mouse_move: Move mouse to coordinates\n"
            "• mouse_scroll: Scroll at current position\n"
            "• keyboard_type: Type text into the focused app\n"
            "• keyboard_press: Press a key in the focused app\n"
            "• keyboard_hotkey: Press a key combination\n"
            "• keyboard_shortcut: Use a named shortcut (copy, paste, save, etc.)\n"
            "• screenshot: Take a screenshot of the entire screen\n"
            "• read_screen: OCR the screen to read text\n"
            "• find_text_on_screen: Find text on screen via OCR\n\n"
            "=== STRATEGY ===\n"
            "1. To open apps: ALWAYS use open_app (not clicking desktop icons)\n"
            "2. For web tasks: use navigate + browser_click/browser_type\n"
            "3. For native apps: use open_app first, then keyboard_type/keyboard_press\n"
            "4. Only use mouse_click as last resort when you know exact coordinates"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        # OS operations (Layer 1 — most reliable)
                        "open_app", "close_app", "open_url", "open_file", "open_folder",
                        "run_command", "list_processes", "kill_process",
                        "get_clipboard", "set_clipboard", "send_notification",
                        "list_apps", "system_info", "active_window",
                        # Browser operations (Layer 2 — for web)
                        "navigate", "browser_click", "browser_type", "browser_press",
                        "fill_form", "select_option", "browser_hover", "browser_scroll",
                        "get_page", "get_elements", "browser_screenshot",
                        "new_tab", "close_tab", "switch_tab", "list_tabs",
                        "evaluate_js", "wait_for_text",
                        # Desktop operations (Layer 3 — fallback)
                        "mouse_click", "mouse_move", "mouse_scroll",
                        "keyboard_type", "keyboard_press", "keyboard_hotkey", "keyboard_shortcut",
                        "screenshot", "read_screen", "find_text_on_screen",
                        # Skill operations (pre-built app workflows)
                        "run_skill", "list_skills",
                    ],
                    "description": "The operation to perform",
                },
                # OS params
                "app_name": {"type": "string", "description": "App name for open_app/close_app (e.g., 'WhatsApp', 'Chrome', 'VS Code')"},
                "url": {"type": "string", "description": "URL for navigate/open_url"},
                "command": {"type": "string", "description": "Shell command for run_command"},
                "file_path": {"type": "string", "description": "File or folder path"},
                "process_name": {"type": "string", "description": "Process name for kill_process/list_processes"},
                "pid": {"type": "integer", "description": "Process ID for kill_process"},
                "notification_title": {"type": "string", "description": "Notification title"},
                "notification_message": {"type": "string", "description": "Notification message"},
                # Browser params
                "selector": {"type": "string", "description": "CSS selector for browser element targeting"},
                "text": {"type": "string", "description": "Text content to find/click/type"},
                "label": {"type": "string", "description": "Input field label for browser_type"},
                "placeholder": {"type": "string", "description": "Input field placeholder for browser_type"},
                "role": {"type": "string", "description": "ARIA role for element targeting (button, link, textbox, etc.)"},
                "role_name": {"type": "string", "description": "ARIA role name for element targeting"},
                "press_enter": {"type": "boolean", "description": "Press Enter after typing"},
                "tab_id": {"type": "string", "description": "Tab ID for tab operations"},
                "js_code": {"type": "string", "description": "JavaScript code for evaluate_js"},
                "fields": {
                    "type": "array",
                    "description": "Form fields for fill_form: [{selector?, label?, placeholder?, value}]",
                    "items": {
                        "type": "object",
                        "properties": {
                            "selector": {"type": "string"},
                            "label": {"type": "string"},
                            "placeholder": {"type": "string"},
                            "value": {"type": "string"},
                        },
                    },
                },
                "direction": {"type": "string", "enum": ["up", "down"], "description": "Scroll direction"},
                "amount": {"type": "integer", "description": "Scroll amount in pixels"},
                "filter_type": {"type": "string", "enum": ["links", "buttons", "inputs", "all"], "description": "Element type filter for get_elements"},
                "full_page": {"type": "boolean", "description": "Full page screenshot"},
                "browser": {"type": "string", "description": "Specific browser for open_url"},
                # Desktop params
                "x": {"type": "integer", "description": "X coordinate for mouse operations"},
                "y": {"type": "integer", "description": "Y coordinate for mouse operations"},
                "key": {"type": "string", "description": "Key name for keyboard_press (enter, tab, escape, etc.)"},
                "hotkey": {"type": "string", "description": "Key combination for keyboard_hotkey (ctrl+c, alt+tab, etc.)"},
                "shortcut_name": {"type": "string", "description": "Named shortcut for keyboard_shortcut (copy, paste, save, undo, etc.)"},
                "timeout": {"type": "integer", "description": "Timeout in milliseconds"},
                "cwd": {"type": "string", "description": "Working directory for run_command"},
                "double_click": {"type": "boolean", "description": "Double-click for browser_click"},
                "right_click": {"type": "boolean", "description": "Right-click for browser_click"},
                # Skill params
                "skill_name": {"type": "string", "description": "Skill name for run_skill (e.g., 'whatsapp_send_message', 'calendar_create_event')"},
                "skill_params": {
                    "type": "object",
                    "description": "Parameters for the skill (e.g., {contact: 'Mom', message: 'Hello!'} for whatsapp_send_message)",
                },
                "category": {"type": "string", "description": "Filter skills by category for list_skills"},
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
        """Route the operation to the correct layer."""

        # ═══════════════════════════════════════════════
        # LAYER 1: OS Operations (shell commands — most reliable)
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
            return await self._os.run_command(
                cmd,
                timeout=kwargs.get("timeout", 30),
                cwd=kwargs.get("cwd"),
            )

        elif op == "list_processes":
            return await self._os.list_processes(
                filter_name=kwargs.get("process_name")
            )

        elif op == "kill_process":
            return await self._os.kill_process(
                pid=kwargs.get("pid"),
                name=kwargs.get("process_name") or kwargs.get("text"),
            )

        elif op == "get_clipboard":
            return await self._os.get_clipboard()

        elif op == "set_clipboard":
            text = kwargs.get("text", "")
            return await self._os.set_clipboard(text)

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
        # LAYER 2: Browser Operations (Playwright/CDP — for web)
        # ═══════════════════════════════════════════════

        elif op == "navigate":
            url = kwargs.get("url", "")
            if not url:
                return {"error": "Provide url"}
            return await self._browser.navigate(url, tab_id=kwargs.get("tab_id"))

        elif op == "browser_click":
            return await self._browser.click(
                selector=kwargs.get("selector"),
                text=kwargs.get("text"),
                role=kwargs.get("role"),
                role_name=kwargs.get("role_name"),
                double_click=kwargs.get("double_click", False),
                right_click=kwargs.get("right_click", False),
                timeout=kwargs.get("timeout", 5000),
            )

        elif op == "browser_type":
            text = kwargs.get("text", "")
            if not text:
                return {"error": "Provide text to type"}
            return await self._browser.type_text(
                text=text,
                selector=kwargs.get("selector"),
                label=kwargs.get("label"),
                placeholder=kwargs.get("placeholder"),
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
            return await self._browser.select_option(
                value=kwargs.get("text", ""),
                selector=kwargs.get("selector"),
                label=kwargs.get("label"),
            )

        elif op == "browser_hover":
            return await self._browser.hover(
                selector=kwargs.get("selector"),
                text=kwargs.get("text"),
            )

        elif op == "browser_scroll":
            return await self._browser.scroll(
                direction=kwargs.get("direction", "down"),
                amount=kwargs.get("amount", 500),
            )

        elif op == "get_page":
            return await self._browser.get_page_snapshot()

        elif op == "get_elements":
            return await self._browser.get_page_elements(
                filter_type=kwargs.get("filter_type")
            )

        elif op == "browser_screenshot":
            return await self._browser.screenshot(
                full_page=kwargs.get("full_page", False)
            )

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
            return await self._browser.wait_for_text(
                text, timeout=kwargs.get("timeout", 10000)
            )

        # ═══════════════════════════════════════════════
        # LAYER 3: Desktop Operations (PyAutoGUI — fallback for native apps)
        # ═══════════════════════════════════════════════

        elif op == "mouse_click":
            self._ensure_desktop()
            if not self._mouse:
                return {"error": "Desktop control not available (PyAutoGUI not installed)"}
            return await self._mouse.click(
                kwargs.get("x"), kwargs.get("y"),
                button=kwargs.get("button", "left"),
            )

        elif op == "mouse_move":
            self._ensure_desktop()
            if not self._mouse:
                return {"error": "Desktop control not available"}
            return await self._mouse.move_to(
                kwargs.get("x", 0), kwargs.get("y", 0),
            )

        elif op == "mouse_scroll":
            self._ensure_desktop()
            if not self._mouse:
                return {"error": "Desktop control not available"}
            return await self._mouse.scroll(
                kwargs.get("amount", 0),
                kwargs.get("x"), kwargs.get("y"),
            )

        elif op == "keyboard_type":
            self._ensure_desktop()
            if not self._keyboard:
                return {"error": "Desktop control not available"}
            return await self._keyboard.type_text(
                kwargs.get("text", ""),
            )

        elif op == "keyboard_press":
            self._ensure_desktop()
            if not self._keyboard:
                return {"error": "Desktop control not available"}
            return await self._keyboard.press(
                kwargs.get("key") or kwargs.get("text", "enter"),
            )

        elif op == "keyboard_hotkey":
            self._ensure_desktop()
            if not self._keyboard:
                return {"error": "Desktop control not available"}
            return await self._keyboard.hotkey(
                kwargs.get("hotkey") or kwargs.get("text", ""),
            )

        elif op == "keyboard_shortcut":
            self._ensure_desktop()
            if not self._keyboard:
                return {"error": "Desktop control not available"}
            return await self._keyboard.shortcut(
                kwargs.get("shortcut_name") or kwargs.get("text", ""),
            )

        elif op == "screenshot":
            self._ensure_desktop()
            if not self._screen:
                return {"error": "Desktop control not available"}
            return await self._screen.capture(
                path=kwargs.get("file_path"),
            )

        elif op == "read_screen":
            self._ensure_desktop()
            if not self._screen:
                return {"error": "Desktop control not available"}
            return await self._screen.read_text()

        elif op == "find_text_on_screen":
            self._ensure_desktop()
            if not self._screen:
                return {"error": "Desktop control not available"}
            return await self._screen.find_text(
                kwargs.get("text", ""),
            )

        # ═══════════════════════════════════════════════
        # SKILLS: Pre-built app workflows
        # ═══════════════════════════════════════════════

        elif op == "run_skill":
            skill_name = kwargs.get("skill_name", "")
            skill_params = kwargs.get("skill_params", {})
            if not skill_name:
                return {"error": "Provide skill_name. Use list_skills to see available skills."}
            registry = _ensure_skills()
            skill = registry.get(skill_name)
            if not skill:
                available = registry.list_names()
                return {"error": f"Unknown skill: {skill_name}", "available_skills": available}
            engine = _get_skill_engine(self)
            result = await engine.run(skill, skill_params)
            return result.to_dict()

        elif op == "list_skills":
            registry = _ensure_skills()
            category = kwargs.get("category")
            if category:
                skills = registry.find_by_category(category)
                return {"skills": [s.to_dict() for s in skills], "category": category}
            return {"skills": registry.list_all(), "categories": registry.list_categories()}

        else:
            return {
                "error": f"Unknown operation: {op}",
                "available_operations": {
                    "os": ["open_app", "close_app", "open_url", "open_file", "open_folder",
                           "run_command", "list_processes", "kill_process",
                           "get_clipboard", "set_clipboard", "send_notification",
                           "list_apps", "system_info", "active_window"],
                    "browser": ["navigate", "browser_click", "browser_type", "browser_press",
                               "fill_form", "select_option", "browser_hover", "browser_scroll",
                               "get_page", "get_elements", "browser_screenshot",
                               "new_tab", "close_tab", "switch_tab", "list_tabs",
                               "evaluate_js", "wait_for_text"],
                    "desktop": ["mouse_click", "mouse_move", "mouse_scroll",
                               "keyboard_type", "keyboard_press", "keyboard_hotkey",
                               "keyboard_shortcut", "screenshot", "read_screen",
                               "find_text_on_screen"],
                    "skills": ["run_skill", "list_skills"],
                },
            }
