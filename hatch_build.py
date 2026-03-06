"""Custom hatch build hook to generate platform-specific wheels.

When compiled Cython extensions (.so/.pyd) are present, hatchling must
produce a platform wheel (e.g. cp311-cp311-macosx_11_0_arm64) instead
of a pure-python wheel (py3-none-any). This hook tells hatchling to
infer the platform tag from the current Python interpreter.

It also dynamically prunes the exclude list: .py source files are only
excluded when their compiled counterpart (.pyd on Windows, .so elsewhere)
actually exists. This prevents shipping a wheel that has *neither* the
source nor the compiled extension — which would cause ModuleNotFoundError.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

# .py files that are expected to be compiled to Cython extensions.
# Listed relative to the repo root — must match pyproject.toml [tool.hatch.build.targets.wheel] exclude.
COMPILED_SOURCES = [
    "plutus/core/agent.py",
    "plutus/core/conversation.py",
    "plutus/core/heartbeat.py",
    "plutus/core/model_router.py",
    "plutus/core/planner.py",
    "plutus/core/scheduler.py",
    "plutus/core/subprocess_manager.py",
    "plutus/core/summarizer.py",
    "plutus/core/worker_pool.py",
    "plutus/pc/browser_control.py",
    "plutus/pc/computer_use.py",
    "plutus/pc/context.py",
    "plutus/pc/desktop_control.py",
    "plutus/pc/smart_click.py",
    "plutus/pc/workflow.py",
    "plutus/tools/code_analysis.py",
    "plutus/tools/code_editor.py",
    "plutus/tools/pc_control.py",
    "plutus/tools/tool_creator.py",
    "plutus/skills/engine.py",
    "plutus/skills/creator.py",
    "plutus/workers/code_analysis_worker.py",
    "plutus/workers/file_edit_worker.py",
    "plutus/workers/shell_worker.py",
    "plutus/workers/custom_worker.py",
]

# Extension suffix for compiled modules on this platform
_EXT = ".pyd" if sys.platform == "win32" else ".so"


def _has_compiled(py_path: str, root: Path) -> bool:
    """Return True if a compiled extension exists for the given .py source."""
    stem = py_path.removesuffix(".py")
    # Cython produces files like agent.cpython-311-x86_64-linux-gnu.so
    # or agent.pyd — check for any matching pattern.
    parent = root / Path(stem).parent
    name = Path(stem).name
    if not parent.is_dir():
        return False
    for entry in parent.iterdir():
        if entry.name.startswith(name) and entry.suffix in (".so", ".pyd"):
            return True
    return False


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        root = Path(self.root)
        has_any_compiled = False

        # Build the exclude list dynamically: only exclude .py sources
        # that have a compiled counterpart available.
        safe_excludes = []
        for src in COMPILED_SOURCES:
            if _has_compiled(src, root):
                safe_excludes.append(src)
                has_any_compiled = True
            # else: keep the .py — no compiled extension exists

        if has_any_compiled:
            # Platform-specific wheel with compiled extensions
            build_data["pure_python"] = False
            build_data["infer_tag"] = True

        # Override the static exclude list from pyproject.toml with our
        # dynamically computed one (only excluding files that have compiled
        # replacements).
        if "shared_data" not in build_data:
            build_data["shared_data"] = {}
        build_data["shared_data"]["safe_excludes"] = safe_excludes

        # Hatch reads exclude from the config, but we can also manipulate
        # force_include to re-add files that were statically excluded.
        # The simplest approach: remove static excludes that lack compiled
        # counterparts by adding them back via force_include.
        force_include = build_data.get("force_include_editable", build_data.get("force_include", {}))
        for src in COMPILED_SOURCES:
            src_path = root / src
            if src_path.exists() and not _has_compiled(src, root):
                # This .py was statically excluded in pyproject.toml but has no
                # compiled replacement — force-include it back into the wheel.
                force_include[str(src_path)] = src
        build_data["force_include"] = force_include
