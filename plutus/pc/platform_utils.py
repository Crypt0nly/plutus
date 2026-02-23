"""Platform detection utilities for cross-platform desktop control.

Detects OS, display server (X11 vs Wayland on Linux), and available tools.
Used by all PC modules to choose the right backend for screenshots, window
management, keyboard/mouse input, etc.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from functools import lru_cache

SYSTEM = platform.system()  # "Windows", "Darwin", "Linux"


@lru_cache(maxsize=1)
def get_display_server() -> str:
    """Detect the active display server on Linux.

    Returns:
        "wayland", "x11", or "unknown" (non-Linux returns "native").
    """
    if SYSTEM != "Linux":
        return "native"

    # Check Wayland first — more modern, increasingly default
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        return "wayland"

    # Check X11
    if os.environ.get("DISPLAY"):
        return "x11"
    if os.environ.get("XDG_SESSION_TYPE", "").lower() == "x11":
        return "x11"

    return "unknown"


def is_wayland() -> bool:
    """Check if the current session is Wayland."""
    return get_display_server() == "wayland"


def is_x11() -> bool:
    """Check if the current session is X11."""
    return get_display_server() == "x11"


@lru_cache(maxsize=1)
def available_tools() -> dict[str, bool]:
    """Detect which platform tools are installed.

    Returns a dict of tool_name -> available (bool).
    """
    tools = {
        # Linux X11 tools
        "xdotool": False,
        "wmctrl": False,
        "xdpyinfo": False,
        "xrandr": False,
        "scrot": False,
        "xclip": False,
        "xsel": False,
        # Linux Wayland tools
        "grim": False,
        "slurp": False,
        "wl-copy": False,
        "wl-paste": False,
        "wlr-randr": False,
        "ydotool": False,
        "wtype": False,
        "swaymsg": False,
        "kdotool": False,
        "gnome-screenshot": False,
        # macOS tools
        "osascript": False,
        "screencapture": False,
        "pbcopy": False,
        "pbpaste": False,
        # Cross-platform
        "tesseract": False,
    }

    for tool_name in tools:
        tools[tool_name] = shutil.which(tool_name) is not None

    return tools


def has_tool(name: str) -> bool:
    """Check if a specific tool is available on the system."""
    return available_tools().get(name, False)


def get_screenshot_command() -> list[str] | None:
    """Get the best available screenshot command for the current platform.

    Returns:
        A command list like ["grim", "-o", ...] or None if no tool found.
        The caller should append the output file path.
    """
    if SYSTEM == "Darwin":
        return ["screencapture", "-x"]

    if SYSTEM == "Linux":
        display = get_display_server()

        if display == "wayland":
            if has_tool("grim"):
                return ["grim"]
            if has_tool("gnome-screenshot"):
                return ["gnome-screenshot", "-f"]
        else:
            # X11 or unknown — try X11 tools first
            if has_tool("scrot"):
                return ["scrot", "-o"]
            if has_tool("gnome-screenshot"):
                return ["gnome-screenshot", "-f"]

    # Windows handled separately (PowerShell)
    return None


def get_screen_size_linux() -> tuple[int, int] | None:
    """Get screen dimensions on Linux, handling both X11 and Wayland.

    Returns (width, height) or None on failure.
    """
    display = get_display_server()

    if display == "wayland":
        # Try wlr-randr (wlroots compositors: Sway, Hyprland, etc.)
        if has_tool("wlr-randr"):
            try:
                result = subprocess.run(
                    ["wlr-randr"], capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if "current" in line.lower():
                        # Parse "1920x1080 px, ..." format
                        import re
                        match = re.search(r"(\d+)x(\d+)", line)
                        if match:
                            return (int(match.group(1)), int(match.group(2)))
            except Exception:
                pass

        # Try swaymsg (Sway compositor)
        if has_tool("swaymsg"):
            try:
                import json
                result = subprocess.run(
                    ["swaymsg", "-t", "get_outputs", "--raw"],
                    capture_output=True, text=True, timeout=5,
                )
                outputs = json.loads(result.stdout)
                for output in outputs:
                    if output.get("active"):
                        rect = output.get("rect", {})
                        w = rect.get("width", 0)
                        h = rect.get("height", 0)
                        if w > 0 and h > 0:
                            return (w, h)
            except Exception:
                pass

        # Try xrandr under XWayland (many Wayland sessions still have it)
        if has_tool("xrandr"):
            dims = _try_xrandr()
            if dims:
                return dims

    else:
        # X11 path
        if has_tool("xdpyinfo"):
            try:
                result = subprocess.run(
                    ["xdpyinfo"], capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.splitlines():
                    if "dimensions:" in line:
                        dims = line.split()[1]
                        w, h = dims.split("x")
                        return (int(w), int(h))
            except Exception:
                pass

        if has_tool("xrandr"):
            dims = _try_xrandr()
            if dims:
                return dims

    return None


def _try_xrandr() -> tuple[int, int] | None:
    """Try to get screen size from xrandr."""
    try:
        import re
        result = subprocess.run(
            ["xrandr"], capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "*" in line:
                match = re.search(r"(\d+)x(\d+)", line)
                if match:
                    return (int(match.group(1)), int(match.group(2)))
    except Exception:
        pass
    return None


def get_window_tool_linux() -> str | None:
    """Get the best available window management tool on Linux.

    Returns:
        "wmctrl", "xdotool", "swaymsg", "kdotool", or None
    """
    display = get_display_server()

    if display == "wayland":
        # Sway
        if has_tool("swaymsg"):
            return "swaymsg"
        # KDE Wayland
        if has_tool("kdotool"):
            return "kdotool"
        # Fallback: some Wayland sessions still have XWayland
        if has_tool("wmctrl"):
            return "wmctrl"
        if has_tool("xdotool"):
            return "xdotool"
    else:
        if has_tool("wmctrl"):
            return "wmctrl"
        if has_tool("xdotool"):
            return "xdotool"

    return None


def get_keyboard_tool_linux() -> str | None:
    """Get the best available keyboard input tool on Linux.

    Returns:
        "xdotool", "wtype", "ydotool", or None
    """
    display = get_display_server()

    if display == "wayland":
        if has_tool("wtype"):
            return "wtype"
        if has_tool("ydotool"):
            return "ydotool"
    else:
        if has_tool("xdotool"):
            return "xdotool"

    return None
