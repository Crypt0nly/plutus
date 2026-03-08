"""Plutus — Autonomous AI agent with subprocess orchestration."""

__version__ = "0.3.26"


def _detect_build_tag() -> str:
    """Detect whether we're running compiled (production) or raw source (dev).

    Checks if a compiled .so/.pyd binary exists for a core module on disk.
    Uses glob on the filesystem to avoid triggering imports (which would
    fail in environments without dependencies installed, e.g. CI test steps).
    """
    try:
        from pathlib import Path

        core_dir = Path(__file__).parent / "core"
        if any(core_dir.glob("agent*.so")) or any(core_dir.glob("agent*.pyd")):
            return ""  # production — no tag needed
    except (NameError, OSError):
        # __file__ is undefined when run via exec() (e.g. version bump scripts)
        pass
    return " (dev)"


build_tag: str = _detect_build_tag()
