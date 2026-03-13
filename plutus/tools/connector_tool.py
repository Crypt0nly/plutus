"""Connector tool — allows the agent to send messages and files through configured connectors.

The agent can use this tool to:
  - Send a message via Telegram, Email, or WhatsApp
  - Send a file or screenshot via Telegram
  - List available connectors and their status
  - Check if a connector is configured
  - Read/send Gmail emails, manage Calendar events, manage Drive files

Usage examples (from the agent):
  connector(action="send", service="telegram", message="Hello from Plutus!")
  connector(action="send_file", service="telegram", file_path="/path/to/screenshot.png")
  connector(action="send", service="email", message="Report", to="a@b.com", subject="Report")
  connector(action="send", service="google_gmail", message="Hello", to="a@b.com", subject="Hi")
  connector(action="google", service="google_gmail",
            google_action="list_messages", query="is:unread")
  connector(action="google", service="google_calendar", google_action="list_events")
  connector(action="google", service="google_calendar", google_action="create_event",
            summary="Meeting", start="2025-01-01T10:00:00Z", end="2025-01-01T11:00:00Z")
  connector(action="google", service="google_drive", google_action="list_files")
  connector(action="google", service="google_drive", google_action="upload_file",
            name="notes.txt", content="Hello world")
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
            "Send messages or files through external services like "
            "Telegram, Email, WhatsApp, Discord, Gmail, Google Calendar, "
            "and Google Drive. "
            "Use action='list' to see available connectors. "
            "Use action='send' with service='telegram' to send a Telegram message. "
            "Use action='send_file' with service='telegram' or service='discord' "
            "and file_path to send a screenshot or file. "
            "Use action='send' with service='email' to send an email "
            "(requires 'to' and 'subject' params). "
            "Use action='send' with service='google_gmail' to send a Gmail email "
            "(requires 'to' and 'subject' params). "
            "Use action='google' to interact with Google services: "
            "service='google_gmail' for reading emails (google_action='list_messages', "
            "'get_message', 'list_labels'), "
            "service='google_calendar' for managing events (google_action='list_events', "
            "'create_event', 'update_event', 'delete_event'), "
            "service='google_drive' for managing files (google_action='list_files', "
            "'get_file', 'upload_file', 'get_file_metadata'). "
            "Use action='manage' with service='discord' to manage the Discord server. "
            "The user configures connectors in the Connectors tab."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "send", "send_file", "list", "status",
                        "manage", "google",
                    ],
                    "description": (
                        "Action to perform. "
                        "'send' = send a text message. "
                        "'send_file' = send a file or screenshot. "
                        "'list' = list all connectors and their status. "
                        "'status' = check if a specific connector is configured. "
                        "'manage' = manage Discord server. "
                        "'google' = interact with Google services "
                        "(Gmail, Calendar, Drive)."
                    ),
                },
                "service": {
                    "type": "string",
                    "enum": [
                        "telegram", "email", "whatsapp", "discord",
                        "google_gmail", "google_calendar", "google_drive",
                    ],
                    "description": (
                        "Which connector to use. Required for 'send', "
                        "'send_file', 'manage', 'google', and 'status' actions."
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
                "google_action": {
                    "type": "string",
                    "enum": [
                        "list_messages", "get_message", "list_labels",
                        "list_events", "create_event", "update_event",
                        "delete_event",
                        "list_files", "get_file", "get_file_metadata",
                        "upload_file",
                    ],
                    "description": (
                        "Google-specific action. Required when action='google'."
                    ),
                },
                "query": {
                    "type": "string",
                    "description": (
                        "Search query for Gmail (e.g. 'is:unread', "
                        "'from:alice@example.com') or Drive "
                        "(e.g. 'name contains \"report\"')."
                    ),
                },
                "message_id": {
                    "type": "string",
                    "description": "Gmail message ID for get_message.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max results to return (default 10).",
                },
                "summary": {
                    "type": "string",
                    "description": "Event title for create_event.",
                },
                "start": {
                    "type": "string",
                    "description": (
                        "Event start time in ISO 8601 format "
                        "(e.g. '2025-01-15T10:00:00-05:00')."
                    ),
                },
                "end": {
                    "type": "string",
                    "description": (
                        "Event end time in ISO 8601 format."
                    ),
                },
                "event_description": {
                    "type": "string",
                    "description": "Event description for create_event.",
                },
                "location": {
                    "type": "string",
                    "description": "Event location for create_event.",
                },
                "event_id": {
                    "type": "string",
                    "description": (
                        "Calendar event ID for update_event/delete_event."
                    ),
                },
                "calendar_id": {
                    "type": "string",
                    "description": (
                        "Calendar ID (default 'primary'). Use for "
                        "calendar operations."
                    ),
                },
                "file_id": {
                    "type": "string",
                    "description": (
                        "Drive file ID for get_file/get_file_metadata."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": (
                        "File content for upload_file action."
                    ),
                },
                "mime_type": {
                    "type": "string",
                    "description": (
                        "MIME type for upload_file (default 'text/plain')."
                    ),
                },
                "updates": {
                    "type": "object",
                    "description": (
                        "Updates dict for update_event "
                        "(e.g. {\"summary\": \"New title\"})."
                    ),
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

        elif action == "google":
            service = kwargs.get("service", "")
            if not service:
                return "Error: 'service' is required (google_gmail, google_calendar, google_drive)"
            return await self._handle_google(service, **kwargs)

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
                "Available: telegram, email, whatsapp, discord, "
                "google_gmail, google_calendar, google_drive"
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
                "Available: telegram, email, whatsapp, discord, "
                "google_gmail, google_calendar, google_drive"
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

        elif service == "google_gmail":
            to = kwargs.get("to", "")
            if not to:
                return (
                    "Error: 'to' (recipient email) is required for Gmail messages"
                )
            send_kwargs["to"] = to
            send_kwargs["subject"] = kwargs.get("subject", "Message from Plutus")

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
                "Available: telegram, email, whatsapp, discord, "
                "google_gmail, google_calendar, google_drive"
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

    async def _handle_google(self, service: str, **kwargs: Any) -> str:
        """Handle Google-specific actions (Gmail, Calendar, Drive)."""
        connector = self._manager.get(service)
        if not connector:
            return (
                f"Error: Unknown Google service '{service}'. "
                "Available: google_gmail, google_calendar, google_drive"
            )
        if not connector.is_configured:
            return (
                f"Error: {connector.display_name} is not authorized. "
                "The user needs to connect it in the Connectors tab."
            )

        google_action = kwargs.get("google_action", "")
        if not google_action:
            return "Error: 'google_action' is required for Google services"

        import json as _json

        try:
            result: dict[str, Any] = {}

            # ── Gmail ──
            if service == "google_gmail":
                if google_action == "list_messages":
                    query = kwargs.get("query", "")
                    max_results = int(kwargs.get("max_results", 10))
                    result = await connector.list_messages(query, max_results)
                elif google_action == "get_message":
                    mid = kwargs.get("message_id", "")
                    if not mid:
                        return "Error: 'message_id' is required"
                    result = await connector.get_message(mid)
                elif google_action == "list_labels":
                    result = await connector.list_labels()
                else:
                    return f"Error: Unknown gmail action '{google_action}'"

            # ── Calendar ──
            elif service == "google_calendar":
                cal_id = kwargs.get("calendar_id", "primary")

                if google_action == "list_events":
                    max_results = int(kwargs.get("max_results", 10))
                    result = await connector.list_events(
                        calendar_id=cal_id,
                        time_min=kwargs.get("start"),
                        time_max=kwargs.get("end"),
                        max_results=max_results,
                    )
                elif google_action == "create_event":
                    summary = kwargs.get("summary", "")
                    start = kwargs.get("start", "")
                    end = kwargs.get("end", "")
                    if not summary or not start or not end:
                        return (
                            "Error: 'summary', 'start', and 'end' "
                            "are required for create_event"
                        )
                    result = await connector.create_event(
                        summary=summary,
                        start=start,
                        end=end,
                        calendar_id=cal_id,
                        description=kwargs.get(
                            "event_description", ""
                        ),
                        location=kwargs.get("location", ""),
                    )
                elif google_action == "update_event":
                    eid = kwargs.get("event_id", "")
                    updates = kwargs.get("updates", {})
                    if not eid:
                        return "Error: 'event_id' is required"
                    if not updates:
                        return "Error: 'updates' dict is required"
                    result = await connector.update_event(
                        eid, updates, calendar_id=cal_id
                    )
                elif google_action == "delete_event":
                    eid = kwargs.get("event_id", "")
                    if not eid:
                        return "Error: 'event_id' is required"
                    result = await connector.delete_event(
                        eid, calendar_id=cal_id
                    )
                else:
                    return (
                        f"Error: Unknown calendar action "
                        f"'{google_action}'"
                    )

            # ── Drive ──
            elif service == "google_drive":
                if google_action == "list_files":
                    query = kwargs.get("query", "")
                    max_results = int(kwargs.get("max_results", 20))
                    result = await connector.list_files(
                        query, max_results
                    )
                elif google_action == "get_file":
                    fid = kwargs.get("file_id", "")
                    if not fid:
                        return "Error: 'file_id' is required"
                    result = await connector.get_file_content(fid)
                elif google_action == "get_file_metadata":
                    fid = kwargs.get("file_id", "")
                    if not fid:
                        return "Error: 'file_id' is required"
                    result = await connector.get_file_metadata(fid)
                elif google_action == "upload_file":
                    name = kwargs.get("name", "")
                    content = kwargs.get("content", "")
                    if not name:
                        return "Error: 'name' is required"
                    if not content:
                        return "Error: 'content' is required"
                    mime = kwargs.get("mime_type", "text/plain")
                    result = await connector.upload_file(
                        name, content, mime
                    )
                else:
                    return (
                        f"Error: Unknown drive action "
                        f"'{google_action}'"
                    )

            else:
                return f"Error: '{service}' does not support google actions"

            # Format result
            if result.get("success"):
                data = result.get("data")
                msg = result.get("message", "")
                if msg and not data:
                    return f"{connector.display_name}: {msg}"
                if data:
                    formatted = _json.dumps(
                        data, indent=2, default=str, ensure_ascii=False
                    )
                    # Truncate very large responses
                    if len(formatted) > 8000:
                        formatted = formatted[:8000] + "\n... [truncated]"
                    prefix = f"{connector.display_name}: {msg}\n" if msg else ""
                    return f"{prefix}{formatted}"
                return f"{connector.display_name}: Done"
            else:
                return (
                    f"{connector.display_name} error: "
                    f"{result.get('message', 'Unknown error')}"
                )

        except Exception as e:
            return (
                f"Error executing {google_action} on "
                f"{connector.display_name}: {e}"
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
