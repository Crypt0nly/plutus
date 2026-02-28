"""Custom hatch build hook to generate platform-specific wheels.

When compiled Cython extensions (.so/.pyd) are present, hatchling must
produce a platform wheel (e.g. cp311-cp311-macosx_11_0_arm64) instead
of a pure-python wheel (py3-none-any). This hook tells hatchling to
infer the platform tag from the current Python interpreter.
"""

from __future__ import annotations

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        # Force platform-specific wheel — required because we include
        # pre-compiled Cython .so/.pyd extensions via artifacts
        build_data["pure_python"] = False
        build_data["infer_tag"] = True
