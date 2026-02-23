"""Window manager — deep cross-platform window orchestration.

Provides intelligent window management: find windows by title/app,
snap to screen edges, tile multiple windows, switch between them,
and manage virtual desktops. Works on Windows, macOS, and Linux.
"""

from __future__ import annotations

import asyncio
import platform
import re
import shutil
from dataclasses import dataclass
from typing import Any

SYSTEM = platform.system()


@dataclass
class WindowInfo:
    """Information about a desktop window."""
    id: str = ""
    title: str = ""
    app: str = ""
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    is_active: bool = False
    is_minimized: bool = False
    is_maximized: bool = False
    pid: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "app": self.app,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "is_active": self.is_active,
            "is_minimized": self.is_minimized,
            "is_maximized": self.is_maximized,
            "pid": self.pid,
        }


class WindowManager:
    """Cross-platform window manager with intelligent operations.

    Usage:
        wm = WindowManager()
        windows = await wm.list_windows()
        await wm.focus("Chrome")
        await wm.snap_left("Chrome")
        await wm.snap_right("Code")
        await wm.tile_windows(["Chrome", "Code", "Terminal"])
        await wm.close("Notepad")
    """

    async def _run(self, cmd: str, timeout: float = 10) -> tuple[str, str, int]:
        """Run a shell command and return (stdout, stderr, returncode)."""
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return (
                stdout.decode("utf-8", errors="replace").strip(),
                stderr.decode("utf-8", errors="replace").strip(),
                proc.returncode or 0,
            )
        except asyncio.TimeoutError:
            proc.kill()
            return ("", "Command timed out", 1)

    async def _get_screen_size(self) -> tuple[int, int]:
        """Get screen dimensions."""
        if SYSTEM == "Windows":
            out, _, _ = await self._run(
                'powershell -Command "[System.Windows.Forms.Screen]::PrimaryScreen.Bounds | '
                'Select-Object Width,Height | ConvertTo-Json"'
            )
            try:
                import json
                data = json.loads(out)
                return (data["Width"], data["Height"])
            except Exception:
                return (1920, 1080)
        elif SYSTEM == "Darwin":
            out, _, _ = await self._run(
                "osascript -e 'tell application \"Finder\" to get bounds of window of desktop'"
            )
            try:
                parts = [int(x.strip()) for x in out.split(",")]
                return (parts[2], parts[3])
            except Exception:
                return (1920, 1080)
        else:
            # Use platform_utils for robust Linux detection (X11 + Wayland)
            try:
                from plutus.pc.platform_utils import get_screen_size_linux
                dims = get_screen_size_linux()
                if dims:
                    return dims
            except Exception:
                pass
            # Manual fallback
            out, _, _ = await self._run("xdpyinfo 2>/dev/null | grep dimensions")
            match = re.search(r'(\d+)x(\d+)', out)
            if match:
                return (int(match.group(1)), int(match.group(2)))
            out, _, _ = await self._run("xrandr 2>/dev/null | grep '*'")
            match = re.search(r'(\d+)x(\d+)', out)
            if match:
                return (int(match.group(1)), int(match.group(2)))
            return (1920, 1080)

    # ─── Window Listing ───

    async def list_windows(self) -> list[dict[str, Any]]:
        """List all visible windows with details."""
        if SYSTEM == "Windows":
            return await self._list_windows_windows()
        elif SYSTEM == "Darwin":
            return await self._list_windows_macos()
        else:
            return await self._list_windows_linux()

    async def _list_windows_windows(self) -> list[dict[str, Any]]:
        cmd = (
            'powershell -Command "'
            "Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | "
            "Select-Object Id, ProcessName, MainWindowTitle | ConvertTo-Json"
            '"'
        )
        out, _, _ = await self._run(cmd)
        windows = []
        try:
            import json
            data = json.loads(out)
            if isinstance(data, dict):
                data = [data]
            for proc in data:
                windows.append(WindowInfo(
                    id=str(proc.get("Id", "")),
                    title=proc.get("MainWindowTitle", ""),
                    app=proc.get("ProcessName", ""),
                    pid=proc.get("Id", 0),
                ).to_dict())
        except Exception:
            pass
        return windows

    async def _list_windows_macos(self) -> list[dict[str, Any]]:
        script = '''
        osascript -e '
        set output to ""
        tell application "System Events"
            set procs to every process whose visible is true
            repeat with p in procs
                set pName to name of p
                try
                    set wins to windows of p
                    repeat with w in wins
                        set wTitle to name of w
                        set output to output & pName & "|" & wTitle & "\\n"
                    end repeat
                end try
            end repeat
        end tell
        return output'
        '''
        out, _, _ = await self._run(script)
        windows = []
        for line in out.strip().split("\n"):
            if "|" in line:
                parts = line.split("|", 1)
                windows.append(WindowInfo(
                    app=parts[0].strip(),
                    title=parts[1].strip() if len(parts) > 1 else "",
                ).to_dict())
        return windows

    async def _list_windows_linux(self) -> list[dict[str, Any]]:
        windows = []

        # Try swaymsg first (Sway/Wayland compositor)
        if shutil.which("swaymsg"):
            try:
                out, _, rc = await self._run("swaymsg -t get_tree --raw")
                if rc == 0:
                    import json as _json
                    tree = _json.loads(out)
                    self._walk_sway_tree(tree, windows)
                    if windows:
                        return windows
            except Exception:
                pass

        if shutil.which("wmctrl"):
            out, _, _ = await self._run("wmctrl -l -p -G")
            for line in out.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split(None, 8)
                if len(parts) >= 9:
                    windows.append(WindowInfo(
                        id=parts[0],
                        x=int(parts[2]) if parts[2].isdigit() else 0,
                        y=int(parts[3]) if parts[3].isdigit() else 0,
                        width=int(parts[4]) if parts[4].isdigit() else 0,
                        height=int(parts[5]) if parts[5].isdigit() else 0,
                        pid=int(parts[1]) if parts[1].isdigit() else 0,
                        title=parts[8] if len(parts) > 8 else "",
                    ).to_dict())
        elif shutil.which("xdotool"):
            out, _, _ = await self._run(
                "xdotool search --onlyvisible --name '' 2>/dev/null"
            )
            for wid in out.strip().split("\n"):
                wid = wid.strip()
                if not wid:
                    continue
                name_out, _, _ = await self._run(f"xdotool getwindowname {wid} 2>/dev/null")
                pid_out, _, _ = await self._run(f"xdotool getwindowpid {wid} 2>/dev/null")
                windows.append(WindowInfo(
                    id=wid,
                    title=name_out.strip(),
                    pid=int(pid_out.strip()) if pid_out.strip().isdigit() else 0,
                ).to_dict())
        return windows

    def _find_sway_focused(self, node: dict) -> dict | None:
        """Find the focused window in the Sway IPC tree."""
        if node.get("focused") and node.get("type") == "con" and node.get("name"):
            return node
        for child in node.get("nodes", []) + node.get("floating_nodes", []):
            result = self._find_sway_focused(child)
            if result:
                return result
        return None

    def _walk_sway_tree(self, node: dict, windows: list) -> None:
        """Recursively walk the Sway IPC tree to find windows."""
        if node.get("type") == "con" and node.get("name") and node.get("pid"):
            rect = node.get("rect", {})
            windows.append(WindowInfo(
                id=str(node.get("id", "")),
                title=node.get("name", ""),
                app=node.get("app_id", "") or node.get("window_properties", {}).get("class", ""),
                x=rect.get("x", 0),
                y=rect.get("y", 0),
                width=rect.get("width", 0),
                height=rect.get("height", 0),
                is_active=node.get("focused", False),
                pid=node.get("pid", 0),
            ).to_dict())
        for child in node.get("nodes", []) + node.get("floating_nodes", []):
            self._walk_sway_tree(child, windows)

    # ─── Window Finding ───

    async def find_window(self, query: str) -> dict[str, Any] | None:
        """Find a window by title or app name (fuzzy match)."""
        windows = await self.list_windows()
        query_lower = query.lower()

        # Exact title match first
        for w in windows:
            if query_lower == w.get("title", "").lower():
                return w

        # Substring match in title
        for w in windows:
            if query_lower in w.get("title", "").lower():
                return w

        # Substring match in app name
        for w in windows:
            if query_lower in w.get("app", "").lower():
                return w

        return None

    # ─── Window Focus ───

    async def focus(self, query: str) -> dict[str, Any]:
        """Bring a window to the foreground by title or app name."""
        window = await self.find_window(query)
        if not window:
            return {"success": False, "error": f"Window not found: {query}"}

        if SYSTEM == "Windows":
            cmd = (
                f'powershell -Command "'
                f"$p = Get-Process -Id {window['pid']}; "
                f"$sig = '[DllImport(\\\"user32.dll\\\")] public static extern bool SetForegroundWindow(IntPtr hWnd);'; "
                f"$type = Add-Type -MemberDefinition $sig -Name Win32Focus -PassThru; "
                f'$type::SetForegroundWindow($p.MainWindowHandle)"'
            )
        elif SYSTEM == "Darwin":
            app = window.get("app", query)
            cmd = f'osascript -e \'tell application "{app}" to activate\''
        else:
            wid = window.get("id", "")
            if wid and shutil.which("swaymsg"):
                cmd = f'swaymsg "[con_id={wid}] focus"'
            elif wid and shutil.which("wmctrl"):
                cmd = f"wmctrl -i -a {wid}"
            elif wid and shutil.which("xdotool"):
                cmd = f"xdotool windowactivate {wid}"
            else:
                return {"success": False, "error": "No window manager tool available"}

        _, err, code = await self._run(cmd)
        return {
            "success": code == 0,
            "action": "focus",
            "window": window,
            "error": err if code != 0 else None,
        }

    # ─── Window Close ───

    async def close(self, query: str) -> dict[str, Any]:
        """Close a window by title or app name."""
        window = await self.find_window(query)
        if not window:
            return {"success": False, "error": f"Window not found: {query}"}

        if SYSTEM == "Windows":
            cmd = f'powershell -Command "Stop-Process -Id {window["pid"]} -Force"'
        elif SYSTEM == "Darwin":
            app = window.get("app", query)
            cmd = f'osascript -e \'tell application "{app}" to quit\''
        else:
            wid = window.get("id", "")
            if wid and shutil.which("swaymsg"):
                cmd = f'swaymsg "[con_id={wid}] kill"'
            elif wid and shutil.which("wmctrl"):
                cmd = f"wmctrl -i -c {wid}"
            elif wid and shutil.which("xdotool"):
                cmd = f"xdotool windowclose {wid}"
            else:
                return {"success": False, "error": "No window manager tool available"}

        _, err, code = await self._run(cmd)
        return {"success": code == 0, "action": "close", "window": window}

    # ─── Window Minimize / Maximize ───

    async def minimize(self, query: str) -> dict[str, Any]:
        """Minimize a window."""
        window = await self.find_window(query)
        if not window:
            return {"success": False, "error": f"Window not found: {query}"}

        if SYSTEM == "Windows":
            cmd = (
                f'powershell -Command "'
                f"$sig = '[DllImport(\\\"user32.dll\\\")] public static extern bool ShowWindow(IntPtr h, int c);'; "
                f"$t = Add-Type -MemberDefinition $sig -Name Win32Min -PassThru; "
                f"$p = Get-Process -Id {window['pid']}; "
                f'$t::ShowWindow($p.MainWindowHandle, 6)"'
            )
        elif SYSTEM == "Darwin":
            app = window.get("app", query)
            cmd = f'osascript -e \'tell application "System Events" to set miniaturized of window 1 of process "{app}" to true\''
        else:
            wid = window.get("id", "")
            cmd = f"xdotool windowminimize {wid}" if shutil.which("xdotool") else ""

        if not cmd:
            return {"success": False, "error": "Cannot minimize on this platform"}

        _, err, code = await self._run(cmd)
        return {"success": code == 0, "action": "minimize", "window": window}

    async def maximize(self, query: str) -> dict[str, Any]:
        """Maximize a window."""
        window = await self.find_window(query)
        if not window:
            return {"success": False, "error": f"Window not found: {query}"}

        if SYSTEM == "Windows":
            cmd = (
                f'powershell -Command "'
                f"$sig = '[DllImport(\\\"user32.dll\\\")] public static extern bool ShowWindow(IntPtr h, int c);'; "
                f"$t = Add-Type -MemberDefinition $sig -Name Win32Max -PassThru; "
                f"$p = Get-Process -Id {window['pid']}; "
                f'$t::ShowWindow($p.MainWindowHandle, 3)"'
            )
        elif SYSTEM == "Darwin":
            app = window.get("app", query)
            cmd = f'osascript -e \'tell application "System Events" to set value of attribute "AXFullScreen" of window 1 of process "{app}" to true\''
        else:
            wid = window.get("id", "")
            if shutil.which("wmctrl"):
                cmd = f"wmctrl -i -r {wid} -b add,maximized_vert,maximized_horz"
            elif shutil.which("xdotool"):
                cmd = f"xdotool windowsize {wid} 100% 100%"
            else:
                return {"success": False, "error": "No window manager tool available"}

        _, err, code = await self._run(cmd)
        return {"success": code == 0, "action": "maximize", "window": window}

    # ─── Window Positioning ───

    async def move(self, query: str, x: int, y: int) -> dict[str, Any]:
        """Move a window to (x, y)."""
        window = await self.find_window(query)
        if not window:
            return {"success": False, "error": f"Window not found: {query}"}

        if SYSTEM == "Windows":
            cmd = (
                f'powershell -Command "'
                f"$sig = '[DllImport(\\\"user32.dll\\\")] public static extern bool MoveWindow(IntPtr h,int x,int y,int w,int h2,bool r);'; "
                f"$t = Add-Type -MemberDefinition $sig -Name Win32Move -PassThru; "
                f"$p = Get-Process -Id {window['pid']}; "
                f'$t::MoveWindow($p.MainWindowHandle, {x}, {y}, 800, 600, $true)"'
            )
        elif SYSTEM == "Darwin":
            app = window.get("app", query)
            cmd = f'osascript -e \'tell application "System Events" to set position of window 1 of process "{app}" to {{{x}, {y}}}\''
        else:
            wid = window.get("id", "")
            if shutil.which("wmctrl"):
                cmd = f"wmctrl -i -r {wid} -e 0,{x},{y},-1,-1"
            elif shutil.which("xdotool"):
                cmd = f"xdotool windowmove {wid} {x} {y}"
            else:
                return {"success": False, "error": "No window manager tool available"}

        _, err, code = await self._run(cmd)
        return {"success": code == 0, "action": "move", "window": window, "position": (x, y)}

    async def resize(self, query: str, width: int, height: int) -> dict[str, Any]:
        """Resize a window."""
        window = await self.find_window(query)
        if not window:
            return {"success": False, "error": f"Window not found: {query}"}

        if SYSTEM == "Windows":
            cmd = (
                f'powershell -Command "'
                f"$sig = '[DllImport(\\\"user32.dll\\\")] public static extern bool MoveWindow(IntPtr h,int x,int y,int w,int h2,bool r);'; "
                f"$t = Add-Type -MemberDefinition $sig -Name Win32Resize -PassThru; "
                f"$p = Get-Process -Id {window['pid']}; "
                f'$t::MoveWindow($p.MainWindowHandle, 0, 0, {width}, {height}, $true)"'
            )
        elif SYSTEM == "Darwin":
            app = window.get("app", query)
            cmd = f'osascript -e \'tell application "System Events" to set size of window 1 of process "{app}" to {{{width}, {height}}}\''
        else:
            wid = window.get("id", "")
            if shutil.which("wmctrl"):
                cmd = f"wmctrl -i -r {wid} -e 0,-1,-1,{width},{height}"
            elif shutil.which("xdotool"):
                cmd = f"xdotool windowsize {wid} {width} {height}"
            else:
                return {"success": False, "error": "No window manager tool available"}

        _, err, code = await self._run(cmd)
        return {"success": code == 0, "action": "resize", "window": window, "size": (width, height)}

    # ─── Smart Snapping ───

    async def snap_left(self, query: str) -> dict[str, Any]:
        """Snap window to the left half of the screen."""
        sw, sh = await self._get_screen_size()
        window = await self.find_window(query)
        if not window:
            return {"success": False, "error": f"Window not found: {query}"}

        await self.focus(query)
        await asyncio.sleep(0.1)

        # Use move + resize for precise control
        result = await self._snap_to(window, 0, 0, sw // 2, sh)
        result["action"] = "snap_left"
        return result

    async def snap_right(self, query: str) -> dict[str, Any]:
        """Snap window to the right half of the screen."""
        sw, sh = await self._get_screen_size()
        window = await self.find_window(query)
        if not window:
            return {"success": False, "error": f"Window not found: {query}"}

        await self.focus(query)
        await asyncio.sleep(0.1)

        result = await self._snap_to(window, sw // 2, 0, sw // 2, sh)
        result["action"] = "snap_right"
        return result

    async def snap_top(self, query: str) -> dict[str, Any]:
        """Snap window to the top half."""
        sw, sh = await self._get_screen_size()
        window = await self.find_window(query)
        if not window:
            return {"success": False, "error": f"Window not found: {query}"}

        result = await self._snap_to(window, 0, 0, sw, sh // 2)
        result["action"] = "snap_top"
        return result

    async def snap_bottom(self, query: str) -> dict[str, Any]:
        """Snap window to the bottom half."""
        sw, sh = await self._get_screen_size()
        window = await self.find_window(query)
        if not window:
            return {"success": False, "error": f"Window not found: {query}"}

        result = await self._snap_to(window, 0, sh // 2, sw, sh // 2)
        result["action"] = "snap_bottom"
        return result

    async def snap_quarter(self, query: str, position: str = "top_left") -> dict[str, Any]:
        """Snap window to a quarter of the screen.

        position: top_left, top_right, bottom_left, bottom_right
        """
        sw, sh = await self._get_screen_size()
        window = await self.find_window(query)
        if not window:
            return {"success": False, "error": f"Window not found: {query}"}

        hw, hh = sw // 2, sh // 2
        positions = {
            "top_left": (0, 0, hw, hh),
            "top_right": (hw, 0, hw, hh),
            "bottom_left": (0, hh, hw, hh),
            "bottom_right": (hw, hh, hw, hh),
        }

        coords = positions.get(position, positions["top_left"])
        result = await self._snap_to(window, *coords)
        result["action"] = f"snap_{position}"
        return result

    async def _snap_to(
        self, window: dict, x: int, y: int, w: int, h: int
    ) -> dict[str, Any]:
        """Move and resize a window to exact position."""
        wid = window.get("id", "")

        if SYSTEM == "Windows":
            cmd = (
                f'powershell -Command "'
                f"$sig = '[DllImport(\\\"user32.dll\\\")] public static extern bool MoveWindow(IntPtr h,int x,int y,int w,int h2,bool r);'; "
                f"$t = Add-Type -MemberDefinition $sig -Name Win32Snap -PassThru; "
                f"$p = Get-Process -Id {window.get('pid', 0)}; "
                f'$t::MoveWindow($p.MainWindowHandle, {x}, {y}, {w}, {h}, $true)"'
            )
        elif SYSTEM == "Darwin":
            app = window.get("app", "")
            cmd = (
                f'osascript -e \'tell application "System Events" to tell process "{app}" to '
                f"set position of window 1 to {{{x}, {y}}}' "
                f'-e \'tell application "System Events" to tell process "{app}" to '
                f"set size of window 1 to {{{w}, {h}}}'"
            )
        else:
            if shutil.which("swaymsg") and wid:
                # Sway: use floating + move/resize
                cmd = (
                    f'swaymsg "[con_id={wid}] floating enable, '
                    f'move position {x} {y}, '
                    f'resize set {w} {h}"'
                )
            elif shutil.which("wmctrl") and wid:
                cmd = f"wmctrl -i -r {wid} -e 0,{x},{y},{w},{h}"
            elif shutil.which("xdotool") and wid:
                cmd = f"xdotool windowmove {wid} {x} {y} && xdotool windowsize {wid} {w} {h}"
            else:
                return {"success": False, "error": "No window manager tool available"}

        _, err, code = await self._run(cmd)
        return {
            "success": code == 0,
            "window": window,
            "bounds": {"x": x, "y": y, "width": w, "height": h},
        }

    # ─── Tiling ───

    async def tile_windows(self, queries: list[str]) -> dict[str, Any]:
        """Tile multiple windows evenly across the screen.

        Arranges 2 windows side-by-side, 3 in thirds, 4 in quadrants, etc.
        """
        sw, sh = await self._get_screen_size()
        n = len(queries)

        if n == 0:
            return {"success": False, "error": "No windows specified"}

        results = []

        if n == 1:
            results.append(await self.maximize(queries[0]))
        elif n == 2:
            results.append(await self.snap_left(queries[0]))
            results.append(await self.snap_right(queries[1]))
        elif n == 3:
            third = sw // 3
            for i, q in enumerate(queries):
                w = await self.find_window(q)
                if w:
                    r = await self._snap_to(w, third * i, 0, third, sh)
                    results.append(r)
        elif n == 4:
            positions = ["top_left", "top_right", "bottom_left", "bottom_right"]
            for q, pos in zip(queries, positions):
                results.append(await self.snap_quarter(q, pos))
        else:
            # Grid layout for 5+
            cols = 3 if n > 4 else 2
            rows = (n + cols - 1) // cols
            cw = sw // cols
            ch = sh // rows
            for i, q in enumerate(queries):
                row, col = divmod(i, cols)
                w = await self.find_window(q)
                if w:
                    r = await self._snap_to(w, col * cw, row * ch, cw, ch)
                    results.append(r)

        return {
            "action": "tile",
            "count": n,
            "results": results,
            "success": all(r.get("success", False) for r in results),
        }

    # ─── Convenience ───

    async def switch_to(self, query: str) -> dict[str, Any]:
        """Switch to a window (alias for focus with a small delay)."""
        result = await self.focus(query)
        await asyncio.sleep(0.3)
        return result

    async def get_active_window(self) -> dict[str, Any]:
        """Get info about the currently focused window."""
        if SYSTEM == "Windows":
            cmd = (
                'powershell -Command "'
                "Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; "
                "public class Win32 { [DllImport(\"user32.dll\")] public static extern IntPtr GetForegroundWindow(); "
                "[DllImport(\"user32.dll\")] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder t, int c); "
                "[DllImport(\"user32.dll\")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid); }'; "
                "$h = [Win32]::GetForegroundWindow(); "
                "$sb = New-Object System.Text.StringBuilder 256; "
                "[Win32]::GetWindowText($h, $sb, 256); "
                "$pid = 0; [Win32]::GetWindowThreadProcessId($h, [ref]$pid); "
                'Write-Output \"$($sb.ToString())|$pid\"'
                '"'
            )
            out, _, _ = await self._run(cmd)
            parts = out.split("|")
            return {"title": parts[0] if parts else "", "pid": int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0}
        elif SYSTEM == "Darwin":
            cmd = 'osascript -e \'tell application "System Events" to get name of first process whose frontmost is true\''
            out, _, _ = await self._run(cmd)
            return {"app": out.strip(), "title": out.strip()}
        else:
            # Try swaymsg first (Wayland/Sway)
            if shutil.which("swaymsg"):
                try:
                    import json as _json
                    out, _, rc = await self._run("swaymsg -t get_tree --raw")
                    if rc == 0:
                        tree = _json.loads(out)
                        focused = self._find_sway_focused(tree)
                        if focused:
                            return {
                                "id": str(focused.get("id", "")),
                                "title": focused.get("name", ""),
                                "app": focused.get("app_id", ""),
                            }
                except Exception:
                    pass
            if shutil.which("xdotool"):
                wid_out, _, _ = await self._run("xdotool getactivewindow")
                name_out, _, _ = await self._run(f"xdotool getwindowname {wid_out.strip()}")
                return {"id": wid_out.strip(), "title": name_out.strip()}
            return {"error": "No window tool available (install xdotool or swaymsg)"}
