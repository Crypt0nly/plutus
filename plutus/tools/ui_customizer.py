"""UI Customization tool — lets the agent fully restyle and restructure the Plutus frontend.

Architecture:
  Plutus's frontend uses CSS variables for all colors, surfaces, and component styles.
  The sidebar navigation is data-driven from a JSON config.  This tool writes:

    ~/.plutus/customization/custom-theme.css   — CSS variable overrides + custom styles
    ~/.plutus/customization/ui-config.json     — layout config (sidebar order, labels, visibility)

  The frontend loads these at startup via /api/customization/* endpoints and applies
  them dynamically — no rebuild, no Node.js, instant effect on page refresh.

Operations:
  - set_theme:      Override CSS variables (colors, fonts, spacing, shadows)
  - set_layout:     Configure sidebar sections, item order, visibility, labels
  - inject_css:     Write arbitrary CSS for advanced design changes
  - get_current:    Read the current customization state
  - reset:          Remove all customizations and restore defaults
  - list_variables: Show all available CSS variables and their current defaults
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from plutus.tools.base import Tool

logger = logging.getLogger("plutus.tools.ui_customizer")

# ── Customization directory ──────────────────────────────────────────────────

def _customization_dir() -> Path:
    d = Path.home() / ".plutus" / "customization"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _theme_css_path() -> Path:
    return _customization_dir() / "custom-theme.css"


def _ui_config_path() -> Path:
    return _customization_dir() / "ui-config.json"


# ── Default CSS variables (for reference) ────────────────────────────────────

DEFAULT_DARK_VARIABLES = {
    # Gray scale (text/surface)
    "--gray-50": "249 250 251",
    "--gray-100": "243 244 246",
    "--gray-200": "229 231 235",
    "--gray-300": "209 213 219",
    "--gray-400": "156 163 175",
    "--gray-500": "107 114 128",
    "--gray-600": "75 85 99",
    "--gray-700": "55 65 81",
    "--gray-800": "31 41 55",
    "--gray-900": "15 18 30",
    "--gray-950": "8 10 20",
    # Surfaces
    "--surface": "15 18 30",
    "--surface-alt": "11 13 24",
    "--surface-deep": "8 10 20",
    # Brand color
    "--plutus-rgb": "99 102 241",
    # Sidebar
    "--sidebar-bg-from": "10 12 22",
    "--sidebar-bg-to": "8 10 20",
    "--sidebar-border": "rgba(255,255,255,0.05)",
    "--sidebar-glow": "rgba(99,102,241,0.08)",
    "--sidebar-divider": "rgba(255,255,255,0.06)",
    "--sidebar-hover": "rgba(255,255,255,0.03)",
    "--sidebar-active-bg-from": "rgba(99,102,241,0.15)",
    "--sidebar-active-bg-to": "rgba(79,70,229,0.08)",
    "--sidebar-active-border": "rgba(99,102,241,0.15)",
    "--sidebar-active-text": "#fff",
    "--sidebar-inactive-text": "#6b7280",
    "--sidebar-inactive-hover": "#d1d5db",
    "--sidebar-section-text": "#4b5563",
    # Chat welcome
    "--welcome-text": "#f3f4f6",
    "--welcome-subtext": "#9ca3af",
    "--welcome-hint": "#4b5563",
    "--prompt-bg": "rgba(255,255,255,0.02)",
    "--prompt-border": "rgba(255,255,255,0.05)",
    "--prompt-hover-bg": "rgba(99,102,241,0.06)",
    "--prompt-hover-border": "rgba(99,102,241,0.15)",
    "--prompt-text": "#6b7280",
    "--prompt-hover-text": "#e5e7eb",
    # Markdown
    "--md-text": "#d1d5db",
    "--md-code-bg": "rgba(15,18,30,0.8)",
    "--md-code-border": "rgba(55,65,81,0.6)",
    "--md-code-text": "#a5b4fc",
    "--md-blockquote-border": "rgba(99,102,241,0.4)",
    "--md-blockquote-bg": "rgba(99,102,241,0.05)",
    "--md-blockquote-text": "#a5b4fc",
    "--md-hr": "rgba(55,65,81,0.5)",
    "--md-link": "#818cf8",
    "--md-heading": "#f9fafb",
}

DEFAULT_LIGHT_VARIABLES = {
    "--gray-50": "15 23 42",
    "--gray-100": "30 41 59",
    "--gray-200": "51 65 85",
    "--gray-300": "71 85 105",
    "--gray-400": "100 116 139",
    "--gray-500": "148 163 184",
    "--gray-600": "203 213 225",
    "--gray-700": "226 232 240",
    "--gray-800": "241 245 249",
    "--gray-900": "248 250 252",
    "--gray-950": "255 255 255",
    "--surface": "248 250 252",
    "--surface-alt": "241 245 249",
    "--surface-deep": "226 232 240",
    "--plutus-rgb": "99 102 241",
}

DEFAULT_LAYOUT = {
    "sections": [
        {
            "label": "Main",
            "collapsible": False,
            "items": [
                {"id": "chat", "label": "Chat", "icon": "MessageSquare", "visible": True},
                {"id": "sessions", "label": "Sessions", "icon": "Layers", "visible": True},
                {"id": "dashboard", "label": "Dashboard", "icon": "LayoutDashboard", "visible": True},
            ],
        },
        {
            "label": "Agent",
            "collapsible": True,
            "items": [
                {"id": "memory", "label": "Memory & Plans", "icon": "Brain", "visible": True},
                {"id": "tools", "label": "Tools", "icon": "Wrench", "visible": True},
                {"id": "workers", "label": "Workers", "icon": "Cpu", "visible": True},
                {"id": "tool-creator", "label": "Tool Creator", "icon": "Sparkles", "visible": True},
                {"id": "skills", "label": "Skills", "icon": "Brain", "visible": True, "badge": "New"},
            ],
        },
        {
            "label": "System",
            "collapsible": True,
            "items": [
                {"id": "connectors", "label": "Connectors", "icon": "Plug", "visible": True, "badge": "New"},
                {"id": "guardrails", "label": "Guardrails", "icon": "Shield", "visible": True},
                {"id": "settings", "label": "Settings", "icon": "Settings", "visible": True},
            ],
        },
    ],
    "sidebar_width": "16rem",
    "sidebar_logo_text": "Plutus",
    "sidebar_show_status": True,
}

# Available Lucide icon names the frontend knows about
AVAILABLE_ICONS = [
    "MessageSquare", "LayoutDashboard", "Shield", "Settings", "Plus",
    "Wrench", "Cpu", "Sparkles", "Brain", "Plug", "Layers",
    "Home", "Star", "Heart", "Zap", "Globe", "Code", "Terminal",
    "Palette", "Music", "Camera", "Video", "Mic", "Bell",
    "Calendar", "Clock", "Map", "Compass", "Bookmark", "Flag",
    "Award", "Target", "TrendingUp", "BarChart", "PieChart",
    "Database", "Server", "Cloud", "Lock", "Unlock", "Key",
    "User", "Users", "Mail", "Send", "Download", "Upload",
    "File", "Folder", "Image", "Monitor", "Smartphone", "Wifi",
]


class UICustomizerTool(Tool):
    """Tool that lets the agent fully customize the Plutus UI at runtime."""

    @property
    def name(self) -> str:
        return "ui_customizer"

    @property
    def description(self) -> str:
        return (
            "Customize the Plutus web interface: change colors, fonts, spacing, "
            "sidebar layout, section order, labels, icons, and visibility. "
            "Changes take effect on page refresh — no rebuild needed.\n\n"
            "Operations:\n"
            "  set_theme     — Override CSS variables (colors, fonts, shadows, spacing)\n"
            "  set_layout    — Configure sidebar sections, item order, visibility, labels, icons\n"
            "  inject_css    — Write arbitrary CSS for advanced design changes\n"
            "  get_current   — Read the current customization state\n"
            "  reset         — Remove all customizations and restore defaults\n"
            "  list_variables — Show all available CSS variables with defaults"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "set_theme",
                        "set_layout",
                        "inject_css",
                        "get_current",
                        "reset",
                        "list_variables",
                    ],
                    "description": "The customization operation to perform",
                },
                "variables": {
                    "type": "object",
                    "description": (
                        "For set_theme: CSS variable overrides as key-value pairs. "
                        "Keys are CSS variable names (e.g. '--gray-950', '--plutus-rgb', "
                        "'--sidebar-active-text'). Values are CSS values. "
                        "Use 'dark' and 'light' top-level keys to target specific themes, "
                        "or set variables at the top level to apply to both."
                    ),
                },
                "layout": {
                    "type": "object",
                    "description": (
                        "For set_layout: sidebar layout configuration. "
                        "Contains 'sections' array with label, collapsible, and items. "
                        "Each item has: id (view name), label, icon (Lucide icon name), "
                        "visible (bool), and optional badge. "
                        "Can also set: sidebar_width, sidebar_logo_text, sidebar_show_status."
                    ),
                },
                "css": {
                    "type": "string",
                    "description": (
                        "For inject_css: raw CSS to inject. This is appended after "
                        "variable overrides, so it can use the custom variables. "
                        "Use this for advanced changes like border-radius, animations, "
                        "font imports, custom component styles, etc."
                    ),
                },
            },
            "required": ["operation"],
        }

    async def execute(self, **kwargs: Any) -> str:
        operation: str = kwargs["operation"]

        handlers = {
            "set_theme": self._set_theme,
            "set_layout": self._set_layout,
            "inject_css": self._inject_css,
            "get_current": self._get_current,
            "reset": self._reset,
            "list_variables": self._list_variables,
        }

        handler = handlers.get(operation)
        if not handler:
            return f"[ERROR] Unknown operation: {operation}"

        try:
            return await handler(**kwargs)
        except Exception as e:
            logger.exception(f"UI customization error ({operation})")
            return f"[ERROR] {e}"

    async def _set_theme(self, **kwargs: Any) -> str:
        variables: dict = kwargs.get("variables", {})
        if not variables:
            return "[ERROR] 'variables' parameter is required for set_theme"

        # Build CSS content
        css_parts = []

        # Check for theme-specific overrides
        dark_vars = variables.pop("dark", {})
        light_vars = variables.pop("light", {})

        # Top-level variables apply to both themes via :root
        if variables:
            lines = []
            for key, value in variables.items():
                if not key.startswith("--"):
                    key = f"--{key}"
                lines.append(f"  {key}: {value};")
            if lines:
                css_parts.append(
                    "/* Custom theme — applied to both light and dark */\n"
                    ":root {\n" + "\n".join(lines) + "\n}\n"
                    ".dark {\n" + "\n".join(lines) + "\n}"
                )

        # Dark-mode specific overrides
        if dark_vars:
            lines = []
            for key, value in dark_vars.items():
                if not key.startswith("--"):
                    key = f"--{key}"
                lines.append(f"  {key}: {value};")
            css_parts.append(
                "/* Custom dark theme */\n"
                ".dark {\n" + "\n".join(lines) + "\n}"
            )

        # Light-mode specific overrides
        if light_vars:
            lines = []
            for key, value in light_vars.items():
                if not key.startswith("--"):
                    key = f"--{key}"
                lines.append(f"  {key}: {value};")
            css_parts.append(
                "/* Custom light theme */\n"
                ":root {\n" + "\n".join(lines) + "\n}"
            )

        # Read existing CSS to preserve inject_css content
        css_path = _theme_css_path()
        existing_custom = ""
        if css_path.exists():
            content = css_path.read_text()
            # Preserve everything after the CUSTOM CSS marker
            marker = "/* ── Custom injected CSS ── */"
            if marker in content:
                existing_custom = content[content.index(marker):]

        # Write the combined CSS
        final_css = "\n\n".join(css_parts)
        if existing_custom:
            final_css += "\n\n" + existing_custom

        css_path.write_text(final_css)
        logger.info("Updated custom theme CSS with %d variable overrides", sum(
            len(v) if isinstance(v, dict) else 1
            for v in [variables, dark_vars, light_vars]
        ))

        return (
            f"Theme updated successfully with variable overrides.\n"
            f"File: {css_path}\n"
            f"The user needs to refresh the page (F5) to see changes."
        )

    async def _set_layout(self, **kwargs: Any) -> str:
        layout: dict = kwargs.get("layout", {})
        if not layout:
            return "[ERROR] 'layout' parameter is required for set_layout"

        # Validate sections if provided
        if "sections" in layout:
            for section in layout["sections"]:
                if "items" not in section:
                    continue
                for item in section["items"]:
                    if "id" not in item:
                        return f"[ERROR] Each item must have an 'id'. Got: {item}"
                    if "icon" in item and item["icon"] not in AVAILABLE_ICONS:
                        return (
                            f"[ERROR] Unknown icon '{item['icon']}'. "
                            f"Available: {', '.join(AVAILABLE_ICONS[:20])}..."
                        )

        # Merge with existing config
        config_path = _ui_config_path()
        existing = {}
        if config_path.exists():
            try:
                existing = json.loads(config_path.read_text())
            except json.JSONDecodeError:
                pass

        existing.update(layout)
        config_path.write_text(json.dumps(existing, indent=2))

        logger.info("Updated UI layout config")
        return (
            f"Layout updated successfully.\n"
            f"File: {config_path}\n"
            f"The user needs to refresh the page (F5) to see changes."
        )

    async def _inject_css(self, **kwargs: Any) -> str:
        css: str = kwargs.get("css", "")
        if not css:
            return "[ERROR] 'css' parameter is required for inject_css"

        css_path = _theme_css_path()
        marker = "/* ── Custom injected CSS ── */"

        # Read existing content
        existing = ""
        if css_path.exists():
            existing = css_path.read_text()

        # Remove old custom CSS section
        if marker in existing:
            existing = existing[:existing.index(marker)].rstrip()

        # Append new custom CSS
        final = existing + f"\n\n{marker}\n{css}\n" if existing else f"{marker}\n{css}\n"
        css_path.write_text(final)

        logger.info("Injected custom CSS (%d chars)", len(css))
        return (
            f"Custom CSS injected successfully ({len(css)} chars).\n"
            f"File: {css_path}\n"
            f"The user needs to refresh the page (F5) to see changes."
        )

    async def _get_current(self, **kwargs: Any) -> str:
        result = {"theme_css": None, "layout": None}

        css_path = _theme_css_path()
        if css_path.exists():
            result["theme_css"] = css_path.read_text()

        config_path = _ui_config_path()
        if config_path.exists():
            try:
                result["layout"] = json.loads(config_path.read_text())
            except json.JSONDecodeError:
                result["layout"] = "[ERROR] Invalid JSON in ui-config.json"

        if not result["theme_css"] and not result["layout"]:
            return "No customizations applied. Using default theme and layout."

        parts = []
        if result["theme_css"]:
            parts.append(f"── Custom Theme CSS ──\n{result['theme_css']}")
        if result["layout"]:
            parts.append(f"── Layout Config ──\n{json.dumps(result['layout'], indent=2)}")

        return "\n\n".join(parts)

    async def _reset(self, **kwargs: Any) -> str:
        css_path = _theme_css_path()
        config_path = _ui_config_path()

        removed = []
        if css_path.exists():
            css_path.unlink()
            removed.append("custom-theme.css")
        if config_path.exists():
            config_path.unlink()
            removed.append("ui-config.json")

        if not removed:
            return "No customizations to reset — already using defaults."

        return (
            f"Reset complete. Removed: {', '.join(removed)}\n"
            f"The user needs to refresh the page (F5) to see the default theme."
        )

    async def _list_variables(self, **kwargs: Any) -> str:
        lines = ["── Dark Mode CSS Variables (defaults) ──\n"]
        for key, value in DEFAULT_DARK_VARIABLES.items():
            lines.append(f"  {key}: {value}")

        lines.append("\n── Light Mode CSS Variables (defaults) ──\n")
        for key, value in DEFAULT_LIGHT_VARIABLES.items():
            lines.append(f"  {key}: {value}")

        lines.append("\n── Available Sidebar Icons ──\n")
        lines.append(f"  {', '.join(AVAILABLE_ICONS)}")

        lines.append("\n── Default Layout Structure ──\n")
        lines.append(json.dumps(DEFAULT_LAYOUT, indent=2))

        return "\n".join(lines)
