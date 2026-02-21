"""Intelligent keyboard controller — natural typing with smart combos.

Supports natural-speed typing with random delays between keystrokes,
Unicode text entry, smart key combinations, and cross-platform hotkeys.
Feels like a real person typing, not a machine pasting text.
"""

from __future__ import annotations

import asyncio
import platform
import random
import time
from dataclasses import dataclass
from typing import Any

SYSTEM = platform.system()


@dataclass
class TypingProfile:
    """How fast and natural the typing feels."""
    wpm: int = 80                    # words per minute
    variance: float = 0.3            # timing variance (0=robotic, 0.5=very human)
    typo_rate: float = 0.0           # probability of typo+backspace (0=perfect)
    pause_between_words: float = 0.05  # extra pause at spaces
    pause_at_punctuation: float = 0.1  # extra pause after . , ! ?
    burst_mode: bool = False         # type in bursts (fast then pause)


TYPING_PROFILES = {
    "natural": TypingProfile(wpm=75, variance=0.3, typo_rate=0.0),
    "fast": TypingProfile(wpm=150, variance=0.15, typo_rate=0.0),
    "careful": TypingProfile(wpm=40, variance=0.4, typo_rate=0.0),
    "instant": TypingProfile(wpm=10000, variance=0.0, typo_rate=0.0),
    "human": TypingProfile(wpm=65, variance=0.35, typo_rate=0.02, burst_mode=True),
}

# Common key name aliases for cross-platform compatibility
KEY_ALIASES = {
    # Modifiers
    "ctrl": "ctrl" if SYSTEM != "Darwin" else "command",
    "cmd": "command" if SYSTEM == "Darwin" else "ctrl",
    "super": "win" if SYSTEM == "Windows" else ("command" if SYSTEM == "Darwin" else "super"),
    "meta": "win" if SYSTEM == "Windows" else ("command" if SYSTEM == "Darwin" else "super"),
    "opt": "alt",
    "option": "alt",
    "return": "enter",
    "esc": "escape",
    "del": "delete",
    "bs": "backspace",
    # Navigation
    "pageup": "pageup",
    "pagedown": "pagedown",
    "home": "home",
    "end": "end",
    # Function keys
    **{f"f{i}": f"f{i}" for i in range(1, 13)},
    # Special
    "space": "space",
    "tab": "tab",
    "capslock": "capslock",
    "printscreen": "printscreen",
}

# Common shortcuts mapped to cross-platform key combos
SMART_SHORTCUTS = {
    "copy": "ctrl+c" if SYSTEM != "Darwin" else "command+c",
    "paste": "ctrl+v" if SYSTEM != "Darwin" else "command+v",
    "cut": "ctrl+x" if SYSTEM != "Darwin" else "command+x",
    "undo": "ctrl+z" if SYSTEM != "Darwin" else "command+z",
    "redo": "ctrl+y" if SYSTEM != "Darwin" else "command+shift+z",
    "save": "ctrl+s" if SYSTEM != "Darwin" else "command+s",
    "save_as": "ctrl+shift+s" if SYSTEM != "Darwin" else "command+shift+s",
    "find": "ctrl+f" if SYSTEM != "Darwin" else "command+f",
    "replace": "ctrl+h" if SYSTEM != "Darwin" else "command+option+f",
    "select_all": "ctrl+a" if SYSTEM != "Darwin" else "command+a",
    "new_tab": "ctrl+t" if SYSTEM != "Darwin" else "command+t",
    "close_tab": "ctrl+w" if SYSTEM != "Darwin" else "command+w",
    "reopen_tab": "ctrl+shift+t" if SYSTEM != "Darwin" else "command+shift+t",
    "next_tab": "ctrl+tab",
    "prev_tab": "ctrl+shift+tab",
    "switch_window": "alt+tab" if SYSTEM != "Darwin" else "command+tab",
    "switch_app": "alt+tab" if SYSTEM != "Darwin" else "command+tab",
    "minimize": "super+d" if SYSTEM == "Windows" else ("command+m" if SYSTEM == "Darwin" else "super+d"),
    "maximize": "super+up" if SYSTEM == "Windows" else ("command+ctrl+f" if SYSTEM == "Darwin" else "super+up"),
    "lock_screen": "super+l" if SYSTEM == "Windows" else ("command+ctrl+q" if SYSTEM == "Darwin" else "super+l"),
    "screenshot": "printscreen" if SYSTEM == "Windows" else ("command+shift+3" if SYSTEM == "Darwin" else "printscreen"),
    "screenshot_area": "super+shift+s" if SYSTEM == "Windows" else ("command+shift+4" if SYSTEM == "Darwin" else "shift+printscreen"),
    "task_manager": "ctrl+shift+escape" if SYSTEM == "Windows" else ("command+option+escape" if SYSTEM == "Darwin" else "ctrl+alt+delete"),
    "file_explorer": "super+e" if SYSTEM == "Windows" else ("command+shift+f" if SYSTEM == "Darwin" else "super+e"),
    "terminal": "ctrl+alt+t" if SYSTEM == "Linux" else ("command+space" if SYSTEM == "Darwin" else "super+r"),
    "address_bar": "ctrl+l" if SYSTEM != "Darwin" else "command+l",
    "refresh": "f5" if SYSTEM != "Darwin" else "command+r",
    "hard_refresh": "ctrl+shift+r" if SYSTEM != "Darwin" else "command+shift+r",
    "dev_tools": "f12" if SYSTEM != "Darwin" else "command+option+i",
    "zoom_in": "ctrl+=" if SYSTEM != "Darwin" else "command+=",
    "zoom_out": "ctrl+-" if SYSTEM != "Darwin" else "command+-",
    "zoom_reset": "ctrl+0" if SYSTEM != "Darwin" else "command+0",
    "go_back": "alt+left" if SYSTEM != "Darwin" else "command+[",
    "go_forward": "alt+right" if SYSTEM != "Darwin" else "command+]",
    "new_window": "ctrl+n" if SYSTEM != "Darwin" else "command+n",
    "close_window": "alt+f4" if SYSTEM != "Darwin" else "command+q",
    "spotlight": "super" if SYSTEM == "Windows" else ("command+space" if SYSTEM == "Darwin" else "super"),
}


