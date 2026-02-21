"""Anthropic-native Computer Use executor.

This module implements the actual desktop actions that Claude's Computer Use Tool
requests: screenshot capture, mouse clicks, keyboard input, scrolling, and
coordinate scaling.

It follows the exact Anthropic specification:
  - Screenshots are captured and returned as base64 PNG images
  - Coordinates are scaled between the API resolution and the actual screen
  - All actions (click, type, key, scroll, drag) are executed via PyAutoGUI
  - The executor is stateless — each action is independent

Reference: https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool
"""

from __future__ import annotations

import base64
import io
import logging
import math
import platform
import subprocess
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("plutus.pc.computer_use")

# ── Display resolution for the API ──────────────────────────────────
# Anthropic recommends sending screenshots at a resolution that fits within
# 1568px on the longest edge and ~1.15 megapixels total. We pre-scale to
# avoid the API's automatic (lossy) downsampling.
API_MAX_LONG_EDGE = 1568
API_MAX_TOTAL_PIXELS = 1_150_000


def _get_scale_factor(width: int, height: int) -> float:
    """Calculate scale factor to meet Anthropic's image constraints."""
    long_edge = max(width, height)
    total_pixels = width * height
    long_edge_scale = API_MAX_LONG_EDGE / long_edge
    total_pixels_scale = math.sqrt(API_MAX_TOTAL_PIXELS / total_pixels)
    return min(1.0, long_edge_scale, total_pixels_scale)


