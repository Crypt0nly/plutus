from uuid import uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.agent_service import AgentService


class CloudAgentRuntime:
    def __init__(self, user_id: str, session: AsyncSession, config: dict = None):
        self.user_id = user_id
        self.session = session
        self.config = config or {}
        self.agent_service = AgentService(session)

    async def process_message(self, message: str, conversation_id: str = None) -> dict:
        """Main entry point. Creates/loads conversation, calls LLM, returns response dict."""
        if conversation_id is None:
            conversation_id = str(uuid4())
            await self.agent_service.create_conversation(conversation_id, self.user_id)

        await self._save_message(conversation_id, "user", message)

        history = await self.agent_service.get_messages(conversation_id)
        messages = [{"role": m.role, "content": m.content} for m in history]

        system_prompt = await self._build_system_prompt()
        response_text = await self._call_llm(messages, system_prompt)

        await self._save_message(conversation_id, "assistant", response_text)

        return {
            "response": response_text,
            "conversation_id": conversation_id,
        }

    async def _call_llm(self, messages: list[dict], system_prompt: str = "") -> str:
        """Call Anthropic or OpenAI based on config."""
        provider = self.config.get("provider", settings.default_llm_provider)

        if provider == "openai":
            return await self._call_openai(messages, system_prompt)
        return await self._call_anthropic(messages, system_prompt)

    async def _call_anthropic(self, messages: list[dict], system_prompt: str) -> str:
        api_key = settings.anthropic_api_key
        model = self.config.get("model", "claude-sonnet-4-20250514")
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                json={
                    "model": model,
                    "max_tokens": 4096,
                    "system": system_prompt,
                    "messages": messages,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]

    async def _call_openai(self, messages: list[dict], system_prompt: str) -> str:
        api_key = settings.openai_api_key
        model = self.config.get("model", "gpt-4o")
        all_messages = [{"role": "system", "content": system_prompt}] + messages
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "messages": all_messages},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def _build_system_prompt(self) -> str:
        """Build system prompt with user context, memory facts, available tools."""
        facts = await self.agent_service.get_memory_facts(self.user_id)
        facts_block = "\n".join(f"- {f}" for f in facts) if facts else "None"
        tools_block = await self.agent_service.get_available_tools(self.user_id)
        return (
            "You are Plutus, a personal AI assistant running in the cloud.\n\n"
            f"User ID: {self.user_id}\n\n"
            f"Memory facts about this user:\n{facts_block}\n\n"
            f"Available tools:\n{tools_block}"
        )

    async def _save_message(self, conv_id: str, role: str, content: str) -> None:
        """Save a message to the database."""
        await self.agent_service.save_message(conv_id, role, content, user_id=self.user_id)
