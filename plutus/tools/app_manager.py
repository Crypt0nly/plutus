"""App manager tool — launch applications and manage windows.

Cross-platform desktop application and window management.
  - Windows: PowerShell + pygetwindow
  - macOS: osascript (AppleScript)
  - Linux: wmctrl / xdotool
"""

from __future__ import annotations

import asyncio
import os
import platform
import shutil
from typing import Any

from plutus.tools.base import Tool

SYSTEM = platform.system()


class AppManagerTool(Tool):
    """Launch applications, list/focus/close/resize desktop windows."""

    @property
    def name(self) -> str:
        return "app_manager"

    @property
    def description(self) -> str:
        return (
            "Launch applications and manage desktop windows. "
            "Open any app by name or path, list all open windows, "
            "focus/minimize/maximize/close/resize/move windows. "
            "Operations: launch, list_windows, focus_window, close_window, "
            "minimize_window, maximize_window, resize_window, move_window."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "launch",
                        "list_windows",
                        "focus_window",
                        "close_window",
                        "minimize_window",
                        "maximize_window",
                        "resize_window",
                        "move_window",
                    ],
                    "description": "The window/app operation to perform",
                },
                "app": {
                    "type": "string",
                    "description": (
                        "Application to launch — name (e.g. 'notepad', 'firefox', "
                        "'code', 'terminal') or full path"
                    ),
                },
                "args": {
                    "type": "string",
                    "description": "Arguments to pass to the launched application",
                },
                "title": {
                    "type": "string",
                    "description": "Window title (substring match) for window operations",
                },
                "window_id": {
                    "type": "string",
                    "description": "Window ID for targeting a specific window (from list_windows)",
                },
                "x": {"type": "integer", "description": "X position for move_window"},
                "y": {"type": "integer", "description": "Y position for move_window"},
                "width": {"type": "integer", "description": "Width for resize_window"},
                "height": {"type": "integer", "description": "Height for resize_window"},
            },
            "required": ["operation"],
        }

    async def execute(self, **kwargs: Any) -> str:
        operation: str = kwargs["operation"]

        handlers = {
            "launch": self._launch,
            "list_windows": self._list_windows,
            "focus_window": self._focus_window,
            "close_window": self._close_window,
            "minimize_window": self._minimize_window,
            "maximize_window": self._maximize_window,
            "resize_window": self._resize_window,
            "move_window": self._move_window,
        }

        handler = handlers.get(operation)
        if not handler:
            return f"[ERROR] Unknown app_manager operation: {operation}"

        try:
            return await handler(kwargs)
        except Exception as e:
            return f"[ERROR] app_manager {operation} failed: {e}"

    # --- Launch ---

    async def _launch(self, kwargs: dict) -> str:
        app = kwargs.get("app", "")
        if not app:
            return "[ERROR] launch requires an 'app' parameter (name or path)"
        args = kwargs.get("args", "")

        if SYSTEM == "Windows":
            return await self._launch_windows(app, args)
        elif SYSTEM == "Darwin":
            return await self._launch_macos(app, args)
        else:
            return await self._launch_linux(app, args)

    async def _launch_windows(self, app: str, args: str) -> str:
        # Try Start-Process with common app aliases
        cmd = f'powershell -Command "Start-Process \'{app}\'"'
        if args:
            cmd = f'powershell -Command "Start-Process \'{app}\' -ArgumentList \'{args}\'"'
        return await self._run(cmd, f"Launched: {app}")

    async def _launch_macos(self, app: str, args: str) -> str:
        # Use 'open' for .app bundles or plain command names
        if os.path.exists(app) or app.endswith(".app"):
            cmd = f"open '{app}'"
            if args:
                cmd += f" --args {args}"
        else:
            # Try 'open -a AppName'
            cmd = f"open -a '{app}'"
            if args:
                cmd += f" --args {args}"
        return await self._run(cmd, f"Launched: {app}")

    async def _launch_linux(self, app: str, args: str) -> str:
        # Find the executable
        resolved = shutil.which(app)
        if resolved:
            full_cmd = f"nohup {resolved} {args} >/dev/null 2>&1 &"
        else:
            # Try common desktop app launchers
            full_cmd = f"nohup {app} {args} >/dev/null 2>&1 &"
        return await self._run(full_cmd, f"Launched: {app}")

    # --- Window listing ---

    async def _list_windows(self, kwargs: dict) -> str:
        if SYSTEM == "Windows":
            return await self._list_windows_windows()
        elif SYSTEM == "Darwin":
            return await self._list_windows_macos()
        else:
            return await self._list_windows_linux()

    async def _list_windows_windows(self) -> str:
        cmd = (
            'powershell -Command "'
            "Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | "
            "Select-Object Id, MainWindowTitle | Format-Table -AutoSize"
            '"'
        )
        return await self._run_capture(cmd) or "No visible windows found"

    async def _list_windows_macos(self) -> str:
        script = (
            'osascript -e \'tell application "System Events" to '
            "get {name, title of windows} of "
            "(every process whose visible is true)'"
        )
        return await self._run_capture(script) or "No visible windows found"

    async def _list_windows_linux(self) -> str:
        # Prefer wmctrl, fall back to xdotool
        if shutil.which("wmctrl"):
            return await self._run_capture("wmctrl -l") or "No windows found"
        elif shutil.which("xdotool"):
            # Get active window list
            result = await self._run_capture(
                "xdotool search --onlyvisible --name '' getwindowname %@"
            )
            return result or "No windows found (install wmctrl for better results)"
        return (
            "[ERROR] Neither wmctrl nor xdotool found. "
            "Install one: sudo apt install wmctrl"
        )

    # --- Window focus ---

    async def _focus_window(self, kwargs: dict) -> str:
        title = kwargs.get("title", "")
        wid = kwargs.get("window_id", "")
        if not title and not wid:
            return "[ERROR] focus_window requires 'title' or 'window_id'"

        if SYSTEM == "Windows":
            ps = (
                f'powershell -Command "'
                f"(Get-Process | Where-Object {{$_.MainWindowTitle -like '*{title}*'}}).MainWindowHandle | "
                f"ForEach-Object {{ [void][System.Runtime.InteropServices.Marshal]::"
                f'SetForegroundWindow($_) }}"'
            )
            return await self._run(ps, f"Focused window: {title}")
        elif SYSTEM == "Darwin":
            script = (
                f'osascript -e \'tell application "System Events" to set frontmost of '
                f"(first process whose name contains \"{title}\") to true'"
            )
            return await self._run(script, f"Focused window: {title}")
        else:
            if wid:
                cmd = f"wmctrl -i -a {wid}" if shutil.which("wmctrl") else f"xdotool windowactivate {wid}"
            else:
                cmd = f"wmctrl -a '{title}'" if shutil.which("wmctrl") else f"xdotool search --name '{title}' windowactivate"
            return await self._run(cmd, f"Focused window: {title or wid}")

    # --- Window close ---

    async def _close_window(self, kwargs: dict) -> str:
        title = kwargs.get("title", "")
        wid = kwargs.get("window_id", "")
        if not title and not wid:
            return "[ERROR] close_window requires 'title' or 'window_id'"

        if SYSTEM == "Windows":
            ps = (
                f'powershell -Command "'
                f"(Get-Process | Where-Object {{$_.MainWindowTitle -like '*{title}*'}}) | "
                f'Stop-Process"'
            )
            return await self._run(ps, f"Closed window: {title}")
        elif SYSTEM == "Darwin":
            script = (
                f'osascript -e \'tell application "{title}" to quit\''
            )
            return await self._run(script, f"Closed window: {title}")
        else:
            if wid:
                cmd = f"wmctrl -i -c {wid}" if shutil.which("wmctrl") else f"xdotool windowclose {wid}"
            else:
                cmd = f"wmctrl -c '{title}'" if shutil.which("wmctrl") else f"xdotool search --name '{title}' windowclose"
            return await self._run(cmd, f"Closed window: {title or wid}")

    # --- Minimize / Maximize ---

    async def _minimize_window(self, kwargs: dict) -> str:
        title = kwargs.get("title", "")
        wid = kwargs.get("window_id", "")
        if not title and not wid:
            return "[ERROR] minimize_window requires 'title' or 'window_id'"

        if SYSTEM == "Windows":
            ps = (
                f'powershell -Command "'
                f"$w = (Get-Process | Where-Object {{$_.MainWindowTitle -like '*{title}*'}}); "
                f'$w.MainWindowHandle | ForEach-Object {{ [void][Console.Window]::ShowWindowAsync($_, 6) }}"'
            )
            return await self._run(ps, f"Minimized: {title}")
        elif SYSTEM == "Darwin":
            script = f'osascript -e \'tell application "System Events" to set miniaturized of window 1 of (first process whose name contains "{title}") to true\''
            return await self._run(script, f"Minimized: {title}")
        else:
            target = wid or await self._find_window_id_linux(title)
            if not target:
                return f"[ERROR] Could not find window: {title}"
            cmd = f"xdotool windowminimize {target}"
            return await self._run(cmd, f"Minimized: {title or wid}")

    async def _maximize_window(self, kwargs: dict) -> str:
        title = kwargs.get("title", "")
        wid = kwargs.get("window_id", "")
        if not title and not wid:
            return "[ERROR] maximize_window requires 'title' or 'window_id'"

        if SYSTEM == "Windows":
            ps = (
                f'powershell -Command "'
                f"$w = (Get-Process | Where-Object {{$_.MainWindowTitle -like '*{title}*'}}); "
                f'$w.MainWindowHandle | ForEach-Object {{ [void][Console.Window]::ShowWindowAsync($_, 3) }}"'
            )
            return await self._run(ps, f"Maximized: {title}")
        elif SYSTEM == "Darwin":
            script = f'osascript -e \'tell application "System Events" to set value of attribute "AXFullScreen" of window 1 of (first process whose name contains "{title}") to true\''
            return await self._run(script, f"Maximized: {title}")
        else:
            target = wid or await self._find_window_id_linux(title)
            if not target:
                return f"[ERROR] Could not find window: {title}"
            if shutil.which("wmctrl"):
                cmd = f"wmctrl -i -r {target} -b add,maximized_vert,maximized_horz"
            else:
                cmd = f"xdotool windowsize {target} 100% 100%"
            return await self._run(cmd, f"Maximized: {title or wid}")

    # --- Resize / Move ---

    async def _resize_window(self, kwargs: dict) -> str:
        title = kwargs.get("title", "")
        wid = kwargs.get("window_id", "")
        width = kwargs.get("width")
        height = kwargs.get("height")
        if not title and not wid:
            return "[ERROR] resize_window requires 'title' or 'window_id'"
        if width is None or height is None:
            return "[ERROR] resize_window requires 'width' and 'height'"

        if SYSTEM == "Windows":
            ps = (
                f'powershell -Command "'
                f"$p = Get-Process | Where-Object {{$_.MainWindowTitle -like '*{title}*'}} | Select-Object -First 1; "
                f"$sig = '[DllImport(\"\"user32.dll\"\")] public static extern bool MoveWindow(IntPtr h,int x,int y,int w,int h2,bool r);'; "
                f"$t = Add-Type -MemberDefinition $sig -Name Win32 -PassThru; "
                f'$t::MoveWindow($p.MainWindowHandle, 0, 0, {width}, {height}, $true)"'
            )
            return await self._run(ps, f"Resized: {title} to {width}x{height}")
        elif SYSTEM == "Darwin":
            script = (
                f'osascript -e \'tell application "System Events" to tell (first process whose name contains "{title}") to '
                f"set size of window 1 to {{{width}, {height}}}'"
            )
            return await self._run(script, f"Resized: {title} to {width}x{height}")
        else:
            target = wid or await self._find_window_id_linux(title)
            if not target:
                return f"[ERROR] Could not find window: {title}"
            if shutil.which("wmctrl"):
                cmd = f"wmctrl -i -r {target} -e 0,-1,-1,{width},{height}"
            else:
                cmd = f"xdotool windowsize {target} {width} {height}"
            return await self._run(cmd, f"Resized: {title or wid} to {width}x{height}")

    async def _move_window(self, kwargs: dict) -> str:
        title = kwargs.get("title", "")
        wid = kwargs.get("window_id", "")
        x = kwargs.get("x")
        y = kwargs.get("y")
        if not title and not wid:
            return "[ERROR] move_window requires 'title' or 'window_id'"
        if x is None or y is None:
            return "[ERROR] move_window requires 'x' and 'y'"

        if SYSTEM == "Windows":
            ps = (
                f'powershell -Command "'
                f"$p = Get-Process | Where-Object {{$_.MainWindowTitle -like '*{title}*'}} | Select-Object -First 1; "
                f"$sig = '[DllImport(\"\"user32.dll\"\")] public static extern bool MoveWindow(IntPtr h,int x,int y,int w,int h2,bool r);'; "
                f"$t = Add-Type -MemberDefinition $sig -Name Win32 -PassThru; "
                f'$t::MoveWindow($p.MainWindowHandle, {x}, {y}, 800, 600, $true)"'
            )
            return await self._run(ps, f"Moved: {title} to ({x}, {y})")
        elif SYSTEM == "Darwin":
            script = (
                f'osascript -e \'tell application "System Events" to tell (first process whose name contains "{title}") to '
                f"set position of window 1 to {{{x}, {y}}}'"
            )
            return await self._run(script, f"Moved: {title} to ({x}, {y})")
        else:
            target = wid or await self._find_window_id_linux(title)
            if not target:
                return f"[ERROR] Could not find window: {title}"
            if shutil.which("wmctrl"):
                cmd = f"wmctrl -i -r {target} -e 0,{x},{y},-1,-1"
            else:
                cmd = f"xdotool windowmove {target} {x} {y}"
            return await self._run(cmd, f"Moved: {title or wid} to ({x}, {y})")

    # --- Helpers ---

    async def _find_window_id_linux(self, title: str) -> str | None:
        """Find a window ID by partial title match on Linux."""
        if shutil.which("xdotool"):
            result = await self._run_capture(
                f"xdotool search --name '{title}'"
            )
            if result:
                return result.strip().split("\n")[0]
        elif shutil.which("wmctrl"):
            result = await self._run_capture("wmctrl -l")
            if result:
                for line in result.strip().split("\n"):
                    if title.lower() in line.lower():
                        return line.split()[0]
        return None

    async def _run(self, cmd: str, success_msg: str) -> str:
        """Run a shell command and return success message or stderr."""
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            return f"[ERROR] {err}" if err else f"[ERROR] Command exited with code {proc.returncode}"
        return success_msg

    async def _run_capture(self, cmd: str) -> str:
        """Run a shell command and return stdout."""
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        return stdout.decode("utf-8", errors="replace").strip()
