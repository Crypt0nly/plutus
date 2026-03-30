"""Speak tool — allows Plutus to respond with voice memos in the UI.

When the agent decides a voice response is appropriate (e.g. the user sent a
voice memo, or the reply is short and conversational), it calls this tool to
synthesize speech via ElevenLabs and stream the audio back to the UI as a
playable voice message.
"""

from __future__ import annotations

import base64
import logging
import time
from pathlib import Path
from typing import Any

from plutus.tools.base import Tool

logger = logging.getLogger("plutus.tools.speak")

AUDIO_CACHE_DIR = Path.home() / ".plutus" / "audio_cache"


class SpeakTool(Tool):
    """Synthesize a voice response and send it to the UI as a voice memo."""

    @property
    def name(self) -> str:
        return "speak"

    @property
    def description(self) -> str:
        return (
            "Respond to the user with a voice memo. Use this when the user sent "
            "a voice message, or when a short spoken reply feels more natural than "
            "text. The text you provide will be converted to speech via ElevenLabs "
            "and played as an audio message in the chat. Always provide a concise, "
            "conversational message — avoid markdown, code blocks, or long text."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": (
                        "The text to speak. Keep it concise and conversational — "
                        "this will be read aloud. Max ~500 words."
                    ),
                },
                "voice": {
                    "type": "string",
                    "description": (
                        "Optional voice name (e.g. 'Rachel', 'Adam', 'Bella'). "
                        "Defaults to the user's configured voice."
                    ),
                },
            },
            "required": ["text"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        text = kwargs.get("text", "").strip()
        voice_name = kwargs.get("voice")

        if not text:
            return {"success": False, "error": "No text provided to speak."}

        # Import connector lazily to avoid circular imports
        try:
            from plutus.connectors.elevenlabs import (
                ElevenLabsConnector,
                DEFAULT_VOICES,
            )
        except ImportError:
            return {
                "success": False,
                "error": "ElevenLabs connector not available.",
            }

        connector = ElevenLabsConnector()
        if not connector._get_key():
            return {
                "success": False,
                "error": (
                    "ElevenLabs is not configured. The user needs to add their "
                    "API key in the Connectors tab to enable voice mode."
                ),
            }

        # Resolve voice
        voice_id = None
        if voice_name:
            voice_id = DEFAULT_VOICES.get(voice_name)

        # Synthesize
        AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        output_path = str(AUDIO_CACHE_DIR / f"speak_{int(time.time() * 1000)}.mp3")

        result = await connector.synthesize(
            text=text,
            voice_id=voice_id,
            output_format="mp3_44100_128",
            output_path=output_path,
        )

        if not result["success"]:
            return {
                "success": False,
                "error": f"TTS failed: {result['message']}",
            }

        # Read the audio file and encode as base64 for the UI
        audio_bytes = Path(output_path).read_bytes()
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        # Return a special marker that the server.py WS handler will recognize
        # and forward as a voice_message event to the UI
        return {
            "success": True,
            "voice_message": True,
            "audio_base64": audio_b64,
            "transcript": text,
            "audio_path": output_path,
            "duration_estimate": max(1, len(text.split()) // 3),  # rough seconds
            "message": f"Voice memo generated ({len(audio_bytes):,} bytes)",
        }
