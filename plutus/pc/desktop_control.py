"""
Desktop Control — Windows UI Automation (UIA) accessibility tree for native apps.

Same pattern as BrowserControl:
  1. desktop_snapshot() → numbered accessibility tree of the focused window
  2. LLM reads the tree, picks a ref number
  3. desktop_click_ref(3) / desktop_type_ref(2, "hello") → precise interaction

Uses pywinauto with UIA backend to access the Windows Accessibility Tree.
Falls back to PyAutoGUI for mouse/keyboard when UIA patterns aren't available.
"""

from __future__ import annotations

import asyncio
import logging
import platform
from typing import Any, Optional

logger = logging.getLogger("plutus.pc.desktop")

# Interactive control types we include in the snapshot
INTERACTIVE_TYPES = {
    "Button", "CheckBox", "ComboBox", "Edit", "Hyperlink",
    "ListItem", "MenuItem", "MenuBar", "Menu", "RadioButton",
    "Slider", "Spinner", "Tab", "TabItem", "TreeItem",
    "DataItem", "Document", "SplitButton", "ToolBar",
}

# Control types we always show (even if not "interactive") for context
CONTEXT_TYPES = {
    "Text", "StatusBar", "Header", "HeaderItem", "Group",
    "TitleBar", "Window", "Pane",
}


