"""Plutus — Autonomous AI agent with subprocess orchestration."""

__version__ = "0.3.149"


def _detect_build_tag() -> str:
    """Detect whether this is a production install or a dev source checkout.

    Production (no tag): installed via pip (no .git repo ancestor).
    Dev (" (dev)"): running from a cloned git repository.
    Falls back to "" (production) when __file__ is unavailable (exec context).
    """
    try:
        from pathlib import Path

        pkg_dir = Path(__file__).resolve().parent
        # Walk up from the package directory looking for a .git folder.
        # If found, we're running from a source checkout → dev.
        # pip-installed packages live in site-packages with no .git ancestor.
        for parent in [pkg_dir, *pkg_dir.parents]:
            if (parent / ".git").is_dir():
                return " (dev)"
            # Stop at filesystem root
            if parent == parent.parent:
                break
    except (NameError, OSError):
        # __file__ is undefined when run via exec() (e.g. version bump scripts)
        pass
    return ""


build_tag: str = _detect_build_tag()
