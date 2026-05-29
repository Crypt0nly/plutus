#!/usr/bin/env python3
"""Check whether a PyPI project has enough remaining storage for dist files.

The publish workflow uses this as a defensive preflight before invoking PyPI's
upload endpoint. PyPI rejects uploads once the project storage cap is reached,
and the upload action can fail after partially uploading a release. This helper
uses the public JSON API to estimate current project usage, compares it with the
local wheel payload, and emits GitHub Actions outputs.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

DEFAULT_PYPI_PROJECT_LIMIT_BYTES = 10 * 1024**3


def _write_output(name: str, value: str | int | bool) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    normalized = str(value).lower() if isinstance(value, bool) else str(value)
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output_file:
            output_file.write(f"{name}={normalized}\n")
    print(f"{name}={normalized}")


def _release_file_size(project: str) -> int:
    url = f"https://pypi.org/pypi/{project}/json"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)

    return sum(
        int(file_info.get("size") or 0)
        for release_files in payload.get("releases", {}).values()
        for file_info in release_files
    )


def _dist_file_size(dist_dir: pathlib.Path) -> int:
    return sum(path.stat().st_size for path in dist_dir.glob("*") if path.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="PyPI project name, e.g. plutus-ai")
    parser.add_argument("--dist-dir", default="dist", help="Directory containing files to upload")
    parser.add_argument(
        "--limit-bytes",
        type=int,
        default=DEFAULT_PYPI_PROJECT_LIMIT_BYTES,
        help="Project storage limit in bytes; PyPI's default is 10 GiB",
    )
    args = parser.parse_args()

    dist_dir = pathlib.Path(args.dist_dir)
    upload_size = _dist_file_size(dist_dir)

    try:
        current_size = _release_file_size(args.project)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        # If PyPI's metadata endpoint is unavailable, do not block publishing.
        # The real upload step remains authoritative and will report any issue.
        _write_output("can_publish", True)
        _write_output("current_size_bytes", 0)
        _write_output("upload_size_bytes", upload_size)
        _write_output("remaining_bytes", args.limit_bytes)
        _write_output("reason", f"storage check unavailable: {exc}")
        return 0

    remaining = args.limit_bytes - current_size
    can_publish = upload_size <= remaining
    reason = (
        f"PyPI has enough storage headroom: upload={upload_size} remaining={remaining}"
        if can_publish
        else f"PyPI storage headroom is insufficient: upload={upload_size} remaining={remaining}"
    )

    _write_output("can_publish", can_publish)
    _write_output("current_size_bytes", current_size)
    _write_output("upload_size_bytes", upload_size)
    _write_output("remaining_bytes", remaining)
    _write_output("reason", reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
