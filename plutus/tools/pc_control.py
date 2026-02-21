"""PC Control Tool — context-aware unified interface for all machine interaction.

This is the main LLM-facing tool that gives the AI "friendly ghost" control
over the entire PC. Every action is wrapped with context awareness:

  1. Before any write action (click, type, etc.), Plutus checks which window
     is active and reports it to the LLM.
  2. If a `target_app` is specified, Plutus auto-focuses that app first.
  3. Every result includes `_context` with the current active app/window,
     so the LLM always knows exactly where it is.

This prevents the #1 problem with computer-use agents: typing into the wrong window.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from plutus.pc.context import ContextEngine, ActionGuard, get_context_engine
from plutus.pc.keyboard import KeyboardController
from plutus.pc.mouse import MouseController
from plutus.pc.screen import ScreenReader, ScreenRegion
from plutus.pc.windows import WindowManager
from plutus.pc.workflow import WorkflowEngine, WorkflowStep, Workflow
from plutus.tools.base import Tool

logger = logging.getLogger("plutus.pc.control")


class PCControlTool(Tool):
    """Context-aware PC control — mouse, keyboard, screen, windows, workflows.

    Every action is guarded by the ContextEngine:
    - Write actions (click, type, etc.) refresh context first
    - If target_app is set, auto-focuses the correct window
    - Every result includes _context with active app/window info
    - Action history is logged for debugging
    """

    def __init__(self):
        self._mouse = MouseController("normal")
        self._keyboard = KeyboardController("natural")
        self._screen = ScreenReader()
        self._windows = WindowManager()
        self._workflow = WorkflowEngine(
            self._mouse, self._keyboard, self._screen, self._windows
        )
        # Context awareness
        self._ctx = get_context_engine()
        self._guard = ActionGuard(self._ctx)

    @property
    def name(self) -> str:
        return "pc"

    @property
    def description(self) -> str:
        return (
            "Control the PC like a friendly ghost — move the mouse smoothly, click, "
            "type naturally, read the screen, manage windows, and run workflows. "
            "This is your primary tool for interacting with the desktop.\n\n"
            "CONTEXT AWARENESS: Every result includes `_context` telling you which "
            "app/window is currently active. Use `target_app` parameter to auto-focus "
            "the correct app before acting (e.g., target_app='WhatsApp' ensures you "
            "type into WhatsApp, not whatever else is open).\n\n"
            "NEW: `get_context` operation — check which app/window is active right now.\n\n"
            "MOUSE operations: move, click, double_click, right_click, drag, scroll, hover\n"
            "KEYBOARD operations: type, press, hotkey, shortcut, key_down, key_up\n"
            "SCREEN operations: screenshot, read_screen, find_text, find_elements, "
            "get_pixel_color, find_color, wait_for_text, wait_for_change, screen_info\n"
            "WINDOW operations: list_windows, find_window, focus, close_window, minimize, maximize, "
            "move_window, resize, snap_left, snap_right, snap_top, snap_bottom, snap_quarter, "
            "tile, active_window, get_context\n"
            "WORKFLOW operations: run_workflow, save_workflow, list_workflows, "
            "list_templates, get_template, delete_workflow\n"
            "SHORTCUT operations: list_shortcuts\n\n"
            "IMPORTANT TIPS:\n"
            "- ALWAYS use `target_app` when clicking/typing into a specific app\n"
            "  e.g., pc(operation='type', text='Hello', target_app='WhatsApp')\n"
            "- Use `get_context` to check which app is active before acting\n"
            "- Use `focus` to switch to a specific app window\n"
            "- Every result has `_context.active_app` so you always know where you are\n"
            "- Use 'screenshot' + 'find_text' to see what's on screen then click it\n"
            "- Use 'shortcut' with names like 'copy', 'paste', 'save', 'new_tab'"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        # Context
                        "get_context",
                        # Mouse
                        "move", "click", "double_click", "right_click", "drag", "scroll", "hover",
                        # Keyboard
                        "type", "press", "hotkey", "shortcut", "key_down", "key_up",
                        # Screen
                        "screenshot", "read_screen", "find_text", "find_elements",
                        "get_pixel_color", "find_color", "wait_for_text", "wait_for_change", "screen_info",
                        # Windows
                        "list_windows", "find_window", "focus", "close_window", "minimize", "maximize",
                        "move_window", "resize", "snap_left", "snap_right", "snap_top", "snap_bottom",
                        "snap_quarter", "tile", "active_window",
                        # Workflow
                        "run_workflow", "save_workflow", "list_workflows",
                        "list_templates", "get_template", "delete_workflow",
                        # Info
                        "list_shortcuts",
                    ],
                    "description": "The PC operation to perform",
                },
                "target_app": {
                    "type": "string",
                    "description": (
                        "IMPORTANT: The app/window that this action targets. "
                        "If set, Plutus will auto-focus this app before acting. "
                        "Use this to prevent typing/clicking into the wrong window. "
                        "Examples: 'WhatsApp', 'Chrome', 'VS Code', 'Notepad', 'Spotify'"
                    ),
                },
                "x": {"type": "integer", "description": "X coordinate (mouse/screen operations)"},
                "y": {"type": "integer", "description": "Y coordinate (mouse/screen operations)"},
                "text": {"type": "string", "description": "Text to type, key to press, or search target"},
                "button": {"type": "string", "enum": ["left", "middle", "right"], "description": "Mouse button"},
                "speed": {"type": "string", "description": "Speed profile: 'careful', 'normal', 'fast', 'instant'"},
                "smooth": {"type": "boolean", "description": "Use smooth/natural movement (default: true)"},
                "amount": {"type": "integer", "description": "Scroll amount (positive=up, negative=down)"},
                "clicks": {"type": "integer", "description": "Number of clicks"},
                "start_x": {"type": "integer", "description": "Drag start X"},
                "start_y": {"type": "integer", "description": "Drag start Y"},
                "end_x": {"type": "integer", "description": "Drag end X"},
                "end_y": {"type": "integer", "description": "Drag end Y"},
                "query": {"type": "string", "description": "Window title or app name to find/focus"},
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Multiple window names for tile operation",
                },
                "width": {"type": "integer", "description": "Width for resize"},
                "height": {"type": "integer", "description": "Height for resize"},
                "position": {"type": "string", "description": "Quarter position: top_left, top_right, bottom_left, bottom_right"},
                "path": {"type": "string", "description": "File path for screenshot"},
                "region": {
                    "type": "object",
                    "description": "Screen region {x, y, width, height}",
                    "properties": {
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                        "width": {"type": "integer"},
                        "height": {"type": "integer"},
                    },
                },
                "timeout": {"type": "number", "description": "Timeout in seconds for wait operations"},
                "color": {"type": "string", "description": "Hex color for find_color (e.g. '#ff0000')"},
                "tolerance": {"type": "integer", "description": "Color matching tolerance (0-255)"},
                "duration": {"type": "number", "description": "Duration for hover"},
                "times": {"type": "integer", "description": "Number of key presses"},
                "clear_first": {"type": "boolean", "description": "Clear field before typing"},
                "workflow_name": {"type": "string", "description": "Name of workflow to run/save/delete"},
                "workflow_description": {"type": "string", "description": "Description for new workflow"},
                "workflow_steps": {
                    "type": "array",
                    "description": "Steps for workflow: [{action, params, description, delay_after}]",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string"},
                            "params": {"type": "object"},
                            "description": {"type": "string"},
                            "delay_after": {"type": "number"},
                        },
                    },
                },
                "case_sensitive": {"type": "boolean", "description": "Case-sensitive text search"},
                "include_base64": {"type": "boolean", "description": "Include base64 in screenshot"},
            },
            "required": ["operation"],
        }

    async def execute(self, **kwargs: Any) -> str:
        op = kwargs.get("operation", "")
        target_app = kwargs.get("target_app")

        try:
            # ─── Pre-action context check ───
            # For write operations, verify we're in the right window
            guard_result = await self._guard.check_before_action(
                operation=op,
                params=kwargs,
                target_app=target_app,
            )

            if not guard_result["proceed"]:
                # Context check failed — wrong window and couldn't focus
                warning = guard_result.get("warning", "Context check failed")
                error_result = {
                    "error": warning,
                    "operation": op,
                    "hint": (
                        "The target app could not be focused. Try using "
                        "pc(operation='focus', query='AppName') first, or "
                        "pc(operation='list_windows') to see what's available."
                    ),
                }
                return json.dumps(self._ctx.enrich_result(error_result, op), default=str)

            # If focus was changed, log it
            if guard_result.get("focus_result") and not guard_result["focus_result"].get("already_active"):
                logger.info(
                    f"Auto-focused {target_app} before {op}: "
                    f"{guard_result['focus_result'].get('app')} - {guard_result['focus_result'].get('title')}"
                )

            # ─── Context Query ───
            if op == "get_context":
                ctx = await self._ctx.get_context(force_refresh=True)
                result = ctx.to_dict()
                result["summary"] = ctx.summary()
                return json.dumps(result, default=str)

            # ─── Mouse ───
            elif op == "move":
                result = await self._mouse.move_to(
                    kwargs.get("x", 0), kwargs.get("y", 0),
                    speed=kwargs.get("speed"),
                    smooth=kwargs.get("smooth", True),
                )
            elif op == "click":
                result = await self._mouse.click(
                    kwargs.get("x"), kwargs.get("y"),
                    button=kwargs.get("button", "left"),
                    clicks=kwargs.get("clicks", 1),
                )
            elif op == "double_click":
                result = await self._mouse.double_click(kwargs.get("x"), kwargs.get("y"))
            elif op == "right_click":
                result = await self._mouse.right_click(kwargs.get("x"), kwargs.get("y"))
            elif op == "drag":
                result = await self._mouse.drag(
                    kwargs.get("start_x", 0), kwargs.get("start_y", 0),
                    kwargs.get("end_x", 0), kwargs.get("end_y", 0),
                    button=kwargs.get("button", "left"),
                )
            elif op == "scroll":
                result = await self._mouse.scroll(
                    kwargs.get("amount", 0),
                    kwargs.get("x"), kwargs.get("y"),
                    smooth=kwargs.get("smooth", True),
                )
            elif op == "hover":
                result = await self._mouse.hover(
                    kwargs.get("x", 0), kwargs.get("y", 0),
                    duration=kwargs.get("duration", 0.5),
                )

            # ─── Keyboard ───
            elif op == "type":
                result = await self._keyboard.type_text(
                    kwargs.get("text", ""),
                    speed=kwargs.get("speed"),
                    clear_first=kwargs.get("clear_first", False),
                )
            elif op == "press":
                result = await self._keyboard.press(
                    kwargs.get("text", "enter"),
                    times=kwargs.get("times", 1),
                )
            elif op == "hotkey":
                result = await self._keyboard.hotkey(kwargs.get("text", ""))
            elif op == "shortcut":
                result = await self._keyboard.shortcut(kwargs.get("text", ""))
            elif op == "key_down":
                result = await self._keyboard.key_down(kwargs.get("text", ""))
            elif op == "key_up":
                result = await self._keyboard.key_up(kwargs.get("text", ""))

            # ─── Screen ───
            elif op == "screenshot":
                region = self._parse_region(kwargs.get("region"))
                result = await self._screen.capture(
                    region=region,
                    path=kwargs.get("path"),
                    include_base64=kwargs.get("include_base64", False),
                )
            elif op == "read_screen":
                region = self._parse_region(kwargs.get("region"))
                result = await self._screen.read_text(region=region)
            elif op == "find_text":
                region = self._parse_region(kwargs.get("region"))
                result = await self._screen.find_text(
                    kwargs.get("text", ""),
                    region=region,
                    case_sensitive=kwargs.get("case_sensitive", False),
                )
            elif op == "find_elements":
                region = self._parse_region(kwargs.get("region"))
                result = await self._screen.find_elements(region=region)
            elif op == "get_pixel_color":
                result = await self._screen.get_pixel_color(
                    kwargs.get("x", 0), kwargs.get("y", 0)
                )
            elif op == "find_color":
                region = self._parse_region(kwargs.get("region"))
                result = await self._screen.find_color(
                    kwargs.get("color", "#000000"),
                    tolerance=kwargs.get("tolerance", 20),
                    region=region,
                )
            elif op == "wait_for_text":
                region = self._parse_region(kwargs.get("region"))
                result = await self._screen.wait_for_text(
                    kwargs.get("text", ""),
                    timeout=kwargs.get("timeout", 30.0),
                    region=region,
                )
            elif op == "wait_for_change":
                region = self._parse_region(kwargs.get("region"))
                result = await self._screen.wait_for_change(
                    region=region,
                    timeout=kwargs.get("timeout", 30.0),
                )
            elif op == "screen_info":
                result = await self._screen.get_screen_info()

            # ─── Windows ───
            elif op == "list_windows":
                result = {"windows": await self._windows.list_windows()}
            elif op == "find_window":
                found = await self._windows.find_window(kwargs.get("query", ""))
                result = {"found": found is not None, "window": found}
            elif op == "focus":
                result = await self._windows.focus(kwargs.get("query", ""))
            elif op == "close_window":
                result = await self._windows.close(kwargs.get("query", ""))
            elif op == "minimize":
                result = await self._windows.minimize(kwargs.get("query", ""))
            elif op == "maximize":
                result = await self._windows.maximize(kwargs.get("query", ""))
            elif op == "move_window":
                result = await self._windows.move(
                    kwargs.get("query", ""),
                    kwargs.get("x", 0), kwargs.get("y", 0),
                )
            elif op == "resize":
                result = await self._windows.resize(
                    kwargs.get("query", ""),
                    kwargs.get("width", 800), kwargs.get("height", 600),
                )
            elif op == "snap_left":
                result = await self._windows.snap_left(kwargs.get("query", ""))
            elif op == "snap_right":
                result = await self._windows.snap_right(kwargs.get("query", ""))
            elif op == "snap_top":
                result = await self._windows.snap_top(kwargs.get("query", ""))
            elif op == "snap_bottom":
                result = await self._windows.snap_bottom(kwargs.get("query", ""))
            elif op == "snap_quarter":
                result = await self._windows.snap_quarter(
                    kwargs.get("query", ""),
                    kwargs.get("position", "top_left"),
                )
            elif op == "tile":
                result = await self._windows.tile_windows(kwargs.get("queries", []))
            elif op == "active_window":
                # Enhanced: return full context, not just window info
                ctx = await self._ctx.get_context(force_refresh=True)
                result = {
                    "title": ctx.active_window_title,
                    "app": ctx.active_app_name,
                    "pid": ctx.active_window_pid,
                    "category": ctx.active_app_category,
                    "browser_tab": ctx.active_browser_tab or None,
                    "document": ctx.active_document or None,
                }

            # ─── Workflow ───
            elif op == "run_workflow":
                name = kwargs.get("workflow_name", "")
                wf = self._workflow.load(name)
                if not wf:
                    wf = self._workflow.get_template(name)
                if not wf:
                    return json.dumps({"error": f"Workflow not found: {name}"})
                wf_result = await self._workflow.run(wf)
                result = wf_result.to_dict()
            elif op == "save_workflow":
                steps = []
                for s in kwargs.get("workflow_steps", []):
                    steps.append(WorkflowStep(
                        action=s.get("action", ""),
                        params=s.get("params", {}),
                        description=s.get("description", ""),
                        delay_after=s.get("delay_after", 0.3),
                    ))
                wf = Workflow(
                    name=kwargs.get("workflow_name", "unnamed"),
                    description=kwargs.get("workflow_description", ""),
                    steps=steps,
                )
                path = self._workflow.save(wf)
                result = {"saved": True, "path": path, "workflow": wf.to_dict()}
            elif op == "list_workflows":
                result = {
                    "workflows": self._workflow.list_workflows(),
                    "templates": self._workflow.list_templates(),
                }
            elif op == "list_templates":
                result = {"templates": self._workflow.list_templates()}
            elif op == "get_template":
                wf = self._workflow.get_template(kwargs.get("workflow_name", ""))
                result = wf.to_dict() if wf else {"error": "Template not found"}
            elif op == "delete_workflow":
                deleted = self._workflow.delete(kwargs.get("workflow_name", ""))
                result = {"deleted": deleted}

            # ─── Info ───
            elif op == "list_shortcuts":
                result = {"shortcuts": KeyboardController.list_shortcuts()}

            else:
                result = {"error": f"Unknown operation: {op}"}

            # ─── Post-action: enrich result with context ───
            if isinstance(result, dict):
                result = await self._guard.post_action(op, kwargs, result)

            return json.dumps(result, default=str)

        except Exception as e:
            error_result = {"error": str(e), "operation": op}
            # Still try to enrich with context even on error
            try:
                error_result = self._ctx.enrich_result(error_result, op)
            except Exception:
                pass
            return json.dumps(error_result, default=str)

    def _parse_region(self, region_data: dict | None) -> ScreenRegion | None:
        """Parse a region dict into a ScreenRegion."""
        if not region_data:
            return None
        return ScreenRegion(
            x=region_data.get("x", 0),
            y=region_data.get("y", 0),
            width=region_data.get("width", 0),
            height=region_data.get("height", 0),
        )
