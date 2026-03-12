"""Video generation tool — Veo (Google video generation).

Allows the agent to generate videos using Google's Veo 3.1 model
via the google-genai SDK. Uses async polling for completion.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

from plutus.tools.base import Tool

logger = logging.getLogger("plutus.tools.video_gen")

DEFAULT_MODEL = "veo-3.1-generate-preview"
VALID_ASPECT_RATIOS = ["16:9", "9:16"]
VALID_RESOLUTIONS = ["720p", "1080p", "4k"]
VALID_DURATIONS = [4, 5, 6, 7, 8]
MAX_POLL_TIME = 600  # 10 minutes max polling


class VideoGenTool(Tool):
    """Generate videos using Google Veo 3.1."""

    @property
    def name(self) -> str:
        return "video_gen"

    @property
    def description(self) -> str:
        return (
            "Generate videos using Google Veo 3.1. "
            "Use action='generate' to create a video from a text prompt. "
            "Use action='image_to_video' to animate an existing image. "
            "Supports aspect ratios (16:9, 9:16), resolutions (720p, 1080p, 4k), "
            "and durations (4-8 seconds). Videos include native audio. "
            "Generation takes 1-5 minutes — the tool polls automatically."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["generate", "image_to_video"],
                    "description": (
                        "'generate' = create video from text prompt. "
                        "'image_to_video' = animate an existing image."
                    ),
                },
                "prompt": {
                    "type": "string",
                    "description": "Text description of the video to generate.",
                },
                "output_path": {
                    "type": "string",
                    "description": (
                        "Where to save the generated video. "
                        "Defaults to ~/plutus_output/video_<timestamp>.mp4"
                    ),
                },
                "input_image": {
                    "type": "string",
                    "description": (
                        "Path to an image to animate. Required for 'image_to_video' action."
                    ),
                },
                "aspect_ratio": {
                    "type": "string",
                    "enum": ["16:9", "9:16"],
                    "description": "Aspect ratio. Default: '16:9'.",
                },
                "resolution": {
                    "type": "string",
                    "enum": ["720p", "1080p", "4k"],
                    "description": "Video resolution. Default: '720p'.",
                },
                "duration": {
                    "type": "integer",
                    "enum": [4, 5, 6, 7, 8],
                    "description": "Video duration in seconds. Default: 6.",
                },
            },
            "required": ["action", "prompt"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "generate")
        prompt = kwargs.get("prompt", "")

        if not prompt:
            return "Error: 'prompt' is required"

        try:
            from google import genai
            from google.genai import types
        except ImportError:
            return (
                "Error: google-genai package not installed. "
                "Install it with: pip install google-genai"
            )

        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            return (
                "Error: No Gemini API key found. Set GEMINI_API_KEY or "
                "GOOGLE_API_KEY environment variable."
            )

        client = genai.Client(api_key=api_key)

        aspect_ratio = kwargs.get("aspect_ratio", "16:9")
        if aspect_ratio not in VALID_ASPECT_RATIOS:
            aspect_ratio = "16:9"

        resolution = kwargs.get("resolution", "720p")
        if resolution not in VALID_RESOLUTIONS:
            resolution = "720p"

        duration = kwargs.get("duration", 6)
        if duration not in VALID_DURATIONS:
            duration = 6

        # Build output path
        output_path = kwargs.get("output_path", "")
        if not output_path:
            output_dir = Path.home() / "plutus_output"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(output_dir / f"video_{int(time.time())}.mp4")
        else:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        if action == "generate":
            return await self._generate(
                client, types, prompt, output_path, aspect_ratio, resolution, duration
            )
        elif action == "image_to_video":
            input_image = kwargs.get("input_image", "")
            if not input_image:
                return "Error: 'input_image' path is required for image_to_video action"
            if not Path(input_image).exists():
                return f"Error: Input image not found: {input_image}"
            return await self._image_to_video(
                client, types, prompt, input_image, output_path,
                aspect_ratio, resolution, duration,
            )
        else:
            return f"Error: Unknown action '{action}'. Use 'generate' or 'image_to_video'."

    async def _generate(
        self, client: Any, types: Any, prompt: str, output_path: str,
        aspect_ratio: str, resolution: str, duration: int,
    ) -> str:
        """Generate a video from a text prompt."""
        import asyncio

        try:
            operation = await asyncio.to_thread(
                client.models.generate_videos,
                model=DEFAULT_MODEL,
                prompt=prompt,
                config=types.GenerateVideosConfig(
                    aspect_ratio=aspect_ratio,
                    resolution=resolution,
                    duration_seconds=duration,
                ),
            )

            return await self._poll_and_save(client, operation, output_path)

        except Exception as e:
            logger.error(f"Video generation failed: {e}")
            return f"Error generating video: {e}"

    async def _image_to_video(
        self, client: Any, types: Any, prompt: str, input_image: str,
        output_path: str, aspect_ratio: str, resolution: str, duration: int,
    ) -> str:
        """Generate a video from an image + text prompt."""
        import asyncio

        try:
            # Upload the image file first
            image_file = await asyncio.to_thread(
                client.files.upload, file=input_image
            )

            operation = await asyncio.to_thread(
                client.models.generate_videos,
                model=DEFAULT_MODEL,
                prompt=prompt,
                image=image_file,
                config=types.GenerateVideosConfig(
                    aspect_ratio=aspect_ratio,
                    resolution=resolution,
                    duration_seconds=duration,
                ),
            )

            return await self._poll_and_save(client, operation, output_path)

        except Exception as e:
            logger.error(f"Image-to-video generation failed: {e}")
            return f"Error generating video from image: {e}"

    async def _poll_and_save(
        self, client: Any, operation: Any, output_path: str,
    ) -> str:
        """Poll the operation until done, then save the video."""
        import asyncio

        start = time.time()
        poll_interval = 10

        while not operation.done:
            if time.time() - start > MAX_POLL_TIME:
                return (
                    "Error: Video generation timed out after 10 minutes. "
                    "The operation may still be running on Google's servers."
                )

            await asyncio.sleep(poll_interval)

            try:
                operation = await asyncio.to_thread(
                    client.operations.get, operation
                )
            except Exception as e:
                logger.warning(f"Poll failed, retrying: {e}")
                continue

        # Download and save
        try:
            generated_video = operation.result.generated_videos[0]

            await asyncio.to_thread(
                client.files.download,
                file=generated_video.video,
            )

            generated_video.video.save(output_path)

            elapsed = int(time.time() - start)
            return (
                f"Video saved to: {output_path} "
                f"(generated in {elapsed}s)"
            )
        except Exception as e:
            logger.error(f"Failed to save video: {e}")
            return f"Error saving generated video: {e}"