class KeyboardController:
    """Cross-platform keyboard controller with natural typing.

    Usage:
        kb = KeyboardController()
        await kb.type_text("Hello, world!")       # natural typing
        await kb.hotkey("ctrl+s")                 # save
        await kb.shortcut("copy")                 # smart shortcut
        await kb.press("enter")                   # single key
        await kb.key_down("shift")                # hold key
        await kb.key_up("shift")                  # release key
        await kb.combo("ctrl", "shift", "p")      # key combination
    """

    def __init__(self, profile: str | TypingProfile = "natural"):
        if isinstance(profile, str):
            self.profile = TYPING_PROFILES.get(profile, TYPING_PROFILES["natural"])
        else:
            self.profile = profile
        self._pag = None

    def _get_pag(self):
        if self._pag is None:
            try:
                import pyautogui
                pyautogui.FAILSAFE = True
                pyautogui.PAUSE = 0
                self._pag = pyautogui
            except ImportError:
                raise RuntimeError("pyautogui not installed. Run: pip install pyautogui")
        return self._pag

    def _resolve_key(self, key: str) -> str:
        """Resolve key aliases to platform-specific key names."""
        return KEY_ALIASES.get(key.lower().strip(), key.lower().strip())

    def _char_delay(self, char: str) -> float:
        """Calculate delay for a character based on typing profile."""
        # Base delay from WPM (average word = 5 chars)
        base = 60.0 / (self.profile.wpm * 5)

        # Add variance
        if self.profile.variance > 0:
            base *= random.uniform(
                1 - self.profile.variance, 1 + self.profile.variance
            )

        # Extra pauses
        if char == " ":
            base += self.profile.pause_between_words * random.uniform(0.5, 1.5)
        elif char in ".!?,;:":
            base += self.profile.pause_at_punctuation * random.uniform(0.5, 1.5)
        elif char == "\n":
            base += self.profile.pause_at_punctuation * random.uniform(1.0, 2.0)

        return max(0.005, base)

    async def type_text(
        self,
        text: str,
        speed: str | None = None,
        clear_first: bool = False,
    ) -> dict[str, Any]:
        """Type text naturally, character by character.

        Args:
            text: The text to type
            speed: Override profile ("natural", "fast", "instant", etc.)
            clear_first: Select all and delete before typing
        """
        pag = self._get_pag()

        if clear_first:
            await self.shortcut("select_all")
            await asyncio.sleep(0.05)
            await self.press("delete")
            await asyncio.sleep(0.05)

        # Use override profile if specified
        profile = self.profile
        if speed:
            profile = TYPING_PROFILES.get(speed, self.profile)

        if profile.wpm >= 5000:
            # Instant mode — use pyperclip or direct paste for speed
            try:
                import pyperclip
                pyperclip.copy(text)
                await self.shortcut("paste")
                return {
                    "action": "type_text",
                    "length": len(text),
                    "method": "paste",
                    "speed": "instant",
                }
            except ImportError:
                pass

        # Natural typing — character by character
        start_time = time.time()
        chars_typed = 0

        for char in text:
            # Handle non-ASCII with write() instead of typewrite()
            if ord(char) > 127:
                try:
                    import pyperclip
                    pyperclip.copy(char)
                    pag.hotkey(
                        "command" if SYSTEM == "Darwin" else "ctrl",
                        "v",
                        _pause=False,
                    )
                except ImportError:
                    pag.press("space", _pause=False)  # fallback
            elif char == "\n":
                pag.press("enter", _pause=False)
            elif char == "\t":
                pag.press("tab", _pause=False)
            else:
                pag.press(char, _pause=False)

            chars_typed += 1
            delay = self._char_delay(char)

            # Burst mode: occasional longer pauses
            if profile.burst_mode and random.random() < 0.05:
                delay += random.uniform(0.2, 0.6)

            await asyncio.sleep(delay)

        elapsed = time.time() - start_time
        effective_wpm = (chars_typed / 5) / (elapsed / 60) if elapsed > 0 else 0

        return {
            "action": "type_text",
            "length": chars_typed,
            "duration": round(elapsed, 2),
            "effective_wpm": round(effective_wpm),
            "method": "natural",
        }

    async def press(self, key: str, times: int = 1) -> dict[str, Any]:
        """Press a single key one or more times."""
        pag = self._get_pag()
        resolved = self._resolve_key(key)

        for i in range(times):
            pag.press(resolved, _pause=False)
            if i < times - 1:
                await asyncio.sleep(random.uniform(0.03, 0.08))

        return {"action": "press", "key": resolved, "times": times}

    async def hotkey(self, combo: str) -> dict[str, Any]:
        """Press a key combination like 'ctrl+shift+s' or 'alt+tab'.

        Automatically resolves platform-specific keys.
        """
        pag = self._get_pag()
        keys = [self._resolve_key(k) for k in combo.split("+")]
        pag.hotkey(*keys, _pause=False)
        await asyncio.sleep(0.05)
        return {"action": "hotkey", "combo": "+".join(keys), "original": combo}

    async def shortcut(self, name: str) -> dict[str, Any]:
        """Execute a named shortcut (cross-platform).

        Examples: "copy", "paste", "save", "undo", "new_tab", "switch_window"
        See SMART_SHORTCUTS for full list.
        """
        combo = SMART_SHORTCUTS.get(name.lower())
        if not combo:
            return {"action": "shortcut", "error": f"Unknown shortcut: {name}",
                    "available": sorted(SMART_SHORTCUTS.keys())}
        result = await self.hotkey(combo)
        result["shortcut_name"] = name
        return result

    async def key_down(self, key: str) -> dict[str, Any]:
        """Hold a key down (for drag operations, etc.)."""
        pag = self._get_pag()
        resolved = self._resolve_key(key)
        pag.keyDown(resolved, _pause=False)
        return {"action": "key_down", "key": resolved}

    async def key_up(self, key: str) -> dict[str, Any]:
        """Release a held key."""
        pag = self._get_pag()
        resolved = self._resolve_key(key)
        pag.keyUp(resolved, _pause=False)
        return {"action": "key_up", "key": resolved}

    async def combo(self, *keys: str) -> dict[str, Any]:
        """Press multiple keys simultaneously."""
        pag = self._get_pag()
        resolved = [self._resolve_key(k) for k in keys]
        pag.hotkey(*resolved, _pause=False)
        await asyncio.sleep(0.05)
        return {"action": "combo", "keys": resolved}

    @staticmethod
    def list_shortcuts() -> dict[str, str]:
        """Return all available smart shortcuts."""
        return dict(SMART_SHORTCUTS)

    @staticmethod
    def list_profiles() -> list[str]:
        """Return available typing profiles."""
        return list(TYPING_PROFILES.keys())
