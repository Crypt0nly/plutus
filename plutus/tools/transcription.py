"""Transcription tool — speech-to-text for voice memos and audio files.

Supports two backends:
  1. OpenAI Whisper API (default) — uses gpt-4o-mini-transcribe or whisper-1
  2. faster-whisper (local fallback) — runs offline, no API key needed

The tool automatically selects the best available backend:
  - If an OpenAI API key is configured, it uses the cloud API
  - Otherwise, it falls back to faster-whisper if installed
  - Users can force a specific backend via the 'backend' parameter

Voice memos from Telegram (.ogg/.oga), WhatsApp (.opus), and the UI
(.mp3/.wav/.webm/.m4a) are all supported.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from plutus.tools.base import Tool

logger = logging.getLogger("plutus.tools.transcription")

# Supported audio formats (superset of Telegram/WhatsApp/UI formats)
SUPPORTED_FORMATS = {
    ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm",
    ".ogg", ".oga", ".opus", ".flac", ".aac",
}

# OpenAI transcription models
OPENAI_MODELS = {
    "default": "gpt-4o-mini-transcribe",
    "accurate": "gpt-4o-transcribe",
    "fast": "whisper-1",
}


class TranscriptionTool(Tool):
    """Transcribe audio files to text using OpenAI Whisper or local faster-whisper."""

    @property
    def name(self) -> str:
        return "transcription"

    @property
    def description(self) -> str:
        return (
            "Transcribe speech from audio files to text. Supports voice memos from "
            "Telegram, WhatsApp, and direct uploads. Formats: mp3, wav, ogg, opus, "
            "m4a, webm, flac, aac, mp4. "
            "Use backend='openai' for cloud transcription (requires OpenAI API key) "
            "or backend='local' for offline transcription via faster-whisper. "
            "If no backend is specified, the best available option is chosen automatically."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "audio_path": {
                    "type": "string",
                    "description": "Path to the audio file to transcribe.",
                },
                "backend": {
                    "type": "string",
                    "enum": ["auto", "openai", "local"],
                    "description": (
                        "Transcription backend. 'auto' picks the best available "
                        "(OpenAI if key is set, else local). Default: 'auto'."
                    ),
                },
                "model": {
                    "type": "string",
                    "enum": ["default", "accurate", "fast"],
                    "description": (
                        "OpenAI model selection. 'default' = gpt-4o-mini-transcribe, "
                        "'accurate' = gpt-4o-transcribe, 'fast' = whisper-1. "
                        "Only used with backend='openai'. Default: 'default'."
                    ),
                },
                "language": {
                    "type": "string",
                    "description": (
                        "ISO 639-1 language code (e.g. 'en', 'de', 'es'). "
                        "Optional — auto-detected if not specified."
                    ),
                },
            },
            "required": ["audio_path"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        audio_path = kwargs.get("audio_path", "")
        backend = kwargs.get("backend", "auto")
        model_key = kwargs.get("model", "default")
        language = kwargs.get("language")

        # Validate input file
        if not audio_path:
            return "Error: 'audio_path' is required."

        path = Path(audio_path)
        if not path.exists():
            return f"Error: Audio file not found: {audio_path}"

        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_FORMATS:
            return (
                f"Error: Unsupported format '{suffix}'. "
                f"Supported: {', '.join(sorted(SUPPORTED_FORMATS))}"
            )

        # Select backend
        if backend == "auto":
            backend = self._select_backend()
        elif backend == "openai" and not self._has_openai_key():
            return (
                "Error: OpenAI backend requested but no API key found. "
                "Set OPENAI_API_KEY or configure the OpenAI connector."
            )
        elif backend == "local" and not self._has_local_backend():
            return (
                "Error: Local backend requested but faster-whisper is not installed. "
                "Install with: pip install faster-whisper"
            )

        if backend == "openai":
            return await self._transcribe_openai(path, model_key, language)
        else:
            return await self._transcribe_local(path, language)

    def _has_openai_key(self) -> bool:
        """Check if an OpenAI API key is available."""
        if os.environ.get("OPENAI_API_KEY"):
            return True
        try:
            from plutus.config import SecretsStore
            return SecretsStore().has_key("openai")
        except Exception:
            return False

    def _get_openai_key(self) -> str | None:
        """Retrieve the OpenAI API key."""
        key = os.environ.get("OPENAI_API_KEY")
        if key:
            return key
        try:
            from plutus.config import SecretsStore
            return SecretsStore().get_key("openai")
        except Exception:
            return None

    def _has_local_backend(self) -> bool:
        """Check if faster-whisper is installed."""
        try:
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            return False

    def _select_backend(self) -> str:
        """Auto-select the best available backend."""
        if self._has_openai_key():
            return "openai"
        if self._has_local_backend():
            return "local"
        return "openai"  # Will fail with a clear error message

    async def _transcribe_openai(
        self, path: Path, model_key: str, language: str | None
    ) -> str:
        """Transcribe using OpenAI's Whisper API."""
        key = self._get_openai_key()
        if not key:
            return (
                "Error: No OpenAI API key found. "
                "Set OPENAI_API_KEY or configure the OpenAI connector."
            )

        model = OPENAI_MODELS.get(model_key, OPENAI_MODELS["default"])

        try:
            import httpx
        except ImportError:
            return "Error: httpx package not installed. Install with: pip install httpx"

        # Convert .ogg/.oga/.opus to .mp3 if needed (OpenAI prefers standard formats)
        audio_path = path
        temp_file = None
        if path.suffix.lower() in {".ogg", ".oga", ".opus"}:
            audio_path, temp_file = await self._convert_to_mp3(path)
            if audio_path is None:
                return temp_file  # temp_file contains the error message

        try:
            # Build multipart form data
            data = {"model": model}
            if language:
                data["language"] = language

            files = {
                "file": (audio_path.name, audio_path.read_bytes(), "audio/mpeg"),
            }

            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {key}"},
                    data=data,
                    files=files,
                )

            if resp.status_code == 200:
                result = resp.json()
                text = result.get("text", "").strip()
                if not text:
                    return "Transcription completed but no speech was detected in the audio."
                return text
            else:
                error = resp.text
                return f"Error: OpenAI API returned status {resp.status_code}: {error}"

        except Exception as e:
            logger.error(f"OpenAI transcription failed: {e}")
            return f"Error during transcription: {e}"
        finally:
            # Clean up temp file
            if temp_file and isinstance(temp_file, Path) and temp_file.exists():
                temp_file.unlink(missing_ok=True)

    async def _transcribe_local(self, path: Path, language: str | None) -> str:
        """Transcribe using faster-whisper (local, offline)."""
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            return (
                "Error: faster-whisper is not installed. "
                "Install with: pip install faster-whisper"
            )

        try:
            def _run():
                model = WhisperModel("base", device="cpu", compute_type="int8")
                kwargs = {}
                if language:
                    kwargs["language"] = language
                segments, info = model.transcribe(str(path), **kwargs)
                text = " ".join(seg.text.strip() for seg in segments)
                return text, info

            text, info = await asyncio.to_thread(_run)

            if not text.strip():
                return "Transcription completed but no speech was detected in the audio."

            lang = getattr(info, "language", "unknown")
            prob = getattr(info, "language_probability", 0)
            return (
                f"{text.strip()}\n\n"
                f"[Local transcription — detected language: {lang} "
                f"(confidence: {prob:.0%})]"
            )

        except Exception as e:
            logger.error(f"Local transcription failed: {e}")
            return f"Error during local transcription: {e}"

    async def _convert_to_mp3(self, path: Path) -> tuple[Path | None, Any]:
        """Convert audio to mp3 using ffmpeg (for formats OpenAI doesn't accept natively)."""
        try:
            tmp = Path(tempfile.mktemp(suffix=".mp3"))
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-i", str(path), "-vn", "-ar", "16000",
                "-ac", "1", "-ab", "128k", "-f", "mp3", str(tmp),
                "-y", "-loglevel", "error",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                error_msg = stderr.decode().strip() if stderr else "Unknown error"
                return None, f"Error converting audio with ffmpeg: {error_msg}"

            return tmp, tmp  # Return path and temp path for cleanup

        except FileNotFoundError:
            return None, (
                "Error: ffmpeg not found. Install it with: "
                "sudo apt install ffmpeg (Linux) or brew install ffmpeg (macOS)"
            )
        except Exception as e:
            return None, f"Error converting audio: {e}"


async def transcribe_audio(
    audio_path: str,
    backend: str = "auto",
    model: str = "default",
    language: str | None = None,
) -> str:
    """Convenience function for transcribing audio from other modules.

    This is the main entry point for the Telegram/WhatsApp bridges and
    other internal callers that need to transcribe voice memos.
    """
    tool = TranscriptionTool()
    return await tool.execute(
        audio_path=audio_path,
        backend=backend,
        model=model,
        language=language,
    )
