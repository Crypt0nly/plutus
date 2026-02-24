"""Model-agnostic LLM client powered by LiteLLM.

Supports Anthropic, OpenAI, local models (Ollama), and any OpenAI-compatible endpoint.
"""

from __future__ import annotations

import logging
import os
from typing import Any, AsyncIterator

import litellm
from pydantic import BaseModel

from plutus.config import ModelConfig, SecretsStore

logger = logging.getLogger("plutus.llm")

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

    def __init__(self, config: ModelConfig, secrets: SecretsStore | None = None):
        self._config = config
        self._secrets = secrets or SecretsStore()
        self._model = self._resolve_model()
        self._key_available = self._ensure_api_key()

    @property
    def key_configured(self) -> bool:
        """Whether an API key is available for the current provider."""
        return self._key_available

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

    def _ensure_api_key(self) -> bool:
        """Resolve the API key from env var or secrets store.

        Returns True if a key is available, False otherwise.
        Does NOT crash — the server can start without a key and prompt the user.
        """
        if self._config.provider in ("ollama", "local"):
            return True

        # Try secrets store (checks env var first, then file)
        key = self._secrets.get_key(self._config.provider)
        if key:
            # Ensure it's in os.environ for LiteLLM
            env_var = self._config.api_key_env
            if not os.environ.get(env_var):
                os.environ[env_var] = key
            return True

        logger.warning(
            f"No API key found for {self._config.provider}. "
            f"Set {self._config.api_key_env} or use the web UI to configure."
        )
        return False

    def reload_key(self) -> bool:
        """Re-check for API key availability (called after user sets a key via UI)."""
        self._key_available = self._ensure_api_key()
        return self._key_available

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

    @staticmethod
    def _sanitize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Ensure every tool_use has a matching tool_result immediately after.

        Anthropic requires strict pairing: each assistant message with tool_calls
        must be followed by tool result messages for every tool_call_id.
        If any are missing, we inject synthetic tool_result messages to prevent
        API errors.
        """
        sanitized: list[dict[str, Any]] = []
        for i, msg in enumerate(messages):
            sanitized.append(msg)

            # Check if this is an assistant message with tool_calls
            tool_calls = msg.get("tool_calls", [])
            if msg.get("role") == "assistant" and tool_calls:
                # Collect the tool_call IDs that need results
                expected_ids = set()
                for tc in tool_calls:
                    tc_id = tc.get("id")
                    if tc_id:
                        expected_ids.add(tc_id)

                # Look ahead for tool_result messages that follow
                found_ids = set()
                for j in range(i + 1, len(messages)):
                    next_msg = messages[j]
                    if next_msg.get("role") == "tool":
                        tcid = next_msg.get("tool_call_id")
                        if tcid in expected_ids:
                            found_ids.add(tcid)
                    else:
                        break  # Stop at first non-tool message

                # Inject synthetic results for any missing tool_call_ids
                missing = expected_ids - found_ids
                for tc_id in missing:
                    logger.warning(f"Injecting synthetic tool_result for orphaned tool_use {tc_id}")
                    # We need to insert AFTER the current message but BEFORE
                    # the next non-tool message. Since we're building a new list,
                    # we can't insert into `sanitized` mid-iteration easily.
                    # Instead, we'll do a second pass below.

        # Second pass: ensure pairing
        result: list[dict[str, Any]] = []
        i = 0
        while i < len(sanitized):
            msg = sanitized[i]
            result.append(msg)

            tool_calls = msg.get("tool_calls", [])
            if msg.get("role") == "assistant" and tool_calls:
                expected_ids = set()
                for tc in tool_calls:
                    tc_id = tc.get("id")
                    if tc_id:
                        expected_ids.add(tc_id)

                # Consume following tool messages
                j = i + 1
                while j < len(sanitized) and sanitized[j].get("role") == "tool":
                    tool_msg = sanitized[j]
                    result.append(tool_msg)
                    tcid = tool_msg.get("tool_call_id")
                    if tcid in expected_ids:
                        expected_ids.discard(tcid)
                    j += 1

                # Inject synthetic results for any still-missing IDs
                for tc_id in expected_ids:
                    logger.warning(f"Sanitizer: injecting tool_result for orphaned tool_use {tc_id}")
                    result.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": "[No result available — tool execution was interrupted]",
                    })

                i = j
                continue

            i += 1

        return result

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a completion request to the LLM."""
        call_kwargs = self._build_kwargs(**kwargs)
        call_kwargs["messages"] = self._sanitize_messages(messages)

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
            import json

            for tc in message.tool_calls:
                args = tc.function.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except (json.JSONDecodeError, ValueError) as e:
                        # Tool call arguments were truncated (likely finish_reason=length)
                        # or malformed. Log and pass empty args — the tool will report
                        # a clear error about missing parameters.
                        logger.warning(
                            f"Failed to parse tool call args for {tc.function.name}: {e}. "
                            f"Raw args (first 300 chars): {repr(args[:300])}"
                        )
                        args = {"__parse_error": str(e), "__raw_preview": args[:500]}
                elif args is None:
                    args = {}
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
