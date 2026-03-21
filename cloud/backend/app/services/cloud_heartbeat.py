"""
Cloud Heartbeat Manager
=======================
Provides per-user autonomous heartbeat for the cloud version of Plutus.

Unlike the local version (which uses a single-user HeartbeatRunner), the cloud
version manages one asyncio task per user.  Each task fires on a configurable
interval, wakes the agent, and injects a heartbeat prompt so Plutus can:
  - Resume the next step in an active plan
  - Run scheduled tasks
  - Proactively improve its own skills

Architecture:
    CloudHeartbeatManager (singleton)
        │
        ├─ user_id → HeartbeatTask (asyncio.Task + config)
        │
        └─ on each beat:
               1. Check quiet hours
               2. Acquire per-user lock (skip if agent is already running)
               3. Call CloudAgentRuntime.process_message(heartbeat_prompt)
               4. Broadcast heartbeat event via WebSocket (if connected)

Usage:
    manager = CloudHeartbeatManager.get_instance()
    await manager.start(user_id, session_factory, interval_seconds=300)
    await manager.stop(user_id)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT = (
    "Heartbeat check-in. "
    "Review your active plan (if any) and continue the next pending step autonomously. "
    "If there is no active plan, reflect on recent tasks and ask yourself: "
    "what skills or tools could I build right now to make future tasks faster? "
    "Build at least one if you identify a gap. "
    "Do not ask the user for permission — just act."
)

# Minimum interval to prevent runaway costs
_MIN_INTERVAL = 60  # seconds
_DEFAULT_INTERVAL = 300  # 5 minutes


@dataclass
class HeartbeatState:
    user_id: str
    interval: int = _DEFAULT_INTERVAL
    enabled: bool = True
    quiet_hours_start: int | None = None  # 0-23
    quiet_hours_end: int | None = None  # 0-23
    max_consecutive: int = 5
    prompt: str = _DEFAULT_PROMPT
    consecutive: int = 0
    last_beat: float | None = None
    task: asyncio.Task | None = field(default=None, repr=False)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


class CloudHeartbeatManager:
    """Singleton manager for per-user cloud heartbeats."""

    _instance: CloudHeartbeatManager | None = None

    def __init__(self) -> None:
        self._states: dict[str, HeartbeatState] = {}
        # Optional WebSocket broadcast callback: (user_id, event_dict) -> None
        self._broadcast_cb: Callable | None = None

    @classmethod
    def get_instance(cls) -> CloudHeartbeatManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_broadcast_callback(self, cb: Callable) -> None:
        self._broadcast_cb = cb

    # ── Public API ────────────────────────────────────────────────────────────

    def is_running(self, user_id: str) -> bool:
        state = self._states.get(user_id)
        return bool(state and state.task and not state.task.done())

    def get_status(self, user_id: str) -> dict:
        state = self._states.get(user_id)
        if not state:
            return {
                "enabled": False,
                "interval_seconds": _DEFAULT_INTERVAL,
                "last_beat": None,
                "running": False,
                "consecutive": 0,
            }
        return {
            "enabled": state.enabled,
            "interval_seconds": state.interval,
            "last_beat": state.last_beat,
            "running": self.is_running(user_id),
            "consecutive": state.consecutive,
            "quiet_hours_start": state.quiet_hours_start,
            "quiet_hours_end": state.quiet_hours_end,
            "max_consecutive": state.max_consecutive,
        }

    async def start(
        self,
        user_id: str,
        session_factory,
        interval_seconds: int = _DEFAULT_INTERVAL,
        prompt: str | None = None,
        quiet_hours_start: int | None = None,
        quiet_hours_end: int | None = None,
        max_consecutive: int = 5,
    ) -> None:
        """Start (or restart) the heartbeat for a user."""
        await self.stop(user_id)

        interval = max(interval_seconds, _MIN_INTERVAL)
        state = HeartbeatState(
            user_id=user_id,
            interval=interval,
            enabled=True,
            quiet_hours_start=quiet_hours_start,
            quiet_hours_end=quiet_hours_end,
            max_consecutive=max_consecutive,
            prompt=prompt or _DEFAULT_PROMPT,
        )
        self._states[user_id] = state
        state.task = asyncio.create_task(
            self._beat_loop(state, session_factory),
            name=f"heartbeat-{user_id[:8]}",
        )
        logger.info("[Heartbeat] Started for user %s (interval=%ds)", user_id[:8], interval)

    async def stop(self, user_id: str) -> None:
        state = self._states.get(user_id)
        if state and state.task and not state.task.done():
            state.task.cancel()
            try:
                await state.task
            except asyncio.CancelledError:
                pass
        if user_id in self._states:
            self._states[user_id].enabled = False
        logger.info("[Heartbeat] Stopped for user %s", user_id[:8])

    def reset_consecutive(self, user_id: str) -> None:
        """Reset consecutive counter when the user sends a real message."""
        state = self._states.get(user_id)
        if state:
            state.consecutive = 0

    async def update_config(
        self,
        user_id: str,
        session_factory,
        interval_seconds: int | None = None,
        prompt: str | None = None,
        quiet_hours_start: int | None = None,
        quiet_hours_end: int | None = None,
        max_consecutive: int | None = None,
    ) -> dict:
        """Update heartbeat config; restart the loop if interval changed."""
        state = self._states.get(user_id)
        if not state:
            # Not running — just return current status
            return self.get_status(user_id)

        restart = False
        if interval_seconds is not None:
            new_interval = max(interval_seconds, _MIN_INTERVAL)
            if new_interval != state.interval:
                state.interval = new_interval
                restart = True
        if prompt is not None:
            state.prompt = prompt
        if quiet_hours_start is not None:
            state.quiet_hours_start = quiet_hours_start
        if quiet_hours_end is not None:
            state.quiet_hours_end = quiet_hours_end
        if max_consecutive is not None:
            state.max_consecutive = max_consecutive

        if restart:
            await self.start(
                user_id,
                session_factory,
                interval_seconds=state.interval,
                prompt=state.prompt,
                quiet_hours_start=state.quiet_hours_start,
                quiet_hours_end=state.quiet_hours_end,
                max_consecutive=state.max_consecutive,
            )
        return self.get_status(user_id)

    # ── Internal loop ─────────────────────────────────────────────────────────

    async def _beat_loop(self, state: HeartbeatState, session_factory) -> None:
        """Main heartbeat loop for a single user."""
        while state.enabled:
            await asyncio.sleep(state.interval)
            if not state.enabled:
                break
            await self._fire_beat(state, session_factory)

    async def _fire_beat(self, state: HeartbeatState, session_factory) -> None:
        """Execute a single heartbeat beat."""
        user_id = state.user_id

        # Quiet hours check
        if self._in_quiet_hours(state):
            logger.debug("[Heartbeat] Quiet hours — skipping beat for %s", user_id[:8])
            return

        # Max consecutive check
        if state.max_consecutive and state.consecutive >= state.max_consecutive:
            logger.debug(
                "[Heartbeat] Max consecutive (%d) reached for %s — skipping",
                state.max_consecutive,
                user_id[:8],
            )
            return

        # Skip if agent is already processing (lock is held)
        if state.lock.locked():
            logger.debug("[Heartbeat] Agent busy — skipping beat for %s", user_id[:8])
            return

        async with state.lock:
            state.last_beat = time.time()
            state.consecutive += 1
            logger.info(
                "[Heartbeat] Firing beat #%d for user %s",
                state.consecutive,
                user_id[:8],
            )

            try:
                async with session_factory() as session:
                    from app.agent.runtime import CloudAgentRuntime
                    from app.services.agent_service import AgentService

                    # Use or create a dedicated heartbeat conversation
                    agent_svc = AgentService(session)
                    conv_id = await self._get_or_create_heartbeat_conv(user_id, agent_svc)

                    runtime = CloudAgentRuntime(
                        user_id=user_id,
                        session=session,
                        config={"is_heartbeat": True},
                    )
                    await runtime.process_message(state.prompt, conversation_id=conv_id)

                # Broadcast heartbeat event if a WS callback is registered
                if self._broadcast_cb:
                    try:
                        await self._broadcast_cb(
                            user_id,
                            {
                                "type": "heartbeat_beat",
                                "consecutive": state.consecutive,
                                "timestamp": state.last_beat,
                            },
                        )
                    except Exception:
                        pass

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "[Heartbeat] Beat failed for user %s: %s",
                    user_id[:8],
                    exc,
                    exc_info=True,
                )

    async def _get_or_create_heartbeat_conv(self, user_id: str, agent_svc) -> str:
        """Return the persistent heartbeat conversation ID for this user."""
        from sqlalchemy import text

        # Use a deterministic conversation ID so heartbeat messages are
        # grouped together and don't pollute the user's chat history.
        conv_id = f"heartbeat-{user_id}"
        try:
            existing = await agent_svc.get_messages(conv_id)
            if not existing:
                await agent_svc.create_conversation(conv_id, user_id)
        except Exception:
            await agent_svc.create_conversation(conv_id, user_id)
        return conv_id

    @staticmethod
    def _in_quiet_hours(state: HeartbeatState) -> bool:
        if state.quiet_hours_start is None or state.quiet_hours_end is None:
            return False
        hour = datetime.now(timezone.utc).hour
        start, end = state.quiet_hours_start, state.quiet_hours_end
        if start <= end:
            return start <= hour < end
        # Wraps midnight (e.g. 22–06)
        return hour >= start or hour < end
