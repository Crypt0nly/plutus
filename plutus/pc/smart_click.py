"""Smart click — find UI elements by text, image, or color and click them.

This is the highest-level interaction primitive: instead of specifying
exact coordinates, the AI says "click the OK button" and this module
finds it on screen and clicks it. Combines OCR, image matching, and
mouse control into a single seamless operation.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from plutus.pc.mouse import MouseController
from plutus.pc.screen import ScreenReader, ScreenRegion

logger = logging.getLogger("plutus.pc.smart_click")


class SmartClick:
    """Find-and-click: locate UI elements by text or image, then click them.

    Usage:
        sc = SmartClick(mouse, screen)
        await sc.click_text("OK")              # find "OK" on screen and click it
        await sc.click_text("Submit", double=True)  # double-click
        await sc.click_near_text("Username", offset_y=30)  # click below "Username" label
        await sc.click_color("#00ff00")        # click a green element
    """

    def __init__(self, mouse: MouseController, screen: ScreenReader):
        self._mouse = mouse
        self._screen = screen

    async def click_text(
        self,
        target: str,
        button: str = "left",
        double: bool = False,
        region: ScreenRegion | None = None,
        timeout: float = 5.0,
        retry_interval: float = 1.0,
    ) -> dict[str, Any]:
        """Find text on screen via OCR and click its center.

        Args:
            target: Text to find (case-insensitive)
            button: Mouse button
            double: Double-click if True
            region: Limit search to screen region
            timeout: How long to keep looking
            retry_interval: Time between OCR attempts
        """
        import time
        start = time.time()
        attempts = 0

        while time.time() - start < timeout:
            attempts += 1
            result = await self._screen.find_text(target, region=region)

            if result.get("found") and result.get("matches"):
                match = result["matches"][0]
                cx = match.get("x", 0) + match.get("width", 0) // 2
                cy = match.get("y", 0) + match.get("height", 0) // 2

                if double:
                    click_result = await self._mouse.double_click(cx, cy)
                else:
                    click_result = await self._mouse.click(cx, cy, button=button)

                return {
                    "success": True,
                    "target": target,
                    "clicked_at": (cx, cy),
                    "match": match,
                    "attempts": attempts,
                    "click": click_result,
                }

            if time.time() - start + retry_interval < timeout:
                await asyncio.sleep(retry_interval)

        return {
            "success": False,
            "target": target,
            "error": f"Text '{target}' not found on screen after {attempts} attempts",
            "attempts": attempts,
        }

    async def click_near_text(
        self,
        target: str,
        offset_x: int = 0,
        offset_y: int = 0,
        button: str = "left",
        region: ScreenRegion | None = None,
    ) -> dict[str, Any]:
        """Find text on screen and click at an offset from it.

        Useful for clicking input fields near their labels:
        - click_near_text("Username", offset_y=30) — click below the label
        - click_near_text("Email", offset_x=200) — click to the right
        """
        result = await self._screen.find_text(target, region=region)

        if not result.get("found") or not result.get("matches"):
            return {
                "success": False,
                "target": target,
                "error": f"Text '{target}' not found on screen",
            }

        match = result["matches"][0]
        cx = match.get("x", 0) + match.get("width", 0) // 2 + offset_x
        cy = match.get("y", 0) + match.get("height", 0) // 2 + offset_y

        click_result = await self._mouse.click(cx, cy, button=button)

        return {
            "success": True,
            "target": target,
            "offset": (offset_x, offset_y),
            "clicked_at": (cx, cy),
            "match": match,
            "click": click_result,
        }

    async def click_color(
        self,
        hex_color: str,
        tolerance: int = 20,
        button: str = "left",
        region: ScreenRegion | None = None,
    ) -> dict[str, Any]:
        """Find a colored element on screen and click it."""
        result = await self._screen.find_color(
            hex_color, tolerance=tolerance, region=region, max_results=1
        )

        if not result.get("found") or not result.get("matches"):
            return {
                "success": False,
                "color": hex_color,
                "error": f"Color {hex_color} not found on screen",
            }

        match = result["matches"][0]
        click_result = await self._mouse.click(match["x"], match["y"], button=button)

        return {
            "success": True,
            "color": hex_color,
            "clicked_at": (match["x"], match["y"]),
            "click": click_result,
        }

    async def click_image(
        self,
        image_path: str,
        button: str = "left",
        confidence: float = 0.8,
    ) -> dict[str, Any]:
        """Find an image on screen and click its center.

        Uses PyAutoGUI's locateOnScreen for template matching.
        """
        try:
            import pyautogui
            location = pyautogui.locateOnScreen(image_path, confidence=confidence)
            if location:
                center = pyautogui.center(location)
                click_result = await self._mouse.click(center.x, center.y, button=button)
                return {
                    "success": True,
                    "image": image_path,
                    "clicked_at": (center.x, center.y),
                    "region": {
                        "x": location.left, "y": location.top,
                        "width": location.width, "height": location.height,
                    },
                    "click": click_result,
                }
            return {
                "success": False,
                "image": image_path,
                "error": "Image not found on screen",
            }
        except ImportError:
            return {"success": False, "error": "pyautogui not installed"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def type_into(
        self,
        label_text: str,
        value: str,
        offset_x: int = 200,
        offset_y: int = 0,
        clear_first: bool = True,
        region: ScreenRegion | None = None,
    ) -> dict[str, Any]:
        """Find a label on screen, click the input field next to it, and type text.

        This is the highest-level form-filling operation:
        type_into("Username", "john@example.com")
        """
        from plutus.pc.keyboard import KeyboardController

        # Click near the label
        click_result = await self.click_near_text(
            label_text, offset_x=offset_x, offset_y=offset_y, region=region
        )

        if not click_result.get("success"):
            return click_result

        await asyncio.sleep(0.2)

        # Type the value
        kb = KeyboardController("fast")
        type_result = await kb.type_text(value, clear_first=clear_first)

        return {
            "success": True,
            "label": label_text,
            "value": value,
            "clicked_at": click_result.get("clicked_at"),
            "typed": type_result,
        }
