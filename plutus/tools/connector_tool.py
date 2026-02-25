"""Connector tool — allows the agent to send messages and files through configured connectors.

The agent can use this tool to:
  - Send a message via Telegram, Email, or WhatsApp
  - Send a file or screenshot via Telegram
  - List available connectors and their status
  - Check if a connector is configured

Usage examples (from the agent):
  connector(action="send", service="telegram", message="Hello from Plutus!")
  connector(action="send_file", service="telegram", file_path="/path/to/screenshot.png")
  connector(action="send", service="email", message="Report", to="a@b.com", subject="Report")
  connector(action="list")
  connector(action="status", service="telegram")
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from plutus.tools.base import Tool

logger = logging.getLogger("plutus.tools.connector")

# Image extensions that should be sent as photos (not documents)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


class ConnectorTool(Tool):
    """Tool for sending messages and files through external connectors."""

    def __init__(self, connector_manager: Any):
        self._manager = connector_manager

    @property
    def name(self) -> str:
        return "connector"

    @property
    def description(self) -> str:
        return (
            "Send messages or files to the user through external services like "
            "Telegram, Email, or WhatsApp. "
            "Use action='list' to see available connectors. "
            "Use action='send' with service='telegram' to send a Telegram message. "
            "Use action='send_file' with service='telegram' and file_path to send "
            "a screenshot or file (images are displayed inline in Telegram). "
            "Use action='send' with service='email' to send an email "
            "(requires 'to' and 'subject' params). "
            "The user configures connectors in the Connectors tab — you just "
            "send messages and files through them."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["send", "send_file", "list", "status"],
                    "description": (
                        "Action to perform. "
                        "'send' = send a text message. "
                        "'send_file' = send a file or screenshot. "
                        "'list' = list all connectors and their status. "
                        "'status' = check if a specific connector is configured."
                    ),
                },
                "service": {
                    "type": "string",
                    "enum": ["telegram", "email", "whatsapp"],
                    "description": (
                        "Which connector to use. Required for 'send', "
                        "'send_file', and 'status' actions."
                    ),
                },
                "message": {
                    "type": "string",
                    "description": (
                        "The message text to send. Required for 'send' action."
                    ),
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "Absolute path to the file to send. Required for "
                        "'send_file' action. Images (.png, .jpg, etc.) are "
                        "sent as photos in Telegram."
                    ),
                },
                "caption": {
                    "type": "string",
                    "description": (
                        "Optional caption for the file (max 1024 chars). "
                        "Used with 'send_file' action."
                    ),
                },
                "to": {
                    "type": "string",
                    "description": (
                        "Recipient email address. Required for email 'send' action."
                    ),
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line. Used for email 'send' action.",
                },
                "contact": {
                    "type": "string",
                    "description": (
                        "WhatsApp contact name. Required for WhatsApp 'send' action."
                    ),
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
            service = kwargs.pop("service", "")
            message = kwargs.pop("message", "")

            if not service:
                return "Error: 'service' parameter is required for send action"
            if not message:
                return "Error: 'message' parameter is required for send action"

            return await self._send_message(service, message, **kwargs)

        elif action == "send_file":
            service = kwargs.get("service", "")
            file_path = kwargs.get("file_path", "")
            caption = kwargs.get("caption", "")

            if not service:
                return "Error: 'service' parameter is required for send_file action"
            if not file_path:
                return "Error: 'file_path' parameter is required for send_file action"

            return await self._send_file(service, file_path, caption)

        else:
            return (
                f"Error: Unknown action '{action}'. "
                "Use 'send', 'send_file', 'list', or 'status'."
            )

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
            lines.append(
                f"\nReady to send: "
                f"{', '.join(c['display_name'] for c in configured)}"
            )
        else:
            lines.append(
                "\nNo connectors configured yet. "
                "Tell the user to go to the Connectors tab in the UI "
                "to set up Telegram, Email, or WhatsApp."
            )

        return "\n".join(lines)

    def _get_status(self, service: str) -> str:
        connector = self._manager.get(service)
        if not connector:
            return (
                f"Error: Unknown connector '{service}'. "
                "Available: telegram, email, whatsapp"
            )

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
            return (
                f"{connector.display_name} is configured and ready{detail_str}"
            )
        else:
            return (
                f"{connector.display_name} is NOT configured. "
                f"Tell the user to go to Settings > Connectors in the UI "
                f"to set it up."
            )

    async def _send_message(self, service: str, message: str, **kwargs: Any) -> str:
        connector = self._manager.get(service)
        if not connector:
            return (
                f"Error: Unknown connector '{service}'. "
                "Available: telegram, email, whatsapp"
            )

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
                return (
                    "Error: 'to' (recipient email) is required for email messages"
                )
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
            return (
                f"Message sent via {connector.display_name}: "
                f"{result.get('message', 'OK')}"
            )
        else:
            return (
                f"Failed to send via {connector.display_name}: "
                f"{result.get('message', 'Unknown error')}"
            )

    async def _send_file(
        self, service: str, file_path: str, caption: str = ""
    ) -> str:
        """Send a file through a connector and broadcast an attachment event."""
        connector = self._manager.get(service)
        if not connector:
            return (
                f"Error: Unknown connector '{service}'. "
                "Available: telegram, email, whatsapp"
            )

        if not connector.is_configured:
            return (
                f"Error: {connector.display_name} is not configured. "
                f"The user needs to set it up in the Connectors tab first."
            )

        # Validate file exists
        path = Path(file_path)
        if not path.exists():
            return f"Error: File not found: {file_path}"
        if not path.is_file():
            return f"Error: Not a file: {file_path}"

        ext = path.suffix.lower()
        is_image = ext in IMAGE_EXTENSIONS
        file_name = path.name
        file_size = path.stat().st_size

        # Send through the connector
        if service == "telegram":
            if is_image:
                result = await connector.send_photo(
                    file_path, caption=caption
                )
            else:
                result = await connector.send_document(
                    file_path, caption=caption
                )
        else:
            return (
                f"Error: send_file is not yet supported for {service}. "
                "Currently only Telegram supports file sending."
            )

        if not result.get("success"):
            return (
                f"Failed to send file via {connector.display_name}: "
                f"{result.get('message', 'Unknown error')}"
            )

        # Broadcast attachment event to the web UI via WebSocket
        await self._broadcast_attachment(
            file_path=file_path,
            file_name=file_name,
            file_size=file_size,
            is_image=is_image,
            caption=caption,
        )

        return (
            f"{'Photo' if is_image else 'File'} sent via "
            f"{connector.display_name}: {result.get('message', 'OK')}"
        )

    async def _broadcast_attachment(
        self,
        file_path: str,
        file_name: str,
        file_size: int,
        is_image: bool,
        caption: str = "",
    ) -> None:
        """Broadcast an attachment event to the web UI via WebSocket."""
        try:
            from plutus.gateway.ws import manager as ws_manager

            event: dict[str, Any] = {
                "type": "attachment",
                "file_name": file_name,
                "file_path": file_path,
                "file_size": file_size,
                "is_image": is_image,
                "caption": caption,
            }

            # For images, include base64 data so the UI can render inline
            if is_image and file_size < 10 * 1024 * 1024:  # <10MB
                with open(file_path, "rb") as f:
                    event["image_base64"] = base64.b64encode(f.read()).decode()

            await ws_manager.broadcast(event)
        except Exception as e:
            logger.debug(f"Could not broadcast attachment event: {e}")
