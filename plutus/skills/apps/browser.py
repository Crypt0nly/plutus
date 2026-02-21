"""Browser skills — reliable workflows for common web tasks.

Strategy: Use direct URLs and Playwright/CDP for all web interaction.
These skills handle common web tasks that users frequently ask for.
"""

from __future__ import annotations
from typing import Any
from urllib.parse import quote
from plutus.skills.engine import SkillDefinition, SkillStep


class GoogleSearch(SkillDefinition):
    name = "google_search"
    description = "Search Google for something and read the results"
    app = "Chrome"
    triggers = ["google", "search for", "look up", "search the web", "google search",
                "find information about", "search online"]
    category = "browser"
    required_params = ["query"]
    optional_params = []

    def build_steps(self, params: dict[str, Any]) -> list[SkillStep]:
        query = params["query"]

        return [
            SkillStep(
                description=f"Search Google for: {query}",
                operation="open_url",
                params={"url": f"https://www.google.com/search?q={quote(query)}"},
                wait_after=3.0,
            ),
            SkillStep(
                description="Wait for search results to load",
                operation="wait_for_text",
                params={"text": "results", "timeout": 10000},
                wait_after=1.0,
                optional=True,
            ),
            SkillStep(
                description="Read the search results",
                operation="get_page",
                params={},
                wait_after=0.0,
            ),
        ]


class OpenWebsite(SkillDefinition):
    name = "open_website"
    description = "Open a website and read its content"
    app = "Chrome"
    triggers = ["open website", "go to website", "visit", "open page", "navigate to"]
    category = "browser"
    required_params = ["url"]
    optional_params = []

    def build_steps(self, params: dict[str, Any]) -> list[SkillStep]:
        url = params["url"]
        # Add https:// if no protocol specified
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"

        return [
            SkillStep(
                description=f"Open: {url}",
                operation="open_url",
                params={"url": url},
                wait_after=3.0,
            ),
            SkillStep(
                description="Read the page content",
                operation="get_page",
                params={},
                wait_after=0.0,
            ),
        ]


class DownloadFile(SkillDefinition):
    name = "download_file"
    description = "Download a file from a URL"
    app = "Chrome"
    triggers = ["download file", "download from", "save file from"]
    category = "browser"
    required_params = ["url"]
    optional_params = ["save_path"]

    def build_steps(self, params: dict[str, Any]) -> list[SkillStep]:
        url = params["url"]
        save_path = params.get("save_path", "")

        if save_path:
            # Use curl/wget for direct download
            cmd = f'curl -L -o "{save_path}" "{url}" 2>&1 || wget -O "{save_path}" "{url}" 2>&1'
        else:
            cmd = f'curl -L -O "{url}" 2>&1 || wget "{url}" 2>&1'

        return [
            SkillStep(
                description=f"Download file from: {url}",
                operation="run_command",
                params={"command": cmd},
                wait_after=2.0,
            ),
        ]
