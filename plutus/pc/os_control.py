"""
OS Control Layer — Cross-platform app launching, system commands, and process management.

This is the PRIMARY way Plutus interacts with the computer, matching OpenClaw's approach.
Instead of trying to click on icons via screenshots, we use native OS commands.
"""

import asyncio
import platform
import subprocess
import os
import json
import shutil
from pathlib import Path
from typing import Optional


def get_os() -> str:
    """Detect the operating system."""
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    elif system == "windows":
        return "windows"
    else:
        return "linux"


# ─── App Registry: Maps common app names to OS-specific launch commands ───

APP_REGISTRY = {
    "windows": {
        # Browsers
        "chrome": "start chrome",
        "google chrome": "start chrome",
        "firefox": "start firefox",
        "edge": "start msedge",
        "brave": "start brave",
        # Communication
        "whatsapp": "start whatsapp:",
        "telegram": "start telegram:",
        "discord": "start discord:",
        "slack": "start slack:",
        "teams": "start msteams:",
        "microsoft teams": "start msteams:",
        "zoom": "start zoommtg:",
        "skype": "start skype:",
        "signal": "start signal:",
        # Productivity
        "word": "start winword",
        "excel": "start excel",
        "powerpoint": "start powerpnt",
        "outlook": "start outlook",
        "onenote": "start onenote:",
        "notepad": "start notepad",
        "notepad++": "start notepad++",
        "calculator": "start calc",
        # Development
        "vscode": "start code",
        "visual studio code": "start code",
        "terminal": "start wt",
        "windows terminal": "start wt",
        "cmd": "start cmd",
        "powershell": "start powershell",
        "git bash": "start git-bash",
        # System
        "file explorer": "start explorer",
        "explorer": "start explorer",
        "settings": "start ms-settings:",
        "control panel": "start control",
        "task manager": "start taskmgr",
        # Media
        "spotify": "start spotify:",
        "vlc": "start vlc",
        "photos": "start ms-photos:",
        # Other
        "paint": "start mspaint",
        "snipping tool": "start snippingtool",
    },
    "macos": {
        # Browsers
        "chrome": "open -a 'Google Chrome'",
        "google chrome": "open -a 'Google Chrome'",
        "firefox": "open -a Firefox",
        "safari": "open -a Safari",
        "brave": "open -a 'Brave Browser'",
        "edge": "open -a 'Microsoft Edge'",
        "arc": "open -a Arc",
        # Communication
        "whatsapp": "open -a WhatsApp",
        "telegram": "open -a Telegram",
        "discord": "open -a Discord",
        "slack": "open -a Slack",
        "teams": "open -a 'Microsoft Teams'",
        "zoom": "open -a zoom.us",
        "skype": "open -a Skype",
        "signal": "open -a Signal",
        "messages": "open -a Messages",
        "facetime": "open -a FaceTime",
        # Productivity
        "word": "open -a 'Microsoft Word'",
        "excel": "open -a 'Microsoft Excel'",
        "powerpoint": "open -a 'Microsoft PowerPoint'",
        "outlook": "open -a 'Microsoft Outlook'",
        "notes": "open -a Notes",
        "reminders": "open -a Reminders",
        "calendar": "open -a Calendar",
        "pages": "open -a Pages",
        "numbers": "open -a Numbers",
        "keynote": "open -a Keynote",
        # Development
        "vscode": "open -a 'Visual Studio Code'",
        "visual studio code": "open -a 'Visual Studio Code'",
        "terminal": "open -a Terminal",
        "iterm": "open -a iTerm",
        "xcode": "open -a Xcode",
        # System
        "finder": "open -a Finder",
        "file explorer": "open -a Finder",
        "settings": "open -a 'System Preferences'",
        "system preferences": "open -a 'System Preferences'",
        "activity monitor": "open -a 'Activity Monitor'",
        # Media
        "spotify": "open -a Spotify",
        "music": "open -a Music",
        "vlc": "open -a VLC",
        "photos": "open -a Photos",
        "preview": "open -a Preview",
    },
    "linux": {
        # Browsers
        "chrome": "google-chrome || chromium-browser || chromium",
        "google chrome": "google-chrome || chromium-browser",
        "firefox": "firefox",
        "brave": "brave-browser",
        # Communication
        "whatsapp": "xdg-open https://web.whatsapp.com",
        "telegram": "telegram-desktop || xdg-open https://web.telegram.org",
        "discord": "discord || xdg-open https://discord.com/app",
        "slack": "slack",
        "teams": "teams || xdg-open https://teams.microsoft.com",
        "signal": "signal-desktop",
        # Productivity
        "libreoffice": "libreoffice",
        "writer": "libreoffice --writer",
        "calc": "libreoffice --calc",
        "impress": "libreoffice --impress",
        # Development
        "vscode": "code",
        "visual studio code": "code",
        "terminal": "x-terminal-emulator || gnome-terminal || konsole || xterm",
        # System
        "file explorer": "xdg-open . || nautilus || dolphin || thunar",
        "files": "nautilus || dolphin || thunar",
        "settings": "gnome-control-center || systemsettings5",
        # Media
        "spotify": "spotify",
        "vlc": "vlc",
    },
}


