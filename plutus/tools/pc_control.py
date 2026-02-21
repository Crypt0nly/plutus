"""
PC Control Tool — OpenClaw-style unified interface for all machine interaction.

Architecture:
  1. SHELL: Open apps, run commands, manage processes via OS-native commands
  2. BROWSER (Accessibility Tree + Refs): Navigate web, snapshot page, interact by ref numbers
  3. DESKTOP (PyAutoGUI fallback): Mouse/keyboard for native apps only

The KEY INNOVATION is the snapshot → ref → act loop:
  1. snapshot() → returns numbered accessibility tree of the page
  2. LLM reads the tree, picks a ref number
  3. click_ref(3) / type_ref(2, "hello") → precise, deterministic interaction
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
    
    Two clean layers:
    1. OS Control: shell commands for apps, files, processes
    2. Browser Control: accessibility tree snapshots + ref-based interaction for web
    + Desktop fallback for native apps when needed
    """

    def __init__(self):
        self._os = OSControl()
        self._browser = BrowserControl()
        self._mouse = None
        self._keyboard = None
        self._screen = None

    def _ensure_desktop(self):
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
            "Control the computer — open apps, browse the web, run commands.\n\n"
            "=== OS OPERATIONS (always use for opening apps and system tasks) ===\n"
            "• open_app: Open any app by name (WhatsApp, Chrome, Spotify, etc.)\n"
            "• close_app, open_url, open_file, open_folder, run_command\n"
            "• list_processes, kill_process, get_clipboard, set_clipboard\n"
            "• send_notification, list_apps, system_info, active_window\n\n"
            "=== BROWSER OPERATIONS (snapshot → ref → act loop) ===\n"
            "The core loop for ALL web interaction:\n"
            "  1. navigate(url) → opens page and returns accessibility tree snapshot\n"
            "  2. snapshot() → refreshes the accessibility tree with numbered [ref] elements\n"
            "  3. click_ref(ref=5) → clicks element [5] from the snapshot\n"
            "  4. type_ref(ref=3, text='hello') → types into element [3]\n"
            "  5. snapshot() → verify the result\n\n"
            "Snapshot example:\n"
            "  Page: Google — https://www.google.com\n"
            "  [1] textbox 'Search' value='' focused\n"
            "  [2] button 'Google Search'\n"
            "  [3] button 'I'm Feeling Lucky'\n"
            "  [4] link 'Gmail'\n\n"
            "Then: type_ref(ref=1, text='weather today', press_enter=true)\n\n"
            "Other browser ops: scroll, new_tab, close_tab, switch_tab, list_tabs,\n"
            "  browser_press, fill_form, evaluate_js, wait_for_text, wait_for_navigation\n\n"
            "=== DESKTOP OPERATIONS (fallback for native apps only) ===\n"
            "• keyboard_type, keyboard_press, keyboard_hotkey, keyboard_shortcut\n"
            "• mouse_click, mouse_move, mouse_scroll, screenshot\n\n"
            "=== SKILLS (pre-built app workflows) ===\n"
            "• run_skill, list_skills, create_skill, update_skill, delete_skill\n\n"
            "=== STRATEGY ===\n"
            "1. Open apps → ALWAYS use open_app\n"
            "2. Web tasks → navigate + snapshot + click_ref/type_ref\n"
            "3. Native apps → open_app + keyboard_type/keyboard_press\n"
            "4. NEVER guess coordinates — use snapshot to see what's on the page"
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
                        # Desktop operations (fallback)
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
                # Ref-based browser params (PRIMARY)
                "ref": {"type": "integer", "description": "Element ref number from snapshot (e.g., 5 to click [5])"},
                "text": {"type": "string", "description": "Text to type, find, or match"},
                "press_enter": {"type": "boolean", "description": "Press Enter after typing"},
                "clear_first": {"type": "boolean", "description": "Clear field before typing (default: true)"},
                "checked": {"type": "boolean", "description": "Check state for check_ref"},
                "value": {"type": "string", "description": "Value for select_ref"},
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
                "double_click": {"type": "boolean", "description": "Double-click"},
                "right_click": {"type": "boolean", "description": "Right-click"},
                # Desktop params
                "x": {"type": "integer", "description": "X coordinate for mouse"},
                "y": {"type": "integer", "description": "Y coordinate for mouse"},
                "button": {"type": "string", "description": "Mouse button (left/right/middle)"},
                "key": {"type": "string", "description": "Key name for keyboard_press"},
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
            return await self._browser.select_option(
                value=kwargs.get("text", ""),
                selector=kwargs.get("selector"),
                label=kwargs.get("label"),
            )

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
        # LAYER 3: Desktop (PyAutoGUI — native apps only)
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

        # ═══════════════════════════════════════════════
        # SELF-IMPROVEMENT
        # ═══════════════════════════════════════════════

        elif op == "create_skill":
            skill_def = kwargs.get("skill_definition", {})
            if not skill_def:
                return {
                    "error": "Provide skill_definition",
                    "example": {
                        "name": "twitter_post_tweet",
                        "description": "Post a tweet on Twitter/X",
                        "app": "Twitter",
                        "category": "social",
                        "triggers": ["tweet", "post on twitter"],
                        "required_params": ["tweet_text"],
                        "optional_params": [],
                        "steps": [
                            {"description": "Open Twitter", "operation": "open_url", "params": {"url": "https://twitter.com/compose/tweet"}, "wait_after": 3.0},
                            {"description": "Type the tweet", "operation": "browser_type", "params": {"text": "{{tweet_text}}", "selector": "[data-testid='tweetTextarea_0']"}, "wait_after": 1.0},
                            {"description": "Click Post", "operation": "browser_click", "params": {"text": "Post"}, "wait_after": 2.0},
                        ],
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
                    "desktop": ["mouse_click", "mouse_move", "mouse_scroll",
                               "keyboard_type", "keyboard_press", "keyboard_hotkey",
                               "keyboard_shortcut", "screenshot"],
                    "skills": ["run_skill", "list_skills"],
                    "self_improvement": ["create_skill", "update_skill", "delete_skill",
                                         "improvement_log", "improvement_stats"],
                },
            }
