"""Plutus Connectors — link Plutus with external messaging services and AI providers."""

from plutus.connectors.ai_providers import (
    AnthropicConnector,
    GeminiConnector,
    OllamaConnector,
    OpenAIConnector,
)
from plutus.connectors.base import BaseConnector, ConnectorManager
from plutus.connectors.discord import DiscordConnector
from plutus.connectors.email import EmailConnector
from plutus.connectors.github import GitHubConnector
from plutus.connectors.google import (
    GmailConnector,
    GoogleCalendarConnector,
    GoogleDriveConnector,
)
from plutus.connectors.telegram import TelegramConnector
from plutus.connectors.web_hosting import NetlifyConnector, VercelConnector
from plutus.connectors.whatsapp import WhatsAppConnector


def create_connector_manager() -> ConnectorManager:
    """Create a ConnectorManager with all built-in connectors registered."""
    mgr = ConnectorManager()

    # AI Providers
    mgr.register(OpenAIConnector())
    mgr.register(AnthropicConnector())
    mgr.register(GeminiConnector())
    mgr.register(OllamaConnector())

    # Messaging Connectors
    mgr.register(TelegramConnector())
    mgr.register(EmailConnector())
    mgr.register(WhatsAppConnector())
    mgr.register(DiscordConnector())

    # Developer Tools
    mgr.register(GitHubConnector())

    # Google Workspace
    mgr.register(GmailConnector())
    mgr.register(GoogleCalendarConnector())
    mgr.register(GoogleDriveConnector())

    # Web Hosting
    mgr.register(VercelConnector())
    mgr.register(NetlifyConnector())

    return mgr


__all__ = [
    "BaseConnector",
    "ConnectorManager",
    "TelegramConnector",
    "EmailConnector",
    "WhatsAppConnector",
    "DiscordConnector",
    "GitHubConnector",
    "OpenAIConnector",
    "AnthropicConnector",
    "GeminiConnector",
    "OllamaConnector",
    "GmailConnector",
    "GoogleCalendarConnector",
    "GoogleDriveConnector",
    "VercelConnector",
    "NetlifyConnector",
    "create_connector_manager",
]
