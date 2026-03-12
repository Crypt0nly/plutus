"""Image generation tool — Nano Banana (Google Gemini image generation).

Allows the agent to generate and edit images using Google's Nano Banana models
via the google-genai SDK.
"""

from __future__ import annotations

import base64
import logging
import os
import time
from pathlib import Path
from typing import Any

from plutus.tools.base import Tool

logger = logging.getLogger("plutus.tools.image_gen")

# Available Nano Banana models
MODELS = {
    "flash": "gemini-3.1-flash-image-preview",
    "pro": "gemini-3-pro-image-preview",
    "default": "gemini-2.5-flash-image",
}

VALID_ASPECT_RATIOS = ["1:1", "3:4", "4:3", "9:16", "16:9"]
VALID_SIZES = ["512", "1024", "2048", "4096"]


class ImageGenTool(Tool):
    """Generate and edit images using Google Nano Banana models."""

    @property
    def name(self) -> str:
        return "image_gen"

    @property
    def description(self) -> str:
        return (
            "Generate or edit images using Google Nano Banana (Gemini image models). "
            "Use action='generate' to create an image from a text prompt. "
            "Use action='edit' to modify an existing image with a text prompt. "
            "Models: 'flash' (fast), 'pro' (high quality), 'default' (balanced). "
            "Supports aspect ratios (1:1, 3:4, 4:3, 9:16, 16:9) and resolutions "
            "(512, 1024, 2048, 4096). Images are saved to the specified output path."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["generate", "edit"],
                    "description": (
                        "'generate' = create image from text prompt. "
                        "'edit' = modify an existing image with a text prompt."
                    ),
                },
                "prompt": {
                    "type": "string",
                    "description": "Text description of the image to generate or edit instruction.",
                },
                "output_path": {
                    "type": "string",
                    "description": (
                        "Where to save the generated image. "
                        "Defaults to ~/plutus_output/image_<timestamp>.png"
                    ),
                },
                "input_image": {
                    "type": "string",
                    "description": (
                        "Path to an existing image to edit. Required for 'edit' action."
                    ),
                },
                "model": {
                    "type": "string",
                    "enum": ["flash", "pro", "default"],
                    "description": (
                        "Model to use. 'flash' = fast generation, "
                        "'pro' = highest quality, 'default' = balanced. "
                        "Default: 'flash'."
                    ),
                },
                "aspect_ratio": {
                    "type": "string",
                    "enum": ["1:1", "3:4", "4:3", "9:16", "16:9"],
                    "description": "Aspect ratio for the generated image. Default: '1:1'.",
                },
                "image_size": {
                    "type": "string",
                    "enum": ["512", "1024", "2048", "4096"],
                    "description": "Image resolution (width in pixels). Default: '1024'.",
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

        model_key = kwargs.get("model", "flash")
        model_name = MODELS.get(model_key, MODELS["flash"])

        aspect_ratio = kwargs.get("aspect_ratio", "1:1")
        if aspect_ratio not in VALID_ASPECT_RATIOS:
            aspect_ratio = "1:1"

        image_size = kwargs.get("image_size", "1024")
        if image_size not in VALID_SIZES:
            image_size = "1024"

        # Build output path
        output_path = kwargs.get("output_path", "")
        if not output_path:
            output_dir = Path.home() / "plutus_output"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(output_dir / f"image_{int(time.time())}.png")
        else:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        if action == "generate":
            return await self._generate(
                client, types, model_name, prompt, output_path, aspect_ratio, image_size
            )
        elif action == "edit":
            input_image = kwargs.get("input_image", "")
            if not input_image:
                return "Error: 'input_image' path is required for edit action"
            if not Path(input_image).exists():
                return f"Error: Input image not found: {input_image}"
            return await self._edit(
                client, types, model_name, prompt, input_image, output_path,
                aspect_ratio, image_size,
            )
        else:
            return f"Error: Unknown action '{action}'. Use 'generate' or 'edit'."

    async def _generate(
        self, client: Any, types: Any, model: str, prompt: str,
        output_path: str, aspect_ratio: str, image_size: str,
    ) -> str:
        """Generate an image from a text prompt."""
        import asyncio

        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                    image_config=types.ImageConfig(
                        aspect_ratio=aspect_ratio,
                        image_size=image_size,
                    ),
                ),
            )

            return self._save_image_response(response, output_path)

        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            return f"Error generating image: {e}"

    async def _edit(
        self, client: Any, types: Any, model: str, prompt: str,
        input_image: str, output_path: str, aspect_ratio: str, image_size: str,
    ) -> str:
        """Edit an existing image with a text prompt."""
        import asyncio

        try:
            from PIL import Image
        except ImportError:
            return "Error: Pillow package not installed. Install with: pip install Pillow"

        try:
            img = Image.open(input_image)

            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model,
                contents=[prompt, img],
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                    image_config=types.ImageConfig(
                        aspect_ratio=aspect_ratio,
                        image_size=image_size,
                    ),
                ),
            )

            return self._save_image_response(response, output_path)

        except Exception as e:
            logger.error(f"Image editing failed: {e}")
            return f"Error editing image: {e}"

    def _save_image_response(self, response: Any, output_path: str) -> str:
        """Extract and save image from the API response."""
        text_parts = []

        if not response.candidates or not response.candidates[0].content.parts:
            return "Error: No image was generated. The model returned an empty response."

        for part in response.candidates[0].content.parts:
            if hasattr(part, "text") and part.text:
                text_parts.append(part.text)
            elif hasattr(part, "inline_data") and part.inline_data:
                # Save the image
                image_data = part.inline_data.data
                with open(output_path, "wb") as f:
                    f.write(image_data)

                result = f"Image saved to: {output_path}"
                if text_parts:
                    result += f"\nModel notes: {' '.join(text_parts)}"
                return result

        if text_parts:
            return (
                f"No image was generated. Model response: {' '.join(text_parts)}"
            )
        return "Error: No image was generated in the response."
