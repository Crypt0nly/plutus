"""Cython build script — compiles protected modules to native extensions.

Usage:
    python build_compiled.py build_ext --inplace

This compiles the "magic" modules (agent orchestration, PC control, workers, etc.)
into platform-specific .so (Linux/macOS) or .pyd (Windows) binaries. The resulting
files are importable by Python but not human-readable.

After compilation, the original .py source files for these modules should be removed
from the wheel (see scripts/strip_sources.py).
"""

from __future__ import annotations

from Cython.Build import cythonize
from setuptools import Extension, setup

# ──────────────────────────────────────────────────────────────
# Protected modules — the core IP that gets compiled
# ──────────────────────────────────────────────────────────────
# These are the files that contain the "magic" — the orchestration
# logic, PC control, subprocess isolation, etc. Everything else
# (CLI, config, gateway, guardrails, basic tools) stays as readable .py.

PROTECTED_MODULES = [
    # Core orchestration
    "plutus/core/agent.py",
    "plutus/core/conversation.py",
    "plutus/core/heartbeat.py",
    "plutus/core/model_router.py",
    "plutus/core/planner.py",
    "plutus/core/scheduler.py",
    "plutus/core/subprocess_manager.py",
    "plutus/core/summarizer.py",
    "plutus/core/worker_pool.py",
    # PC control
    "plutus/pc/browser_control.py",
    "plutus/pc/computer_use.py",
    "plutus/pc/context.py",
    "plutus/pc/desktop_control.py",
    "plutus/pc/smart_click.py",
    "plutus/pc/workflow.py",
    # Advanced tools
    "plutus/tools/code_analysis.py",
    "plutus/tools/code_editor.py",
    "plutus/tools/pc_control.py",
    "plutus/tools/tool_creator.py",
    # Skills engine
    "plutus/skills/engine.py",
    "plutus/skills/creator.py",
    # Workers
    "plutus/workers/code_analysis_worker.py",
    "plutus/workers/file_edit_worker.py",
    "plutus/workers/shell_worker.py",
    "plutus/workers/custom_worker.py",
]


def make_extensions() -> list[Extension]:
    """Create Extension objects from the module list."""
    extensions = []
    for path in PROTECTED_MODULES:
        # Convert file path to dotted module name: plutus/core/agent.py -> plutus.core.agent
        module_name = path.replace("/", ".").removesuffix(".py")
        extensions.append(Extension(module_name, [path]))
    return extensions


# Guard required for macOS which uses "spawn" (not "fork") for multiprocessing.
# Without this, spawned Cython worker processes re-execute the entire script
# and crash with "An attempt has been made to start a new process before the
# current process has finished its bootstrapping phase."
if __name__ == "__main__":
    ext_modules = cythonize(
        make_extensions(),
        compiler_directives={
            "language_level": "3",
            "boundscheck": False,
            "wraparound": False,
        },
        nthreads=4,
    )

    setup(
        name="plutus-ai",
        ext_modules=ext_modules,
        packages=["plutus"],
    )