class DesktopControl:
    """
    Windows UI Automation controller — provides accessibility tree snapshots
    and ref-based interaction for native Windows applications.
    """

    def __init__(self):
        self._ref_map: dict[int, dict[str, Any]] = {}
        self._ref_counter: int = 0
        self._uia_available: bool = False
        self._pywinauto_available: bool = False
        self._pyautogui_available: bool = False
        self._initialized: bool = False

    def _ensure_init(self):
        """Lazy-initialize UIA libraries."""
        if self._initialized:
            return

        self._initialized = True

        # Only works on Windows
        if platform.system() != "Windows":
            logger.info("Desktop UIA control only available on Windows")
            return

        # Try pywinauto first (preferred)
        try:
            import pywinauto
            from pywinauto import Desktop as PywinautoDesktop
            self._pywinauto_available = True
            self._uia_available = True
            logger.info("pywinauto UIA backend available")
        except ImportError:
            logger.warning("pywinauto not installed — run: pip install pywinauto")

        # Try uiautomation as fallback
        if not self._uia_available:
            try:
                import uiautomation
                self._uia_available = True
                logger.info("uiautomation library available")
            except ImportError:
                logger.warning("uiautomation not installed — run: pip install uiautomation")

        # PyAutoGUI as last resort for mouse/keyboard
        try:
            import pyautogui
            self._pyautogui_available = True
        except ImportError:
            pass

    async def snapshot(self, window_title: Optional[str] = None, max_depth: int = 8) -> dict[str, Any]:
        """
        Take an accessibility tree snapshot of the focused (or specified) window.
        Returns a numbered list of interactive elements, just like BrowserControl.snapshot().
        """
        self._ensure_init()

        if not self._uia_available:
            return {
                "success": False,
                "error": "Windows UI Automation not available. Install pywinauto: pip install pywinauto",
                "hint": "This feature only works on Windows with pywinauto installed.",
            }

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, self._snapshot_sync, window_title, max_depth
            )
            return result
        except Exception as e:
            logger.error(f"Desktop snapshot failed: {e}")
            return {"success": False, "error": str(e)}

    def _snapshot_sync(self, window_title: Optional[str], max_depth: int) -> dict[str, Any]:
        """Synchronous snapshot implementation using pywinauto."""
        if self._pywinauto_available:
            return self._snapshot_pywinauto(window_title, max_depth)
        else:
            return self._snapshot_uiautomation(window_title, max_depth)

    def _snapshot_pywinauto(self, window_title: Optional[str], max_depth: int) -> dict[str, Any]:
        """Snapshot using pywinauto UIA backend."""
        from pywinauto import Desktop as PywinautoDesktop
        from pywinauto.application import Application

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

    def _snapshot_uiautomation(self, window_title: Optional[str], max_depth: int) -> dict[str, Any]:
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

    async def click_ref(self, ref: int, double_click: bool = False) -> dict[str, Any]:
        """Click an element by its ref number from the snapshot."""
        self._ensure_init()

        if ref not in self._ref_map:
            return {
                "success": False,
                "error": f"Ref [{ref}] not found. Take a new desktop_snapshot() to get current refs.",
            }

        elem_info = self._ref_map[ref]
        element = elem_info["element"]
        backend = elem_info.get("backend", "pywinauto")

        try:
            result = await asyncio.get_event_loop().run_in_executor(
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

    def _click_element_sync(self, element, backend: str, double_click: bool):
        """Synchronous click using UIA patterns."""
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

    async def type_ref(self, ref: int, text: str, clear_first: bool = True, press_enter: bool = False) -> dict[str, Any]:
        """Type text into an element by its ref number."""
        self._ensure_init()

        if ref not in self._ref_map:
            return {
                "success": False,
                "error": f"Ref [{ref}] not found. Take a new desktop_snapshot() to get current refs.",
            }

        elem_info = self._ref_map[ref]
        element = elem_info["element"]
        backend = elem_info.get("backend", "pywinauto")

        try:
            result = await asyncio.get_event_loop().run_in_executor(
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

    def _type_element_sync(self, element, backend: str, text: str, clear_first: bool, press_enter: bool):
        """Synchronous type using UIA ValuePattern or keyboard input."""
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
            import time
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
            import time
            time.sleep(0.1)
            if clear_first:
                element.type_keys("^a", set_foreground=False)
                time.sleep(0.05)
            element.type_keys(text, with_spaces=True, set_foreground=False)
            if press_enter:
                element.type_keys("{ENTER}", set_foreground=False)

    async def select_ref(self, ref: int, value: str) -> dict[str, Any]:
        """Select an option in a combo box or list by ref number."""
        self._ensure_init()

        if ref not in self._ref_map:
            return {"success": False, "error": f"Ref [{ref}] not found."}

        elem_info = self._ref_map[ref]
        element = elem_info["element"]
        backend = elem_info.get("backend", "pywinauto")

        try:
            result = await asyncio.get_event_loop().run_in_executor(
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
            # Try to find and select the item
            try:
                sp = element.GetSelectionPattern()
                # Expand combo box first
                try:
                    ep = element.GetExpandCollapsePattern()
                    if ep:
                        ep.Expand()
                        import time
                        time.sleep(0.2)
                except Exception:
                    pass
                # Find the item by name
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
                # Try expanding and clicking
                try:
                    element.expand()
                    import time
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
        element = elem_info["element"]
        backend = elem_info.get("backend", "pywinauto")

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

    async def get_focused_window(self) -> dict[str, Any]:
        """Get info about the currently focused window."""
        self._ensure_init()

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
        """Get focused window info synchronously."""
        if self._pywinauto_available:
            from pywinauto import Desktop as PywinautoDesktop
            import ctypes
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

    async def list_windows(self) -> dict[str, Any]:
        """List all visible windows."""
        self._ensure_init()

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
        """List windows synchronously."""
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

    async def focus_window(self, title: str) -> dict[str, Any]:
        """Bring a window to the foreground by title."""
        self._ensure_init()

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
        """Focus window synchronously."""
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

    async def _get_element_center(self, element, backend: str) -> Optional[tuple[int, int]]:
        """Get the center coordinates of an element."""
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
        """Press a keyboard key or hotkey."""
        self._ensure_init()

        try:
            if self._pywinauto_available:
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
                # Handle hotkeys like "ctrl+c"
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

            elif self._pyautogui_available:
                import pyautogui
                if "+" in key:
                    parts = key.lower().split("+")
                    pyautogui.hotkey(*parts)
                else:
                    pyautogui.press(key.lower())
                return {"success": True, "action": "key_press", "key": key}

            return {"success": False, "error": "No keyboard input method available"}
        except Exception as e:
            return {"success": False, "error": str(e)}
