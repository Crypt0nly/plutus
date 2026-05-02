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

Live-config guarantee
---------------------
The runner reads its configuration freshly on every loop iteration, so
changes to interval / quiet hours / max_consecutive / prompt / blocked_ops
take effect on the next sleep wake-up — no restart required. To make a
change apply *immediately* (without waiting for the current sleep to elapse),
call ``update_config()`` which wakes the in-flight sleep.

To avoid relying on every caller remembering to invoke ``update_config()``
after mutating config, the runner can be constructed with a callable that
returns the current ``HeartbeatConfig`` (e.g. ``lambda: cfg.heartbeat``).
In that case it always reads live values from the parent config object on
every iteration.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from collections.abc import Awaitable, Callable
from typing import Any, Union

from plutus.config import HeartbeatConfig

logger = logging.getLogger("plutus.heartbeat")

DEFAULT_HEARTBEAT_PROMPT = (
    "[HEARTBEAT] This is an automatic check-in. Review your current plan "
    "(if any) and continue working on the next pending step. If there is "
    "nothing to do, respond briefly that you're standing by. Do NOT ask the "
    "user for input — just continue autonomously or confirm you're idle."
)


HeartbeatConfigSource = Union[HeartbeatConfig, Callable[[], HeartbeatConfig]]


class HeartbeatRunner:
    """Background async task that sends periodic heartbeats to the agent."""

    def __init__(
        self,
        config: HeartbeatConfigSource,
        on_beat: Callable[[str], Awaitable[Any]],
        on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ):
        self._config_provider: Callable[[], HeartbeatConfig]
        self._set_config_source(config)
        self._on_beat = on_beat  # called with the heartbeat prompt
        self._on_event = on_event  # optional: forward agent events to WS
        self._task: asyncio.Task | None = None
        self._consecutive_beats: int = 0
        self._paused: bool = False
        self._stop_event = asyncio.Event()
        # Set whenever config changes (or stop is requested) so an in-flight
        # sleep wakes up and re-reads the new interval immediately.
        self._wake_event = asyncio.Event()

    # -- helpers ------------------------------------------------------------

    def _set_config_source(self, config: HeartbeatConfigSource) -> None:
        if callable(config):
            self._config_provider = config  # type: ignore[assignment]
        else:
            cfg_ref = config
            self._config_provider = lambda: cfg_ref

    @property
    def _config(self) -> HeartbeatConfig:
        return self._config_provider()

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
        self._wake_event.clear()
        self._task = asyncio.create_task(self._loop(), name="heartbeat")
        cfg = self._config
        logger.info(
            "Heartbeat started (interval=%ds, max_consecutive=%d)",
            cfg.interval_seconds,
            cfg.max_consecutive,
        )

    def stop(self) -> None:
        self._stop_event.set()
        # Wake any in-flight sleep so the loop notices the stop_event without
        # waiting for cancellation to propagate through asyncio.sleep.
        self._wake_event.set()
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

    def update_config(self, config: HeartbeatConfigSource | None = None) -> None:
        """Apply an updated heartbeat configuration.

        If ``config`` is provided, it replaces the current config source.
        Either way, this wakes any in-flight sleep so the new interval and
        other fields take effect immediately, and synchronises the runner's
        running state with the ``enabled`` flag.
        """
        if config is not None:
            self._set_config_source(config)

        # Wake an in-flight sleep so the new interval applies right away.
        self._wake_event.set()

        cfg = self._config
        if cfg.enabled and not self.running:
            self.start()
        elif not cfg.enabled and self.running:
            self.stop()

    def status(self) -> dict[str, Any]:
        cfg = self._config
        return {
            "enabled": cfg.enabled,
            "running": self.running,
            "paused": self._paused,
            "interval_seconds": cfg.interval_seconds,
            "consecutive_beats": self._consecutive_beats,
            "max_consecutive": cfg.max_consecutive,
            "quiet_hours_start": cfg.quiet_hours_start,
            "quiet_hours_end": cfg.quiet_hours_end,
            "blocked_ops": list(cfg.blocked_ops),
        }

    # -- internal loop -------------------------------------------------------

    def _in_quiet_hours(self) -> bool:
        cfg = self._config
        start = cfg.quiet_hours_start
        end = cfg.quiet_hours_end
        if not start or not end:
            return False

        now = datetime.now().strftime("%H:%M")
        # Handle overnight ranges like 23:00 -> 07:00
        if start <= end:
            return start <= now < end
        else:
            return now >= start or now < end

    async def _interruptible_sleep(self, seconds: float) -> bool:
        """Sleep up to *seconds*, returning early if ``_wake_event`` is set.

        Returns True if the sleep was interrupted (config changed or stop
        requested), False if it ran to completion.
        """
        if seconds <= 0:
            return False
        try:
            await asyncio.wait_for(self._wake_event.wait(), timeout=seconds)
            return True
        except asyncio.TimeoutError:
            return False

    async def _loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                # Always read interval freshly from the live config so that
                # mid-flight updates apply on the next sleep cycle.
                cfg = self._config
                interval = max(1, int(cfg.interval_seconds))

                # Clear before sleeping so any update_config()/stop() call
                # during the sleep is observed and wakes us.
                self._wake_event.clear()
                interrupted = await self._interruptible_sleep(interval)

                if self._stop_event.is_set():
                    break

                if interrupted:
                    # Config or stop changed mid-sleep — restart the loop to
                    # re-read the (possibly different) interval before doing
                    # anything else.
                    continue

                if self._paused:
                    continue

                if self._in_quiet_hours():
                    logger.debug("Skipping heartbeat — quiet hours")
                    continue

                cfg = self._config
                if self._consecutive_beats >= cfg.max_consecutive:
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

                prompt = cfg.prompt or DEFAULT_HEARTBEAT_PROMPT
                self._consecutive_beats += 1

                logger.info("Heartbeat #%d firing", self._consecutive_beats)

                if self._on_event:
                    await self._on_event(
                        {
                            "type": "heartbeat",
                            "beat": self._consecutive_beats,
                            "max": cfg.max_consecutive,
                        }
                    )

                try:
                    await self._on_beat(prompt)
                except Exception:
                    logger.exception("Heartbeat agent call failed")

        except asyncio.CancelledError:
            logger.debug("Heartbeat loop cancelled")
