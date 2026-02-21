"""Heartbeat system — periodically wakes Plutus so it can work autonomously 24/7.

The heartbeat sends a synthetic "check-in" message to the agent at a
configurable interval.  The agent can then review its current plan, continue
executing tasks, or go idle if there's nothing to do.

Fully configurable:
  - enabled / disabled
  - interval (seconds)
  - quiet hours (pause overnight, etc.)
  - max consecutive beats without user interaction (safety valve)
  - custom prompt override
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Awaitable

from plutus.config import HeartbeatConfig

logger = logging.getLogger("plutus.heartbeat")

DEFAULT_HEARTBEAT_PROMPT = (
    "[HEARTBEAT] This is an automatic check-in. Review your current plan "
    "(if any) and continue working on the next pending step. If there is "
    "nothing to do, respond briefly that you're standing by. Do NOT ask the "
    "user for input — just continue autonomously or confirm you're idle."
)


class HeartbeatRunner:
    """Background async task that sends periodic heartbeats to the agent."""

    def __init__(
        self,
        config: HeartbeatConfig,
        on_beat: Callable[[str], Awaitable[Any]],
        on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ):
        self._config = config
        self._on_beat = on_beat  # called with the heartbeat prompt
        self._on_event = on_event  # optional: forward agent events to WS
        self._task: asyncio.Task | None = None
        self._consecutive_beats: int = 0
        self._paused: bool = False
        self._stop_event = asyncio.Event()

    # -- public controls -----------------------------------------------------

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def consecutive_beats(self) -> int:
        return self._consecutive_beats

    def reset_consecutive(self) -> None:
        """Call this whenever the user sends a real message."""
        self._consecutive_beats = 0

    def start(self) -> None:
        if self.running:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop(), name="heartbeat")
        logger.info(
            "Heartbeat started (interval=%ds, max_consecutive=%d)",
            self._config.interval_seconds,
            self._config.max_consecutive,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        logger.info("Heartbeat stopped")

    def pause(self) -> None:
        self._paused = True
        logger.info("Heartbeat paused")

    def resume(self) -> None:
        self._paused = False
        logger.info("Heartbeat resumed")

    def update_config(self, config: HeartbeatConfig) -> None:
        self._config = config
        # If it was running, restart with new config
        if self.running:
            self.stop()
            if config.enabled:
                self.start()

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self._config.enabled,
            "running": self.running,
            "paused": self._paused,
            "interval_seconds": self._config.interval_seconds,
            "consecutive_beats": self._consecutive_beats,
            "max_consecutive": self._config.max_consecutive,
            "quiet_hours_start": self._config.quiet_hours_start,
            "quiet_hours_end": self._config.quiet_hours_end,
        }

    # -- internal loop -------------------------------------------------------

    def _in_quiet_hours(self) -> bool:
        start = self._config.quiet_hours_start
        end = self._config.quiet_hours_end
        if not start or not end:
            return False

        now = datetime.now().strftime("%H:%M")
        # Handle overnight ranges like 23:00 -> 07:00
        if start <= end:
            return start <= now < end
        else:
            return now >= start or now < end

    async def _loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(self._config.interval_seconds)

                if self._stop_event.is_set():
                    break

                if self._paused:
                    continue

                if self._in_quiet_hours():
                    logger.debug("Skipping heartbeat — quiet hours")
                    continue

                if self._consecutive_beats >= self._config.max_consecutive:
                    logger.info(
                        "Heartbeat paused — %d consecutive beats with no user interaction",
                        self._consecutive_beats,
                    )
                    self._paused = True
                    if self._on_event:
                        await self._on_event(
                            {
                                "type": "heartbeat_paused",
                                "reason": "max_consecutive_reached",
                                "count": self._consecutive_beats,
                            }
                        )
                    continue

                prompt = self._config.prompt or DEFAULT_HEARTBEAT_PROMPT
                self._consecutive_beats += 1

                logger.info("Heartbeat #%d firing", self._consecutive_beats)

                if self._on_event:
                    await self._on_event(
                        {
                            "type": "heartbeat",
                            "beat": self._consecutive_beats,
                            "max": self._config.max_consecutive,
                        }
                    )

                try:
                    await self._on_beat(prompt)
                except Exception:
                    logger.exception("Heartbeat agent call failed")

        except asyncio.CancelledError:
            logger.debug("Heartbeat loop cancelled")
