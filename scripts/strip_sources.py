#!/usr/bin/env python3
"""Strip .py source files for modules that have been compiled to .so/.pyd.

Run this AFTER `python build_compiled.py build_ext --inplace` and BEFORE
`python -m build` to ensure the wheel only contains compiled binaries
for protected modules (not the readable .py source).

Usage:
    python scripts/strip_sources.py          # dry-run (shows what would be deleted)
    python scripts/strip_sources.py --apply  # actually delete the .py files
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Must match the list in build_compiled.py
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


def find_compiled(source_path: Path) -> Path | None:
    """Find the compiled .so or .pyd file corresponding to a .py source."""
    parent = source_path.parent
    stem = source_path.stem  # e.g. "agent"

    # Cython produces files like: agent.cpython-311-x86_64-linux-gnu.so
    for ext_file in parent.iterdir():
        if ext_file.stem.startswith(stem + ".cpython") or ext_file.stem == stem:
            if ext_file.suffix in (".so", ".pyd"):
                return ext_file
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Strip .py source for compiled modules")
    parser.add_argument(
        "--apply", action="store_true", help="Actually delete files (default is dry-run)"
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    stripped = 0
    missing_compiled = 0

    for rel_path in PROTECTED_MODULES:
        source = root / rel_path
        if not source.exists():
            continue

        compiled = find_compiled(source)
        if compiled is None:
            print(f"  WARNING: No compiled binary found for {rel_path} — skipping")
            missing_compiled += 1
            continue

        if args.apply:
            source.unlink()
            # Also remove the .c intermediate file if present
            c_file = source.with_suffix(".c")
            if c_file.exists():
                c_file.unlink()
            print(f"  DELETED: {rel_path}  (compiled: {compiled.name})")
        else:
            print(f"  WOULD DELETE: {rel_path}  (compiled: {compiled.name})")
        stripped += 1

    print()
    if missing_compiled:
        print(f"  {missing_compiled} module(s) missing compiled binaries — run build_compiled.py first")
    if args.apply:
        print(f"  Stripped {stripped} source file(s).")
    else:
        print(f"  Would strip {stripped} source file(s). Run with --apply to delete.")

    if missing_compiled and args.apply:
        sys.exit(1)


if __name__ == "__main__":
    main()
