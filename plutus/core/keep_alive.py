"""Cross-platform sleep prevention.

Prevents the OS from entering sleep/standby while Plutus is running.
Works on Windows, macOS, and Linux.
"""

from __future__ import annotations

import logging
import platform
import subprocess
import sys

logger = logging.getLogger(__name__)


class KeepAlive:
    """Prevents the system from sleeping while active.

    - **Windows**: Uses ``SetThreadExecutionState`` to tell the OS the system is busy.
    - **macOS**: Spawns ``caffeinate -i -s`` which prevents idle *and* lid-close sleep
      (lid-close prevention only works on AC power).
    - **Linux**: Uses ``systemd-inhibit`` to block the sleep/idle inhibitor locks.
    """

    def __init__(self) -> None:
        self._active = False
        self._process: subprocess.Popen | None = None  # macOS / Linux child process
        self._system = platform.system()  # "Windows", "Darwin", "Linux"

    @property
    def active(self) -> bool:
        return self._active

    def enable(self) -> None:
        """Start preventing system sleep."""
        if self._active:
            return

        try:
            if self._system == "Windows":
                self._enable_windows()
            elif self._system == "Darwin":
                self._enable_macos()
            elif self._system == "Linux":
                self._enable_linux()
            else:
                logger.warning("Keep-alive not supported on %s", self._system)
                return

            self._active = True
            logger.info("Keep-alive enabled (%s)", self._system)
        except Exception:
            logger.warning("Failed to enable keep-alive", exc_info=True)

    def disable(self) -> None:
        """Stop preventing system sleep."""
        if not self._active:
            return

        try:
            if self._system == "Windows":
                self._disable_windows()
            elif self._system in ("Darwin", "Linux"):
                self._stop_child()
            self._active = False
            logger.info("Keep-alive disabled")
        except Exception:
            logger.warning("Failed to disable keep-alive", exc_info=True)

    # ── Windows ──────────────────────────────────────────────────────────

    def _enable_windows(self) -> None:
        import ctypes

        ES_CONTINUOUS = 0x80000000
        ES_SYSTEM_REQUIRED = 0x00000001
        ES_DISPLAY_REQUIRED = 0x00000002
        ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
        )

    def _disable_windows(self) -> None:
        import ctypes

        ES_CONTINUOUS = 0x80000000
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)

    # ── macOS ────────────────────────────────────────────────────────────

    def _enable_macos(self) -> None:
        # -i  = prevent idle sleep
        # -s  = prevent system sleep (including lid-close on AC power)
        # -w  = wait for PID (our own process, so caffeinate dies when we do)
        self._process = subprocess.Popen(
            ["caffeinate", "-i", "-s", "-w", str(subprocess.os.getpid())],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # ── Linux ────────────────────────────────────────────────────────────

    def _enable_linux(self) -> None:
        # systemd-inhibit blocks sleep while the wrapped command is alive.
        # We use 'sleep infinity' as a no-op command that stays alive.
        self._process = subprocess.Popen(
            [
                "systemd-inhibit",
                "--what=sleep:idle",
                "--who=Plutus",
                "--why=Keeping Plutus server alive",
                "--mode=block",
                "sleep",
                "infinity",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # ── Shared ───────────────────────────────────────────────────────────

    def _stop_child(self) -> None:
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

    def status(self) -> dict:
        return {
            "active": self._active,
            "platform": self._system,
        }
