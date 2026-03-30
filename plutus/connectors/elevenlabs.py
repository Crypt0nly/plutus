"""ElevenLabs connector — text-to-speech voice mode for Plutus.

Allows Plutus to respond with voice memos through Telegram, WhatsApp, and
the local UI. Each user connects their own ElevenLabs API key through the
connectors tab. The connector provides:

  - Text-to-speech synthesis via the ElevenLabs API
  - Voice selection (configurable default voice)
  - Model selection (multilingual_v2, flash, turbo)
  - Audio output in mp3/ogg format for messaging platforms

The connector follows the AIProviderConnector pattern: it stores the API key
securely via SecretsStore and exposes configuration through the standard
connector schema so the UI renders the setup form automatically.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from plutus.connectors.ai_providers import AIProviderConnector

logger = logging.getLogger("plutus.connectors.elevenlabs")

# Default output directory for generated audio
AUDIO_OUTPUT_DIR = Path.home() / ".plutus" / "audio_cache"

# Available ElevenLabs TTS models
MODELS = {
    "eleven_multilingual_v2": "Multilingual v2 — Best quality, 29 languages",
    "eleven_flash_v2_5": "Flash v2.5 — Low latency, great for real-time",
    "eleven_turbo_v2_5": "Turbo v2.5 — Balanced speed and quality",
    "eleven_multilingual_v1": "Multilingual v1 — Legacy",
}

MODEL_IDS = {
    "eleven_multilingual_v2": "eleven_multilingual_v2",
    "eleven_flash_v2_5": "eleven_flash_v2_5",
    "eleven_turbo_v2_5": "eleven_turbo_v2_5",
    "eleven_multilingual_v1": "eleven_multilingual_v1",
}

# Pre-built voice IDs (ElevenLabs defaults)
DEFAULT_VOICES = {
    "Rachel": "21m00Tcm4TlvDq8ikWAM",
    "Adam": "pNInz6obpgDQGcFmaJgB",
    "Antoni": "ErXwobaYiN019PkySvjV",
    "Bella": "EXAVITQu4vr4xnSDxMaL",
    "Domi": "AZnzlk1XvdvUeBnXmlld",
    "Elli": "MF3mGyEYCl7XYWbV9V6O",
    "Josh": "TxGEqnHWrfWFTfGW9XjX",
    "Sam": "yoZ06aMxZJJ28mfd3POQ",
    "Arnold": "VR6AewLTigWG4xSOukaG",
    "Callum": "N2lVS1w4EtoT3dr4eOWO",
    "Charlie": "IKne3meq5aSn9XLyUdCD",
    "Charlotte": "XB0fDUnXU5powFXDhCwa",
    "Clyde": "2EiwWnXFnvU5JabPnv8n",
    "Daniel": "onwK4e9ZLuTAKqWW03F9",
    "Dave": "CYw3kZ02Hs0563khs1Fj",
    "Emily": "LcfcDJNUP1GQjkzn1xUU",
    "Ethan": "g5CIjZEefAph4nQFvHAz",
    "Fin": "D38z5RcWu1voky8WS1ja",
    "Freya": "jsCqWAovK2LkecY7zXl4",
    "George": "JBFqnCBsd6RMkjVDRZzb",
    "Gigi": "jBpfuIE2acCO8z3wKNLl",
    "Giovanni": "zcAOhNBS3c14rBihAFp1",
    "Glinda": "z9fAnlkpzviPz146aGWa",
    "Grace": "oWAxZDx7w5VEj9dCyTzz",
    "Harry": "SOYHLrjzK2X1ezoPC6cr",
    "James": "ZQe5CZNOzWyzPSCn5a3c",
    "Jeremy": "bVMeCyTHy58xNoL34h3p",
    "Jessie": "t0jbNlBVZ17f02VDIeMI",
    "Joseph": "Zlb1dXrM653N07WRdFW3",
    "Liam": "TX3LPaxmHKxFdv7VOQHJ",
    "Lily": "pFZP5JQG7iQjIQuC4Bku",
    "Matilda": "XrExE9yKIg1WjnnlVkGX",
    "Nicole": "piTKgcLEGmPE4e6mEKli",
    "Patrick": "ODq5zmih8GrVes37Dizd",
    "River": "SAz9YHcvj6GT2YYXdXww",
    "Serena": "pMsXgVXv3BLzUgSXRplE",
    "Thomas": "GBv7mTt0atIp3Br8iCZE",
}

# Default voice if none configured
DEFAULT_VOICE_NAME = "Rachel"
DEFAULT_VOICE_ID = DEFAULT_VOICES[DEFAULT_VOICE_NAME]


class ElevenLabsConnector(AIProviderConnector):
    """ElevenLabs text-to-speech connector.

    Users connect their own API key. Once configured, Plutus can respond
    with voice memos on any messaging channel or the local UI.
    """

    name = "elevenlabs"
    display_name = "ElevenLabs"
    description = "Voice mode \u2014 respond with voice memos via text-to-speech"
    icon = "AudioLines"
    env_var = "ELEVENLABS_API_KEY"
    provider_key = "elevenlabs"
    docs_url = "https://elevenlabs.io/app/settings/api-keys"
    features = ["Text-to-Speech", "Voice Mode", "30+ Voices", "29 Languages"]

    def __init__(self):
        super().__init__()
        AUDIO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def config_schema(self) -> list[dict[str, Any]]:
        """Configuration fields for the UI.

        Uses 'select' and 'toggle' types so the frontend renders proper
        dropdowns and switches instead of raw text inputs.
        """
        voice_options = [
            {"value": name, "label": name}
            for name in sorted(DEFAULT_VOICES.keys())
        ]
        model_options = [
            {"value": model_id, "label": label}
            for model_id, label in MODELS.items()
        ]

        return [
            {
                "name": "api_key",
                "label": "API Key",
                "type": "password",
                "required": True,
                "placeholder": "Enter your ElevenLabs API key",
                "help": f"Get your key from {self.docs_url}",
            },
            {
                "name": "voice_mode_enabled",
                "label": "Enable Voice Mode",
                "type": "toggle",
                "required": False,
                "default": True,
                "help": (
                    "When enabled, Plutus can respond with voice memos in "
                    "the chat UI, Telegram, and WhatsApp."
                ),
            },
            {
                "name": "voice_name",
                "label": "Default Voice",
                "type": "select",
                "required": False,
                "options": voice_options,
                "default": DEFAULT_VOICE_NAME,
                "help": "The voice Plutus will use when speaking.",
            },
            {
                "name": "model",
                "label": "TTS Model",
                "type": "select",
                "required": False,
                "options": model_options,
                "default": "eleven_multilingual_v2",
                "help": "The model used for speech synthesis.",
            },
        ]

    def _sensitive_fields(self) -> list[str]:
        return ["api_key"]

    @property
    def voice_mode_enabled(self) -> bool:
        """Whether voice mode is currently enabled."""
        val = self._config.get("voice_mode_enabled", True)
        if isinstance(val, bool):
            return val
        return str(val).lower() in ("true", "1", "yes")

    @property
    def default_voice_id(self) -> str:
        """Get the configured default voice ID."""
        voice_name = self._config.get("voice_name", DEFAULT_VOICE_NAME)
        return DEFAULT_VOICES.get(voice_name, DEFAULT_VOICE_ID)

    @property
    def default_model(self) -> str:
        """Get the configured TTS model ID."""
        model_key = self._config.get("model", "eleven_multilingual_v2")
        # Accept both the model ID directly or legacy short names
        if model_key in MODEL_IDS:
            return MODEL_IDS[model_key]
        # Legacy fallback for old configs
        legacy_map = {
            "multilingual_v2": "eleven_multilingual_v2",
            "flash": "eleven_flash_v2_5",
            "turbo": "eleven_turbo_v2_5",
            "multilingual_v1": "eleven_multilingual_v1",
        }
        return legacy_map.get(model_key, "eleven_multilingual_v2")

    async def _test_with_key(self, key: str) -> dict[str, Any]:
        """Test the ElevenLabs API connection."""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.elevenlabs.io/v1/user",
                    headers={"xi-api-key": key},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    tier = data.get("subscription", {}).get("tier", "unknown")
                    chars_left = data.get("subscription", {}).get(
                        "character_count", 0
                    )
                    char_limit = data.get("subscription", {}).get(
                        "character_limit", 0
                    )
                    return {
                        "success": True,
                        "message": (
                            f"Connected to ElevenLabs ({tier} plan). "
                            f"Characters used: {chars_left:,}/{char_limit:,}"
                        ),
                    }
                elif resp.status_code == 401:
                    return {"success": False, "message": "Invalid API key"}
                else:
                    return {
                        "success": False,
                        "message": f"API returned status {resp.status_code}",
                    }
        except Exception as e:
            return {"success": False, "message": f"Connection failed: {e}"}

    async def synthesize(
        self,
        text: str,
        voice_id: str | None = None,
        model: str | None = None,
        output_format: str = "mp3_44100_128",
        output_path: str | None = None,
    ) -> dict[str, Any]:
        """Synthesize text to speech and return the audio file path.

        Args:
            text: The text to convert to speech.
            voice_id: ElevenLabs voice ID. Uses configured default if not specified.
            model: ElevenLabs model ID. Uses configured default if not specified.
            output_format: Audio format. Default: mp3_44100_128.
            output_path: Where to save the audio. Auto-generated if not specified.

        Returns:
            {"success": bool, "audio_path": str, "message": str}
        """
        key = self._get_key()
        if not key:
            return {
                "success": False,
                "audio_path": "",
                "message": "No ElevenLabs API key configured.",
            }

        if not text or not text.strip():
            return {
                "success": False,
                "audio_path": "",
                "message": "No text provided for synthesis.",
            }

        # Truncate very long text (ElevenLabs has a ~5000 char limit per request)
        if len(text) > 4500:
            text = text[:4500] + "..."

        voice = voice_id or self.default_voice_id
        tts_model = model or self.default_model

        # Build output path
        if not output_path:
            ext = "mp3" if "mp3" in output_format else "ogg"
            output_path = str(
                AUDIO_OUTPUT_DIR / f"tts_{int(time.time() * 1000)}.{ext}"
            )

        try:
            import httpx

            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                    headers={
                        "xi-api-key": key,
                        "Content-Type": "application/json",
                        "Accept": "audio/mpeg",
                    },
                    json={
                        "text": text,
                        "model_id": tts_model,
                        "voice_settings": {
                            "stability": 0.5,
                            "similarity_boost": 0.75,
                            "style": 0.0,
                            "use_speaker_boost": True,
                        },
                    },
                    params={"output_format": output_format},
                )

                if resp.status_code == 200:
                    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                    Path(output_path).write_bytes(resp.content)
                    logger.info(
                        f"TTS audio saved: {output_path} "
                        f"({len(resp.content)} bytes)"
                    )
                    return {
                        "success": True,
                        "audio_path": output_path,
                        "message": f"Audio generated ({len(resp.content)} bytes)",
                    }
                else:
                    error = resp.text
                    logger.error(f"ElevenLabs TTS failed: {resp.status_code} {error}")
                    return {
                        "success": False,
                        "audio_path": "",
                        "message": f"ElevenLabs API error ({resp.status_code}): {error[:200]}",
                    }

        except Exception as e:
            logger.error(f"ElevenLabs TTS failed: {e}")
            return {
                "success": False,
                "audio_path": "",
                "message": f"TTS synthesis failed: {e}",
            }

    async def synthesize_for_telegram(
        self, text: str, voice_id: str | None = None
    ) -> dict[str, Any]:
        """Generate audio optimized for Telegram voice messages (.ogg opus)."""
        result = await self.synthesize(
            text=text,
            voice_id=voice_id,
            output_format="mp3_22050_32",
        )

        if not result["success"]:
            return result

        # Convert mp3 to ogg/opus for Telegram
        mp3_path = result["audio_path"]
        ogg_path = mp3_path.replace(".mp3", ".ogg")

        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-i", mp3_path, "-c:a", "libopus",
                "-b:a", "32k", "-vn", str(ogg_path),
                "-y", "-loglevel", "error",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode == 0:
                Path(mp3_path).unlink(missing_ok=True)
                result["audio_path"] = ogg_path
                return result
            else:
                logger.warning(f"ogg conversion failed, using mp3: {stderr.decode()}")
                return result

        except FileNotFoundError:
            logger.warning("ffmpeg not found, sending mp3 instead of ogg")
            return result

    async def synthesize_for_whatsapp(
        self, text: str, voice_id: str | None = None
    ) -> dict[str, Any]:
        """Generate audio optimized for WhatsApp voice messages."""
        return await self.synthesize(
            text=text,
            voice_id=voice_id,
            output_format="mp3_22050_32",
        )

    async def send_message(self, text: str, **kwargs: Any) -> dict[str, Any]:
        """Synthesize text to speech (connector interface)."""
        result = await self.synthesize(text=text)
        return {
            "success": result["success"],
            "message": result["message"],
            "audio_path": result.get("audio_path", ""),
        }

    def status(self) -> dict[str, Any]:
        """Return status with voice-mode-specific fields."""
        base = super().status()
        base["voice_mode_enabled"] = self.voice_mode_enabled
        base["available_voices"] = sorted(DEFAULT_VOICES.keys())
        return base


async def text_to_speech(
    text: str,
    voice_id: str | None = None,
    model: str | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Convenience function for TTS from other modules.

    Returns {"success": bool, "audio_path": str, "message": str}
    """
    connector = ElevenLabsConnector()
    return await connector.synthesize(
        text=text,
        voice_id=voice_id,
        model=model,
        output_path=output_path,
    )
