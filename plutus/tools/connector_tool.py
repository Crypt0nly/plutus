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
            "Telegram, Email, WhatsApp, or Discord. "
            "Use action='list' to see available connectors. "
            "Use action='send' with service='telegram' to send a Telegram message. "
            "Use action='send_file' with service='telegram' or service='discord' "
            "and file_path to send a screenshot or file. "
            "Use action='send' with service='email' to send an email "
            "(requires 'to' and 'subject' params). "
            "Use action='send' with service='discord' to send a Discord message "
            "(optional 'channel_id' param). "
            "Use action='manage' with service='discord' to manage the Discord server "
            "(channels, roles, members). "
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
                    "enum": ["send", "send_file", "list", "status", "manage"],
                    "description": (
                        "Action to perform. "
                        "'send' = send a text message. "
                        "'send_file' = send a file or screenshot. "
                        "'list' = list all connectors and their status. "
                        "'status' = check if a specific connector is configured. "
                        "'manage' = manage Discord server (channels, roles, members)."
                    ),
                },
                "service": {
                    "type": "string",
                    "enum": ["telegram", "email", "whatsapp", "discord"],
                    "description": (
                        "Which connector to use. Required for 'send', "
                        "'send_file', 'manage', and 'status' actions."
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
                "channel_id": {
                    "type": "string",
                    "description": (
                        "Discord channel ID to send message to. "
                        "If not specified, uses the default channel."
                    ),
                },
                "discord_action": {
                    "type": "string",
                    "enum": [
                        "list_channels", "create_channel", "delete_channel", "edit_channel",
                        "list_members", "kick_member", "ban_member", "unban_member",
                        "list_roles", "create_role", "delete_role",
                        "assign_role", "remove_role",
                        "delete_message", "purge_messages", "guild_info",
                    ],
                    "description": (
                        "Discord management action. Required when action='manage'."
                    ),
                },
                "target_id": {
                    "type": "string",
                    "description": (
                        "Target ID for Discord management actions "
                        "(user_id, role_id, channel_id, message_id depending on action)."
                    ),
                },
                "name": {
                    "type": "string",
                    "description": "Name for creating channels or roles.",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for moderation actions (kick, ban).",
                },
                "role_id": {
                    "type": "string",
                    "description": "Role ID for assign_role/remove_role actions.",
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

            return await self._send_file(service, file_path, caption, **kwargs)

        elif action == "manage":
            service = kwargs.get("service", "")
            if service != "discord":
                return "Error: 'manage' action is only supported for Discord"
            return await self._manage_discord(**kwargs)

        else:
            return (
                f"Error: Unknown action '{action}'. "
                "Use 'send', 'send_file', 'list', 'status', or 'manage'."
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
                "to set up Telegram, Email, WhatsApp, or Discord."
            )

        return "\n".join(lines)

    def _get_status(self, service: str) -> str:
        connector = self._manager.get(service)
        if not connector:
            return (
                f"Error: Unknown connector '{service}'. "
                "Available: telegram, email, whatsapp, discord"
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
            elif service == "discord":
                if config.get("bot_username"):
                    details.append(f"Bot: {config['bot_username']}")
                if config.get("guild_name"):
                    details.append(f"Server: {config['guild_name']}")
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
                "Available: telegram, email, whatsapp, discord"
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

        elif service == "discord":
            if kwargs.get("channel_id"):
                send_kwargs["channel_id"] = kwargs["channel_id"]

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
        self, service: str, file_path: str, caption: str = "", **kwargs: Any
    ) -> str:
        """Send a file through a connector and broadcast an attachment event."""
        connector = self._manager.get(service)
        if not connector:
            return (
                f"Error: Unknown connector '{service}'. "
                "Available: telegram, email, whatsapp, discord"
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
        elif service == "discord":
            channel_id = kwargs.get("channel_id")
            result = await connector.send_file(
                file_path, caption=caption, channel_id=channel_id
            )
        else:
            return (
                f"Error: send_file is not yet supported for {service}. "
                "Currently only Telegram and Discord support file sending."
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

    async def _manage_discord(self, **kwargs: Any) -> str:
        """Execute a Discord server management action."""
        connector = self._manager.get("discord")
        if not connector:
            return "Error: Discord connector not available"
        if not connector.is_configured:
            return (
                "Error: Discord is not configured. "
                "The user needs to set it up in the Connectors tab first."
            )

        discord_action = kwargs.get("discord_action", "")
        if not discord_action:
            return (
                "Error: 'discord_action' is required. Options: "
                "list_channels, create_channel, delete_channel, edit_channel, "
                "list_members, kick_member, ban_member, unban_member, "
                "list_roles, create_role, delete_role, assign_role, remove_role, "
                "delete_message, purge_messages, guild_info"
            )

        target_id = kwargs.get("target_id", "")
        name = kwargs.get("name", "")
        reason = kwargs.get("reason", "")
        role_id = kwargs.get("role_id", "")
        channel_id = kwargs.get("channel_id", "")

        try:
            if discord_action == "guild_info":
                result = await connector.get_guild_info()
            elif discord_action == "list_channels":
                result = await connector.list_channels()
            elif discord_action == "create_channel":
                if not name:
                    return "Error: 'name' is required to create a channel"
                result = await connector.create_channel(name, **kwargs)
            elif discord_action == "delete_channel":
                if not target_id:
                    return "Error: 'target_id' (channel_id) is required"
                result = await connector.delete_channel(int(target_id))
            elif discord_action == "edit_channel":
                if not target_id:
                    return "Error: 'target_id' (channel_id) is required"
                result = await connector.edit_channel(int(target_id), **kwargs)
            elif discord_action == "list_members":
                result = await connector.list_members()
            elif discord_action == "kick_member":
                if not target_id:
                    return "Error: 'target_id' (user_id) is required"
                result = await connector.kick_member(int(target_id), reason=reason)
            elif discord_action == "ban_member":
                if not target_id:
                    return "Error: 'target_id' (user_id) is required"
                result = await connector.ban_member(int(target_id), reason=reason)
            elif discord_action == "unban_member":
                if not target_id:
                    return "Error: 'target_id' (user_id) is required"
                result = await connector.unban_member(int(target_id))
            elif discord_action == "list_roles":
                result = await connector.list_roles()
            elif discord_action == "create_role":
                if not name:
                    return "Error: 'name' is required to create a role"
                result = await connector.create_role(name, **kwargs)
            elif discord_action == "delete_role":
                if not target_id:
                    return "Error: 'target_id' (role_id) is required"
                result = await connector.delete_role(int(target_id))
            elif discord_action == "assign_role":
                if not target_id:
                    return "Error: 'target_id' (user_id) is required"
                if not role_id:
                    return "Error: 'role_id' is required"
                result = await connector.assign_role(int(target_id), int(role_id))
            elif discord_action == "remove_role":
                if not target_id:
                    return "Error: 'target_id' (user_id) is required"
                if not role_id:
                    return "Error: 'role_id' is required"
                result = await connector.remove_role(int(target_id), int(role_id))
            elif discord_action == "delete_message":
                if not channel_id:
                    return "Error: 'channel_id' is required"
                if not target_id:
                    return "Error: 'target_id' (message_id) is required"
                result = await connector.delete_message(int(channel_id), int(target_id))
            elif discord_action == "purge_messages":
                if not channel_id:
                    return "Error: 'channel_id' is required"
                limit = int(kwargs.get("limit", 10))
                result = await connector.purge_messages(int(channel_id), limit=limit)
            else:
                return f"Error: Unknown discord_action '{discord_action}'"

            if result.get("success"):
                # Format the result nicely
                import json
                display = {k: v for k, v in result.items() if k != "success"}
                if display.get("message") and len(display) == 1:
                    return f"Discord: {display['message']}"
                dumped = json.dumps(display, indent=2, default=str)
                return (
                    f"Discord action '{discord_action}' "
                    f"succeeded:\n{dumped}"
                )
            else:
                err = result.get("message", "Unknown error")
                return (
                    f"Discord action '{discord_action}' "
                    f"failed: {err}"
                )

        except Exception as e:
            return f"Error executing Discord action '{discord_action}': {str(e)}"

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
