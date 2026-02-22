"""Plutus Connectors — link Plutus with external messaging services."""

from plutus.connectors.base import BaseConnector, ConnectorManager
from plutus.connectors.telegram import TelegramConnector
from plutus.connectors.email import EmailConnector
from plutus.connectors.whatsapp import WhatsAppConnector


def create_connector_manager() -> ConnectorManager:
    """Create a ConnectorManager with all built-in connectors registered."""
    mgr = ConnectorManager()
    mgr.register(TelegramConnector())
    mgr.register(EmailConnector())
    mgr.register(WhatsAppConnector())
    return mgr


__all__ = [
    "BaseConnector",
    "ConnectorManager",
    "TelegramConnector",
    "EmailConnector",
    "WhatsAppConnector",
    "create_connector_manager",
]
