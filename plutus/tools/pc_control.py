"""PC Control Tool — the unified interface for all machine interaction.

This is the main LLM-facing tool that gives the AI "friendly ghost" control
over the entire PC. It wraps mouse, keyboard, screen, windows, and workflow
into a single tool with clear, intuitive operations.

The AI calls this tool to interact with the machine just like a human would:
move the mouse, click buttons, type text, read the screen, manage windows,
and run multi-step workflows.
"""

from __future__ import annotations

import json
from typing import Any

from plutus.pc.keyboard import KeyboardController
from plutus.pc.mouse import MouseController
from plutus.pc.screen import ScreenReader, ScreenRegion
from plutus.pc.windows import WindowManager
from plutus.pc.workflow import WorkflowEngine, WorkflowStep, Workflow
from plutus.tools.base import Tool


class PCControlTool(Tool):
    """Unified PC control — mouse, keyboard, screen, windows, workflows."""

    def __init__(self):
        self._mouse = MouseController("normal")
        self._keyboard = KeyboardController("natural")
        self._screen = ScreenReader()
        self._windows = WindowManager()
        self._workflow = WorkflowEngine(
            self._mouse, self._keyboard, self._screen, self._windows
        )

    @property
    def name(self) -> str:
        return "pc"

    @property
    def description(self) -> str:
        return (
            "Control the PC like a friendly ghost — move the mouse smoothly, click, "
            "type naturally, read the screen, manage windows, and run workflows. "
            "This is your primary tool for interacting with the desktop.\n\n"
            "MOUSE operations: move, click, double_click, right_click, drag, scroll, hover\n"
            "KEYBOARD operations: type, press, hotkey, shortcut, key_down, key_up\n"
            "SCREEN operations: screenshot, read_screen, find_text, find_elements, "
            "get_pixel_color, find_color, wait_for_text, wait_for_change, screen_info\n"
            "WINDOW operations: list_windows, find_window, focus, close, minimize, maximize, "
            "move_window, resize, snap_left, snap_right, snap_top, snap_bottom, snap_quarter, "
            "tile, active_window\n"
            "WORKFLOW operations: run_workflow, save_workflow, list_workflows, "
            "list_templates, get_template, delete_workflow\n"
            "SHORTCUT operations: list_shortcuts — shows all available keyboard shortcuts\n\n"
            "Tips:\n"
            "- Use 'screenshot' + 'find_text' to see what's on screen then click it\n"
            "- Use 'shortcut' with names like 'copy', 'paste', 'save', 'new_tab' for cross-platform combos\n"
            "- Use 'snap_left'/'snap_right' to arrange windows side by side\n"
            "- Use 'tile' to arrange multiple windows in a grid\n"
            "- Use 'wait_for_text' to wait for loading screens or dialogs"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
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

        try:
            # ─── Mouse ───
            if op == "move":
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
                result = await self._windows.get_active_window()

            # ─── Workflow ───
            elif op == "run_workflow":
                name = kwargs.get("workflow_name", "")
                wf = self._workflow.load(name)
                if not wf:
                    # Check templates
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

            return json.dumps(result, default=str)

        except Exception as e:
            return json.dumps({"error": str(e), "operation": op})

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
