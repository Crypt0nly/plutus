"""
Desktop Control — Cross-platform accessibility tree for native apps.

Same pattern as BrowserControl:
  1. desktop_snapshot() -> numbered accessibility tree of the focused window
  2. LLM reads the tree, picks a ref number
  3. desktop_click_ref(3) / desktop_type_ref(2, "hello") -> precise interaction

Backends:
  - Windows: pywinauto UIA / uiautomation
  - macOS:   AppleScript via System Events accessibility
  - Linux:   xdotool + AT-SPI2 (via python-atspi2 or subprocess)

Falls back to PyAutoGUI for mouse/keyboard when native patterns aren't available.
"""

from __future__ import annotations

import asyncio
import json
import logging
import platform
import shutil
import subprocess
import time
from typing import Any

logger = logging.getLogger("plutus.pc.desktop")

SYSTEM = platform.system()

# Interactive control types we include in the snapshot
INTERACTIVE_TYPES = {
    "Button", "CheckBox", "ComboBox", "Edit", "Hyperlink",
    "ListItem", "MenuItem", "MenuBar", "Menu", "RadioButton",
    "Slider", "Spinner", "Tab", "TabItem", "TreeItem",
    "DataItem", "Document", "SplitButton", "ToolBar",
    # macOS equivalents
    "AXButton", "AXCheckBox", "AXComboBox", "AXTextField", "AXLink",
    "AXMenuItem", "AXMenuBar", "AXRadioButton", "AXSlider", "AXTabGroup",
    "AXTextArea", "AXPopUpButton",
    # Linux AT-SPI equivalents
    "push button", "check box", "combo box", "text", "link",
    "menu item", "menu bar", "radio button", "slider", "page tab",
    "tree item", "list item",
}

# Control types we always show (even if not "interactive") for context
CONTEXT_TYPES = {
    "Text", "StatusBar", "Header", "HeaderItem", "Group",
    "TitleBar", "Window", "Pane",
    # macOS
    "AXStaticText", "AXGroup", "AXWindow", "AXScrollArea",
    # Linux AT-SPI
    "label", "status bar", "panel", "frame", "filler",
}


