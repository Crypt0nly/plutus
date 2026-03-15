"""Cython build script — compiles protected modules to native extensions.

Usage:
    python build_compiled.py build_ext --inplace

This compiles the "product glue" modules — the installer, onboarding, server
orchestration, and auto-configuration that turn the raw engine into a polished
product — into platform-specific .so (Linux/macOS) or .pyd (Windows) binaries.
The resulting files are importable by Python but not human-readable.

The engine underneath (core agent, tools, PC control, skills, connectors,
guardrails) is shipped as readable .py so developers can inspect, fork, and
contribute.

After compilation, the original .py source files for these modules should be
removed from the wheel (see the exclude list in pyproject.toml).
"""

from __future__ import annotations

import os
import sys

from Cython.Build import cythonize
from setuptools import Extension, setup

# ──────────────────────────────────────────────────────────────
# Protected modules — the product glue that gets compiled
# ──────────────────────────────────────────────────────────────
# These are the files that turn raw code into a product a non-technical
# person can use: the CLI (installer, onboarding wizard, auto-setup),
# the gateway (server startup, API routes, WebSocket orchestration),
# and product-level features (heartbeat monitoring, task scheduler).
#
# Everything else — the AI engine, tools, PC control, skills, connectors,
# guardrails — stays as readable .py and is open source.

PROTECTED_MODULES = [
    # CLI — installer, onboarding wizard, setup commands, auto-configuration
    "plutus/cli.py",

    # Gateway — server startup orchestration, API surface, WebSocket handling
    "plutus/gateway/server.py",
    "plutus/gateway/routes.py",
    "plutus/gateway/ws.py",

    # Product features — monitoring and scheduling that make it "just work"
    "plutus/core/heartbeat.py",
    "plutus/core/scheduler.py",
]


def make_extensions() -> list[Extension]:
    """Create Extension objects from the module list."""
    extensions = []
    for path in PROTECTED_MODULES:
        # Convert file path to dotted module name: plutus/core/agent.py -> plutus.core.agent
        module_name = path.replace("/", ".").removesuffix(".py")
        extensions.append(Extension(module_name, [path]))
    return extensions


# On macOS, Python defaults to the "spawn" multiprocessing start method (not
# "fork"), so nthreads>0 causes Cython worker processes to re-import this
# script and crash. On Linux and Windows, parallel compilation works fine.
def _compile_threads() -> int:
    if sys.platform == "darwin":
        return 0  # serial on macOS to avoid spawn crash
    return os.cpu_count() or 1


if __name__ == "__main__":
    ext_modules = cythonize(
        make_extensions(),
        compiler_directives={
            "language_level": "3",
            "boundscheck": False,
            "wraparound": False,
        },
        nthreads=_compile_threads(),
    )

    setup(
        name="plutus-ai",
        ext_modules=ext_modules,
        packages=["plutus"],
    )
