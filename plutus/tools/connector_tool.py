"""Connector tool — allows the agent to send messages and files through configured connectors.

The agent can use this tool to:
  - Send a message via Telegram, Email, or WhatsApp
  - Send a file or screenshot via Telegram
  - List available connectors and their status
  - Check if a connector is configured
  - Read/send Gmail emails, manage Calendar events, manage Drive files
  - Manage GitHub repos, issues, PRs, branches, files, workflows, and more

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
  connector(action="github", service="github", github_action="list_repos")
  connector(action="github", service="github", github_action="list_issues", owner="octocat", repo="Hello-World")
  connector(action="github", service="github", github_action="create_issue", owner="octocat", repo="Hello-World",
            title="Bug report", body="Something is broken")
  connector(action="github", service="github", github_action="get_file", path="README.md", owner="me", repo="my-repo")
  connector(action="list")
  connector(action="status", service="telegram")
  connector(action="custom", service="custom_jira", method="GET", endpoint="/rest/api/2/issue/KEY-1")
  connector(action="create_connector", connector_id="jira", connector_display_name="Jira",
            connector_description="My Jira instance", base_url="https://mycompany.atlassian.net",
            auth_type="basic_auth", connector_credentials={"username": "me", "password": "token"})
  connector(action="delete_connector", connector_id="jira")
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
            "Google Drive, GitHub, and custom API services. "
            "Use action='list' to see available connectors. "
            "Use action='send' with service='telegram' to send a Telegram message. "
            "Use action='send_file' with service='telegram', 'discord', 'whatsapp', or 'email' "
            "and file_path to send a screenshot or file. "
            "For whatsapp, also pass contact='Name'. "
            "For email, also pass to='recipient@example.com' and optionally subject='...' . "
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
            "'get_file', 'upload_file', 'get_file_metadata', 'read_doc'). "
            "Use google_action='read_doc' with a file_id to read the full text content "
            "of Google Docs, Google Slides, Google Sheets, Word (.docx), PowerPoint (.pptx), "
            "or any Drive file. Auto-detects the file type and returns the text. "
            "Use action='manage' with service='discord' to manage the Discord server. "
            "Use action='github' with service='github' to interact with GitHub: "
            "manage repos, issues, pull requests, branches, files, commits, releases, "
            "workflows, collaborators, and search. Requires github_action parameter. "
            "Use action='custom' with a custom connector service name to make "
            "HTTP requests to any user-configured API. "
            "Use action='create_connector' to programmatically create a new custom "
            "API connector. Use action='delete_connector' to remove one. "
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
                        "manage", "google", "github",
                        "custom", "create_connector", "delete_connector",
                    ],
                    "description": (
                        "Action to perform. "
                        "'send' = send a text message. "
                        "'send_file' = send a file or screenshot. "
                        "'list' = list all connectors and their status. "
                        "'status' = check if a specific connector is configured. "
                        "'manage' = manage Discord server. "
                        "'google' = interact with Google services "
                        "(Gmail, Calendar, Drive). "
                        "'github' = interact with GitHub "
                        "(repos, issues, PRs, branches, files, workflows, etc.). "
                        "'custom' = make HTTP request to a custom API connector. "
                        "'create_connector' = create a new custom API connector. "
                        "'delete_connector' = delete a custom API connector."
                    ),
                },
                "service": {
                    "type": "string",
                    "enum": [
                        "telegram", "email", "whatsapp", "discord",
                        "google_gmail", "google_calendar", "google_drive",
                        "github",
                    ],
                    "description": (
                        "Which connector to use. Required for 'send', "
                        "'send_file', 'manage', 'google', 'github', "
                        "and 'status' actions."
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
                    "description": (
                        "Name for creating channels, roles, repos, branches, "
                        "or releases."
                    ),
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
                        "upload_file", "read_doc",
                    ],
                    "description": (
                        "Google-specific action. Required when action='google'."
                    ),
                },
                "github_action": {
                    "type": "string",
                    "enum": [
                        # Repos
                        "list_repos", "get_repo", "create_repo", "delete_repo",
                        "fork_repo",
                        # Issues
                        "list_issues", "get_issue", "create_issue", "update_issue",
                        "comment_on_issue",
                        # Pull Requests
                        "list_pull_requests", "get_pull_request",
                        "create_pull_request", "merge_pull_request",
                        "review_pull_request",
                        # Branches
                        "list_branches", "create_branch", "delete_branch",
                        # Files
                        "get_file", "create_or_update_file", "delete_file",
                        # Commits & Releases
                        "list_commits", "list_releases", "create_release",
                        # Workflows
                        "list_workflows", "list_workflow_runs", "trigger_workflow",
                        # Collaborators
                        "list_collaborators", "add_collaborator",
                        "remove_collaborator",
                        # Search
                        "search_repos", "search_code",
                    ],
                    "description": (
                        "GitHub-specific action. Required when action='github'. "
                        "Covers repos, issues, PRs, branches, files, commits, "
                        "releases, workflows, collaborators, and search."
                    ),
                },
                "owner": {
                    "type": "string",
                    "description": (
                        "GitHub repository owner (username or org). "
                        "Falls back to the default owner configured in the "
                        "GitHub connector if not provided."
                    ),
                },
                "repo": {
                    "type": "string",
                    "description": (
                        "GitHub repository name. Falls back to the default "
                        "repo configured in the GitHub connector if not provided."
                    ),
                },
                "title": {
                    "type": "string",
                    "description": (
                        "Title for creating issues, PRs, or releases."
                    ),
                },
                "body": {
                    "type": "string",
                    "description": (
                        "Body text for issues, PRs, comments, or releases."
                    ),
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Labels for issues (list of label names).",
                },
                "assignees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Assignees for issues (list of usernames).",
                },
                "state": {
                    "type": "string",
                    "description": (
                        "State filter for listing issues/PRs ('open', 'closed', 'all'). "
                        "Also used for updating issue state."
                    ),
                },
                "issue_number": {
                    "type": "integer",
                    "description": "Issue or PR number for get/update/comment operations.",
                },
                "pr_number": {
                    "type": "integer",
                    "description": "Pull request number for PR operations.",
                },
                "head": {
                    "type": "string",
                    "description": "Head branch for creating a pull request.",
                },
                "base": {
                    "type": "string",
                    "description": "Base branch for creating a pull request.",
                },
                "draft": {
                    "type": "boolean",
                    "description": "Whether to create a draft PR (default false).",
                },
                "merge_method": {
                    "type": "string",
                    "enum": ["merge", "squash", "rebase"],
                    "description": "Merge method for merging a PR (default 'merge').",
                },
                "event": {
                    "type": "string",
                    "enum": ["APPROVE", "REQUEST_CHANGES", "COMMENT"],
                    "description": "Review event type for review_pull_request.",
                },
                "branch": {
                    "type": "string",
                    "description": (
                        "Branch name for branch operations, file operations, "
                        "or listing commits."
                    ),
                },
                "from_branch": {
                    "type": "string",
                    "description": (
                        "Source branch when creating a new branch (default 'main')."
                    ),
                },
                "path": {
                    "type": "string",
                    "description": (
                        "File path within the repo for file operations "
                        "(get_file, create_or_update_file, delete_file)."
                    ),
                },
                "ref": {
                    "type": "string",
                    "description": (
                        "Git ref (branch, tag, or SHA) for reading files "
                        "at a specific version."
                    ),
                },
                "sha": {
                    "type": "string",
                    "description": (
                        "SHA of the existing file (required for updating "
                        "or deleting files). Get it via get_file first."
                    ),
                },
                "commit_message": {
                    "type": "string",
                    "description": "Commit message for file create/update/delete.",
                },
                "tag_name": {
                    "type": "string",
                    "description": "Tag name for creating a release.",
                },
                "prerelease": {
                    "type": "boolean",
                    "description": "Whether the release is a prerelease.",
                },
                "target": {
                    "type": "string",
                    "description": (
                        "Target branch/commitish for creating a release "
                        "(default 'main')."
                    ),
                },
                "workflow_id": {
                    "type": "string",
                    "description": "Workflow ID or filename for workflow operations.",
                },
                "workflow_status": {
                    "type": "string",
                    "description": (
                        "Status filter for listing workflow runs "
                        "(e.g. 'completed', 'in_progress', 'failure')."
                    ),
                },
                "inputs": {
                    "type": "object",
                    "description": (
                        "Input parameters for triggering a workflow dispatch."
                    ),
                },
                "username": {
                    "type": "string",
                    "description": (
                        "GitHub username for collaborator operations."
                    ),
                },
                "permission": {
                    "type": "string",
                    "enum": ["pull", "push", "admin"],
                    "description": (
                        "Permission level for adding a collaborator "
                        "(default 'push')."
                    ),
                },
                "private": {
                    "type": "boolean",
                    "description": "Whether to create a private repo (default true).",
                },
                "auto_init": {
                    "type": "boolean",
                    "description": (
                        "Whether to initialize the repo with a README "
                        "(default true)."
                    ),
                },
                "per_page": {
                    "type": "integer",
                    "description": (
                        "Number of results per page for list operations "
                        "(default varies by endpoint)."
                    ),
                },
                "query": {
                    "type": "string",
                    "description": (
                        "Search query for Gmail (e.g. 'is:unread', "
                        "'from:alice@example.com'), Drive "
                        "(e.g. 'name contains \"report\"'), "
                        "or GitHub search (repos/code)."
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
                        "File content for upload_file (Drive) or "
                        "create_or_update_file (GitHub)."
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
                "description": {
                    "type": "string",
                    "description": (
                        "Description for creating a repo or release."
                    ),
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                    "description": (
                        "HTTP method for custom API requests. "
                        "Default: GET."
                    ),
                },
                "endpoint": {
                    "type": "string",
                    "description": (
                        "API endpoint path for custom API requests "
                        "(e.g. '/api/v2/users'). Appended to the base URL."
                    ),
                },
                "request_body": {
                    "type": "object",
                    "description": (
                        "Request body for custom API POST/PUT/PATCH requests."
                    ),
                },
                "request_params": {
                    "type": "object",
                    "description": (
                        "Query parameters for custom API requests."
                    ),
                },
                "request_headers": {
                    "type": "object",
                    "description": (
                        "Additional headers for this specific custom API request."
                    ),
                },
                "connector_id": {
                    "type": "string",
                    "description": (
                        "ID for creating/deleting custom connectors. "
                        "Alphanumeric and underscores only."
                    ),
                },
                "connector_display_name": {
                    "type": "string",
                    "description": "Display name for a new custom connector.",
                },
                "connector_description": {
                    "type": "string",
                    "description": "Description for a new custom connector.",
                },
                "base_url": {
                    "type": "string",
                    "description": (
                        "Base URL for a new custom connector "
                        "(e.g. 'https://api.example.com/v1')."
                    ),
                },
                "auth_type": {
                    "type": "string",
                    "enum": ["none", "api_key", "bearer_token", "basic_auth"],
                    "description": "Authentication type for a new custom connector.",
                },
                "connector_credentials": {
                    "type": "object",
                    "description": (
                        "Credentials for a new custom connector. Keys depend on auth_type: "
                        "api_key: {api_key: '...'}, bearer_token: {token: '...'}, "
                        "basic_auth: {username: '...', password: '...'}"
                    ),
                },
                "connector_headers": {
                    "type": "object",
                    "description": (
                        "Default headers for a new custom connector "
                        "(e.g. {'Accept': 'application/json'})."
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
            service = kwargs.pop("service", "")
            file_path = kwargs.pop("file_path", "")
            caption = kwargs.pop("caption", "")

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
            service = kwargs.pop("service", "")
            if not service:
                return "Error: 'service' is required (google_gmail, google_calendar, google_drive)"
            return await self._handle_google(service, **kwargs)

        elif action == "github":
            return await self._handle_github(**kwargs)

        elif action == "custom":
            return await self._handle_custom(**kwargs)

        elif action == "create_connector":
            return await self._handle_create_connector(**kwargs)

        elif action == "delete_connector":
            return await self._handle_delete_connector(**kwargs)

        else:
            return (
                f"Error: Unknown action '{action}'. "
                "Use 'send', 'send_file', 'list', 'status', 'manage', "
                "'google', 'github', 'custom', 'create_connector', "
                "or 'delete_connector'."
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
                "to set up Telegram, Email, WhatsApp, Discord, or GitHub."
            )

        return "\n".join(lines)

    def _get_status(self, service: str) -> str:
        connector = self._manager.get(service)
        if not connector:
            return (
                f"Error: Unknown connector '{service}'. "
                "Available: telegram, email, whatsapp, discord, "
                "google_gmail, google_calendar, google_drive, github"
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
            elif service == "github":
                if config.get("username"):
                    details.append(f"User: @{config['username']}")
                if config.get("default_owner"):
                    details.append(f"Default owner: {config['default_owner']}")
                if config.get("default_repo"):
                    details.append(f"Default repo: {config['default_repo']}")
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
                "google_gmail, google_calendar, google_drive, github"
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

        elif service == "github":
            # For GitHub, send_message creates an issue
            send_kwargs["owner"] = kwargs.get("owner")
            send_kwargs["repo"] = kwargs.get("repo")
            send_kwargs["title"] = kwargs.get("title", message[:80])

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
                "google_gmail, google_calendar, google_drive, github"
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
        elif service == "whatsapp":
            contact = kwargs.get("contact", "")
            result = await connector.send_file(
                file_path, caption=caption, contact=contact
            )
        elif service == "email":
            to = kwargs.get("to", "")
            subject = kwargs.get("subject", "")
            if not to:
                return "Error: 'to' (recipient email address) is required when sending a file via email"
            result = await connector.send_file(
                file_path, caption=caption, to=to, subject=subject
            )
        else:
            return (
                f"Error: send_file is not yet supported for {service}. "
                "Supported services: telegram, discord, whatsapp, email."
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
                elif google_action == "read_doc":
                    fid = kwargs.get("file_id", "")
                    if not fid:
                        return "Error: 'file_id' is required for read_doc"
                    mime = kwargs.get("mime_type", "")
                    result = await connector.read_doc(fid, mime)
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

    # ── GitHub ───────────────────────────────────────────────────

    async def _handle_github(self, **kwargs: Any) -> str:
        """Handle GitHub-specific actions (repos, issues, PRs, branches, files, etc.)."""
        connector = self._manager.get("github")
        if not connector:
            return (
                "Error: GitHub connector not available. "
                "The user needs to set it up in the Connectors tab."
            )
        if not connector.is_configured:
            return (
                "Error: GitHub is not configured. "
                "The user needs to add their Personal Access Token "
                "in the Connectors tab first."
            )

        github_action = kwargs.get("github_action", "")
        if not github_action:
            return (
                "Error: 'github_action' is required. Options: "
                "list_repos, get_repo, create_repo, delete_repo, fork_repo, "
                "list_issues, get_issue, create_issue, update_issue, comment_on_issue, "
                "list_pull_requests, get_pull_request, create_pull_request, "
                "merge_pull_request, review_pull_request, "
                "list_branches, create_branch, delete_branch, "
                "get_file, create_or_update_file, delete_file, "
                "list_commits, list_releases, create_release, "
                "list_workflows, list_workflow_runs, trigger_workflow, "
                "list_collaborators, add_collaborator, remove_collaborator, "
                "search_repos, search_code"
            )

        import json as _json

        # Common params
        owner = kwargs.get("owner")
        repo = kwargs.get("repo")

        try:
            result: dict[str, Any] = {}

            # ── Repository operations ──
            if github_action == "list_repos":
                result = await connector.list_repos(
                    owner=owner,
                    repo_type=kwargs.get("repo_type", "owner"),
                    sort=kwargs.get("sort", "updated"),
                    per_page=int(kwargs.get("per_page", 30)),
                )

            elif github_action == "get_repo":
                result = await connector.get_repo(owner=owner, repo=repo)

            elif github_action == "create_repo":
                name = kwargs.get("name", "")
                if not name:
                    return "Error: 'name' is required to create a repository"
                result = await connector.create_repo(
                    name=name,
                    description=kwargs.get("description", ""),
                    private=kwargs.get("private", True),
                    auto_init=kwargs.get("auto_init", True),
                )

            elif github_action == "delete_repo":
                result = await connector.delete_repo(owner=owner, repo=repo)

            elif github_action == "fork_repo":
                result = await connector.fork_repo(owner=owner, repo=repo)

            # ── Issue operations ──
            elif github_action == "list_issues":
                # labels can be a list or comma-separated string
                raw_labels = kwargs.get("labels", "")
                if isinstance(raw_labels, list):
                    raw_labels = ",".join(raw_labels)
                result = await connector.list_issues(
                    state=kwargs.get("state", "open"),
                    labels=raw_labels,
                    per_page=int(kwargs.get("per_page", 30)),
                    owner=owner,
                    repo=repo,
                )

            elif github_action == "get_issue":
                issue_number = kwargs.get("issue_number")
                if not issue_number:
                    return "Error: 'issue_number' is required"
                result = await connector.get_issue(
                    int(issue_number), owner=owner, repo=repo
                )

            elif github_action == "create_issue":
                title = kwargs.get("title", "")
                if not title:
                    return "Error: 'title' is required to create an issue"
                result = await connector.create_issue(
                    title=title,
                    body=kwargs.get("body", ""),
                    labels=kwargs.get("labels"),
                    assignees=kwargs.get("assignees"),
                    owner=owner,
                    repo=repo,
                )

            elif github_action == "update_issue":
                issue_number = kwargs.get("issue_number")
                if not issue_number:
                    return "Error: 'issue_number' is required"
                result = await connector.update_issue(
                    int(issue_number),
                    title=kwargs.get("title"),
                    body=kwargs.get("body"),
                    state=kwargs.get("state"),
                    labels=kwargs.get("labels"),
                    assignees=kwargs.get("assignees"),
                    owner=owner,
                    repo=repo,
                )

            elif github_action == "comment_on_issue":
                issue_number = kwargs.get("issue_number")
                body = kwargs.get("body", "")
                if not issue_number:
                    return "Error: 'issue_number' is required"
                if not body:
                    return "Error: 'body' is required for commenting"
                result = await connector.comment_on_issue(
                    int(issue_number), body, owner=owner, repo=repo
                )

            # ── Pull Request operations ──
            elif github_action == "list_pull_requests":
                result = await connector.list_pull_requests(
                    state=kwargs.get("state", "open"),
                    per_page=int(kwargs.get("per_page", 30)),
                    owner=owner,
                    repo=repo,
                )

            elif github_action == "get_pull_request":
                pr_number = kwargs.get("pr_number")
                if not pr_number:
                    return "Error: 'pr_number' is required"
                result = await connector.get_pull_request(
                    int(pr_number), owner=owner, repo=repo
                )

            elif github_action == "create_pull_request":
                title = kwargs.get("title", "")
                head = kwargs.get("head", "")
                base = kwargs.get("base", "")
                if not title:
                    return "Error: 'title' is required"
                if not head:
                    return "Error: 'head' (source branch) is required"
                if not base:
                    return "Error: 'base' (target branch) is required"
                result = await connector.create_pull_request(
                    title=title,
                    head=head,
                    base=base,
                    body=kwargs.get("body", ""),
                    draft=kwargs.get("draft", False),
                    owner=owner,
                    repo=repo,
                )

            elif github_action == "merge_pull_request":
                pr_number = kwargs.get("pr_number")
                if not pr_number:
                    return "Error: 'pr_number' is required"
                result = await connector.merge_pull_request(
                    int(pr_number),
                    merge_method=kwargs.get("merge_method", "merge"),
                    commit_title=kwargs.get("title", ""),
                    owner=owner,
                    repo=repo,
                )

            elif github_action == "review_pull_request":
                pr_number = kwargs.get("pr_number")
                if not pr_number:
                    return "Error: 'pr_number' is required"
                result = await connector.review_pull_request(
                    int(pr_number),
                    event=kwargs.get("event", "COMMENT"),
                    body=kwargs.get("body", ""),
                    owner=owner,
                    repo=repo,
                )

            # ── Branch operations ──
            elif github_action == "list_branches":
                result = await connector.list_branches(
                    per_page=int(kwargs.get("per_page", 30)),
                    owner=owner,
                    repo=repo,
                )

            elif github_action == "create_branch":
                branch_name = kwargs.get("branch") or kwargs.get("name", "")
                if not branch_name:
                    return "Error: 'branch' (or 'name') is required"
                result = await connector.create_branch(
                    branch_name=branch_name,
                    from_branch=kwargs.get("from_branch", "main"),
                    owner=owner,
                    repo=repo,
                )

            elif github_action == "delete_branch":
                branch_name = kwargs.get("branch") or kwargs.get("name", "")
                if not branch_name:
                    return "Error: 'branch' (or 'name') is required"
                result = await connector.delete_branch(
                    branch_name, owner=owner, repo=repo
                )

            # ── File operations ──
            elif github_action == "get_file":
                path = kwargs.get("path", "")
                if not path:
                    return "Error: 'path' is required (file path in the repo)"
                result = await connector.get_file(
                    path,
                    ref=kwargs.get("ref"),
                    owner=owner,
                    repo=repo,
                )

            elif github_action == "create_or_update_file":
                path = kwargs.get("path", "")
                content = kwargs.get("content", "")
                message = kwargs.get("commit_message", "")
                if not path:
                    return "Error: 'path' is required"
                if not content:
                    return "Error: 'content' is required"
                if not message:
                    return "Error: 'commit_message' is required"
                result = await connector.create_or_update_file(
                    path=path,
                    content=content,
                    message=message,
                    branch=kwargs.get("branch"),
                    sha=kwargs.get("sha"),
                    owner=owner,
                    repo=repo,
                )

            elif github_action == "delete_file":
                path = kwargs.get("path", "")
                message = kwargs.get("commit_message", "")
                sha = kwargs.get("sha", "")
                if not path:
                    return "Error: 'path' is required"
                if not message:
                    return "Error: 'commit_message' is required"
                if not sha:
                    return "Error: 'sha' is required (get it via get_file first)"
                result = await connector.delete_file(
                    path=path,
                    message=message,
                    sha=sha,
                    branch=kwargs.get("branch"),
                    owner=owner,
                    repo=repo,
                )

            # ── Commit & Release operations ──
            elif github_action == "list_commits":
                result = await connector.list_commits(
                    branch=kwargs.get("branch"),
                    per_page=int(kwargs.get("per_page", 20)),
                    owner=owner,
                    repo=repo,
                )

            elif github_action == "list_releases":
                result = await connector.list_releases(
                    per_page=int(kwargs.get("per_page", 10)),
                    owner=owner,
                    repo=repo,
                )

            elif github_action == "create_release":
                tag_name = kwargs.get("tag_name", "")
                if not tag_name:
                    return "Error: 'tag_name' is required"
                result = await connector.create_release(
                    tag_name=tag_name,
                    name=kwargs.get("name", ""),
                    body=kwargs.get("body", ""),
                    draft=kwargs.get("draft", False),
                    prerelease=kwargs.get("prerelease", False),
                    target=kwargs.get("target", "main"),
                    owner=owner,
                    repo=repo,
                )

            # ── Workflow operations ──
            elif github_action == "list_workflows":
                result = await connector.list_workflows(
                    owner=owner, repo=repo
                )

            elif github_action == "list_workflow_runs":
                result = await connector.list_workflow_runs(
                    workflow_id=kwargs.get("workflow_id"),
                    status=kwargs.get("workflow_status"),
                    per_page=int(kwargs.get("per_page", 10)),
                    owner=owner,
                    repo=repo,
                )

            elif github_action == "trigger_workflow":
                workflow_id = kwargs.get("workflow_id", "")
                if not workflow_id:
                    return "Error: 'workflow_id' is required"
                result = await connector.trigger_workflow(
                    workflow_id=workflow_id,
                    ref=kwargs.get("ref", "main"),
                    inputs=kwargs.get("inputs"),
                    owner=owner,
                    repo=repo,
                )

            # ── Collaborator operations ──
            elif github_action == "list_collaborators":
                result = await connector.list_collaborators(
                    owner=owner, repo=repo
                )

            elif github_action == "add_collaborator":
                username = kwargs.get("username", "")
                if not username:
                    return "Error: 'username' is required"
                result = await connector.add_collaborator(
                    username=username,
                    permission=kwargs.get("permission", "push"),
                    owner=owner,
                    repo=repo,
                )

            elif github_action == "remove_collaborator":
                username = kwargs.get("username", "")
                if not username:
                    return "Error: 'username' is required"
                result = await connector.remove_collaborator(
                    username=username, owner=owner, repo=repo
                )

            # ── Search operations ──
            elif github_action == "search_repos":
                query = kwargs.get("query", "")
                if not query:
                    return "Error: 'query' is required for search"
                result = await connector.search_repos(
                    query, per_page=int(kwargs.get("per_page", 10))
                )

            elif github_action == "search_code":
                query = kwargs.get("query", "")
                if not query:
                    return "Error: 'query' is required for search"
                result = await connector.search_code(
                    query, owner=owner, repo=repo,
                    per_page=int(kwargs.get("per_page", 10)),
                )

            else:
                return f"Error: Unknown github_action '{github_action}'"

            # ── Format result ──
            if result.get("success"):
                # Remove the success key for cleaner output
                display = {k: v for k, v in result.items() if k != "success"}
                msg = display.pop("message", "")

                if msg and not display:
                    return f"GitHub: {msg}"

                if display:
                    formatted = _json.dumps(
                        display, indent=2, default=str, ensure_ascii=False
                    )
                    # Truncate very large responses
                    if len(formatted) > 8000:
                        formatted = formatted[:8000] + "\n... [truncated]"
                    prefix = f"GitHub: {msg}\n" if msg else ""
                    return f"{prefix}{formatted}"

                return f"GitHub: Done"
            else:
                return (
                    f"GitHub error: "
                    f"{result.get('message', 'Unknown error')}"
                )

        except Exception as e:
            return (
                f"Error executing GitHub action '{github_action}': {e}"
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

    # ── Custom API Connector handlers ──────────────────────────

    async def _handle_custom(self, **kwargs: Any) -> str:
        """Handle custom API connector requests."""
        service = kwargs.get("service", "")
        if not service:
            return "Error: 'service' parameter is required for custom action (e.g. 'custom_jira')"

        # Ensure the service name has the custom_ prefix
        if not service.startswith("custom_"):
            service = f"custom_{service}"

        connector = self._manager.get(service)
        if not connector:
            # List available custom connectors
            all_connectors = self._manager.list_all()
            custom = [c for c in all_connectors if c.get("is_custom")]
            if custom:
                names = ", ".join(c["name"] for c in custom)
                return f"Error: Custom connector '{service}' not found. Available custom connectors: {names}"
            return (
                f"Error: Custom connector '{service}' not found. "
                "No custom connectors are configured. "
                "Use action='create_connector' to create one, or the user can "
                "add one in the Connectors tab."
            )

        if not connector.is_configured:
            return f"Error: Custom connector '{service}' is not configured. The user needs to configure it in the Connectors tab."

        # Import here to avoid circular imports
        from plutus.connectors.custom_api import CustomAPIConnector
        if not isinstance(connector, CustomAPIConnector):
            return f"Error: '{service}' is not a custom API connector. Use the appropriate action instead."

        method = kwargs.get("method", "GET")
        endpoint = kwargs.get("endpoint", "/")
        body = kwargs.get("request_body")
        params = kwargs.get("request_params")
        headers = kwargs.get("request_headers")

        try:
            result = await connector.request(
                method=method,
                endpoint=endpoint,
                body=body,
                headers=headers,
                params=params,
            )

            if result.get("success"):
                import json
                response_body = result.get("body", "")
                if isinstance(response_body, (dict, list)):
                    body_str = json.dumps(response_body, indent=2)
                    # Truncate very large responses
                    if len(body_str) > 8000:
                        body_str = body_str[:8000] + "\n... (truncated)"
                else:
                    body_str = str(response_body)[:8000]

                return (
                    f"HTTP {result.get('status_code')} — Success\n\n"
                    f"Response:\n{body_str}"
                )
            else:
                error = result.get("error", result.get("body", "Unknown error"))
                return f"HTTP {result.get('status_code', '?')} — Error: {error}"

        except Exception as e:
            return f"Error making request to {service}: {str(e)}"

    async def _handle_create_connector(self, **kwargs: Any) -> str:
        """Handle creating a new custom API connector."""
        from plutus.connectors.custom_api import CustomConnectorManager

        connector_id = kwargs.get("connector_id", "")
        if not connector_id:
            return "Error: 'connector_id' is required (e.g. 'jira', 'notion', 'slack')"

        display_name = kwargs.get("connector_display_name", "")
        description = kwargs.get("connector_description", "")
        base_url = kwargs.get("base_url", "")
        auth_type = kwargs.get("auth_type", "none")
        credentials = kwargs.get("connector_credentials")
        default_headers = kwargs.get("connector_headers")

        if not base_url:
            return "Error: 'base_url' is required (e.g. 'https://api.example.com/v1')"

        success, message, connector = CustomConnectorManager.create_custom_connector(
            connector_id=connector_id,
            display_name=display_name,
            description=description,
            base_url=base_url,
            auth_type=auth_type,
            credentials=credentials,
            default_headers=default_headers,
        )

        if success and connector:
            # Register it in the live connector manager
            self._manager.register(connector)
            return (
                f"Custom connector created: {connector.display_name}\n"
                f"  Service name: {connector.name}\n"
                f"  Base URL: {base_url}\n"
                f"  Auth: {auth_type}\n\n"
                f"You can now use it with:\n"
                f"  connector(action='custom', service='{connector.name}', "
                f"method='GET', endpoint='/...')"
            )
        else:
            return f"Error creating connector: {message}"

    async def _handle_delete_connector(self, **kwargs: Any) -> str:
        """Handle deleting a custom API connector."""
        from plutus.connectors.custom_api import CustomConnectorManager

        connector_id = kwargs.get("connector_id", "")
        if not connector_id:
            return "Error: 'connector_id' is required"

        success, message = CustomConnectorManager.delete_custom_connector(connector_id)

        if success:
            # Remove from live connector manager
            full_name = f"custom_{connector_id}"
            if full_name in self._manager._connectors:
                del self._manager._connectors[full_name]
            return f"Custom connector '{connector_id}' deleted successfully."
        else:
            return f"Error: {message}"
