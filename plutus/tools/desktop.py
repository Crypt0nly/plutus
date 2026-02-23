"""Desktop tool — GUI automation via PyAutoGUI.

Provides full desktop control: screenshots, mouse clicks, keyboard input,
hotkeys, scrolling, and on-screen image location. Works cross-platform
(Windows, macOS, Linux with X11).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from plutus.tools.base import Tool

# Safety: disable PyAutoGUI's fail-safe only if explicitly opted out
# By default, moving mouse to (0,0) will raise FailSafeException
_FAILSAFE = os.environ.get("PLUTUS_DESKTOP_FAILSAFE", "1") != "0"


def _get_pyautogui():
    """Lazy import to avoid hard crash if pyautogui is not installed."""
    try:
        import pyautogui

        pyautogui.FAILSAFE = _FAILSAFE
        pyautogui.PAUSE = 0.1  # small pause between actions for stability
        return pyautogui
    except ImportError:
        raise RuntimeError(
            "pyautogui is not installed. Run: pip install pyautogui\n"
            "On Linux you also need: sudo apt install python3-tk python3-dev scrot"
        )


class DesktopTool(Tool):
    """Full desktop GUI automation — see the screen, click, type, scroll."""

    @property
    def name(self) -> str:
        return "desktop"

    @property
    def description(self) -> str:
        return (
            "Control the desktop GUI. Take screenshots of the entire screen, "
            "click at coordinates, type text, press hotkeys (e.g. ctrl+c, alt+tab), "
            "move the mouse, scroll, and locate images on screen. "
            "Use this to interact with any application visible on the desktop. "
            "Operations: screenshot, click, double_click, right_click, type_text, "
            "hotkey, mouse_move, scroll, locate_on_screen, get_mouse_position, get_screen_size."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "screenshot",
                        "click",
                        "double_click",
                        "right_click",
                        "type_text",
                        "hotkey",
                        "mouse_move",
                        "scroll",
                        "locate_on_screen",
                        "get_mouse_position",
                        "get_screen_size",
                    ],
                    "description": "The desktop operation to perform",
                },
                "x": {
                    "type": "integer",
                    "description": "X coordinate on screen (for click, mouse_move)",
                },
                "y": {
                    "type": "integer",
                    "description": "Y coordinate on screen (for click, mouse_move)",
                },
                "text": {
                    "type": "string",
                    "description": (
                        "Text to type (for type_text) or key combo "
                        "like 'ctrl+c', 'alt+tab', 'enter' (for hotkey)"
                    ),
                },
                "path": {
                    "type": "string",
                    "description": (
                        "File path — for screenshot: where to save the image; "
                        "for locate_on_screen: path to the image to find"
                    ),
                },
                "region": {
                    "type": "object",
                    "description": (
                        "Screen region for screenshot {x, y, width, height}. "
                        "Omit to capture the full screen."
                    ),
                    "properties": {
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                        "width": {"type": "integer"},
                        "height": {"type": "integer"},
                    },
                },
                "clicks": {
                    "type": "integer",
                    "description": "Number of clicks (default: 1)",
                },
                "amount": {
                    "type": "integer",
                    "description": "Scroll amount — positive for up, negative for down (for scroll)",
                },
                "interval": {
                    "type": "number",
                    "description": "Seconds between keystrokes when typing (default: 0.03)",
                },
                "duration": {
                    "type": "number",
                    "description": "Duration in seconds for mouse movement animation (default: 0.25)",
                },
                "button": {
                    "type": "string",
                    "enum": ["left", "middle", "right"],
                    "description": "Mouse button (default: left)",
                },
            },
            "required": ["operation"],
        }

    async def execute(self, **kwargs: Any) -> str:
        operation: str = kwargs["operation"]

        handlers = {
            "screenshot": self._screenshot,
            "click": self._click,
            "double_click": self._double_click,
            "right_click": self._right_click,
            "type_text": self._type_text,
            "hotkey": self._hotkey,
            "mouse_move": self._mouse_move,
            "scroll": self._scroll,
            "locate_on_screen": self._locate_on_screen,
            "get_mouse_position": self._get_mouse_position,
            "get_screen_size": self._get_screen_size,
        }

        handler = handlers.get(operation)
        if not handler:
            return f"[ERROR] Unknown desktop operation: {operation}"

        try:
            return handler(kwargs)
        except RuntimeError as e:
            return f"[ERROR] {e}"
        except Exception as e:
            return f"[ERROR] Desktop {operation} failed: {e}"

    # --- Operations ---

    def _screenshot(self, kwargs: dict) -> str:
        pag = _get_pyautogui()
        default_path = os.path.join(
            str(Path.home() / ".plutus" / "screenshots"), "desktop_screenshot.png"
        )
        os.makedirs(os.path.dirname(default_path), exist_ok=True)
        path = kwargs.get("path", default_path)
        region = kwargs.get("region")

        if region:
            img = pag.screenshot(region=(region["x"], region["y"], region["width"], region["height"]))
        else:
            img = pag.screenshot()

        img.save(path)
        width, height = img.size
        return f"Screenshot saved to: {path} ({width}x{height})"

    def _click(self, kwargs: dict) -> str:
        pag = _get_pyautogui()
        x = kwargs.get("x")
        y = kwargs.get("y")
        clicks = kwargs.get("clicks", 1)
        button = kwargs.get("button", "left")

        if x is not None and y is not None:
            pag.click(x=x, y=y, clicks=clicks, button=button)
            return f"Clicked ({button}) at ({x}, {y}) x{clicks}"
        else:
            pag.click(clicks=clicks, button=button)
            return f"Clicked ({button}) at current position x{clicks}"

    def _double_click(self, kwargs: dict) -> str:
        pag = _get_pyautogui()
        x = kwargs.get("x")
        y = kwargs.get("y")

        if x is not None and y is not None:
            pag.doubleClick(x=x, y=y)
            return f"Double-clicked at ({x}, {y})"
        else:
            pag.doubleClick()
            return "Double-clicked at current position"

    def _right_click(self, kwargs: dict) -> str:
        pag = _get_pyautogui()
        x = kwargs.get("x")
        y = kwargs.get("y")

        if x is not None and y is not None:
            pag.rightClick(x=x, y=y)
            return f"Right-clicked at ({x}, {y})"
        else:
            pag.rightClick()
            return "Right-clicked at current position"

    def _type_text(self, kwargs: dict) -> str:
        pag = _get_pyautogui()
        text = kwargs.get("text", "")
        if not text:
            return "[ERROR] type_text requires a 'text' parameter"
        interval = kwargs.get("interval", 0.03)
        pag.typewrite(text, interval=interval) if text.isascii() else pag.write(text)
        return f"Typed {len(text)} characters"

    def _hotkey(self, kwargs: dict) -> str:
        pag = _get_pyautogui()
        text = kwargs.get("text", "")
        if not text:
            return "[ERROR] hotkey requires a 'text' parameter (e.g. 'ctrl+c', 'alt+tab')"

        # Parse combo like "ctrl+shift+s" into individual keys
        keys = [k.strip() for k in text.split("+")]
        pag.hotkey(*keys)
        return f"Pressed hotkey: {text}"

    def _mouse_move(self, kwargs: dict) -> str:
        pag = _get_pyautogui()
        x = kwargs.get("x")
        y = kwargs.get("y")
        duration = kwargs.get("duration", 0.25)

        if x is None or y is None:
            return "[ERROR] mouse_move requires 'x' and 'y' parameters"
        pag.moveTo(x, y, duration=duration)
        return f"Moved mouse to ({x}, {y})"

    def _scroll(self, kwargs: dict) -> str:
        pag = _get_pyautogui()
        amount = kwargs.get("amount", 0)
        x = kwargs.get("x")
        y = kwargs.get("y")

        if x is not None and y is not None:
            pag.scroll(amount, x=x, y=y)
            return f"Scrolled {amount} at ({x}, {y})"
        else:
            pag.scroll(amount)
            return f"Scrolled {amount} at current position"

    def _locate_on_screen(self, kwargs: dict) -> str:
        pag = _get_pyautogui()
        path = kwargs.get("path", "")
        if not path:
            return "[ERROR] locate_on_screen requires a 'path' to the image to find"

        if not os.path.isfile(path):
            return f"[ERROR] Image file not found: {path}"

        try:
            location = pag.locateOnScreen(path, confidence=0.8)
            if location:
                center = pag.center(location)
                return (
                    f"Found image at region: (x={location.left}, y={location.top}, "
                    f"w={location.width}, h={location.height})\n"
                    f"Center point: ({center.x}, {center.y})"
                )
            return "Image not found on screen"
        except pag.ImageNotFoundException:
            return "Image not found on screen"

    def _get_mouse_position(self, kwargs: dict) -> str:
        pag = _get_pyautogui()
        pos = pag.position()
        return f"Mouse position: ({pos.x}, {pos.y})"

    def _get_screen_size(self, kwargs: dict) -> str:
        pag = _get_pyautogui()
        size = pag.size()
        return f"Screen size: {size.width}x{size.height}"
