"""Smart mouse controller — human-like movement with bezier curves.

Instead of teleporting the cursor, this moves it along smooth curves
with natural acceleration/deceleration, random micro-jitter, and
configurable speed profiles. Feels like a real person using the mouse.
"""

from __future__ import annotations

import asyncio
import math
import platform
import random
import time
from dataclasses import dataclass, field
from typing import Any

SYSTEM = platform.system()


@dataclass
class MouseProfile:
    """Movement personality — how the mouse "feels"."""
    speed: float = 1.0          # 0.5 = slow/careful, 1.0 = normal, 2.0 = fast
    smoothness: int = 50        # bezier curve resolution (more = smoother)
    jitter: float = 1.5         # random pixel offset for human feel
    overshoot: float = 0.05     # slight overshoot probability
    pause_before_click: float = 0.08  # brief pause before clicking (seconds)
    click_duration: float = 0.06      # how long a click is held


# Pre-built profiles
PROFILES = {
    "careful": MouseProfile(speed=0.6, smoothness=80, jitter=0.5, overshoot=0.02),
    "normal": MouseProfile(speed=1.0, smoothness=50, jitter=1.5, overshoot=0.05),
    "fast": MouseProfile(speed=2.0, smoothness=30, jitter=2.0, overshoot=0.08),
    "precise": MouseProfile(speed=0.4, smoothness=100, jitter=0.0, overshoot=0.0),
    "instant": MouseProfile(speed=100.0, smoothness=5, jitter=0.0, overshoot=0.0),
}


def _bezier_point(t: float, p0: tuple, p1: tuple, p2: tuple, p3: tuple) -> tuple:
    """Compute a point on a cubic bezier curve at parameter t."""
    u = 1 - t
    return (
        u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
    )


