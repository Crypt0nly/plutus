"""Model-agnostic LLM client powered by LiteLLM.

Supports Anthropic, OpenAI, local models (Ollama), and any OpenAI-compatible endpoint.
"""

from __future__ import annotations

import os
from typing import Any, AsyncIterator

import litellm
from pydantic import BaseModel

from plutus.config import ModelConfig

# Suppress litellm's verbose logging
litellm.suppress_debug_info = True


class ToolDefinition(BaseModel):
    """Tool definition for function calling."""

    name: str
    description: str
    parameters: dict[str, Any]


class ToolCall(BaseModel):
    """A tool call from the LLM response."""

    id: str
    name: str
    arguments: dict[str, Any]


class LLMMessage(BaseModel):
    role: str  # "system", "user", "assistant", "tool"
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class LLMResponse(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] = []
    finish_reason: str | None = None
    usage: dict[str, int] = {}


class LLMClient:
    """Unified LLM client with tool-calling support."""

    def __init__(self, config: ModelConfig):
        self._config = config
        self._model = self._resolve_model()
        self._ensure_api_key()

    def _resolve_model(self) -> str:
        """Map provider/model to litellm model string."""
        provider = self._config.provider
        model = self._config.model

        if provider == "anthropic":
            return f"anthropic/{model}" if not model.startswith("anthropic/") else model
        if provider == "openai":
            return f"openai/{model}" if not model.startswith("openai/") else model
        if provider == "ollama":
            return f"ollama/{model}" if not model.startswith("ollama/") else model
        # Custom / OpenAI-compatible
        return model

    def _ensure_api_key(self) -> None:
        """Verify the API key env var is set."""
        key = os.environ.get(self._config.api_key_env, "")
        if not key and self._config.provider not in ("ollama", "local"):
            raise EnvironmentError(
                f"Missing API key: set the {self._config.api_key_env} environment variable. "
                f"Run `plutus setup` to configure."
            )

    def _build_kwargs(self, **overrides: Any) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
        }
        if self._config.base_url:
            kwargs["api_base"] = self._config.base_url
        kwargs.update(overrides)
        return kwargs

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a completion request to the LLM."""
        call_kwargs = self._build_kwargs(**kwargs)
        call_kwargs["messages"] = messages

        if tools:
            call_kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]

        response = await litellm.acompletion(**call_kwargs)
        return self._parse_response(response)

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream a completion response, yielding text chunks."""
        call_kwargs = self._build_kwargs(stream=True, **kwargs)
        call_kwargs["messages"] = messages

        if tools:
            call_kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]

        response = await litellm.acompletion(**call_kwargs)
        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    def _parse_response(self, response: Any) -> LLMResponse:
        choice = response.choices[0]
        message = choice.message

        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                import json

                args = tc.function.arguments
                if isinstance(args, str):
                    args = json.loads(args)
                tool_calls.append(
                    ToolCall(id=tc.id, name=tc.function.name, arguments=args)
                )

        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens or 0,
                "completion_tokens": response.usage.completion_tokens or 0,
                "total_tokens": response.usage.total_tokens or 0,
            }

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            usage=usage,
        )
