"""Plutus — Autonomous AI agent with subprocess orchestration."""

__version__ = "0.3.26"


def _detect_build_tag() -> str:
    """Detect whether we're running compiled (production) or raw source (dev).

    Checks if any of the protected Cython-compiled modules exist as native
    extensions (.so on Linux/macOS, .pyd on Windows). If they do, this is a
    production wheel build. Otherwise, it's a dev/source install.
    """
    import importlib.util

    # Just check one core module — if it's compiled, they all are
    spec = importlib.util.find_spec("plutus.core.agent")
    if spec and spec.origin:
        if spec.origin.endswith((".so", ".pyd")):
            return ""  # production — no tag needed
    return " (dev)"


build_tag: str = _detect_build_tag()
