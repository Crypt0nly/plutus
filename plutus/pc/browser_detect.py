"""Cross-platform browser detection for Plutus.

Scans the user's machine for installed Chromium-family browsers (Chrome, Brave,
Edge, Vivaldi, Opera, Arc, Chromium, Canary) and returns a ranked list so the
user can pick which one Plutus should connect to via CDP.

Ported from OpenClaw's chrome.executables.ts with Python-idiomatic adjustments.

SAFETY NOTE (Windows):
  This module must NEVER launch arbitrary executables to probe them.  The old
  ``_is_chromium_exe`` helper ran unknown .exe files with ``--version``, which
  caused MS Teams, PowerPoint, PowerShell and other apps to open whenever the
  Settings tab was displayed.  All Windows version-reading now uses the Win32
  ``GetFileVersionInfo`` API via ctypes (no subprocess), and unknown executables
  are identified exclusively by filesystem markers (chrome.dll, *.pak files),
  never by executing them.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("plutus.pc.browser_detect")

# ──────────────────────────────────────────────────────────────────────────────
# Data types
# ──────────────────────────────────────────────────────────────────────────────

BROWSER_KINDS = ("chrome", "brave", "edge", "canary", "chromium", "vivaldi", "opera", "arc", "custom")


@dataclass
class BrowserInfo:
    kind: str          # one of BROWSER_KINDS
    name: str          # human-readable display name, e.g. "Google Chrome"
    path: str          # absolute path to the executable
    version: str = ""  # e.g. "120.0.6099.130"
    is_default: bool = False  # True if this is the OS default browser


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _exists(p: str) -> bool:
    try:
        return Path(p).exists()
    except Exception:
        return False


def _exec_text(cmd: list[str], timeout: float = 2.0) -> Optional[str]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _infer_kind(identifier: str) -> str:
    s = identifier.lower()
    if "brave" in s:
        return "brave"
    if "edge" in s or "msedge" in s:
        return "edge"
    if "canary" in s or "sxs" in s:
        return "canary"
    if "arc" in s or "thebrowser" in s:
        return "arc"
    if "vivaldi" in s:
        return "vivaldi"
    if "opera" in s:
        return "opera"
    if "chromium" in s:
        return "chromium"
    return "chrome"


def _display_name(kind: str, raw: str = "") -> str:
    mapping = {
        "chrome": "Google Chrome",
        "brave": "Brave Browser",
        "edge": "Microsoft Edge",
        "canary": "Google Chrome Canary",
        "chromium": "Chromium",
        "vivaldi": "Vivaldi",
        "opera": "Opera",
        "arc": "Arc",
        "custom": "Custom Browser",
    }
    return mapping.get(kind, raw or kind.title())


def _get_version_mac(exe_path: str) -> str:
    """Read CFBundleShortVersionString from the .app bundle."""
    try:
        app_dir = Path(exe_path)
        # Walk up to find the .app bundle
        for parent in app_dir.parents:
            if parent.suffix == ".app":
                plist = parent / "Contents" / "Info.plist"
                if plist.exists():
                    out = _exec_text(
                        ["/usr/bin/defaults", "read", str(plist), "CFBundleShortVersionString"]
                    )
                    return out or ""
                break
    except Exception:
        pass
    return ""


def _get_version_unix(exe_path: str) -> str:
    out = _exec_text([exe_path, "--version"], timeout=3.0)
    if out:
        # "Google Chrome 120.0.6099.130" → "120.0.6099.130"
        parts = out.split()
        for part in reversed(parts):
            if part[0].isdigit():
                return part
    return ""


def _get_version_windows(exe_path: str) -> str:
    """Read the file version from a Windows PE executable using ctypes.

    This uses the Win32 GetFileVersionInfo API directly — no subprocess, no
    PowerShell, no external process is launched.
    """
    try:
        import ctypes
        import ctypes.wintypes  # type: ignore[import]

        ver_dll = ctypes.windll.version  # type: ignore[attr-defined]

        # GetFileVersionInfoSizeW returns the required buffer size (0 on failure)
        size = ver_dll.GetFileVersionInfoSizeW(exe_path, None)
        if not size:
            return ""

        buf = ctypes.create_string_buffer(size)
        if not ver_dll.GetFileVersionInfoW(exe_path, 0, size, buf):
            return ""

        # VerQueryValueW with path "\\" returns a pointer to VS_FIXEDFILEINFO
        p_info = ctypes.c_void_p()
        n_info = ctypes.c_uint(0)
        if not ver_dll.VerQueryValueW(buf, "\\", ctypes.byref(p_info), ctypes.byref(n_info)):
            return ""

        class _FIXEDFILEINFO(ctypes.Structure):
            _fields_ = [
                ("dwSignature",        ctypes.c_uint32),
                ("dwStrucVersion",     ctypes.c_uint32),
                ("dwFileVersionMS",    ctypes.c_uint32),
                ("dwFileVersionLS",    ctypes.c_uint32),
                ("dwProductVersionMS", ctypes.c_uint32),
                ("dwProductVersionLS", ctypes.c_uint32),
            ]

        info = ctypes.cast(p_info, ctypes.POINTER(_FIXEDFILEINFO)).contents
        ms = info.dwFileVersionMS
        ls = info.dwFileVersionLS
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except Exception:
        return ""


def _get_exe_display_name_windows(exe_path: str) -> str:
    """Read the FileDescription from a Windows PE using ctypes.

    Falls back to a prettified stem name.  No subprocess is launched.
    """
    try:
        import ctypes
        import ctypes.wintypes  # type: ignore[import]

        ver_dll = ctypes.windll.version  # type: ignore[attr-defined]

        size = ver_dll.GetFileVersionInfoSizeW(exe_path, None)
        if not size:
            raise ValueError("no version info")

        buf = ctypes.create_string_buffer(size)
        if not ver_dll.GetFileVersionInfoW(exe_path, 0, size, buf):
            raise ValueError("GetFileVersionInfoW failed")

        # Query the string table for FileDescription.
        # We need to find the language/codepage first via \VarFileInfo\Translation
        p_trans = ctypes.c_void_p()
        n_trans = ctypes.c_uint(0)
        if ver_dll.VerQueryValueW(buf, r"\VarFileInfo\Translation",
                                   ctypes.byref(p_trans), ctypes.byref(n_trans)):
            # First translation entry: LOWORD=language, HIWORD=codepage
            lang_cp = ctypes.cast(p_trans, ctypes.POINTER(ctypes.c_uint32)).contents.value
            lang = lang_cp & 0xFFFF
            cp   = (lang_cp >> 16) & 0xFFFF
            sub_block = f"\\StringFileInfo\\{lang:04X}{cp:04X}\\FileDescription"
        else:
            # Fallback: English US + Unicode
            sub_block = r"\StringFileInfo\040904B0\FileDescription"

        p_desc = ctypes.c_void_p()
        n_desc = ctypes.c_uint(0)
        if ver_dll.VerQueryValueW(buf, sub_block, ctypes.byref(p_desc), ctypes.byref(n_desc)):
            desc = ctypes.wstring_at(p_desc.value)  # type: ignore[arg-type]
            if desc and desc.strip():
                return desc.strip()
    except Exception:
        pass

    return Path(exe_path).stem.replace("-", " ").replace("_", " ").title()


# ──────────────────────────────────────────────────────────────────────────────
# macOS detection
# ──────────────────────────────────────────────────────────────────────────────

# macOS bundle IDs for Chromium-family browsers
_MAC_BUNDLE_IDS: list[tuple[str, str]] = [
    ("com.google.Chrome",                "chrome"),
    ("com.google.Chrome.canary",         "canary"),
    ("com.google.Chrome.beta",           "chrome"),
    ("com.google.Chrome.dev",            "chrome"),
    ("com.brave.Browser",                "brave"),
    ("com.brave.Browser.beta",           "brave"),
    ("com.brave.Browser.nightly",        "brave"),
    ("com.microsoft.Edge",               "edge"),
    ("com.microsoft.EdgeBeta",           "edge"),
    ("com.microsoft.EdgeDev",            "edge"),
    ("com.microsoft.EdgeCanary",         "edge"),
    ("org.chromium.Chromium",            "chromium"),
    ("com.vivaldi.Vivaldi",              "vivaldi"),
    ("com.operasoftware.Opera",          "opera"),
    ("com.operasoftware.OperaGX",        "opera"),
    ("com.yandex.desktop.yandex-browser","chromium"),
    ("company.thebrowser.Browser",       "arc"),
]

# Well-known install paths on macOS (fallback when bundle ID lookup fails)
_MAC_PATHS: list[tuple[str, str]] = [
    ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",         "chrome"),
    ("/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary", "canary"),
    ("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",         "brave"),
    ("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",       "edge"),
    ("/Applications/Chromium.app/Contents/MacOS/Chromium",                   "chromium"),
    ("/Applications/Vivaldi.app/Contents/MacOS/Vivaldi",                     "vivaldi"),
    ("/Applications/Opera.app/Contents/MacOS/Opera",                         "opera"),
    ("/Applications/Arc.app/Contents/MacOS/Arc",                             "arc"),
]


def _detect_default_browser_mac() -> Optional[str]:
    """Return the bundle ID of the macOS default browser, or None."""
    import plistlib
    plist_path = (
        Path.home()
        / "Library/Preferences/com.apple.LaunchServices/com.apple.launchservices.secure.plist"
    )
    if not plist_path.exists():
        return None
    try:
        raw = _exec_text(
            ["/usr/bin/plutil", "-extract", "LSHandlers", "json", "-o", "-", "--", str(plist_path)],
            timeout=3.0,
        )
        if not raw:
            return None
        import json
        handlers = json.loads(raw)
        for scheme in ("https", "http"):
            for entry in handlers:
                if not isinstance(entry, dict):
                    continue
                if entry.get("LSHandlerURLScheme") != scheme:
                    continue
                role = entry.get("LSHandlerRoleAll") or entry.get("LSHandlerRoleViewer")
                if role:
                    return role
    except Exception:
        pass
    return None


def _exe_from_bundle_id(bundle_id: str) -> Optional[str]:
    app_path_raw = _exec_text(
        ["/usr/bin/osascript", "-e", f'POSIX path of (path to application id "{bundle_id}")'],
        timeout=3.0,
    )
    if not app_path_raw:
        return None
    app_path = app_path_raw.strip().rstrip("/")
    exe_name = _exec_text(
        ["/usr/bin/defaults", "read", f"{app_path}/Contents/Info", "CFBundleExecutable"],
        timeout=2.0,
    )
    if not exe_name:
        return None
    exe = f"{app_path}/Contents/MacOS/{exe_name.strip()}"
    return exe if _exists(exe) else None


def _scan_mac() -> list[BrowserInfo]:
    results: list[BrowserInfo] = []
    seen: set[str] = set()
    default_bundle = _detect_default_browser_mac()

    # 1. Iterate known bundle IDs
    for bundle_id, kind in _MAC_BUNDLE_IDS:
        exe = _exe_from_bundle_id(bundle_id)
        if exe and exe not in seen:
            seen.add(exe)
            version = _get_version_mac(exe)
            is_default = (bundle_id == default_bundle)
            results.append(BrowserInfo(
                kind=kind,
                name=_display_name(kind),
                path=exe,
                version=version,
                is_default=is_default,
            ))

    # 2. Fallback: well-known paths
    for path, kind in _MAC_PATHS:
        if _exists(path) and path not in seen:
            seen.add(path)
            version = _get_version_mac(path)
            results.append(BrowserInfo(
                kind=kind,
                name=_display_name(kind),
                path=path,
                version=version,
            ))

    return results


# ──────────────────────────────────────────────────────────────────────────────
# Windows detection
# ──────────────────────────────────────────────────────────────────────────────

# Registry App Paths keys for known Chromium browsers only
_WIN_REGISTRY_PATHS = [
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\brave.exe",
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\vivaldi.exe",
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\opera.exe",
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chromium.exe",
]

_WIN_KNOWN_PATHS: list[tuple[str, str]] = [
    (r"C:\Program Files\Google\Chrome\Application\chrome.exe",                "chrome"),
    (r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",          "chrome"),
    (r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",   "brave"),
    (r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe", "brave"),
    (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",         "edge"),
    (r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",               "edge"),
    (r"C:\Program Files\Vivaldi\Application\vivaldi.exe",                     "vivaldi"),
    (r"C:\Program Files\Opera\launcher.exe",                                  "opera"),
    (r"C:\Program Files\Opera GX\launcher.exe",                               "opera"),
]

# LocalAppData paths (user-level installs)
_WIN_LOCAL_APPDATA_PATHS: list[tuple[str, str]] = [
    (r"Google\Chrome\Application\chrome.exe",                                 "chrome"),
    (r"Google\Chrome SxS\Application\chrome.exe",                             "canary"),
    (r"BraveSoftware\Brave-Browser\Application\brave.exe",                    "brave"),
    (r"Microsoft\Edge\Application\msedge.exe",                                "edge"),
    (r"Vivaldi\Application\vivaldi.exe",                                      "vivaldi"),
]

# Allowlist of exe stems that are definitively known Chromium browsers.
# The registry scan will ONLY add executables whose stem appears in this set
# (or whose _infer_kind() returns a non-"chrome" kind, meaning the name itself
# is a known browser name).  Unknown stems are skipped — we never execute them.
_WIN_KNOWN_BROWSER_STEMS: frozenset[str] = frozenset({
    "chrome", "chrome_proxy",
    "msedge", "microsoftedge",
    "brave", "brave-browser",
    "vivaldi",
    "opera", "opera_gx_stable", "launcher",
    "chromium", "chromium-browser",
    "canary",
    "comet",          # Perplexity's Chromium fork
    "arc",
    "yandex",
    "coccoc",         # Vietnamese Chromium fork
    "whale",          # Naver Whale
    "naver",
    "cent",           # CentBrowser
    "slimjet",
    "iridium",
    "ungoogled",
})


def _read_registry_value(key_path: str) -> Optional[str]:
    try:
        import winreg  # type: ignore[import]
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, key_path) as k:
                    val, _ = winreg.QueryValueEx(k, "")
                    return str(val)
            except OSError:
                continue
    except ImportError:
        pass
    return None


def _is_chromium_dir(app_dir: Path) -> bool:
    """Return True if *app_dir* contains the filesystem markers of a Chromium build.

    This is a pure filesystem check — no executable is launched.
    Chromium builds always ship with chrome.dll and at least one .pak file.
    """
    chromium_markers = {
        "chrome.dll",
        "chrome_100_percent.pak",
        "chrome_200_percent.pak",
        "resources.pak",
        "icudtl.dat",
    }
    try:
        files_here = {f.name.lower() for f in app_dir.iterdir() if f.is_file()}
        return bool(chromium_markers.intersection(files_here))
    except Exception:
        return False


def _scan_windows_registry_app_paths() -> list[tuple[str, str]]:
    """Scan App Paths registry entries, returning only known-browser exe names."""
    found: list[tuple[str, str]] = []
    try:
        import winreg  # type: ignore[import]
        base = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, base) as root:
                    i = 0
                    while True:
                        try:
                            sub_name = winreg.EnumKey(root, i)
                            i += 1
                            if not sub_name.lower().endswith(".exe"):
                                continue
                            # Only process exe names that are known browser stems
                            stem = Path(sub_name).stem.lower()
                            if stem not in _WIN_KNOWN_BROWSER_STEMS and _infer_kind(stem) == "chrome":
                                # Unknown name that doesn't match any known browser pattern → skip
                                continue
                            try:
                                with winreg.OpenKey(root, sub_name) as sub:
                                    val, _ = winreg.QueryValueEx(sub, "")
                                    exe = str(val).strip('"')
                                    found.append((exe, sub_name))
                            except OSError:
                                pass
                        except OSError:
                            break
            except OSError:
                continue
    except ImportError:
        pass
    return found


def _scan_windows_default_browser() -> Optional[str]:
    """Return the executable path of the Windows default browser."""
    try:
        import winreg  # type: ignore[import]
        # Read ProgId for https scheme
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive,
                    r"SOFTWARE\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice") as k:
                    prog_id, _ = winreg.QueryValueEx(k, "ProgId")
                    # Resolve ProgId to exe
                    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                        f"{prog_id}\\shell\\open\\command") as cmd_key:
                        cmd, _ = winreg.QueryValueEx(cmd_key, "")
                        # cmd looks like: "C:\...\chrome.exe" -- "%1"
                        import re
                        m = re.match(r'"?([^"]+\.exe)"?', cmd.strip())
                        if m:
                            return m.group(1)
            except OSError:
                continue
    except ImportError:
        pass
    return None


def _scan_windows() -> list[BrowserInfo]:
    results: list[BrowserInfo] = []
    seen: set[str] = set()
    default_exe = _scan_windows_default_browser()

    def _add(exe: str, kind: Optional[str] = None, name: Optional[str] = None):
        """Add a browser to results if not already seen."""
        norm = exe.lower()
        if norm in seen or not _exists(exe):
            return
        seen.add(norm)
        k = kind or _infer_kind(exe)
        n = name or _display_name(k, Path(exe).stem)
        version = _get_version_windows(exe)
        is_default = bool(default_exe and Path(default_exe).resolve() == Path(exe).resolve())
        results.append(BrowserInfo(kind=k, name=n, path=exe, version=version, is_default=is_default))

    # 1. Windows default browser
    if default_exe:
        _add(default_exe)

    # 2. Hardcoded registry App Paths (fast, reliable for known browsers)
    for reg_path in _WIN_REGISTRY_PATHS:
        exe = _read_registry_value(reg_path)
        if exe:
            _add(exe.strip('"'))

    # 3. Scan App Paths registry entries — filtered to known browser stems only
    #    (no unknown executables are ever launched)
    for exe, sub_name in _scan_windows_registry_app_paths():
        if not exe:
            continue
        exe = exe.strip('"')
        if _exists(exe):
            kind = _infer_kind(exe)
            n = _display_name(kind, Path(exe).stem)
            _add(exe, kind, n)

    # 4. Well-known Program Files paths
    for path, kind in _WIN_KNOWN_PATHS:
        _add(path, kind)

    # 5. LocalAppData (user installs)
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if local_appdata:
        for rel, kind in _WIN_LOCAL_APPDATA_PATHS:
            _add(os.path.join(local_appdata, rel), kind)

    # 6. Filesystem scan: look for Chromium builds in common install dirs.
    #    Identification is done ONLY by filesystem markers (chrome.dll, *.pak),
    #    never by executing the binary.
    scan_roots = [
        os.environ.get("PROGRAMFILES", r"C:\Program Files"),
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
        local_appdata,
        os.path.join(os.environ.get("APPDATA", ""), "..", "Local"),
    ]
    for root_dir in scan_roots:
        if not root_dir:
            continue
        try:
            root_path = Path(root_dir).resolve()
            if not root_path.exists():
                continue
            # Walk one level deep into each top-level directory
            for vendor_dir in root_path.iterdir():
                if not vendor_dir.is_dir():
                    continue
                # Look for Application subdirectory (standard Chromium layout)
                for app_dir in [vendor_dir / "Application", vendor_dir]:
                    if not app_dir.is_dir():
                        continue
                    # Check if this looks like a Chromium app dir via filesystem markers
                    if not _is_chromium_dir(app_dir):
                        continue
                    # Find the main exe — only add it, never execute it
                    for f in app_dir.iterdir():
                        if f.suffix.lower() != ".exe":
                            continue
                        stem = f.stem.lower()
                        # Skip helper/installer exes
                        if any(x in stem for x in ("setup", "install", "update", "helper",
                                                     "crash", "uninstall", "elevation",
                                                     "notification", "recovery")):
                            continue
                        exe = str(f)
                        if exe.lower() not in seen:
                            kind = _infer_kind(exe)
                            # Use ctypes-based display name (no subprocess)
                            name = _get_exe_display_name_windows(exe)
                            _add(exe, kind if kind != "chrome" else "custom", name)
        except Exception:
            continue

    return results


# ──────────────────────────────────────────────────────────────────────────────
# Linux detection
# ──────────────────────────────────────────────────────────────────────────────

_LINUX_DESKTOP_IDS: list[tuple[str, str]] = [
    ("google-chrome.desktop",              "chrome"),
    ("google-chrome-beta.desktop",         "chrome"),
    ("google-chrome-unstable.desktop",     "chrome"),
    ("brave-browser.desktop",              "brave"),
    ("microsoft-edge.desktop",             "edge"),
    ("microsoft-edge-beta.desktop",        "edge"),
    ("microsoft-edge-dev.desktop",         "edge"),
    ("microsoft-edge-canary.desktop",      "edge"),
    ("chromium.desktop",                   "chromium"),
    ("chromium-browser.desktop",           "chromium"),
    ("vivaldi.desktop",                    "vivaldi"),
    ("vivaldi-stable.desktop",             "vivaldi"),
    ("opera.desktop",                      "opera"),
    ("opera-gx.desktop",                   "opera"),
    ("org.chromium.Chromium.desktop",      "chromium"),
]

_LINUX_EXECUTABLES: list[tuple[str, str]] = [
    ("google-chrome",          "chrome"),
    ("google-chrome-stable",   "chrome"),
    ("google-chrome-beta",     "chrome"),
    ("google-chrome-unstable", "chrome"),
    ("brave-browser",          "brave"),
    ("brave",                  "brave"),
    ("microsoft-edge",         "edge"),
    ("microsoft-edge-beta",    "edge"),
    ("microsoft-edge-dev",     "edge"),
    ("chromium",               "chromium"),
    ("chromium-browser",       "chromium"),
    ("vivaldi",                "vivaldi"),
    ("vivaldi-stable",         "vivaldi"),
    ("opera",                  "opera"),
    ("opera-stable",           "opera"),
]


def _which(cmd: str) -> Optional[str]:
    out = _exec_text(["which", cmd], timeout=2.0)
    return out if out and _exists(out) else None


def _scan_linux() -> list[BrowserInfo]:
    results: list[BrowserInfo] = []
    seen: set[str] = set()

    # 1. xdg default browser
    default_desktop = (
        _exec_text(["xdg-settings", "get", "default-web-browser"])
        or _exec_text(["xdg-mime", "query", "default", "x-scheme-handler/http"])
    )

    # 2. Scan .desktop files
    desktop_dirs = [
        Path.home() / ".local/share/applications",
        Path("/usr/local/share/applications"),
        Path("/usr/share/applications"),
        Path("/var/lib/snapd/desktop/applications"),
    ]

    for desktop_id, kind in _LINUX_DESKTOP_IDS:
        for d in desktop_dirs:
            desktop_file = d / desktop_id
            if not desktop_file.exists():
                continue
            try:
                content = desktop_file.read_text(errors="replace")
                exec_line = None
                for line in content.splitlines():
                    if line.startswith("Exec="):
                        exec_line = line[5:].strip()
                        break
                if not exec_line:
                    continue
                # Extract the executable (first token, strip %u/%f etc.)
                exe_token = exec_line.split()[0].strip('"\'')
                # Resolve to absolute path
                if not exe_token.startswith("/"):
                    exe_token = _which(exe_token) or exe_token
                if _exists(exe_token) and exe_token not in seen:
                    seen.add(exe_token)
                    version = _get_version_unix(exe_token)
                    is_default = (desktop_id == default_desktop)
                    results.append(BrowserInfo(
                        kind=kind,
                        name=_display_name(kind),
                        path=exe_token,
                        version=version,
                        is_default=is_default,
                    ))
            except Exception:
                continue
            break  # found in this dir, skip remaining dirs

    # 3. Fallback: scan PATH for known executables
    for exe_name, kind in _LINUX_EXECUTABLES:
        resolved = _which(exe_name)
        if resolved and resolved not in seen:
            seen.add(resolved)
            version = _get_version_unix(resolved)
            results.append(BrowserInfo(kind=kind, name=_display_name(kind), path=resolved, version=version))

    return results


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def detect_browsers() -> list[BrowserInfo]:
    """Return all detected Chromium-family browsers on the current machine.

    Results are sorted: default browser first, then by kind priority
    (chrome > brave > edge > chromium > others).
    """
    system = platform.system()
    try:
        if system == "Darwin":
            browsers = _scan_mac()
        elif system == "Windows":
            browsers = _scan_windows()
        elif system == "Linux":
            browsers = _scan_linux()
        else:
            browsers = []
    except Exception as e:
        logger.warning(f"Browser detection failed: {e}")
        browsers = []

    # Sort: default first, then by kind priority
    kind_priority = {"chrome": 0, "brave": 1, "edge": 2, "canary": 3,
                     "chromium": 4, "vivaldi": 5, "opera": 6, "arc": 7, "custom": 99}
    browsers.sort(key=lambda b: (0 if b.is_default else 1, kind_priority.get(b.kind, 50)))
    return browsers


def get_browser_launch_args(browser_path: str, debug_port: int = 9222) -> list[str]:
    """Return the CLI args needed to launch a browser with CDP enabled.

    The caller is responsible for actually spawning the process.
    """
    return [
        browser_path,
        f"--remote-debugging-port={debug_port}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        # Use a separate profile so the debug session doesn't interfere with
        # the user's normal browsing — but still inherits their default profile
        # data via the user-data-dir below.
    ]


def get_user_data_dir(browser_path: str) -> Optional[str]:
    """Return the default user-data-dir for the given browser executable path,
    so Plutus can inherit the user's existing logins and cookies."""
    system = platform.system()
    home = Path.home()
    p = browser_path.lower()

    if system == "Darwin":
        if "brave" in p:
            d = home / "Library/Application Support/BraveSoftware/Brave-Browser"
        elif "edge" in p or "msedge" in p:
            d = home / "Library/Application Support/Microsoft Edge"
        elif "vivaldi" in p:
            d = home / "Library/Application Support/Vivaldi"
        elif "opera" in p:
            d = home / "Library/Application Support/com.operasoftware.Opera"
        elif "chromium" in p:
            d = home / "Library/Application Support/Chromium"
        else:
            d = home / "Library/Application Support/Google/Chrome"

    elif system == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local"))
        if "brave" in p:
            d = local / "BraveSoftware/Brave-Browser/User Data"
        elif "msedge" in p or "edge" in p:
            d = local / "Microsoft/Edge/User Data"
        elif "vivaldi" in p:
            d = local / "Vivaldi/User Data"
        elif "opera" in p:
            d = local / "Programs/Opera/User Data"
        elif "chromium" in p:
            d = local / "Chromium/User Data"
        else:
            d = local / "Google/Chrome/User Data"

    elif system == "Linux":
        if "brave" in p:
            d = home / ".config/BraveSoftware/Brave-Browser"
        elif "edge" in p or "msedge" in p:
            d = home / ".config/microsoft-edge"
        elif "vivaldi" in p:
            d = home / ".config/vivaldi"
        elif "opera" in p:
            d = home / ".config/opera"
        elif "chromium" in p:
            d = home / ".config/chromium"
        else:
            d = home / ".config/google-chrome"
    else:
        return None

    return str(d) if d.exists() else None