def _generate_curve(
    start: tuple[int, int],
    end: tuple[int, int],
    steps: int,
    jitter: float = 1.5,
) -> list[tuple[int, int]]:
    """Generate a smooth bezier curve path from start to end with natural feel."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    dist = math.sqrt(dx**2 + dy**2)

    # Control points offset perpendicular to the line for natural curvature
    offset = dist * random.uniform(0.1, 0.3) * random.choice([-1, 1])
    mid_x = (start[0] + end[0]) / 2
    mid_y = (start[1] + end[1]) / 2

    # Perpendicular direction
    if dist > 0:
        perp_x = -dy / dist * offset
        perp_y = dx / dist * offset
    else:
        perp_x = perp_y = 0

    cp1 = (
        start[0] + dx * random.uniform(0.2, 0.4) + perp_x * 0.5,
        start[1] + dy * random.uniform(0.2, 0.4) + perp_y * 0.5,
    )
    cp2 = (
        start[0] + dx * random.uniform(0.6, 0.8) + perp_x,
        start[1] + dy * random.uniform(0.6, 0.8) + perp_y,
    )

    points = []
    for i in range(steps + 1):
        t = i / steps
        # Ease-in-out timing for natural acceleration
        t_eased = t * t * (3 - 2 * t)
        px, py = _bezier_point(t_eased, start, cp1, cp2, end)

        # Add micro-jitter (not on first/last points)
        if 0 < i < steps and jitter > 0:
            px += random.gauss(0, jitter)
            py += random.gauss(0, jitter)

        points.append((int(round(px)), int(round(py))))

    return points


class MouseController:
    """Cross-platform mouse controller with human-like behavior.

    Usage:
        mouse = MouseController()
        await mouse.move_to(500, 300)           # smooth move
        await mouse.click(500, 300)              # move + click
        await mouse.double_click(500, 300)       # move + double click
        await mouse.right_click(500, 300)        # move + right click
        await mouse.drag(100, 100, 500, 300)     # smooth drag
        await mouse.scroll(amount=-3, x=500, y=300)  # scroll down
    """

    def __init__(self, profile: str | MouseProfile = "normal"):
        if isinstance(profile, str):
            self.profile = PROFILES.get(profile, PROFILES["normal"])
        else:
            self.profile = profile
        self._pag = None

    def _get_pag(self):
        """Lazy import pyautogui."""
        if self._pag is None:
            try:
                import pyautogui
                pyautogui.FAILSAFE = True
                pyautogui.PAUSE = 0  # we handle timing ourselves
                self._pag = pyautogui
            except ImportError:
                raise RuntimeError(
                    "pyautogui not installed. Run: pip install pyautogui\n"
                    "Linux also needs: sudo apt install python3-tk scrot"
                )
        return self._pag

    def get_position(self) -> tuple[int, int]:
        """Get current mouse position."""
        pag = self._get_pag()
        pos = pag.position()
        return (pos.x, pos.y)

    def get_screen_size(self) -> tuple[int, int]:
        """Get screen dimensions."""
        pag = self._get_pag()
        size = pag.size()
        return (size.width, size.height)

    async def move_to(
        self,
        x: int,
        y: int,
        speed: float | None = None,
        smooth: bool = True,
    ) -> dict[str, Any]:
        """Move mouse to (x, y) along a smooth bezier curve.

        Args:
            x, y: Target coordinates
            speed: Override profile speed (0.5=slow, 1.0=normal, 2.0=fast)
            smooth: If False, teleport instantly
        """
        pag = self._get_pag()
        start = self.get_position()
        target = (x, y)

        if not smooth or self.profile.speed >= 50:
            pag.moveTo(x, y, duration=0)
            return {"action": "move", "from": start, "to": target, "smooth": False}

        # Calculate duration based on distance and speed
        dist = math.sqrt((x - start[0])**2 + (y - start[1])**2)
        spd = speed or self.profile.speed
        base_duration = max(0.1, min(1.5, dist / (800 * spd)))

        # Generate curve
        steps = max(10, int(self.profile.smoothness * base_duration))
        points = _generate_curve(start, target, steps, self.profile.jitter)

        # Animate along the curve
        delay = base_duration / len(points)
        for px, py in points:
            pag.moveTo(px, py, duration=0, _pause=False)
            await asyncio.sleep(delay)

        # Overshoot correction
        if random.random() < self.profile.overshoot and dist > 50:
            overshoot_x = x + random.randint(-3, 3)
            overshoot_y = y + random.randint(-3, 3)
            pag.moveTo(overshoot_x, overshoot_y, duration=0, _pause=False)
            await asyncio.sleep(0.03)
            pag.moveTo(x, y, duration=0, _pause=False)

        return {
            "action": "move",
            "from": start,
            "to": target,
            "distance": round(dist),
            "duration": round(base_duration, 3),
            "smooth": True,
        }

    async def click(
        self,
        x: int | None = None,
        y: int | None = None,
        button: str = "left",
        clicks: int = 1,
        move: bool = True,
    ) -> dict[str, Any]:
        """Click at (x, y) with optional smooth movement first."""
        pag = self._get_pag()

        if x is not None and y is not None and move:
            move_result = await self.move_to(x, y)
        else:
            move_result = None

        # Brief human-like pause before clicking
        if self.profile.pause_before_click > 0:
            await asyncio.sleep(
                self.profile.pause_before_click * random.uniform(0.7, 1.3)
            )

        pos = self.get_position()
        pag.click(x=pos[0], y=pos[1], clicks=clicks, button=button, _pause=False)

        return {
            "action": "click",
            "position": pos,
            "button": button,
            "clicks": clicks,
            "moved": move_result is not None,
        }

    async def double_click(
        self, x: int | None = None, y: int | None = None
    ) -> dict[str, Any]:
        """Double-click at (x, y)."""
        return await self.click(x, y, clicks=2)

    async def right_click(
        self, x: int | None = None, y: int | None = None
    ) -> dict[str, Any]:
        """Right-click at (x, y)."""
        return await self.click(x, y, button="right")

    async def middle_click(
        self, x: int | None = None, y: int | None = None
    ) -> dict[str, Any]:
        """Middle-click at (x, y)."""
        return await self.click(x, y, button="middle")

    async def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        button: str = "left",
        speed: float | None = None,
    ) -> dict[str, Any]:
        """Smooth drag from (start_x, start_y) to (end_x, end_y)."""
        pag = self._get_pag()

        # Move to start
        await self.move_to(start_x, start_y, speed=speed)
        await asyncio.sleep(0.05)

        # Press and hold
        pag.mouseDown(button=button, _pause=False)
        await asyncio.sleep(0.05)

        # Smooth drag to end
        dist = math.sqrt((end_x - start_x)**2 + (end_y - start_y)**2)
        spd = speed or self.profile.speed
        duration = max(0.2, min(2.0, dist / (500 * spd)))
        steps = max(15, int(self.profile.smoothness * duration))
        points = _generate_curve(
            (start_x, start_y), (end_x, end_y), steps, self.profile.jitter * 0.5
        )

        delay = duration / len(points)
        for px, py in points:
            pag.moveTo(px, py, duration=0, _pause=False)
            await asyncio.sleep(delay)

        # Release
        await asyncio.sleep(0.05)
        pag.mouseUp(button=button, _pause=False)

        return {
            "action": "drag",
            "from": (start_x, start_y),
            "to": (end_x, end_y),
            "distance": round(dist),
            "button": button,
        }

    async def scroll(
        self,
        amount: int,
        x: int | None = None,
        y: int | None = None,
        smooth: bool = True,
    ) -> dict[str, Any]:
        """Scroll at position. Positive = up, negative = down.

        With smooth=True, scrolls incrementally for a natural feel.
        """
        pag = self._get_pag()

        if x is not None and y is not None:
            await self.move_to(x, y)

        if smooth and abs(amount) > 1:
            direction = 1 if amount > 0 else -1
            for _ in range(abs(amount)):
                pag.scroll(direction, _pause=False)
                await asyncio.sleep(random.uniform(0.03, 0.08))
        else:
            pag.scroll(amount, _pause=False)

        pos = self.get_position()
        return {
            "action": "scroll",
            "amount": amount,
            "position": pos,
            "smooth": smooth,
        }

    async def hover(self, x: int, y: int, duration: float = 0.5) -> dict[str, Any]:
        """Move to position and hover for a duration (triggers tooltips)."""
        await self.move_to(x, y)
        await asyncio.sleep(duration)
        return {"action": "hover", "position": (x, y), "duration": duration}
