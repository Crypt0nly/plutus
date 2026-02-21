"""Spotify skills — reliable workflows for Spotify.

Strategy: Spotify can be controlled via:
  1. URI scheme: spotify:track:ID, spotify:search:QUERY (opens desktop app)
  2. Web URL: open.spotify.com/search/QUERY (opens in browser)
  3. Keyboard shortcuts: Space (play/pause), Ctrl+Right (next), Ctrl+Left (prev)
  
We use the URI scheme for the desktop app (most reliable) and fall back
to the web player if the desktop app isn't available.
"""

from __future__ import annotations
from typing import Any
from urllib.parse import quote
from plutus.skills.engine import SkillDefinition, SkillStep


class SpotifyPlaySong(SkillDefinition):
    name = "spotify_play_song"
    description = "Search for and play a specific song on Spotify"
    app = "Spotify"
    triggers = ["play song", "play music", "play on spotify", "spotify play",
                "listen to", "put on"]
    category = "music"
    required_params = ["query"]
    optional_params = []

    def build_steps(self, params: dict[str, Any]) -> list[SkillStep]:
        query = params["query"]

        return [
            # Open Spotify search via web (works whether desktop or web)
            SkillStep(
                description=f"Open Spotify and search for: {query}",
                operation="open_url",
                params={"url": f"https://open.spotify.com/search/{quote(query)}"},
                wait_after=4.0,
            ),
            SkillStep(
                description="Wait for search results to load",
                operation="wait_for_text",
                params={"text": "Songs", "timeout": 10000},
                wait_after=1.0,
                optional=True,
            ),
            SkillStep(
                description="Get the search results page",
                operation="get_page",
                params={},
                wait_after=0.5,
            ),
            SkillStep(
                description="Click the first song result to play it",
                operation="browser_click",
                params={"selector": "[data-testid='tracklist-row'] button[aria-label='Play']"},
                wait_after=1.0,
                retry_on_fail=True,
                optional=True,
            ),
            # Fallback: click the first play button on the page
            SkillStep(
                description="Click play button (fallback)",
                operation="browser_click",
                params={"role": "button", "role_name": "Play"},
                wait_after=1.0,
                optional=True,
            ),
        ]


class SpotifySearchPlay(SkillDefinition):
    name = "spotify_search_play"
    description = "Search Spotify for an artist, album, or playlist and play it"
    app = "Spotify"
    triggers = ["spotify search", "find on spotify", "play artist", "play album",
                "play playlist"]
    category = "music"
    required_params = ["query"]
    optional_params = ["type"]  # "artist", "album", "playlist"

    def build_steps(self, params: dict[str, Any]) -> list[SkillStep]:
        query = params["query"]
        search_type = params.get("type", "")

        if search_type:
            query_with_type = f"{query} {search_type}"
        else:
            query_with_type = query

        return [
            SkillStep(
                description=f"Open Spotify search for: {query_with_type}",
                operation="open_url",
                params={"url": f"https://open.spotify.com/search/{quote(query_with_type)}"},
                wait_after=4.0,
            ),
            SkillStep(
                description="Wait for results to load",
                operation="wait_for_text",
                params={"text": "Songs", "timeout": 10000},
                wait_after=1.0,
                optional=True,
            ),
            SkillStep(
                description="Read search results",
                operation="get_page",
                params={},
                wait_after=0.0,
            ),
        ]


class SpotifyPlayPause(SkillDefinition):
    name = "spotify_play_pause"
    description = "Toggle play/pause on Spotify"
    app = "Spotify"
    triggers = ["pause spotify", "resume spotify", "pause music", "play pause",
                "stop music", "unpause"]
    category = "music"
    required_params = []
    optional_params = []

    def build_steps(self, params: dict[str, Any]) -> list[SkillStep]:
        return [
            SkillStep(
                description="Open Spotify",
                operation="open_app",
                params={"app_name": "Spotify"},
                wait_after=1.0,
            ),
            SkillStep(
                description="Toggle play/pause with keyboard shortcut",
                operation="keyboard_hotkey",
                params={"hotkey": "space"},
                wait_after=0.5,
            ),
        ]


class SpotifyNextTrack(SkillDefinition):
    name = "spotify_next_track"
    description = "Skip to the next track on Spotify"
    app = "Spotify"
    triggers = ["next song", "skip song", "next track", "skip track"]
    category = "music"
    required_params = []
    optional_params = []

    def build_steps(self, params: dict[str, Any]) -> list[SkillStep]:
        return [
            SkillStep(
                description="Open Spotify",
                operation="open_app",
                params={"app_name": "Spotify"},
                wait_after=1.0,
            ),
            SkillStep(
                description="Skip to next track",
                operation="keyboard_hotkey",
                params={"hotkey": "ctrl+right"},
                wait_after=0.5,
            ),
        ]