class ComputerUseExecutor:
    """Executes desktop actions requested by Claude's Computer Use Tool.

    This class is the bridge between Claude's abstract actions and the real desktop.
    It handles:
      - Screenshot capture (returns base64 PNG at API-appropriate resolution)
      - Mouse actions (click, move, drag, scroll) with coordinate scaling
      - Keyboard actions (type, key combos)
      - Display info for the tool definition

    Usage:
        executor = ComputerUseExecutor()
        # Get tool definition for the API
        tool_def = executor.get_tool_definition()
        # Execute an action from Claude
        result = executor.execute_action(action="screenshot")
        result = executor.execute_action(action="left_click", coordinate=[500, 300])
    """

    def __init__(self, display_number: int | None = None):
        self._display_number = display_number
        self._screen_width: int = 0
        self._screen_height: int = 0
        self._scale_factor: float = 1.0
        self._api_width: int = 0
        self._api_height: int = 0
        self._initialized = False
        self._last_screenshot_path: str | None = None

    def _ensure_initialized(self) -> None:
        """Lazy-initialize screen dimensions on first use."""
        if self._initialized:
            return
        try:
            self._detect_screen_size()
            self._initialized = True
        except Exception as e:
            logger.warning(f"Could not detect screen size: {e}. Using defaults.")
            self._screen_width = 1920
            self._screen_height = 1080
            self._compute_scale()
            self._initialized = True

    def _detect_screen_size(self) -> None:
        """Detect the actual screen resolution."""
        system = platform.system()

        if system == "Windows":
            try:
                import ctypes
                user32 = ctypes.windll.user32
                user32.SetProcessDPIAware()
                self._screen_width = user32.GetSystemMetrics(0)
                self._screen_height = user32.GetSystemMetrics(1)
            except Exception:
                self._screen_width, self._screen_height = 1920, 1080

        elif system == "Darwin":
            try:
                result = subprocess.run(
                    ["system_profiler", "SPDisplaysDataType"],
                    capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.splitlines():
                    if "Resolution" in line:
                        parts = line.split()
                        for i, p in enumerate(parts):
                            if p == "x" and i > 0 and i < len(parts) - 1:
                                self._screen_width = int(parts[i - 1])
                                self._screen_height = int(parts[i + 1])
                                break
                        if self._screen_width > 0:
                            break
                if self._screen_width == 0:
                    self._screen_width, self._screen_height = 1920, 1080
            except Exception:
                self._screen_width, self._screen_height = 1920, 1080

        else:  # Linux
            try:
                result = subprocess.run(
                    ["xdpyinfo"], capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.splitlines():
                    if "dimensions:" in line:
                        dims = line.split()[1]
                        w, h = dims.split("x")
                        self._screen_width = int(w)
                        self._screen_height = int(h)
                        break
                if self._screen_width == 0:
                    self._screen_width, self._screen_height = 1920, 1080
            except Exception:
                self._screen_width, self._screen_height = 1920, 1080

        self._compute_scale()

    def _compute_scale(self) -> None:
        """Compute the scale factor and API dimensions."""
        self._scale_factor = _get_scale_factor(self._screen_width, self._screen_height)
        self._api_width = int(self._screen_width * self._scale_factor)
        self._api_height = int(self._screen_height * self._scale_factor)
        logger.info(
            f"Screen: {self._screen_width}x{self._screen_height}, "
            f"API: {self._api_width}x{self._api_height}, "
            f"Scale: {self._scale_factor:.3f}"
        )

    def _to_screen_coords(self, api_x: int, api_y: int) -> tuple[int, int]:
        """Convert API coordinates to actual screen coordinates."""
        if self._scale_factor >= 1.0:
            return api_x, api_y
        screen_x = int(api_x / self._scale_factor)
        screen_y = int(api_y / self._scale_factor)
        # Clamp to screen bounds
        screen_x = max(0, min(screen_x, self._screen_width - 1))
        screen_y = max(0, min(screen_y, self._screen_height - 1))
        return screen_x, screen_y

    # ── Public API ──────────────────────────────────────────────────

    def get_tool_definition(self) -> dict[str, Any]:
        """Return the Anthropic-native computer use tool definition.

        This is a schema-less tool — the schema is built into Claude's model.
        """
        self._ensure_initialized()
        tool_def: dict[str, Any] = {
            "type": "computer_20250124",
            "name": "computer",
            "display_width_px": self._api_width,
            "display_height_px": self._api_height,
        }
        if self._display_number is not None:
            tool_def["display_number"] = self._display_number
        return tool_def

    def get_display_info(self) -> dict[str, Any]:
        """Return display info for the UI/status endpoints."""
        self._ensure_initialized()
        return {
            "screen_width": self._screen_width,
            "screen_height": self._screen_height,
            "api_width": self._api_width,
            "api_height": self._api_height,
            "scale_factor": round(self._scale_factor, 3),
            "last_screenshot": self._last_screenshot_path,
        }

    def execute_action(self, action: str, **params: Any) -> dict[str, Any]:
        """Execute a computer use action and return the result.

        Args:
            action: The action type (screenshot, left_click, type, key, etc.)
            **params: Action-specific parameters

        Returns:
            A dict with either:
              - {"type": "image", "base64": "...", "media_type": "image/png"} for screenshots
              - {"type": "text", "text": "..."} for action confirmations
              - {"type": "error", "error": "..."} for errors
        """
        self._ensure_initialized()

        try:
            handler = getattr(self, f"_action_{action}", None)
            if handler is None:
                return {"type": "error", "error": f"Unknown action: {action}"}
            return handler(**params)
        except Exception as e:
            logger.exception(f"Action {action} failed")
            return {"type": "error", "error": f"Action {action} failed: {str(e)}"}

    # ── Action handlers ─────────────────────────────────────────────

    def _action_screenshot(self, **kwargs) -> dict[str, Any]:
        """Capture the screen and return as base64 PNG."""
        try:
            import pyautogui
            screenshot = pyautogui.screenshot()
        except Exception as e:
            # Fallback: try using scrot on Linux or other methods
            return self._fallback_screenshot()

        # Resize to API dimensions
        if self._scale_factor < 1.0:
            screenshot = screenshot.resize(
                (self._api_width, self._api_height),
                resample=3  # LANCZOS
            )

        # Convert to base64 PNG
        buffer = io.BytesIO()
        screenshot.save(buffer, format="PNG", optimize=True)
        b64_data = base64.standard_b64encode(buffer.getvalue()).decode("utf-8")

        # Also save to disk for the UI
        screenshots_dir = Path.home() / ".plutus" / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshots_dir / "latest.png"
        screenshot.save(str(screenshot_path), format="PNG")
        self._last_screenshot_path = str(screenshot_path)

        return {
            "type": "image",
            "base64": b64_data,
            "media_type": "image/png",
        }

    def _fallback_screenshot(self) -> dict[str, Any]:
        """Fallback screenshot capture using platform-specific tools."""
        system = platform.system()
        screenshots_dir = Path.home() / ".plutus" / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshots_dir / "latest.png"

        try:
            if system == "Linux":
                subprocess.run(
                    ["scrot", "-o", str(screenshot_path)],
                    timeout=5, check=True
                )
            elif system == "Darwin":
                subprocess.run(
                    ["screencapture", "-x", str(screenshot_path)],
                    timeout=5, check=True
                )
            elif system == "Windows":
                # PowerShell screenshot
                ps_cmd = (
                    "Add-Type -AssemblyName System.Windows.Forms;"
                    "[System.Windows.Forms.Screen]::PrimaryScreen | ForEach-Object {"
                    "$bmp = New-Object System.Drawing.Bitmap($_.Bounds.Width, $_.Bounds.Height);"
                    "$g = [System.Drawing.Graphics]::FromImage($bmp);"
                    "$g.CopyFromScreen($_.Bounds.Location, [System.Drawing.Point]::Empty, $_.Bounds.Size);"
                    f"$bmp.Save('{screenshot_path}')"
                    "}"
                )
                subprocess.run(
                    ["powershell", "-Command", ps_cmd],
                    timeout=10, check=True
                )
            else:
                return {"type": "error", "error": f"No screenshot method for {system}"}

            from PIL import Image
            img = Image.open(str(screenshot_path))

            # Resize if needed
            if self._scale_factor < 1.0:
                img = img.resize(
                    (self._api_width, self._api_height),
                    resample=3
                )
                img.save(str(screenshot_path), format="PNG")

            buffer = io.BytesIO()
            img.save(buffer, format="PNG", optimize=True)
            b64_data = base64.standard_b64encode(buffer.getvalue()).decode("utf-8")
            self._last_screenshot_path = str(screenshot_path)

            return {
                "type": "image",
                "base64": b64_data,
                "media_type": "image/png",
            }
        except Exception as e:
            return {"type": "error", "error": f"Screenshot fallback failed: {e}"}

    def _action_left_click(self, coordinate: list[int] | None = None, **kwargs) -> dict[str, Any]:
        """Click at the given coordinates."""
        if not coordinate or len(coordinate) != 2:
            return {"type": "error", "error": "left_click requires coordinate [x, y]"}
        import pyautogui
        x, y = self._to_screen_coords(coordinate[0], coordinate[1])
        pyautogui.click(x, y)
        return {"type": "text", "text": f"Clicked at ({x}, {y})"}

    def _action_right_click(self, coordinate: list[int] | None = None, **kwargs) -> dict[str, Any]:
        """Right-click at the given coordinates."""
        if not coordinate or len(coordinate) != 2:
            return {"type": "error", "error": "right_click requires coordinate [x, y]"}
        import pyautogui
        x, y = self._to_screen_coords(coordinate[0], coordinate[1])
        pyautogui.rightClick(x, y)
        return {"type": "text", "text": f"Right-clicked at ({x}, {y})"}

    def _action_middle_click(self, coordinate: list[int] | None = None, **kwargs) -> dict[str, Any]:
        """Middle-click at the given coordinates."""
        if not coordinate or len(coordinate) != 2:
            return {"type": "error", "error": "middle_click requires coordinate [x, y]"}
        import pyautogui
        x, y = self._to_screen_coords(coordinate[0], coordinate[1])
        pyautogui.middleClick(x, y)
        return {"type": "text", "text": f"Middle-clicked at ({x}, {y})"}

    def _action_double_click(self, coordinate: list[int] | None = None, **kwargs) -> dict[str, Any]:
        """Double-click at the given coordinates."""
        if not coordinate or len(coordinate) != 2:
            return {"type": "error", "error": "double_click requires coordinate [x, y]"}
        import pyautogui
        x, y = self._to_screen_coords(coordinate[0], coordinate[1])
        pyautogui.doubleClick(x, y)
        return {"type": "text", "text": f"Double-clicked at ({x}, {y})"}

    def _action_triple_click(self, coordinate: list[int] | None = None, **kwargs) -> dict[str, Any]:
        """Triple-click at the given coordinates."""
        if not coordinate or len(coordinate) != 2:
            return {"type": "error", "error": "triple_click requires coordinate [x, y]"}
        import pyautogui
        x, y = self._to_screen_coords(coordinate[0], coordinate[1])
        pyautogui.click(x, y, clicks=3)
        return {"type": "text", "text": f"Triple-clicked at ({x}, {y})"}

    def _action_mouse_move(self, coordinate: list[int] | None = None, **kwargs) -> dict[str, Any]:
        """Move the mouse cursor to the given coordinates."""
        if not coordinate or len(coordinate) != 2:
            return {"type": "error", "error": "mouse_move requires coordinate [x, y]"}
        import pyautogui
        x, y = self._to_screen_coords(coordinate[0], coordinate[1])
        pyautogui.moveTo(x, y, duration=0.3)
        return {"type": "text", "text": f"Moved cursor to ({x}, {y})"}

    def _action_left_click_drag(
        self,
        start_coordinate: list[int] | None = None,
        coordinate: list[int] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Click and drag from start_coordinate to coordinate."""
        if not start_coordinate or len(start_coordinate) != 2:
            return {"type": "error", "error": "left_click_drag requires start_coordinate [x, y]"}
        if not coordinate or len(coordinate) != 2:
            return {"type": "error", "error": "left_click_drag requires coordinate [x, y]"}
        import pyautogui
        sx, sy = self._to_screen_coords(start_coordinate[0], start_coordinate[1])
        ex, ey = self._to_screen_coords(coordinate[0], coordinate[1])
        pyautogui.moveTo(sx, sy, duration=0.1)
        pyautogui.mouseDown()
        pyautogui.moveTo(ex, ey, duration=0.5)
        pyautogui.mouseUp()
        return {"type": "text", "text": f"Dragged from ({sx}, {sy}) to ({ex}, {ey})"}

    def _action_type(self, text: str = "", **kwargs) -> dict[str, Any]:
        """Type text using the keyboard."""
        if not text:
            return {"type": "error", "error": "type requires text parameter"}
        import pyautogui
        # Use pyperclip + paste for reliability with special characters
        try:
            import pyperclip
            pyperclip.copy(text)
            system = platform.system()
            if system == "Darwin":
                pyautogui.hotkey("command", "v")
            else:
                pyautogui.hotkey("ctrl", "v")
            time.sleep(0.1)
            return {"type": "text", "text": f"Typed: {text[:50]}{'...' if len(text) > 50 else ''}"}
        except ImportError:
            # Fallback to pyautogui.write (ASCII only)
            pyautogui.write(text, interval=0.02)
            return {"type": "text", "text": f"Typed: {text[:50]}{'...' if len(text) > 50 else ''}"}

    def _action_key(self, text: str = "", **kwargs) -> dict[str, Any]:
        """Press a key or key combination (e.g., 'ctrl+s', 'Return', 'space')."""
        if not text:
            return {"type": "error", "error": "key requires text parameter"}
        import pyautogui

        # Map common Anthropic key names to PyAutoGUI names
        key_map = {
            "Return": "enter",
            "return": "enter",
            "Enter": "enter",
            "BackSpace": "backspace",
            "Backspace": "backspace",
            "Delete": "delete",
            "Escape": "escape",
            "Tab": "tab",
            "space": "space",
            "Space": "space",
            "Up": "up",
            "Down": "down",
            "Left": "left",
            "Right": "right",
            "Home": "home",
            "End": "end",
            "Page_Up": "pageup",
            "Page_Down": "pagedown",
            "super": "win",
            "Super_L": "win",
            "Super_R": "win",
            "ctrl": "ctrl",
            "Control_L": "ctrl",
            "alt": "alt",
            "Alt_L": "alt",
            "shift": "shift",
            "Shift_L": "shift",
        }

        # Handle key combinations (e.g., "ctrl+s", "alt+F4")
        if "+" in text:
            keys = [key_map.get(k.strip(), k.strip().lower()) for k in text.split("+")]
            # On macOS, map ctrl to command for common shortcuts
            if platform.system() == "Darwin":
                keys = ["command" if k == "ctrl" else k for k in keys]
            pyautogui.hotkey(*keys)
            return {"type": "text", "text": f"Pressed: {'+'.join(keys)}"}
        else:
            key = key_map.get(text, text.lower())
            pyautogui.press(key)
            return {"type": "text", "text": f"Pressed: {key}"}

    def _action_scroll(
        self,
        coordinate: list[int] | None = None,
        direction: str = "down",
        amount: int = 3,
        **kwargs,
    ) -> dict[str, Any]:
        """Scroll at the given coordinates in the specified direction."""
        import pyautogui

        if coordinate and len(coordinate) == 2:
            x, y = self._to_screen_coords(coordinate[0], coordinate[1])
            pyautogui.moveTo(x, y, duration=0.1)

        scroll_map = {
            "up": amount,
            "down": -amount,
            "left": -amount,
            "right": amount,
        }
        scroll_amount = scroll_map.get(direction, -amount)

        if direction in ("left", "right"):
            pyautogui.hscroll(scroll_amount)
        else:
            pyautogui.scroll(scroll_amount)

        return {"type": "text", "text": f"Scrolled {direction} by {amount}"}

    def _action_wait(self, duration: float = 1.0, **kwargs) -> dict[str, Any]:
        """Wait for a specified duration."""
        duration = min(duration, 10.0)  # Cap at 10 seconds
        time.sleep(duration)
        return {"type": "text", "text": f"Waited {duration}s"}

    def _action_hold_key(self, text: str = "", duration: float = 0.5, **kwargs) -> dict[str, Any]:
        """Hold down a key for a specified duration."""
        if not text:
            return {"type": "error", "error": "hold_key requires text parameter"}
        import pyautogui
        key = text.lower()
        pyautogui.keyDown(key)
        time.sleep(min(duration, 5.0))
        pyautogui.keyUp(key)
        return {"type": "text", "text": f"Held {key} for {duration}s"}

    def _action_left_mouse_down(self, coordinate: list[int] | None = None, **kwargs) -> dict[str, Any]:
        """Press and hold the left mouse button."""
        import pyautogui
        if coordinate and len(coordinate) == 2:
            x, y = self._to_screen_coords(coordinate[0], coordinate[1])
            pyautogui.moveTo(x, y, duration=0.1)
        pyautogui.mouseDown()
        return {"type": "text", "text": "Left mouse button down"}

    def _action_left_mouse_up(self, **kwargs) -> dict[str, Any]:
        """Release the left mouse button."""
        import pyautogui
        pyautogui.mouseUp()
        return {"type": "text", "text": "Left mouse button up"}

    def _action_cursor_position(self, **kwargs) -> dict[str, Any]:
        """Get the current cursor position in API coordinates."""
        import pyautogui
        x, y = pyautogui.position()
        # Convert screen coords to API coords
        api_x = int(x * self._scale_factor)
        api_y = int(y * self._scale_factor)
        return {"type": "text", "text": f"Cursor position: ({api_x}, {api_y})"}
