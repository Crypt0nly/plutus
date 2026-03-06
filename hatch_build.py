"""Custom hatch build hook to generate platform-specific wheels.

When compiled Cython extensions (.so/.pyd) are present, hatchling must
produce a platform wheel (e.g. cp311-cp311-macosx_11_0_arm64) instead
of a pure-python wheel (py3-none-any). This hook tells hatchling to
infer the platform tag from the current Python interpreter.

It also dynamically handles the exclude list: .py source files are only
excluded when their compiled counterpart (.pyd on Windows, .so elsewhere)
actually exists. If the compiled extension is missing, the .py source is
force-included back into the wheel so it doesn't ship empty modules.
"""

from __future__ import annotations

import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

# .py files that are expected to be compiled to Cython extensions.
# Listed relative to the repo root — must match pyproject.toml
# [tool.hatch.build.targets.wheel] exclude.
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

        # For each statically-excluded .py file, check whether a compiled
        # extension actually exists.  If not, force-include the .py source
        # back into the wheel so it doesn't ship with a missing module.
        force_include = dict(build_data.get("force_include", {}))

        for src in COMPILED_SOURCES:
            if _has_compiled(src, root):
                has_any_compiled = True
            else:
                # No compiled extension — re-add the .py source
                src_path = root / src
                if src_path.exists():
                    force_include[str(src_path)] = src

        build_data["force_include"] = force_include

        if has_any_compiled:
            # Platform-specific wheel with compiled extensions
            build_data["pure_python"] = False
            build_data["infer_tag"] = True
