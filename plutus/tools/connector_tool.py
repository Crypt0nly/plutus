"""Connector tool — allows the agent to send messages through configured connectors.

The agent can use this tool to:
  - Send a message via Telegram, Email, or WhatsApp
  - List available connectors and their status
  - Check if a connector is configured

Usage examples (from the agent):
  connector(action="send", service="telegram", message="Hello from Plutus!")
  connector(action="send", service="email", message="Report attached", to="user@example.com", subject="Daily Report")
  connector(action="list")
  connector(action="status", service="telegram")
"""

from __future__ import annotations

import logging
from typing import Any

from plutus.tools.base import Tool

logger = logging.getLogger("plutus.tools.connector")


class ConnectorTool(Tool):
    """Tool for sending messages through external connectors (Telegram, Email, WhatsApp)."""

    def __init__(self, connector_manager: Any):
        self._manager = connector_manager

    @property
    def name(self) -> str:
        return "connector"

    @property
    def description(self) -> str:
        return (
            "Send messages to the user through external services like Telegram, Email, or WhatsApp. "
            "Use action='list' to see available connectors. "
            "Use action='send' with service='telegram' to send a Telegram message. "
            "Use action='send' with service='email' to send an email (requires 'to' and 'subject' params). "
            "The user configures connectors in the Connectors tab — you just send messages through them."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["send", "list", "status"],
                    "description": (
                        "Action to perform. "
                        "'send' = send a message through a connector. "
                        "'list' = list all connectors and their status. "
                        "'status' = check if a specific connector is configured."
                    ),
                },
                "service": {
                    "type": "string",
                    "enum": ["telegram", "email", "whatsapp"],
                    "description": "Which connector to use. Required for 'send' and 'status' actions.",
                },
                "message": {
                    "type": "string",
                    "description": "The message text to send. Required for 'send' action.",
                },
                "to": {
                    "type": "string",
                    "description": "Recipient email address. Required for email 'send' action.",
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line. Used for email 'send' action.",
                },
                "contact": {
                    "type": "string",
                    "description": "WhatsApp contact name. Required for WhatsApp 'send' action.",
                },
                "parse_mode": {
                    "type": "string",
                    "enum": ["HTML", "Markdown", "plain"],
                    "description": "Message formatting for Telegram. Default: HTML.",
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "list")

        if action == "list":
            return self._list_connectors()

        elif action == "status":
            service = kwargs.get("service", "")
            if not service:
                return "Error: 'service' parameter is required for status action"
            return self._get_status(service)

        elif action == "send":
            service = kwargs.get("service", "")
            message = kwargs.get("message", "")

            if not service:
                return "Error: 'service' parameter is required for send action"
            if not message:
                return "Error: 'message' parameter is required for send action"

            return await self._send_message(service, message, **kwargs)

        else:
            return f"Error: Unknown action '{action}'. Use 'send', 'list', or 'status'."

    def _list_connectors(self) -> str:
        connectors = self._manager.list_all()
        if not connectors:
            return "No connectors available."

        lines = ["Available connectors:\n"]
        for c in connectors:
            status = "Connected" if c["configured"] else "Not configured"
            lines.append(f"  - {c['display_name']} ({c['name']}): {status}")

        configured = [c for c in connectors if c["configured"]]
        if configured:
            lines.append(f"\nReady to send: {', '.join(c['display_name'] for c in configured)}")
        else:
            lines.append(
                "\nNo connectors configured yet. "
                "Tell the user to go to the Connectors tab in the UI to set up Telegram, Email, or WhatsApp."
            )

        return "\n".join(lines)

    def _get_status(self, service: str) -> str:
        connector = self._manager.get(service)
        if not connector:
            return f"Error: Unknown connector '{service}'. Available: telegram, email, whatsapp"

        if connector.is_configured:
            config = connector.get_config()
            details = []
            if service == "telegram":
                if config.get("bot_username"):
                    details.append(f"Bot: {config['bot_username']}")
                if config.get("chat_id"):
                    details.append(f"Chat ID: {config['chat_id']}")
            elif service == "email":
                if config.get("email"):
                    details.append(f"From: {config['email']}")
            detail_str = f" ({', '.join(details)})" if details else ""
            return f"{connector.display_name} is configured and ready{detail_str}"
        else:
            return (
                f"{connector.display_name} is NOT configured. "
                f"Tell the user to go to Settings > Connectors in the UI to set it up."
            )

    async def _send_message(self, service: str, message: str, **kwargs: Any) -> str:
        connector = self._manager.get(service)
        if not connector:
            return f"Error: Unknown connector '{service}'. Available: telegram, email, whatsapp"

        if not connector.is_configured:
            return (
                f"Error: {connector.display_name} is not configured. "
                f"The user needs to set it up in the Connectors tab first."
            )

        # Build service-specific params
        send_kwargs: dict[str, Any] = {}

        if service == "email":
            to = kwargs.get("to", "")
            if not to:
                return "Error: 'to' (recipient email) is required for email messages"
            send_kwargs["to"] = to
            send_kwargs["subject"] = kwargs.get("subject", "Message from Plutus")
            send_kwargs["html"] = True  # Default to HTML for rich formatting

        elif service == "whatsapp":
            contact = kwargs.get("contact", "")
            if not contact:
                return "Error: 'contact' (WhatsApp contact name) is required"
            send_kwargs["contact"] = contact

        elif service == "telegram":
            parse_mode = kwargs.get("parse_mode", "HTML")
            if parse_mode == "plain":
                parse_mode = ""
            send_kwargs["parse_mode"] = parse_mode

        result = await connector.send_message(message, **send_kwargs)

        if result.get("success"):
            return f"Message sent via {connector.display_name}: {result.get('message', 'OK')}"
        else:
            return f"Failed to send via {connector.display_name}: {result.get('message', 'Unknown error')}"