class OSControl:
    """Cross-platform OS control layer — the primary way to interact with the computer."""

    def __init__(self):
        self.os_type = get_os()
        self.app_registry = APP_REGISTRY.get(self.os_type, {})

    # ─── App Launching ───

    async def open_app(self, app_name: str) -> dict:
        """Open an application by name using OS-native commands."""
        app_lower = app_name.lower().strip()

        # Check registry first
        if app_lower in self.app_registry:
            cmd = self.app_registry[app_lower]
            return await self._run_launch_command(cmd, app_name)

        # Try fuzzy match
        for key, cmd in self.app_registry.items():
            if app_lower in key or key in app_lower:
                return await self._run_launch_command(cmd, app_name)

        # Fallback: try OS-specific generic open
        return await self._generic_open(app_name)

    async def _run_launch_command(self, cmd: str, app_name: str) -> dict:
        """Execute a launch command and return result."""
        try:
            if self.os_type == "windows":
                # Windows: use cmd /c for start commands
                process = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    shell=True,
                )
            else:
                # macOS/Linux: use bash
                process = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=10
            )

            if process.returncode == 0 or self.os_type == "windows":
                return {
                    "success": True,
                    "app": app_name,
                    "method": "os_command",
                    "command": cmd,
                    "message": f"Successfully opened {app_name}",
                }
            else:
                error = stderr.decode().strip() if stderr else "Unknown error"
                return {
                    "success": False,
                    "app": app_name,
                    "error": error,
                    "command": cmd,
                    "suggestion": f"Try opening {app_name} manually or check if it's installed",
                }
        except asyncio.TimeoutError:
            # Timeout usually means the app opened (it's running)
            return {
                "success": True,
                "app": app_name,
                "method": "os_command",
                "command": cmd,
                "message": f"Launched {app_name} (app is running)",
            }
        except Exception as e:
            return {
                "success": False,
                "app": app_name,
                "error": str(e),
            }

    async def _generic_open(self, app_name: str) -> dict:
        """Try to open an app using generic OS commands."""
        if self.os_type == "windows":
            # Try 'start' with the app name directly
            cmd = f"start {app_name}"
        elif self.os_type == "macos":
            cmd = f"open -a '{app_name}'"
        else:
            # Linux: try the app name as a command
            cmd = app_name.lower().replace(" ", "-")

        return await self._run_launch_command(cmd, app_name)

    async def close_app(self, app_name: str) -> dict:
        """Close an application by name."""
        try:
            if self.os_type == "windows":
                # Use taskkill on Windows
                cmd = f'taskkill /IM "{app_name}.exe" /F 2>nul || taskkill /FI "WINDOWTITLE eq *{app_name}*" /F'
            elif self.os_type == "macos":
                cmd = f"osascript -e 'quit app \"{app_name}\"'"
            else:
                cmd = f"pkill -f '{app_name}' || killall '{app_name}'"

            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=10
            )

            return {
                "success": True,
                "app": app_name,
                "message": f"Closed {app_name}",
            }
        except Exception as e:
            return {"success": False, "app": app_name, "error": str(e)}

    # ─── URL Opening ───

    async def open_url(self, url: str, browser: Optional[str] = None) -> dict:
        """Open a URL in the default or specified browser."""
        try:
            if browser:
                browser_lower = browser.lower()
                if browser_lower in self.app_registry:
                    if self.os_type == "windows":
                        cmd = f"start {browser_lower} {url}"
                    elif self.os_type == "macos":
                        app_name = {
                            "chrome": "Google Chrome",
                            "firefox": "Firefox",
                            "safari": "Safari",
                            "edge": "Microsoft Edge",
                            "brave": "Brave Browser",
                            "arc": "Arc",
                        }.get(browser_lower, browser)
                        cmd = f"open -a '{app_name}' '{url}'"
                    else:
                        cmd = f"{browser_lower} '{url}'"
                else:
                    cmd = self._default_open_url_cmd(url)
            else:
                cmd = self._default_open_url_cmd(url)

            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(process.communicate(), timeout=10)

            return {
                "success": True,
                "url": url,
                "browser": browser or "default",
                "message": f"Opened {url}",
            }
        except Exception as e:
            return {"success": False, "url": url, "error": str(e)}

    def _default_open_url_cmd(self, url: str) -> str:
        if self.os_type == "windows":
            return f'start "" "{url}"'
        elif self.os_type == "macos":
            return f"open '{url}'"
        else:
            return f"xdg-open '{url}'"

    # ─── Shell Command Execution ───

    async def run_command(
        self, command: str, timeout: int = 30, cwd: Optional[str] = None
    ) -> dict:
        """Execute a shell command and return the output."""
        try:
            if self.os_type == "windows":
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    shell=True,
                )
            else:
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )

            return {
                "success": process.returncode == 0,
                "exit_code": process.returncode,
                "stdout": stdout.decode(errors="replace").strip() if stdout else "",
                "stderr": stderr.decode(errors="replace").strip() if stderr else "",
                "command": command,
            }
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"Command timed out after {timeout}s",
                "command": command,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "command": command}

    # ─── Process Management ───

    async def list_processes(self, filter_name: Optional[str] = None) -> dict:
        """List running processes, optionally filtered by name."""
        try:
            if self.os_type == "windows":
                cmd = "tasklist /FO CSV /NH"
            else:
                cmd = "ps aux"

            result = await self.run_command(cmd)
            if not result["success"]:
                return result

            processes = []
            lines = result["stdout"].split("\n")

            if self.os_type == "windows":
                for line in lines:
                    parts = line.strip().strip('"').split('","')
                    if len(parts) >= 5:
                        name = parts[0]
                        pid = parts[1]
                        mem = parts[4] if len(parts) > 4 else ""
                        if filter_name and filter_name.lower() not in name.lower():
                            continue
                        processes.append({"name": name, "pid": pid, "memory": mem})
            else:
                for line in lines[1:]:  # Skip header
                    parts = line.split(None, 10)
                    if len(parts) >= 11:
                        name = parts[10]
                        pid = parts[1]
                        cpu = parts[2]
                        mem = parts[3]
                        if filter_name and filter_name.lower() not in name.lower():
                            continue
                        processes.append(
                            {"name": name, "pid": pid, "cpu": cpu, "memory": mem}
                        )

            return {
                "success": True,
                "count": len(processes),
                "processes": processes[:50],  # Limit to 50
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def kill_process(self, pid: Optional[int] = None, name: Optional[str] = None) -> dict:
        """Kill a process by PID or name."""
        try:
            if pid:
                if self.os_type == "windows":
                    cmd = f"taskkill /PID {pid} /F"
                else:
                    cmd = f"kill -9 {pid}"
            elif name:
                if self.os_type == "windows":
                    cmd = f'taskkill /IM "{name}" /F'
                else:
                    cmd = f"pkill -9 -f '{name}'"
            else:
                return {"success": False, "error": "Provide either pid or name"}

            return await self.run_command(cmd)
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── System Info ───

    async def get_active_window(self) -> dict:
        """Get the currently active/focused window."""
        try:
            if self.os_type == "windows":
                # PowerShell to get active window
                cmd = 'powershell -Command "Add-Type -TypeDefinition \'using System; using System.Runtime.InteropServices; public class Win { [DllImport(\\\"user32.dll\\\")] public static extern IntPtr GetForegroundWindow(); [DllImport(\\\"user32.dll\\\")] public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder text, int count); } \'; $h = [Win]::GetForegroundWindow(); $sb = New-Object System.Text.StringBuilder 256; [Win]::GetWindowText($h, $sb, 256); $sb.ToString()"'
            elif self.os_type == "macos":
                cmd = "osascript -e 'tell application \"System Events\" to get name of first application process whose frontmost is true'"
            else:
                cmd = "xdotool getactivewindow getwindowname 2>/dev/null || echo 'unknown'"

            result = await self.run_command(cmd, timeout=5)
            title = result.get("stdout", "").strip()

            return {
                "success": True,
                "window_title": title,
                "os": self.os_type,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_system_info(self) -> dict:
        """Get basic system information."""
        return {
            "success": True,
            "os": self.os_type,
            "platform": platform.platform(),
            "hostname": platform.node(),
            "python_version": platform.python_version(),
            "home_dir": str(Path.home()),
            "cwd": os.getcwd(),
        }

    # ─── File Operations ───

    async def open_file(self, file_path: str) -> dict:
        """Open a file with the default application."""
        try:
            path = Path(file_path).expanduser().resolve()
            if not path.exists():
                return {"success": False, "error": f"File not found: {file_path}"}

            if self.os_type == "windows":
                cmd = f'start "" "{path}"'
            elif self.os_type == "macos":
                cmd = f"open '{path}'"
            else:
                cmd = f"xdg-open '{path}'"

            return await self._run_launch_command(cmd, str(path))
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def open_folder(self, folder_path: str) -> dict:
        """Open a folder in the file explorer."""
        try:
            path = Path(folder_path).expanduser().resolve()
            if not path.exists():
                return {"success": False, "error": f"Folder not found: {folder_path}"}

            if self.os_type == "windows":
                cmd = f'explorer "{path}"'
            elif self.os_type == "macos":
                cmd = f"open '{path}'"
            else:
                cmd = f"xdg-open '{path}'"

            return await self._run_launch_command(cmd, str(path))
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Clipboard ───

    async def get_clipboard(self) -> dict:
        """Get the current clipboard content."""
        try:
            if self.os_type == "windows":
                cmd = "powershell -Command Get-Clipboard"
            elif self.os_type == "macos":
                cmd = "pbpaste"
            else:
                cmd = "xclip -selection clipboard -o 2>/dev/null || xsel --clipboard --output 2>/dev/null"

            result = await self.run_command(cmd, timeout=5)
            return {
                "success": True,
                "content": result.get("stdout", ""),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def set_clipboard(self, text: str) -> dict:
        """Set the clipboard content."""
        try:
            if self.os_type == "windows":
                cmd = f'powershell -Command "Set-Clipboard -Value \'{text}\'"'
            elif self.os_type == "macos":
                cmd = f"echo '{text}' | pbcopy"
            else:
                cmd = f"echo '{text}' | xclip -selection clipboard"

            result = await self.run_command(cmd, timeout=5)
            return {"success": True, "message": "Clipboard updated"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Notifications ───

    async def send_notification(self, title: str, message: str) -> dict:
        """Send a desktop notification."""
        try:
            if self.os_type == "windows":
                cmd = f'powershell -Command "New-BurntToastNotification -Text \'{title}\', \'{message}\'" 2>nul || powershell -Command "[System.Reflection.Assembly]::LoadWithPartialName(\'System.Windows.Forms\'); [System.Windows.Forms.MessageBox]::Show(\'{message}\', \'{title}\')"'
            elif self.os_type == "macos":
                cmd = f"osascript -e 'display notification \"{message}\" with title \"{title}\"'"
            else:
                cmd = f"notify-send '{title}' '{message}'"

            result = await self.run_command(cmd, timeout=10)
            return {"success": True, "message": f"Notification sent: {title}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Convenience: List installed apps ───

    async def list_available_apps(self) -> dict:
        """List apps that Plutus knows how to open on this OS."""
        apps = []
        for name in sorted(self.app_registry.keys()):
            apps.append(name)
        return {
            "success": True,
            "os": self.os_type,
            "apps": apps,
            "count": len(apps),
            "note": "These are apps Plutus can open by name. You can also open any app by its executable name.",
        }