class DesktopControl:
    """
    Cross-platform accessibility controller — provides accessibility tree snapshots
    and ref-based interaction for native applications on Windows, macOS, and Linux.
    """

    def __init__(self):
        self._ref_map: dict[int, dict[str, Any]] = {}
        self._ref_counter: int = 0
        self._uia_available: bool = False
        self._pywinauto_available: bool = False
        self._pyautogui_available: bool = False
        self._macos_available: bool = False
        self._linux_atspi_available: bool = False
        self._linux_xdotool_available: bool = False
        self._initialized: bool = False

    def _ensure_init(self):
        """Lazy-initialize platform-specific libraries."""
        if self._initialized:
            return

        self._initialized = True

        if SYSTEM == "Windows":
            self._init_windows()
        elif SYSTEM == "Darwin":
            self._init_macos()
        else:
            self._init_linux()

        # PyAutoGUI as last resort for mouse/keyboard (all platforms)
        try:
            import pyautogui  # noqa: F401
            self._pyautogui_available = True
        except ImportError:
            pass

    def _init_windows(self):
        """Initialize Windows UIA backends."""
        # Try pywinauto first (preferred)
        try:
            import pywinauto  # noqa: F401
            from pywinauto import Desktop as PywinautoDesktop  # noqa: F401
            self._pywinauto_available = True
            self._uia_available = True
            logger.info("pywinauto UIA backend available")
        except ImportError:
            logger.warning("pywinauto not installed — run: pip install pywinauto")

        # Try uiautomation as fallback
        if not self._uia_available:
            try:
                import uiautomation  # noqa: F401
                self._uia_available = True
                logger.info("uiautomation library available")
            except ImportError:
                logger.warning("uiautomation not installed — run: pip install uiautomation")

    def _init_macos(self):
        """Initialize macOS accessibility via AppleScript."""
        if shutil.which("osascript"):
            self._macos_available = True
            logger.info("macOS AppleScript accessibility available")
        else:
            logger.warning("osascript not found — macOS accessibility unavailable")

    def _init_linux(self):
        """Initialize Linux accessibility backends."""
        # Check for xdotool
        if shutil.which("xdotool"):
            self._linux_xdotool_available = True
            logger.info("xdotool available for Linux desktop control")

        # Check for AT-SPI2 (accessibility tree on Linux)
        try:
            atspi_check = (
                "import gi; gi.require_version('Atspi', '2.0'); "
                "from gi.repository import Atspi"
            )
            result = subprocess.run(
                ["python3", "-c", atspi_check],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0:
                self._linux_atspi_available = True
                logger.info("AT-SPI2 accessibility available for Linux")
        except Exception:
            pass

        if not self._linux_xdotool_available and not self._linux_atspi_available:
            logger.warning(
                "No Linux desktop control tools found. Install: "
                "sudo apt install xdotool (or: pip install pyatspi)"
            )

    # ─── Snapshot ───────────────────────────────────────────────────

    async def snapshot(self, window_title: str | None = None, max_depth: int = 8) -> dict[str, Any]:
        """
        Take an accessibility tree snapshot of the focused (or specified) window.
        Returns a numbered list of interactive elements, just like BrowserControl.snapshot().
        """
        self._ensure_init()

        if SYSTEM == "Windows":
            return await self._snapshot_windows(window_title, max_depth)
        elif SYSTEM == "Darwin":
            return await self._snapshot_macos(window_title, max_depth)
        else:
            return await self._snapshot_linux(window_title, max_depth)

    # ─── Windows snapshot ───

    async def _snapshot_windows(self, window_title: str | None, max_depth: int) -> dict[str, Any]:
        if not self._uia_available:
            return {
                "success": False,
                "error": "Windows UI Automation not available. Install pywinauto: pip install pywinauto",
                "hint": "This feature requires pywinauto installed.",
            }
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, self._snapshot_sync, window_title, max_depth
            )
            return result
        except Exception as e:
            logger.error(f"Desktop snapshot failed: {e}")
            return {"success": False, "error": str(e)}

    def _snapshot_sync(self, window_title: str | None, max_depth: int) -> dict[str, Any]:
        """Synchronous snapshot implementation using pywinauto."""
        if self._pywinauto_available:
            return self._snapshot_pywinauto(window_title, max_depth)
        else:
            return self._snapshot_uiautomation(window_title, max_depth)

    def _snapshot_pywinauto(self, window_title: str | None, max_depth: int) -> dict[str, Any]:
        """Snapshot using pywinauto UIA backend."""
        from pywinauto import Desktop as PywinautoDesktop

        desktop = PywinautoDesktop(backend="uia")

        # Find the target window
        if window_title:
            windows = desktop.windows(title_re=f".*{window_title}.*", visible_only=True)
        else:
            # Get the foreground window
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return {"success": False, "error": "No foreground window found"}
            windows = desktop.windows(handle=hwnd)

        if not windows:
            return {"success": False, "error": f"No window found{' matching: ' + window_title if window_title else ''}"}

        window = windows[0]
        window_wrapper = window.wrapper_object()

        # Reset ref map
        self._ref_map = {}
        self._ref_counter = 0

        # Build the accessibility tree
        lines = []
        window_title_str = window_wrapper.window_text() or "Unknown"
        window_class = window_wrapper.friendly_class_name() or ""
        lines.append(f"Window: {window_title_str} [{window_class}]")
        lines.append("")

        # Walk the tree
        self._walk_element_pywinauto(window_wrapper, lines, depth=0, max_depth=max_depth)

        snapshot_text = "\n".join(lines)

        return {
            "success": True,
            "window": window_title_str,
            "snapshot": snapshot_text,
            "element_count": self._ref_counter,
            "hint": "Use ref numbers to interact: desktop_click_ref(1), desktop_type_ref(2, 'text'), etc.",
        }

    def _walk_element_pywinauto(self, element, lines: list, depth: int, max_depth: int):
        """Recursively walk the UIA tree and build the numbered element list."""
        if depth > max_depth:
            return

        try:
            children = element.children()
        except Exception:
            return

        for child in children:
            try:
                control_type = child.friendly_class_name() or ""
                name = child.window_text() or ""
                auto_id = ""
                is_enabled = True
                value = ""

                try:
                    elem_info = child.element_info
                    auto_id = elem_info.automation_id or ""
                    is_enabled = elem_info.enabled
                except Exception:
                    pass

                # Try to get value for editable fields
                try:
                    if control_type in ("Edit", "ComboBox", "Document"):
                        iface = child.iface_value
                        if iface:
                            value = iface.CurrentValue or ""
                except Exception:
                    pass

                # Determine if this is interactive
                is_interactive = control_type in INTERACTIVE_TYPES
                is_context = control_type in CONTEXT_TYPES

                if is_interactive and is_enabled:
                    self._ref_counter += 1
                    ref = self._ref_counter

                    # Store ref info for later interaction
                    self._ref_map[ref] = {
                        "element": child,
                        "control_type": control_type,
                        "name": name,
                        "auto_id": auto_id,
                        "value": value,
                        "backend": "pywinauto",
                    }

                    # Format the line
                    indent = "  " * min(depth, 4)
                    display = f"{indent}[{ref}] {control_type.lower()}"
                    if name:
                        display += f' "{name}"'
                    if value and value != name:
                        display += f' value="{value[:100]}"'
                    if auto_id and auto_id != name:
                        display += f' (id: {auto_id})'

                    lines.append(display)

                elif is_context and name and name.strip():
                    # Show context elements without ref numbers
                    indent = "  " * min(depth, 4)
                    truncated = name[:200] + "..." if len(name) > 200 else name
                    lines.append(f"{indent}{control_type.lower()}: {truncated}")

                # Recurse into children
                self._walk_element_pywinauto(child, lines, depth + 1, max_depth)

            except Exception as e:
                logger.debug(f"Error processing element: {e}")
                continue

    def _snapshot_uiautomation(self, window_title: str | None, max_depth: int) -> dict[str, Any]:
        """Snapshot using uiautomation library (fallback)."""
        import uiautomation as auto

        # Find the target window
        if window_title:
            window = auto.WindowControl(searchDepth=1, Name=window_title)
        else:
            window = auto.GetForegroundControl()

        if not window or not window.Exists(0):
            return {"success": False, "error": "No window found"}

        # Reset ref map
        self._ref_map = {}
        self._ref_counter = 0

        lines = []
        window_name = window.Name or "Unknown"
        lines.append(f"Window: {window_name}")
        lines.append("")

        self._walk_element_uiautomation(window, lines, depth=0, max_depth=max_depth)

        snapshot_text = "\n".join(lines)

        return {
            "success": True,
            "window": window_name,
            "snapshot": snapshot_text,
            "element_count": self._ref_counter,
            "hint": "Use ref numbers to interact: desktop_click_ref(1), desktop_type_ref(2, 'text'), etc.",
        }

    def _walk_element_uiautomation(self, element, lines: list, depth: int, max_depth: int):
        """Walk tree using uiautomation library."""
        if depth > max_depth:
            return

        try:
            children = element.GetChildren()
        except Exception:
            return

        for child in children:
            try:
                control_type = child.ControlTypeName or ""
                # Remove "Control" suffix
                control_type = control_type.replace("Control", "")
                name = child.Name or ""
                auto_id = child.AutomationId or ""
                is_enabled = child.IsEnabled

                value = ""
                try:
                    vp = child.GetValuePattern()
                    if vp:
                        value = vp.Value or ""
                except Exception:
                    pass

                is_interactive = control_type in INTERACTIVE_TYPES
                is_context = control_type in CONTEXT_TYPES

                if is_interactive and is_enabled:
                    self._ref_counter += 1
                    ref = self._ref_counter

                    self._ref_map[ref] = {
                        "element": child,
                        "control_type": control_type,
                        "name": name,
                        "auto_id": auto_id,
                        "value": value,
                        "backend": "uiautomation",
                    }

                    indent = "  " * min(depth, 4)
                    display = f"{indent}[{ref}] {control_type.lower()}"
                    if name:
                        display += f' "{name}"'
                    if value and value != name:
                        display += f' value="{value[:100]}"'
                    if auto_id and auto_id != name:
                        display += f' (id: {auto_id})'

                    lines.append(display)

                elif is_context and name and name.strip():
                    indent = "  " * min(depth, 4)
                    truncated = name[:200] + "..." if len(name) > 200 else name
                    lines.append(f"{indent}{control_type.lower()}: {truncated}")

                self._walk_element_uiautomation(child, lines, depth + 1, max_depth)

            except Exception:
                continue

    # ─── macOS snapshot ───

    async def _snapshot_macos(self, window_title: str | None, max_depth: int) -> dict[str, Any]:
        """Take accessibility snapshot on macOS via AppleScript + System Events."""
        if not self._macos_available:
            return {
                "success": False,
                "error": "macOS accessibility not available (osascript not found).",
            }

        try:
            # Get the frontmost app or match by title
            if window_title:
                app_script = f'''
                tell application "System Events"
                    set targetApp to ""
                    repeat with p in (every process whose visible is true)
                        try
                            repeat with w in windows of p
                                if name of w contains "{window_title}" then
                                    set targetApp to name of p
                                    exit repeat
                                end if
                            end repeat
                        end try
                        if targetApp is not "" then exit repeat
                    end repeat
                    return targetApp
                end tell
                '''
                proc = await asyncio.create_subprocess_exec(
                    "osascript", "-e", app_script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
                app_name = stdout.decode().strip()
                if not app_name:
                    return {"success": False, "error": f"No window found matching: {window_title}"}
            else:
                # Get frontmost application
                proc = await asyncio.create_subprocess_exec(
                    "osascript", "-e",
                    'tell application "System Events" to get name of first process whose frontmost is true',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
                app_name = stdout.decode().strip()
                if not app_name:
                    return {"success": False, "error": "No frontmost application found"}

            # Get the UI element tree via AppleScript
            tree_script = f'''
            tell application "System Events"
                tell process "{app_name}"
                    set frontmost to true
                    delay 0.2
                    set output to ""
                    try
                        set winName to name of window 1
                    on error
                        set winName to "{app_name}"
                    end try
                    set output to output & "Window: " & winName & linefeed & linefeed

                    -- Walk UI elements up to depth {min(max_depth, 4)}
                    try
                        set uiElems to entire contents of window 1
                        repeat with elem in uiElems
                            try
                                set elemRole to role of elem
                                set elemDesc to ""
                                try
                                    set elemDesc to description of elem
                                end try
                                set elemTitle to ""
                                try
                                    set elemTitle to title of elem
                                end try
                                if elemTitle is missing value then set elemTitle to ""
                                set elemValue to ""
                                try
                                    set elemValue to value of elem as text
                                end try
                                if elemValue is missing value then set elemValue to ""
                                set elemEnabled to true
                                try
                                    set elemEnabled to enabled of elem
                                end try

                                set line_out to elemRole & "|" & elemTitle & "|" & elemDesc & "|" & elemValue & "|" & (elemEnabled as text)
                                set output to output & line_out & linefeed
                            on error
                                -- skip elements that can't be read
                            end try
                        end repeat
                    on error errMsg
                        set output to output & "Error reading UI: " & errMsg
                    end try
                    return output
                end tell
            end tell
            '''
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", tree_script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            raw = stdout.decode("utf-8", errors="replace").strip()

            if not raw:
                err = stderr.decode("utf-8", errors="replace").strip()
                return {
                    "success": False,
                    "error": f"Could not read accessibility tree: {err}",
                    "hint": (
                        "Ensure the app has accessibility permissions. "
                        "Go to System Settings > Privacy & Security > Accessibility "
                        "and add Terminal / your terminal app."
                    ),
                }

            # Parse the raw output into structured snapshot
            self._ref_map = {}
            self._ref_counter = 0
            lines = []

            for line in raw.split("\n"):
                line = line.strip()
                if not line:
                    continue
                if line.startswith("Window:") or line.startswith("Error"):
                    lines.append(line)
                    continue

                parts = line.split("|")
                if len(parts) < 5:
                    continue

                role = parts[0].strip()
                title = parts[1].strip()
                desc = parts[2].strip()
                value = parts[3].strip()
                enabled = parts[4].strip().lower() == "true"

                display_name = title or desc
                is_interactive = role in INTERACTIVE_TYPES or role.startswith("AX") and any(
                    t in role for t in ("Button", "CheckBox", "ComboBox", "TextField",
                                        "Link", "MenuItem", "RadioButton", "Slider",
                                        "Tab", "PopUp", "TextArea")
                )
                is_context = role in CONTEXT_TYPES or role in ("AXStaticText", "AXGroup")

                if is_interactive and enabled:
                    self._ref_counter += 1
                    ref = self._ref_counter

                    self._ref_map[ref] = {
                        "role": role,
                        "title": title,
                        "description": desc,
                        "value": value,
                        "backend": "macos",
                        "app": app_name,
                    }

                    role_short = role.replace("AX", "").lower()
                    display = f"  [{ref}] {role_short}"
                    if display_name:
                        display += f' "{display_name}"'
                    if value and value != display_name:
                        display += f' value="{value[:100]}"'
                    lines.append(display)

                elif is_context and display_name:
                    role_short = role.replace("AX", "").lower()
                    truncated = display_name[:200] + "..." if len(display_name) > 200 else display_name
                    lines.append(f"  {role_short}: {truncated}")

            if not lines:
                lines.append("(No UI elements found)")

            return {
                "success": True,
                "window": app_name,
                "snapshot": "\n".join(lines),
                "element_count": self._ref_counter,
                "platform": "macos",
                "hint": "Use ref numbers to interact: desktop_click_ref(1), desktop_type_ref(2, 'text'), etc.",
            }

        except TimeoutError:
            return {"success": False, "error": "AppleScript timed out reading accessibility tree"}
        except Exception as e:
            logger.error(f"macOS snapshot failed: {e}")
            return {"success": False, "error": str(e)}

    # ─── Linux snapshot ───

    async def _snapshot_linux(self, window_title: str | None, max_depth: int) -> dict[str, Any]:
        """Take accessibility snapshot on Linux via AT-SPI2 or xdotool fallback."""
        if self._linux_atspi_available:
            return await self._snapshot_linux_atspi(window_title, max_depth)

        if self._linux_xdotool_available:
            return await self._snapshot_linux_xdotool(window_title)

        return {
            "success": False,
            "error": (
                "No Linux desktop accessibility tools available. "
                "Install xdotool: sudo apt install xdotool\n"
                "For full accessibility tree: sudo apt install python3-gi gir1.2-atspi-2.0 at-spi2-core"
            ),
        }

    async def _snapshot_linux_atspi(self, window_title: str | None, max_depth: int) -> dict[str, Any]:
        """Snapshot using AT-SPI2 accessibility tree on Linux."""
        # Use a subprocess to avoid importing gi in the main process
        atspi_script = f'''
import json, sys
import gi
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi

max_depth = {max_depth}
target_title = {json.dumps(window_title)}

desktop = Atspi.get_desktop(0)
n_children = desktop.get_child_count()

# Find the target window
target_app = None
target_win = None

for i in range(n_children):
    app = desktop.get_child_at_index(i)
    if app is None:
        continue
    app_name = app.get_name() or ""
    for j in range(app.get_child_count()):
        win = app.get_child_at_index(j)
        if win is None:
            continue
        win_name = win.get_name() or ""
        win_role = win.get_role_name() or ""
        if win_role not in ("frame", "window", "dialog"):
            continue
        if target_title:
            if target_title.lower() in win_name.lower():
                target_app = app
                target_win = win
                break
        else:
            # Try to find the active window
            try:
                state_set = win.get_state_set()
                if state_set.contains(Atspi.StateType.ACTIVE):
                    target_app = app
                    target_win = win
                    break
            except Exception:
                pass
    if target_win:
        break

# If no active window found, just take the first visible one
if not target_win:
    for i in range(n_children):
        app = desktop.get_child_at_index(i)
        if app is None:
            continue
        for j in range(app.get_child_count()):
            win = app.get_child_at_index(j)
            if win is None:
                continue
            win_role = win.get_role_name() or ""
            if win_role in ("frame", "window"):
                win_name = win.get_name() or ""
                if win_name:
                    target_app = app
                    target_win = win
                    break
        if target_win:
            break

if not target_win:
    print(json.dumps({{"success": False, "error": "No window found"}}))
    sys.exit(0)

elements = []
ref = 0

interactive_roles = {{
    "push button", "check box", "combo box", "text", "link",
    "menu item", "menu bar", "radio button", "slider", "page tab",
    "tree item", "list item", "toggle button", "spin button",
    "entry", "password text",
}}
context_roles = {{
    "label", "status bar", "panel", "frame", "filler",
    "heading", "section", "paragraph",
}}

def walk(node, depth):
    global ref
    if depth > max_depth or node is None:
        return
    try:
        role = node.get_role_name() or ""
        name = node.get_name() or ""
        desc = node.get_description() or ""
        display_name = name or desc

        try:
            state_set = node.get_state_set()
            enabled = state_set.contains(Atspi.StateType.SENSITIVE) or state_set.contains(Atspi.StateType.ENABLED)
        except Exception:
            enabled = True

        value = ""
        try:
            val_iface = node.get_value()
            if val_iface:
                value = str(val_iface.get_current_value())
        except Exception:
            pass

        if role in interactive_roles and enabled:
            ref += 1
            elements.append({{
                "ref": ref,
                "role": role,
                "name": display_name,
                "value": value,
                "depth": depth,
            }})
        elif role in context_roles and display_name:
            elements.append({{
                "ref": 0,
                "role": role,
                "name": display_name,
                "value": "",
                "depth": depth,
            }})

        for k in range(node.get_child_count()):
            child = node.get_child_at_index(k)
            walk(child, depth + 1)
    except Exception:
        pass

walk(target_win, 0)

win_name = target_win.get_name() or "Unknown"
app_name = target_app.get_name() if target_app else ""

print(json.dumps({{
    "success": True,
    "window": win_name,
    "app": app_name,
    "elements": elements,
    "element_count": ref,
}}))
'''
        try:
            proc = await asyncio.create_subprocess_exec(
                "python3", "-c", atspi_script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            raw = stdout.decode("utf-8", errors="replace").strip()

            if not raw:
                err = stderr.decode("utf-8", errors="replace").strip()
                return {"success": False, "error": f"AT-SPI2 failed: {err}"}

            data = json.loads(raw)
            if not data.get("success"):
                return data

            # Build ref map and snapshot text
            self._ref_map = {}
            self._ref_counter = 0
            lines = [f"Window: {data['window']}", ""]

            for elem in data.get("elements", []):
                indent = "  " * min(elem["depth"], 4)
                if elem["ref"] > 0:
                    self._ref_counter += 1
                    ref = self._ref_counter
                    self._ref_map[ref] = {
                        "role": elem["role"],
                        "name": elem["name"],
                        "value": elem["value"],
                        "backend": "linux_atspi",
                    }
                    display = f"{indent}[{ref}] {elem['role']}"
                    if elem["name"]:
                        display += f' "{elem["name"]}"'
                    if elem["value"] and elem["value"] != elem["name"]:
                        display += f' value="{elem["value"][:100]}"'
                    lines.append(display)
                else:
                    if elem["name"]:
                        truncated = elem["name"][:200]
                        lines.append(f"{indent}{elem['role']}: {truncated}")

            return {
                "success": True,
                "window": data["window"],
                "snapshot": "\n".join(lines),
                "element_count": self._ref_counter,
                "platform": "linux_atspi",
                "hint": "Use ref numbers to interact: desktop_click_ref(1), desktop_type_ref(2, 'text'), etc.",
            }

        except TimeoutError:
            return {"success": False, "error": "AT-SPI2 snapshot timed out"}
        except Exception as e:
            logger.error(f"Linux AT-SPI2 snapshot failed: {e}")
            return {"success": False, "error": str(e)}

    async def _snapshot_linux_xdotool(self, window_title: str | None) -> dict[str, Any]:
        """Minimal snapshot using xdotool (no full accessibility tree)."""
        try:
            if window_title:
                proc = await asyncio.create_subprocess_exec(
                    "xdotool", "search", "--name", window_title,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                proc = await asyncio.create_subprocess_exec(
                    "xdotool", "getactivewindow",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            wid = stdout.decode().strip().split("\n")[0]

            if not wid:
                return {"success": False, "error": "No window found"}

            # Get window name
            proc = await asyncio.create_subprocess_exec(
                "xdotool", "getwindowname", wid,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            win_name = stdout.decode().strip()

            self._ref_map = {}
            self._ref_counter = 0

            return {
                "success": True,
                "window": win_name,
                "window_id": wid,
                "snapshot": (
                    f"Window: {win_name} (id: {wid})\n\n"
                    "Note: Full accessibility tree requires AT-SPI2.\n"
                    "Install: sudo apt install python3-gi gir1.2-atspi-2.0 at-spi2-core\n"
                    "For now, use coordinate-based interaction via desktop_click(x, y)."
                ),
                "element_count": 0,
                "platform": "linux_xdotool",
                "hint": "Install AT-SPI2 for full element tree, or use screenshot + coordinate clicks.",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Click ref ──────────────────────────────────────────────────

    async def click_ref(self, ref: int, double_click: bool = False) -> dict[str, Any]:
        """Click an element by its ref number from the snapshot."""
        self._ensure_init()

        if ref not in self._ref_map:
            return {
                "success": False,
                "error": f"Ref [{ref}] not found. Take a new desktop_snapshot() to get current refs.",
            }

        elem_info = self._ref_map[ref]
        backend = elem_info.get("backend", "pywinauto")

        if backend == "macos":
            return await self._click_ref_macos(ref, elem_info, double_click)
        elif backend == "linux_atspi":
            return await self._click_ref_linux(ref, elem_info, double_click)
        else:
            return await self._click_ref_windows(ref, elem_info, double_click)

    async def _click_ref_windows(self, ref: int, elem_info: dict, double_click: bool) -> dict[str, Any]:
        """Click element on Windows using UIA."""
        element = elem_info["element"]
        backend = elem_info.get("backend", "pywinauto")

        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self._click_element_sync, element, backend, double_click
            )
            return {
                "success": True,
                "action": "double_click" if double_click else "click",
                "ref": ref,
                "element": f'{elem_info["control_type"]} "{elem_info["name"]}"',
                "hint": "Take a desktop_snapshot() to see the updated state.",
            }
        except Exception as e:
            # Fallback: click at element center using coordinates
            try:
                coords = await self._get_element_center(element, backend)
                if coords and self._pyautogui_available:
                    import pyautogui
                    if double_click:
                        pyautogui.doubleClick(coords[0], coords[1])
                    else:
                        pyautogui.click(coords[0], coords[1])
                    return {
                        "success": True,
                        "action": "click (coordinate fallback)",
                        "ref": ref,
                        "element": f'{elem_info["control_type"]} "{elem_info["name"]}"',
                        "coordinates": coords,
                    }
            except Exception:
                pass
            return {"success": False, "error": str(e), "ref": ref}

    async def _click_ref_macos(self, ref: int, elem_info: dict, double_click: bool) -> dict[str, Any]:
        """Click element on macOS using AppleScript AXPress."""
        app_name = elem_info.get("app", "")
        title = elem_info.get("title", "")
        role = elem_info.get("role", "")
        desc = elem_info.get("description", "")
        search_name = title or desc

        if not search_name:
            return {"success": False, "error": "Element has no identifiable name for clicking", "ref": ref}

        # Use AppleScript to find and click the element
        click_action = "click" if not double_click else "click"
        script = f'''
        tell application "System Events"
            tell process "{app_name}"
                set frontmost to true
                delay 0.2
                try
                    set targetElems to entire contents of window 1
                    repeat with elem in targetElems
                        try
                            set elemTitle to ""
                            try
                                set elemTitle to title of elem
                            end try
                            if elemTitle is missing value then set elemTitle to ""
                            set elemDesc to ""
                            try
                                set elemDesc to description of elem
                            end try
                            if elemDesc is missing value then set elemDesc to ""

                            if elemTitle is "{search_name}" or elemDesc is "{search_name}" then
                                {click_action} elem
                                return "clicked"
                            end if
                        end try
                    end repeat
                    return "not_found"
                on error errMsg
                    return "error:" & errMsg
                end try
            end tell
        end tell
        '''
        try:
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
            result = stdout.decode().strip()

            if result == "clicked":
                return {
                    "success": True,
                    "action": "double_click" if double_click else "click",
                    "ref": ref,
                    "element": f'{role} "{search_name}"',
                    "hint": "Take a desktop_snapshot() to see the updated state.",
                }
            elif result == "not_found":
                return {"success": False, "error": f"Element '{search_name}' not found in current window", "ref": ref}
            else:
                return {"success": False, "error": result, "ref": ref}
        except Exception as e:
            return {"success": False, "error": str(e), "ref": ref}

    async def _click_ref_linux(self, ref: int, elem_info: dict, double_click: bool) -> dict[str, Any]:
        """Click element on Linux — falls back to PyAutoGUI coordinate click."""
        # AT-SPI2 doesn't easily support direct clicking; use PyAutoGUI
        if not self._pyautogui_available:
            return {
                "success": False,
                "error": "PyAutoGUI not available for clicking. Install: pip install pyautogui",
                "ref": ref,
            }

        return {
            "success": False,
            "error": (
                "Direct element clicking via AT-SPI2 is not yet supported. "
                "Use screenshot + coordinate-based click instead: desktop click x=100 y=200"
            ),
            "ref": ref,
            "hint": "Take a screenshot first, then click at the element's coordinates.",
        }

    def _click_element_sync(self, element, backend: str, double_click: bool):
        """Synchronous click using UIA patterns (Windows)."""
        if backend == "uiautomation":
            if double_click:
                element.DoubleClick()
            else:
                # Try InvokePattern first (most reliable for buttons)
                try:
                    ip = element.GetInvokePattern()
                    if ip:
                        ip.Invoke()
                        return
                except Exception:
                    pass
                element.Click()
        else:
            # pywinauto
            try:
                # Try invoke pattern first
                iface = element.iface_invoke
                if iface:
                    iface.Invoke()
                    return
            except Exception:
                pass

            if double_click:
                element.double_click_input()
            else:
                element.click_input()

    # ─── Type ref ───────────────────────────────────────────────────

    async def type_ref(self, ref: int, text: str, clear_first: bool = True, press_enter: bool = False) -> dict[str, Any]:
        """Type text into an element by its ref number."""
        self._ensure_init()

        if ref not in self._ref_map:
            return {
                "success": False,
                "error": f"Ref [{ref}] not found. Take a new desktop_snapshot() to get current refs.",
            }

        elem_info = self._ref_map[ref]
        backend = elem_info.get("backend", "pywinauto")

        if backend == "macos":
            return await self._type_ref_macos(ref, elem_info, text, clear_first, press_enter)
        elif backend in ("pywinauto", "uiautomation"):
            return await self._type_ref_windows(ref, elem_info, text, clear_first, press_enter)
        else:
            return {"success": False, "error": "Type not supported on this backend yet", "ref": ref}

    async def _type_ref_windows(self, ref: int, elem_info: dict, text: str, clear_first: bool, press_enter: bool) -> dict[str, Any]:
        """Type text on Windows."""
        element = elem_info["element"]
        backend = elem_info.get("backend", "pywinauto")

        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self._type_element_sync, element, backend, text, clear_first, press_enter
            )
            return {
                "success": True,
                "action": "type",
                "ref": ref,
                "element": f'{elem_info["control_type"]} "{elem_info["name"]}"',
                "text": text,
                "pressed_enter": press_enter,
            }
        except Exception as e:
            # Fallback: click element then type with pyautogui
            try:
                coords = await self._get_element_center(element, backend)
                if coords and self._pyautogui_available:
                    import pyautogui
                    pyautogui.click(coords[0], coords[1])
                    await asyncio.sleep(0.1)
                    if clear_first:
                        pyautogui.hotkey("ctrl", "a")
                        await asyncio.sleep(0.05)
                    pyautogui.typewrite(text, interval=0.02) if text.isascii() else pyautogui.write(text)
                    if press_enter:
                        pyautogui.press("enter")
                    return {
                        "success": True,
                        "action": "type (keyboard fallback)",
                        "ref": ref,
                        "text": text,
                    }
            except Exception:
                pass
            return {"success": False, "error": str(e), "ref": ref}

    async def _type_ref_macos(self, ref: int, elem_info: dict, text: str, clear_first: bool, press_enter: bool) -> dict[str, Any]:
        """Type text on macOS using AppleScript."""
        app_name = elem_info.get("app", "")
        title = elem_info.get("title", "")
        desc = elem_info.get("description", "")
        search_name = title or desc

        # Escape text for AppleScript
        escaped_text = text.replace("\\", "\\\\").replace('"', '\\"')

        clear_cmd = 'keystroke "a" using command down' if clear_first else ""
        enter_cmd = "keystroke return" if press_enter else ""

        script = f'''
        tell application "System Events"
            tell process "{app_name}"
                set frontmost to true
                delay 0.2
                try
                    set targetElems to entire contents of window 1
                    repeat with elem in targetElems
                        try
                            set elemTitle to ""
                            try
                                set elemTitle to title of elem
                            end try
                            if elemTitle is missing value then set elemTitle to ""
                            set elemDesc to ""
                            try
                                set elemDesc to description of elem
                            end try
                            if elemDesc is missing value then set elemDesc to ""

                            if elemTitle is "{search_name}" or elemDesc is "{search_name}" then
                                click elem
                                delay 0.1
                                {clear_cmd}
                                delay 0.05
                                keystroke "{escaped_text}"
                                {enter_cmd}
                                return "typed"
                            end if
                        end try
                    end repeat
                    return "not_found"
                on error errMsg
                    return "error:" & errMsg
                end try
            end tell
        end tell
        '''
        try:
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
            result = stdout.decode().strip()

            if result == "typed":
                return {
                    "success": True,
                    "action": "type",
                    "ref": ref,
                    "text": text,
                    "pressed_enter": press_enter,
                }
            elif result == "not_found":
                return {"success": False, "error": f"Element '{search_name}' not found", "ref": ref}
            else:
                return {"success": False, "error": result, "ref": ref}
        except Exception as e:
            return {"success": False, "error": str(e), "ref": ref}

    def _type_element_sync(self, element, backend: str, text: str, clear_first: bool, press_enter: bool):
        """Synchronous type using UIA ValuePattern or keyboard input (Windows)."""
        if backend == "uiautomation":
            # Try ValuePattern first
            try:
                vp = element.GetValuePattern()
                if vp:
                    if clear_first:
                        vp.SetValue("")
                    vp.SetValue(text)
                    if press_enter:
                        import uiautomation as auto
                        auto.SendKeys("{Enter}")
                    return
            except Exception:
                pass
            # Fallback to click + type
            element.Click()
            time.sleep(0.1)
            if clear_first:
                import uiautomation as auto
                auto.SendKeys("{Ctrl}a")
                time.sleep(0.05)
            import uiautomation as auto
            auto.SendKeys(text, interval=0.02)
            if press_enter:
                auto.SendKeys("{Enter}")
        else:
            # pywinauto
            try:
                # Try ValuePattern
                iface = element.iface_value
                if iface:
                    if clear_first:
                        iface.SetValue("")
                    iface.SetValue(text)
                    if press_enter:
                        element.type_keys("{ENTER}")
                    return
            except Exception:
                pass
            # Fallback to keyboard input
            element.click_input()
            time.sleep(0.1)
            if clear_first:
                element.type_keys("^a", set_foreground=False)
                time.sleep(0.05)
            element.type_keys(text, with_spaces=True, set_foreground=False)
            if press_enter:
                element.type_keys("{ENTER}", set_foreground=False)

    # ─── Select / Toggle (Windows only for now) ────────────────────

    async def select_ref(self, ref: int, value: str) -> dict[str, Any]:
        """Select an option in a combo box or list by ref number."""
        self._ensure_init()

        if ref not in self._ref_map:
            return {"success": False, "error": f"Ref [{ref}] not found."}

        elem_info = self._ref_map[ref]
        backend = elem_info.get("backend", "pywinauto")

        if backend in ("macos", "linux_atspi"):
            return {"success": False, "error": f"Select not yet supported on {backend}", "ref": ref}

        element = elem_info["element"]

        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self._select_element_sync, element, backend, value
            )
            return {
                "success": True,
                "action": "select",
                "ref": ref,
                "element": f'{elem_info["control_type"]} "{elem_info["name"]}"',
                "value": value,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "ref": ref}

    def _select_element_sync(self, element, backend: str, value: str):
        """Synchronous select using UIA SelectionPattern."""
        if backend == "uiautomation":
            try:
                element.GetSelectionPattern()
                try:
                    ep = element.GetExpandCollapsePattern()
                    if ep:
                        ep.Expand()
                        time.sleep(0.2)
                except Exception:
                    pass
                items = element.GetChildren()
                for item in items:
                    if item.Name and value.lower() in item.Name.lower():
                        try:
                            sip = item.GetSelectionItemPattern()
                            if sip:
                                sip.Select()
                                return
                        except Exception:
                            item.Click()
                            return
            except Exception:
                pass
            raise RuntimeError(f"Could not select '{value}'")
        else:
            # pywinauto
            try:
                element.select(value)
            except Exception:
                try:
                    element.expand()
                    time.sleep(0.2)
                    child = element.child_window(title_re=f".*{value}.*")
                    child.click_input()
                except Exception:
                    raise RuntimeError(f"Could not select '{value}'")

    async def toggle_ref(self, ref: int) -> dict[str, Any]:
        """Toggle a checkbox or radio button by ref number."""
        self._ensure_init()

        if ref not in self._ref_map:
            return {"success": False, "error": f"Ref [{ref}] not found."}

        elem_info = self._ref_map[ref]
        backend = elem_info.get("backend", "pywinauto")

        if backend == "macos":
            # On macOS, toggle is just a click
            return await self.click_ref(ref)
        elif backend in ("linux_atspi",):
            return await self.click_ref(ref)

        element = elem_info["element"]

        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self._toggle_element_sync, element, backend
            )
            return {
                "success": True,
                "action": "toggle",
                "ref": ref,
                "element": f'{elem_info["control_type"]} "{elem_info["name"]}"',
            }
        except Exception as e:
            return {"success": False, "error": str(e), "ref": ref}

    def _toggle_element_sync(self, element, backend: str):
        """Synchronous toggle using UIA TogglePattern."""
        if backend == "uiautomation":
            try:
                tp = element.GetTogglePattern()
                if tp:
                    tp.Toggle()
                    return
            except Exception:
                pass
            element.Click()
        else:
            # pywinauto
            try:
                iface = element.iface_toggle
                if iface:
                    iface.Toggle()
                    return
            except Exception:
                pass
            element.click_input()

    # ─── Window info ────────────────────────────────────────────────

    async def get_focused_window(self) -> dict[str, Any]:
        """Get info about the currently focused window."""
        self._ensure_init()

        if SYSTEM == "Windows":
            return await self._get_focused_window_windows()
        elif SYSTEM == "Darwin":
            return await self._get_focused_window_macos()
        else:
            return await self._get_focused_window_linux()

    async def _get_focused_window_windows(self) -> dict[str, Any]:
        if not self._uia_available:
            return {"success": False, "error": "UIA not available"}
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, self._get_focused_window_sync
            )
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_focused_window_sync(self) -> dict[str, Any]:
        """Get focused window info synchronously (Windows)."""
        if self._pywinauto_available:
            import ctypes

            from pywinauto import Desktop as PywinautoDesktop
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return {"success": False, "error": "No foreground window"}

            desktop = PywinautoDesktop(backend="uia")
            windows = desktop.windows(handle=hwnd)
            if windows:
                w = windows[0].wrapper_object()
                return {
                    "success": True,
                    "title": w.window_text(),
                    "class_name": w.friendly_class_name(),
                    "handle": hwnd,
                    "rect": {
                        "left": w.rectangle().left,
                        "top": w.rectangle().top,
                        "right": w.rectangle().right,
                        "bottom": w.rectangle().bottom,
                    },
                }
        return {"success": False, "error": "Could not get focused window"}

    async def _get_focused_window_macos(self) -> dict[str, Any]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e",
                'tell application "System Events" to get name of first process whose frontmost is true',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            app = stdout.decode().strip()

            # Get window title
            proc2 = await asyncio.create_subprocess_exec(
                "osascript", "-e",
                f'tell application "System Events" to get name of window 1 of process "{app}"',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout2, _ = await asyncio.wait_for(proc2.communicate(), timeout=5)
            title = stdout2.decode().strip()

            return {"success": True, "app": app, "title": title or app}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _get_focused_window_linux(self) -> dict[str, Any]:
        if self._linux_xdotool_available:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "xdotool", "getactivewindow", "getwindowname",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
                title = stdout.decode().strip()
                return {"success": True, "title": title}
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": False, "error": "xdotool not available"}

    async def list_windows(self) -> dict[str, Any]:
        """List all visible windows."""
        self._ensure_init()

        if SYSTEM == "Windows":
            return await self._list_windows_windows()
        elif SYSTEM == "Darwin":
            return await self._list_windows_macos()
        else:
            return await self._list_windows_linux()

    async def _list_windows_windows(self) -> dict[str, Any]:
        if not self._uia_available:
            return {"success": False, "error": "UIA not available"}
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, self._list_windows_sync
            )
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _list_windows_sync(self) -> dict[str, Any]:
        """List windows synchronously (Windows)."""
        if self._pywinauto_available:
            from pywinauto import Desktop as PywinautoDesktop
            desktop = PywinautoDesktop(backend="uia")
            windows = desktop.windows(visible_only=True)
            window_list = []
            for w in windows:
                try:
                    wrapper = w.wrapper_object()
                    title = wrapper.window_text()
                    if title and title.strip():
                        window_list.append({
                            "title": title,
                            "class_name": wrapper.friendly_class_name(),
                        })
                except Exception:
                    continue
            return {"success": True, "windows": window_list, "count": len(window_list)}
        return {"success": False, "error": "pywinauto not available"}

    async def _list_windows_macos(self) -> dict[str, Any]:
        try:
            script = '''
            tell application "System Events"
                set output to ""
                set procs to every process whose visible is true
                repeat with p in procs
                    set pName to name of p
                    try
                        set wins to windows of p
                        repeat with w in wins
                            set wTitle to name of w
                            set output to output & pName & "|" & wTitle & linefeed
                        end repeat
                    end try
                end repeat
                return output
            end tell
            '''
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            raw = stdout.decode().strip()

            window_list = []
            for line in raw.split("\n"):
                if "|" in line:
                    parts = line.split("|", 1)
                    window_list.append({
                        "app": parts[0].strip(),
                        "title": parts[1].strip() if len(parts) > 1 else "",
                    })

            return {"success": True, "windows": window_list, "count": len(window_list)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _list_windows_linux(self) -> dict[str, Any]:
        if self._linux_xdotool_available:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "xdotool", "search", "--onlyvisible", "--name", "",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
                wids = stdout.decode().strip().split("\n")

                window_list = []
                for wid in wids[:50]:  # Limit to 50
                    wid = wid.strip()
                    if not wid:
                        continue
                    proc2 = await asyncio.create_subprocess_exec(
                        "xdotool", "getwindowname", wid,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout2, _ = await asyncio.wait_for(proc2.communicate(), timeout=3)
                    name = stdout2.decode().strip()
                    if name:
                        window_list.append({"id": wid, "title": name})

                return {"success": True, "windows": window_list, "count": len(window_list)}
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": False, "error": "No window listing tool available"}

    async def focus_window(self, title: str) -> dict[str, Any]:
        """Bring a window to the foreground by title."""
        self._ensure_init()

        if SYSTEM == "Windows":
            return await self._focus_window_windows(title)
        elif SYSTEM == "Darwin":
            return await self._focus_window_macos(title)
        else:
            return await self._focus_window_linux(title)

    async def _focus_window_windows(self, title: str) -> dict[str, Any]:
        if not self._pywinauto_available:
            return {"success": False, "error": "pywinauto not available"}
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, self._focus_window_sync, title
            )
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _focus_window_sync(self, title: str) -> dict[str, Any]:
        """Focus window synchronously (Windows)."""
        from pywinauto import Desktop as PywinautoDesktop
        desktop = PywinautoDesktop(backend="uia")
        windows = desktop.windows(title_re=f".*{title}.*", visible_only=True)
        if not windows:
            return {"success": False, "error": f"No window matching: {title}"}
        w = windows[0].wrapper_object()
        w.set_focus()
        return {
            "success": True,
            "window": w.window_text(),
            "hint": "Window focused. Use desktop_snapshot() to see its contents.",
        }

    async def _focus_window_macos(self, title: str) -> dict[str, Any]:
        try:
            # Find the app that owns this window
            script = f'''
            tell application "System Events"
                repeat with p in (every process whose visible is true)
                    try
                        repeat with w in windows of p
                            if name of w contains "{title}" then
                                set frontmost of p to true
                                return name of p
                            end if
                        end repeat
                    end try
                end repeat
                return ""
            end tell
            '''
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            app = stdout.decode().strip()
            if app:
                return {"success": True, "window": title, "app": app}
            return {"success": False, "error": f"No window matching: {title}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _focus_window_linux(self, title: str) -> dict[str, Any]:
        if self._linux_xdotool_available:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "xdotool", "search", "--name", title,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
                wid = stdout.decode().strip().split("\n")[0]
                if wid:
                    proc2 = await asyncio.create_subprocess_exec(
                        "xdotool", "windowactivate", wid,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await asyncio.wait_for(proc2.communicate(), timeout=5)
                    return {"success": True, "window": title, "window_id": wid}
                return {"success": False, "error": f"No window matching: {title}"}
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": False, "error": "xdotool not available"}

    # ─── Utility methods ────────────────────────────────────────────

    async def _get_element_center(self, element, backend: str) -> tuple[int, int] | None:
        """Get the center coordinates of an element (Windows UIA)."""
        try:
            def _get_center():
                if backend == "uiautomation":
                    rect = element.BoundingRectangle
                    return (
                        (rect.left + rect.right) // 2,
                        (rect.top + rect.bottom) // 2,
                    )
                else:
                    rect = element.rectangle()
                    return (
                        (rect.left + rect.right) // 2,
                        (rect.top + rect.bottom) // 2,
                    )
            return await asyncio.get_event_loop().run_in_executor(None, _get_center)
        except Exception:
            return None

    async def scroll_window(self, direction: str = "down", amount: int = 3) -> dict[str, Any]:
        """Scroll the focused window using mouse wheel."""
        self._ensure_init()

        if not self._pyautogui_available:
            return {"success": False, "error": "PyAutoGUI not available for scrolling"}

        try:
            import pyautogui
            scroll_amount = amount if direction == "up" else -amount
            pyautogui.scroll(scroll_amount)
            return {
                "success": True,
                "action": "scroll",
                "direction": direction,
                "amount": amount,
                "hint": "Take a desktop_snapshot() to see the updated state.",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def press_key(self, key: str) -> dict[str, Any]:
        """Press a keyboard key or hotkey (cross-platform)."""
        self._ensure_init()

        try:
            if SYSTEM == "Windows" and self._pywinauto_available:
                from pywinauto.keyboard import send_keys
                # Convert common key names to pywinauto format
                key_map = {
                    "enter": "{ENTER}", "tab": "{TAB}", "escape": "{ESC}",
                    "backspace": "{BACKSPACE}", "delete": "{DELETE}",
                    "up": "{UP}", "down": "{DOWN}", "left": "{LEFT}", "right": "{RIGHT}",
                    "home": "{HOME}", "end": "{END}", "pageup": "{PGUP}", "pagedown": "{PGDN}",
                    "f1": "{F1}", "f2": "{F2}", "f3": "{F3}", "f4": "{F4}", "f5": "{F5}",
                    "space": " ",
                }
                if "+" in key:
                    parts = key.lower().split("+")
                    combo = ""
                    for p in parts[:-1]:
                        if p in ("ctrl", "control"):
                            combo += "^"
                        elif p in ("alt",):
                            combo += "%"
                        elif p in ("shift",):
                            combo += "+"
                        elif p in ("win", "windows"):
                            combo += "#"
                    last = parts[-1]
                    combo += key_map.get(last, last)
                    await asyncio.get_event_loop().run_in_executor(None, send_keys, combo)
                else:
                    pw_key = key_map.get(key.lower(), key)
                    await asyncio.get_event_loop().run_in_executor(None, send_keys, pw_key)
                return {"success": True, "action": "key_press", "key": key}

            elif SYSTEM == "Darwin" and self._macos_available:
                # Use AppleScript for key presses on macOS
                key_lower = key.lower()
                if "+" in key_lower:
                    parts = key_lower.split("+")
                    modifiers = []
                    for p in parts[:-1]:
                        if p in ("ctrl", "control"):
                            modifiers.append("control down")
                        elif p == "alt":
                            modifiers.append("option down")
                        elif p == "shift":
                            modifiers.append("shift down")
                        elif p in ("cmd", "command", "super"):
                            modifiers.append("command down")
                    actual_key = parts[-1]
                    mod_str = ", ".join(modifiers)
                    script = f'tell application "System Events" to keystroke "{actual_key}" using {{{mod_str}}}'
                else:
                    special_keys = {
                        "enter": "return", "tab": "tab", "escape": "escape",
                        "backspace": "delete", "delete": "forward delete",
                        "up": "up arrow", "down": "down arrow",
                        "left": "left arrow", "right": "right arrow",
                        "space": "space",
                    }
                    if key_lower in special_keys:
                        script = f'tell application "System Events" to key code {_macos_keycode(key_lower)}'
                    else:
                        script = f'tell application "System Events" to keystroke "{key_lower}"'

                proc = await asyncio.create_subprocess_exec(
                    "osascript", "-e", script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.communicate(), timeout=5)
                return {"success": True, "action": "key_press", "key": key}

            elif self._pyautogui_available:
                import pyautogui
                if "+" in key:
                    parts = key.lower().split("+")
                    # On macOS, map ctrl to command for common shortcuts
                    if SYSTEM == "Darwin":
                        parts = ["command" if p == "ctrl" else p for p in parts]
                    pyautogui.hotkey(*parts)
                else:
                    pyautogui.press(key.lower())
                return {"success": True, "action": "key_press", "key": key}

            return {"success": False, "error": "No keyboard input method available"}
        except Exception as e:
            return {"success": False, "error": str(e)}


def _macos_keycode(key: str) -> int:
    """Map common key names to macOS virtual key codes."""
    codes = {
        "return": 36, "enter": 36, "tab": 48, "space": 49,
        "backspace": 51, "delete": 51, "escape": 53,
        "up": 126, "down": 125, "left": 123, "right": 124,
        "home": 115, "end": 119, "pageup": 116, "pagedown": 121,
        "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96,
    }
    return codes.get(key.lower(), 36)
