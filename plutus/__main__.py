"""Allow running plutus as `python -m plutus`.

On Windows, also detects if the Scripts directory (where pip places
``plutus.exe``) is missing from PATH and offers to fix it automatically.
"""

from __future__ import annotations

import os
import sys


def _ensure_windows_path() -> None:
    """On Windows, check that the user-scripts dir is on PATH.

    pip installs console-script entry points into a ``Scripts/`` directory
    that is often *not* on the user's PATH (especially for ``--user``
    installs).  When that happens, ``plutus start`` fails with
    "not recognized as a cmdlet".

    This helper detects the situation and adds the directory to the user's
    persistent PATH so that future terminal sessions just work.
    """
    if sys.platform != "win32":
        return

    import shutil

    # If `plutus` is already findable on PATH, nothing to do.
    if shutil.which("plutus") is not None:
        return

    # Locate the Scripts dir that contains plutus.exe
    from pathlib import Path

    candidates = [
        # --user install: %APPDATA%\Python\Python3XX\Scripts
        Path(os.environ.get("APPDATA", ""))
        / "Python"
        / f"Python{sys.version_info[0]}{sys.version_info[1]}"
        / "Scripts",
        # System install: same dir as python.exe\Scripts
        Path(sys.executable).parent / "Scripts",
    ]

    scripts_dir: Path | None = None
    for candidate in candidates:
        if (candidate / "plutus.exe").exists():
            scripts_dir = candidate
            break

    if scripts_dir is None:
        return

    scripts_str = str(scripts_dir)

    # Check if already in user PATH (even if current session doesn't see it)
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Environment",
            0,
            winreg.KEY_READ,
        ) as key:
            current_path, _ = winreg.QueryValueEx(key, "Path")
    except (OSError, FileNotFoundError):
        current_path = ""

    # Normalise for comparison
    path_entries = [p.strip().rstrip("\\").lower() for p in current_path.split(";") if p.strip()]
    if scripts_str.rstrip("\\").lower() in path_entries:
        # Already registered but the current terminal session is stale.
        print(
            f"\n  Note: '{scripts_str}' is already in your PATH.\n"
            "  Please restart your terminal for the 'plutus' command to work.\n"
        )
        return

    # Offer to add it
    print(
        f"\n  The 'plutus' command was not found on your PATH.\n"
        f"  The executable is at: {scripts_str}\\plutus.exe\n"
    )
    try:
        answer = input("  Add this directory to your PATH automatically? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"

    if answer in ("", "y", "yes"):
        try:
            import winreg

            new_path = f"{current_path};{scripts_str}" if current_path else scripts_str

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Environment",
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)

            # Broadcast WM_SETTINGCHANGE so new terminals pick it up
            try:
                import ctypes

                ctypes.windll.user32.SendMessageTimeoutW(
                    0xFFFF, 0x001A, 0,  # HWND_BROADCAST, WM_SETTINGCHANGE
                    "Environment", 0x0002, 5000, None,  # SMTO_ABORTIFHUNG
                )
            except Exception:
                pass

            # Also add to current process PATH so this session works
            os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + scripts_str

            print(
                f"\n  Added '{scripts_str}' to your user PATH.\n"
                "  Restart your terminal, then 'plutus start' will work directly.\n"
                "  For now, 'python -m plutus start' works immediately.\n"
            )
        except OSError as exc:
            print(f"\n  Could not update PATH automatically: {exc}")
            print(f"  Please add this directory to your PATH manually:\n    {scripts_str}\n")
    else:
        print(
            f"\n  Skipped. You can always run Plutus with:\n"
            f"    python -m plutus start\n"
            f"\n  Or add this to your PATH manually:\n"
            f"    {scripts_str}\n"
        )


if __name__ == "__main__":
    _ensure_windows_path()

    from plutus.cli import main

    main()
