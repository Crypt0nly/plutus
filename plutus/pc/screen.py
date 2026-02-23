"""Screen reader — OCR, element detection, and visual understanding.

Captures the screen, reads text via OCR, finds UI elements by text/color,
detects clickable regions, and provides the AI with a structured understanding
of what's currently visible on screen.
"""

from __future__ import annotations

import asyncio
import base64
import io
import os
import platform
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SYSTEM = platform.system()


@dataclass
class ScreenElement:
    """A detected element on screen."""
    text: str = ""
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    confidence: float = 0.0
    element_type: str = "text"  # text, button, input, link, icon, image

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "center": self.center,
            "confidence": round(self.confidence, 2),
            "type": self.element_type,
        }


@dataclass
class ScreenRegion:
    """A rectangular region of the screen."""
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    def to_tuple(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)


class ScreenReader:
    """Cross-platform screen reader with OCR and element detection.

    Usage:
        screen = ScreenReader()
        await screen.capture()                    # full screenshot
        await screen.capture(region=...)          # region screenshot
        text = await screen.read_text()           # OCR full screen
        elements = await screen.find_text("OK")   # find text on screen
        elements = await screen.find_elements()   # detect all UI elements
        color = await screen.get_pixel_color(x, y)
        await screen.wait_for_text("Loading", timeout=10)
    """

    def __init__(self, screenshots_dir: str | None = None):
        self._screenshots_dir = screenshots_dir or str(
            Path.home() / ".plutus" / "screenshots"
        )
        os.makedirs(self._screenshots_dir, exist_ok=True)
        self._pag = None
        self._last_capture_path: str | None = None
        self._last_capture_time: float = 0

    def _get_pag(self):
        if self._pag is None:
            try:
                import pyautogui
                pyautogui.FAILSAFE = True
                pyautogui.PAUSE = 0
                self._pag = pyautogui
            except ImportError:
                raise RuntimeError("pyautogui not installed")
        return self._pag

    def _capture_fallback(self, path: str) -> Any:
        """Capture screenshot using platform-native tools when PyAutoGUI fails.

        Used on Wayland where PyAutoGUI can't access the display, and as a
        general fallback on macOS/Linux.
        """
        from PIL import Image

        if SYSTEM == "Darwin":
            subprocess.run(
                ["screencapture", "-x", path], timeout=5, check=True,
            )
            return Image.open(path)

        if SYSTEM == "Linux":
            from plutus.pc.platform_utils import get_screenshot_command
            cmd = get_screenshot_command()
            if cmd:
                subprocess.run([*cmd, path], timeout=5, check=True)
                return Image.open(path)

        raise RuntimeError("No screenshot method available for this platform")

    async def capture(
        self,
        region: ScreenRegion | None = None,
        path: str | None = None,
        include_base64: bool = False,
    ) -> dict[str, Any]:
        """Capture a screenshot of the full screen or a region.

        Returns path to saved image and optionally base64-encoded data.
        """
        if path is None:
            timestamp = int(time.time() * 1000)
            path = os.path.join(self._screenshots_dir, f"screen_{timestamp}.png")

        img = None

        # Try PyAutoGUI first (works on X11, Windows, macOS)
        try:
            pag = self._get_pag()
            if region:
                img = pag.screenshot(region=region.to_tuple())
            else:
                img = pag.screenshot()
        except Exception:
            # Fallback: use platform-native tools (Wayland, headless, etc.)
            try:
                img = self._capture_fallback(path)
            except Exception as e:
                return {
                    "error": f"Screenshot failed: {e}",
                    "hint": (
                        "On Wayland, install grim: sudo apt install grim\n"
                        "On macOS, grant screen recording permission.\n"
                        "On X11, install scrot: sudo apt install scrot"
                    ),
                }

        img.save(path)
        self._last_capture_path = path
        self._last_capture_time = time.time()

        result: dict[str, Any] = {
            "path": path,
            "size": {"width": img.size[0], "height": img.size[1]},
            "timestamp": self._last_capture_time,
        }

        if include_base64:
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            result["base64"] = base64.b64encode(buf.getvalue()).decode()

        return result

    async def read_text(
        self,
        region: ScreenRegion | None = None,
        language: str = "eng",
    ) -> dict[str, Any]:
        """Read all text from the screen using OCR.

        Requires tesseract: sudo apt install tesseract-ocr
        Or on Windows: choco install tesseract
        """
        # Capture first
        capture = await self.capture(region=region)
        path = capture["path"]

        try:
            # Try pytesseract first
            import pytesseract
            from PIL import Image

            img = Image.open(path)
            # Get detailed data with bounding boxes
            data = pytesseract.image_to_data(
                img, lang=language, output_type=pytesseract.Output.DICT
            )

            # Build text and elements
            full_text = pytesseract.image_to_string(img, lang=language).strip()
            elements = []

            for i in range(len(data["text"])):
                text = data["text"][i].strip()
                conf = int(data["conf"][i]) if data["conf"][i] != "-1" else 0
                if text and conf > 30:
                    elements.append(ScreenElement(
                        text=text,
                        x=data["left"][i],
                        y=data["top"][i],
                        width=data["width"][i],
                        height=data["height"][i],
                        confidence=conf / 100.0,
                        element_type="text",
                    ))

            return {
                "text": full_text,
                "elements": [e.to_dict() for e in elements],
                "element_count": len(elements),
                "screenshot": path,
                "method": "tesseract",
            }

        except ImportError:
            # Fallback: try tesseract CLI directly
            try:
                result = subprocess.run(
                    ["tesseract", path, "stdout", "-l", language],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    return {
                        "text": result.stdout.strip(),
                        "elements": [],
                        "element_count": 0,
                        "screenshot": path,
                        "method": "tesseract_cli",
                    }
            except FileNotFoundError:
                pass

            return {
                "text": "",
                "error": (
                    "OCR not available. Install: pip install pytesseract && "
                    "sudo apt install tesseract-ocr (Linux) or "
                    "choco install tesseract (Windows)"
                ),
                "screenshot": path,
                "method": "none",
            }

    async def find_text(
        self,
        target: str,
        region: ScreenRegion | None = None,
        case_sensitive: bool = False,
    ) -> dict[str, Any]:
        """Find all occurrences of text on screen and return their positions."""
        ocr_result = await self.read_text(region=region)

        if ocr_result.get("error"):
            return ocr_result

        matches = []
        for elem in ocr_result.get("elements", []):
            elem_text = elem["text"]
            search_text = target

            if not case_sensitive:
                elem_text = elem_text.lower()
                search_text = search_text.lower()

            if search_text in elem_text:
                matches.append(elem)

        # Also try to find multi-word matches by combining adjacent elements
        if not matches and " " in target:
            all_elements = ocr_result.get("elements", [])
            full_text = ocr_result.get("text", "")
            if target.lower() in full_text.lower():
                # Text exists but split across elements
                # Return approximate position from first matching word
                first_word = target.split()[0]
                for elem in all_elements:
                    if first_word.lower() in elem["text"].lower():
                        matches.append({
                            **elem,
                            "text": target,
                            "note": "approximate_position",
                        })
                        break

        return {
            "target": target,
            "found": len(matches) > 0,
            "matches": matches,
            "count": len(matches),
            "screenshot": ocr_result.get("screenshot"),
        }

    async def find_elements(
        self,
        region: ScreenRegion | None = None,
    ) -> dict[str, Any]:
        """Detect all visible UI elements on screen using OCR + heuristics."""
        ocr_result = await self.read_text(region=region)

        if ocr_result.get("error"):
            return ocr_result

        elements = ocr_result.get("elements", [])

        # Classify elements based on text patterns and position
        classified = []
        for elem in elements:
            text = elem.get("text", "")
            el_type = "text"

            # Heuristic classification
            if text in ("OK", "Cancel", "Yes", "No", "Close", "Save", "Open",
                       "Submit", "Apply", "Next", "Back", "Done", "Accept",
                       "Decline", "Continue", "Skip", "Retry", "Delete"):
                el_type = "button"
            elif text.startswith("http") or text.startswith("www."):
                el_type = "link"
            elif re.match(r'^[A-Z][a-z]+$', text) and elem.get("width", 0) < 200:
                el_type = "menu_item"
            elif text in ("X", "×", "✕", "☰", "⋮", "…"):
                el_type = "icon"

            classified.append({**elem, "type": el_type})

        return {
            "elements": classified,
            "count": len(classified),
            "screenshot": ocr_result.get("screenshot"),
        }

    async def get_pixel_color(self, x: int, y: int) -> dict[str, Any]:
        """Get the color of a pixel at (x, y)."""
        pag = self._get_pag()
        try:
            img = pag.screenshot(region=(x, y, 1, 1))
            pixel = img.getpixel((0, 0))
            r, g, b = pixel[0], pixel[1], pixel[2]
            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            return {
                "x": x, "y": y,
                "rgb": {"r": r, "g": g, "b": b},
                "hex": hex_color,
            }
        except Exception as e:
            return {"error": str(e)}

    async def find_color(
        self,
        hex_color: str,
        tolerance: int = 20,
        region: ScreenRegion | None = None,
        max_results: int = 10,
    ) -> dict[str, Any]:
        """Find all pixels matching a color on screen."""
        pag = self._get_pag()

        # Parse target color
        hex_color = hex_color.lstrip("#")
        target_r = int(hex_color[0:2], 16)
        target_g = int(hex_color[2:4], 16)
        target_b = int(hex_color[4:6], 16)

        if region:
            img = pag.screenshot(region=region.to_tuple())
            offset_x, offset_y = region.x, region.y
        else:
            img = pag.screenshot()
            offset_x, offset_y = 0, 0

        # Sample pixels (checking every pixel would be too slow)
        matches = []
        width, height = img.size
        step = max(5, min(width, height) // 100)

        for y in range(0, height, step):
            for x in range(0, width, step):
                r, g, b = img.getpixel((x, y))[:3]
                if (abs(r - target_r) <= tolerance and
                    abs(g - target_g) <= tolerance and
                    abs(b - target_b) <= tolerance):
                    matches.append({
                        "x": x + offset_x,
                        "y": y + offset_y,
                        "rgb": {"r": r, "g": g, "b": b},
                    })
                    if len(matches) >= max_results:
                        break
            if len(matches) >= max_results:
                break

        return {
            "target_color": f"#{hex_color}",
            "tolerance": tolerance,
            "found": len(matches) > 0,
            "matches": matches,
            "count": len(matches),
        }

    async def wait_for_text(
        self,
        target: str,
        timeout: float = 30.0,
        interval: float = 1.0,
        region: ScreenRegion | None = None,
    ) -> dict[str, Any]:
        """Wait for text to appear on screen (polls via OCR).

        Useful for waiting for loading screens, dialogs, etc.
        """
        start = time.time()
        attempts = 0

        while time.time() - start < timeout:
            attempts += 1
            result = await self.find_text(target, region=region)
            if result.get("found"):
                return {
                    "found": True,
                    "target": target,
                    "matches": result["matches"],
                    "elapsed": round(time.time() - start, 2),
                    "attempts": attempts,
                }
            await asyncio.sleep(interval)

        return {
            "found": False,
            "target": target,
            "elapsed": round(time.time() - start, 2),
            "attempts": attempts,
            "error": f"Text '{target}' not found within {timeout}s",
        }

    async def wait_for_change(
        self,
        region: ScreenRegion | None = None,
        timeout: float = 30.0,
        threshold: float = 0.05,
    ) -> dict[str, Any]:
        """Wait for the screen to change (useful after clicking).

        Compares screenshots to detect when content updates.
        """
        pag = self._get_pag()
        start = time.time()

        # Take reference screenshot
        if region:
            ref_img = pag.screenshot(region=region.to_tuple())
        else:
            ref_img = pag.screenshot()

        ref_pixels = list(ref_img.getdata())

        while time.time() - start < timeout:
            await asyncio.sleep(0.3)

            if region:
                new_img = pag.screenshot(region=region.to_tuple())
            else:
                new_img = pag.screenshot()

            new_pixels = list(new_img.getdata())

            # Calculate difference
            if len(ref_pixels) == len(new_pixels):
                diff_count = sum(
                    1 for a, b in zip(ref_pixels, new_pixels) if a != b
                )
                diff_ratio = diff_count / len(ref_pixels)

                if diff_ratio > threshold:
                    return {
                        "changed": True,
                        "diff_ratio": round(diff_ratio, 4),
                        "elapsed": round(time.time() - start, 2),
                    }

        return {
            "changed": False,
            "elapsed": round(time.time() - start, 2),
            "error": f"Screen did not change within {timeout}s",
        }

    async def get_screen_info(self) -> dict[str, Any]:
        """Get screen dimensions and basic info."""
        pag = self._get_pag()
        size = pag.size()
        pos = pag.position()

        return {
            "screen_width": size.width,
            "screen_height": size.height,
            "mouse_x": pos.x,
            "mouse_y": pos.y,
            "platform": SYSTEM,
            "screenshots_dir": self._screenshots_dir,
        }

    @property
    def last_capture(self) -> str | None:
        """Path to the most recent screenshot."""
        return self._last_capture_path
