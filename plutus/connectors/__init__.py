"""Plutus Connectors — link Plutus with external messaging services."""

from plutus.connectors.base import BaseConnector, ConnectorManager
from plutus.connectors.discord import DiscordConnector
from plutus.connectors.email import EmailConnector
from plutus.connectors.telegram import TelegramConnector
from plutus.connectors.whatsapp import WhatsAppConnector


def create_connector_manager() -> ConnectorManager:
    """Create a ConnectorManager with all built-in connectors registered."""
    mgr = ConnectorManager()
    mgr.register(TelegramConnector())
    mgr.register(EmailConnector())
    mgr.register(WhatsAppConnector())
    mgr.register(DiscordConnector())
    return mgr


__all__ = [
    "BaseConnector",
    "ConnectorManager",
    "TelegramConnector",
    "EmailConnector",
    "WhatsAppConnector",
    "DiscordConnector",
    "create_connector_manager",
]
