"""Session Registry — manages multiple concurrent agent sessions.

Each session has its own AgentRuntime instance and asyncio.Lock so that
multiple conversations can run fully in parallel without blocking each other.

Special connector sessions (telegram, whatsapp, discord, email) are
pre-created at startup and persist indefinitely.  User-created sessions
are created on demand and can be closed when no longer needed.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("plutus.session_registry")

# Well-known connector session IDs — these are created automatically at startup
CONNECTOR_SESSIONS: dict[str, str] = {
    "telegram": "session_telegram",
    "whatsapp": "session_whatsapp",
    "discord": "session_discord",
    "email": "session_email",
}

# Human-readable display names for sessions
SESSION_DISPLAY_NAMES: dict[str, str] = {
    "session_telegram": "Telegram",
    "session_whatsapp": "WhatsApp",
    "session_discord": "Discord",
    "session_email": "Email",
}

# Emoji icons for sessions
SESSION_ICONS: dict[str, str] = {
    "session_telegram": "✈️",
    "session_whatsapp": "💬",
    "session_discord": "🎮",
    "session_email": "📧",
}


@dataclass
class Session:
    """Represents a single agent session."""

    session_id: str
    agent: Any  # AgentRuntime
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    conversation_id: str | None = None
    display_name: str = "Chat"
    icon: str = "💬"
    is_connector: bool = False
    connector_name: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_active: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_processing: bool = False

    def touch(self) -> None:
        """Update last_active timestamp."""
        self.last_active = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "display_name": self.display_name,
            "icon": self.icon,
            "is_connector": self.is_connector,
            "connector_name": self.connector_name,
            "conversation_id": self.conversation_id,
            "is_processing": self.is_processing,
            "created_at": self.created_at.isoformat(),
            "last_active": self.last_active.isoformat(),
        }


class SessionRegistry:
    """Registry of all active agent sessions.

    Thread-safe for asyncio use.  All public methods are coroutine-safe.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._registry_lock = asyncio.Lock()
        self._agent_factory: Any = None  # set via set_agent_factory()

    def set_agent_factory(self, factory: Any) -> None:
        """Set the callable used to create new AgentRuntime instances.

        The factory should be an async callable that returns an AgentRuntime.
        Signature: async factory(session_id: str, connector_name: str | None) -> AgentRuntime
        """
        self._agent_factory = factory

    async def create_session(
        self,
        session_id: str | None = None,
        display_name: str = "New Chat",
        icon: str = "💬",
        is_connector: bool = False,
        connector_name: str | None = None,
    ) -> Session:
        """Create and register a new session.

        If session_id is None, a random UUID-based ID is generated.
        Returns the existing session if session_id already exists.
        """
        if session_id is None:
            session_id = f"session_{uuid.uuid4().hex[:12]}"

        async with self._registry_lock:
            if session_id in self._sessions:
                return self._sessions[session_id]

            if self._agent_factory is None:
                raise RuntimeError("SessionRegistry: agent_factory not set")

            agent = await self._agent_factory(
                session_id=session_id,
                connector_name=connector_name,
            )

            # Start a fresh conversation for this session, tagging
            # connector conversations with their platform name so the
            # conversation history list can display the right icon.
            conv_metadata = (
                {"connector_name": connector_name} if connector_name else None
            )
            conv_id = await agent.conversation.start_conversation(
                metadata=conv_metadata,
            )

            session = Session(
                session_id=session_id,
                agent=agent,
                conversation_id=conv_id,
                display_name=display_name,
                icon=icon,
                is_connector=is_connector,
                connector_name=connector_name,
            )
            self._sessions[session_id] = session
            logger.info(
                f"Session created: {session_id!r} ({display_name!r}), "
                f"conversation_id={conv_id!r}"
            )
            return session

    async def get_or_create(
        self,
        session_id: str,
        display_name: str = "Chat",
        icon: str = "💬",
        is_connector: bool = False,
        connector_name: str | None = None,
    ) -> Session:
        """Get an existing session or create it if it doesn't exist."""
        if session_id in self._sessions:
            return self._sessions[session_id]
        return await self.create_session(
            session_id=session_id,
            display_name=display_name,
            icon=icon,
            is_connector=is_connector,
            connector_name=connector_name,
        )

    def get(self, session_id: str) -> Session | None:
        """Get a session by ID (synchronous, no lock needed for reads)."""
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[dict[str, Any]]:
        """Return a list of all sessions as dicts, sorted by last_active desc."""
        sessions = sorted(
            self._sessions.values(),
            key=lambda s: s.last_active,
            reverse=True,
        )
        return [s.to_dict() for s in sessions]

    async def close_session(self, session_id: str) -> bool:
        """Close and remove a session.

        Connector sessions cannot be closed — they persist for the lifetime
        of the Plutus process.  Returns True if the session was removed.
        """
        async with self._registry_lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            if session.is_connector:
                logger.warning(
                    f"Attempted to close connector session {session_id!r} — ignored"
                )
                return False
            # Cancel any in-progress task
            try:
                session.agent.cancel()
            except Exception:
                pass
            del self._sessions[session_id]
            logger.info(f"Session closed: {session_id!r}")
            return True

    async def new_conversation_in_session(self, session_id: str) -> str | None:
        """Start a new conversation within an existing session.

        Returns the new conversation_id, or None if the session doesn't exist.
        """
        session = self._sessions.get(session_id)
        if not session:
            return None
        conv_metadata = (
            {"connector_name": session.connector_name}
            if session.connector_name
            else None
        )
        conv_id = await session.agent.conversation.start_conversation(
            metadata=conv_metadata,
        )
        session.conversation_id = conv_id
        session.touch()
        logger.info(
            f"New conversation in session {session_id!r}: {conv_id!r}"
        )
        return conv_id

    def reload_all_models(self) -> None:
        """Hot-reload model config on ALL session agents.

        Called by the config update route when the user changes the model
        via the CommandCenter.  Without this, only the global agent would
        be reloaded while session agents keep using the old provider/model.
        """
        count = 0
        for session in self._sessions.values():
            try:
                session.agent.reload_model()
                count += 1
            except Exception as exc:
                logger.warning(
                    f"Failed to reload model for session {session.session_id!r}: {exc}"
                )
        logger.info(f"Reloaded model config on {count} session agent(s)")

    async def ensure_connector_sessions(self) -> None:
        """Create all connector sessions if they don't already exist."""
        for connector_name, session_id in CONNECTOR_SESSIONS.items():
            if session_id not in self._sessions:
                display_name = SESSION_DISPLAY_NAMES.get(session_id, connector_name.title())
                icon = SESSION_ICONS.get(session_id, "🔌")
                await self.create_session(
                    session_id=session_id,
                    display_name=display_name,
                    icon=icon,
                    is_connector=True,
                    connector_name=connector_name,
                )
                logger.info(f"Connector session ready: {session_id!r}")


# Module-level singleton
_registry: SessionRegistry | None = None


def get_registry() -> SessionRegistry:
    """Get the global SessionRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = SessionRegistry()
    return _registry
