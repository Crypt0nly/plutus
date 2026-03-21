"""
cloud_connector_executor.py
============================
Implements the ``connector`` tool for the cloud agent runtime.

Reads credentials from the user's ``connector_credentials`` DB column and
dispatches to the appropriate external API.  Mirrors the local
``ConnectorTool`` / connector classes but is fully cloud-native (no local
filesystem, no webbrowser, no PKCE localhost server).

Supported actions
-----------------
- list          — list configured connectors
- status        — check a specific connector
- send          — send a text message (Telegram, Discord, Email, GitHub issue)
- google        — Gmail / Calendar / Drive operations
- github        — Full GitHub API (repos, issues, PRs, branches, files, etc.)
- custom        — HTTP request to a user-configured custom API connector
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Google OAuth access token helper
# ---------------------------------------------------------------------------


async def _get_google_access_token(creds: dict) -> str | None:
    """Return a valid Google access token.

    We use access_type=online (no refresh token), so we simply return the
    stored access token.  If it has expired the Google API will return a 401
    and the user should re-authorize via the Connectors tab.

    Supports two credential layouts:
    1. OAuth flow (new): creds = {"oauth_tokens": {"access_token": ..., "expires_at": ...}, ...}
    2. Legacy manual entry: creds = {"access_token": ..., ...}
    """
    # New layout: tokens stored under oauth_tokens by the server-side OAuth flow
    oauth_tokens = creds.get("oauth_tokens")
    if oauth_tokens:
        return oauth_tokens.get("access_token")

    # Legacy layout: manually entered credentials
    return creds.get("access_token")


# ---------------------------------------------------------------------------
# GitHub helper
# ---------------------------------------------------------------------------

_GH_BASE = "https://api.github.com"
_GH_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


async def _gh(
    method: str,
    path: str,
    token: str,
    *,
    json_body: dict | None = None,
    params: dict | None = None,
) -> dict[str, Any]:
    url = f"{_GH_BASE}{path}"
    headers = {**_GH_HEADERS, "Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(method, url, headers=headers, json=json_body, params=params)
        if resp.status_code >= 400:
            return {
                "success": False,
                "message": f"GitHub API error {resp.status_code}: {resp.text[:300]}",
            }
        try:
            return {"success": True, "data": resp.json()}
        except Exception:
            return {"success": True, "data": resp.text}


# ---------------------------------------------------------------------------
# Telegram helper
# ---------------------------------------------------------------------------

_TG_BASE = "https://api.telegram.org/bot{token}/{method}"


async def _tg(token: str, method: str, **params: Any) -> dict:
    url = _TG_BASE.format(token=token, method=method)
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=params)
        return resp.json()


# ---------------------------------------------------------------------------
# Discord helper
# ---------------------------------------------------------------------------

_DC_BASE = "https://discord.com/api/v10"


async def _dc(
    method: str,
    path: str,
    token: str,
    *,
    json_body: dict | None = None,
) -> dict[str, Any]:
    url = f"{_DC_BASE}{path}"
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(method, url, headers=headers, json=json_body)
        if resp.status_code >= 400:
            return {
                "success": False,
                "message": f"Discord API error {resp.status_code}: {resp.text[:300]}",
            }
        try:
            return {"success": True, "data": resp.json()}
        except Exception:
            return {"success": True, "data": {}}


# ---------------------------------------------------------------------------
# Google API helper
# ---------------------------------------------------------------------------

_GOOGLE_BASE = "https://www.googleapis.com"
_GMAIL_BASE = "https://gmail.googleapis.com"
_GCAL_BASE = "https://www.googleapis.com/calendar/v3"
_GDRIVE_BASE = "https://www.googleapis.com/drive/v3"


async def _google_api(
    method: str,
    url: str,
    access_token: str,
    *,
    json_body: dict | None = None,
    params: dict | None = None,
    data: bytes | None = None,
    extra_headers: dict | None = None,
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        **(extra_headers or {}),
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(
            method,
            url,
            headers=headers,
            json=json_body,
            params=params,
            content=data,
        )
        if resp.status_code == 401:
            return {
                "success": False,
                "message": "Google token expired — re-authorize in Connectors tab",
            }
        if resp.status_code >= 400:
            return {
                "success": False,
                "message": f"Google API error {resp.status_code}: {resp.text[:300]}",
            }
        try:
            return {"success": True, "data": resp.json()}
        except Exception:
            return {"success": True, "data": resp.text}


# ---------------------------------------------------------------------------
# Main executor class
# ---------------------------------------------------------------------------


class CloudConnectorExecutor:
    """
    Execute connector tool calls for a specific cloud user.

    Instantiate with the user's ``connector_credentials`` dict (from DB).
    """

    def __init__(self, user_id: str, credentials: dict[str, Any]) -> None:
        self._user_id = user_id
        self._creds = credentials  # { connector_name: { field: value, ... } }

    # ── Public entry point ────────────────────────────────────────────────────

    async def execute(self, **kwargs: Any) -> str:
        """Dispatch a connector tool call and return a human-readable string."""
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

        elif action == "manage":
            service = kwargs.get("service", "")
            if service != "discord":
                return "Error: 'manage' action is only supported for Discord"
            return await self._manage_discord(**kwargs)

        elif action == "google":
            service = kwargs.get("service", "")
            if not service:
                return "Error: 'service' is required (gmail, google_calendar, google_drive)"
            return await self._handle_google(service, **kwargs)

        elif action == "github":
            return await self._handle_github(**kwargs)

        elif action == "custom":
            return await self._handle_custom(**kwargs)

        elif action == "create_connector":
            return (
                "Custom connector creation is managed via the Connectors tab in the UI. "
                "Please add your connector there and then use action='custom' to call it."
            )

        elif action == "delete_connector":
            return "Custom connector deletion is managed via the Connectors tab in the UI."

        else:
            return (
                f"Error: Unknown action '{action}'. "
                "Use 'send', 'list', 'status', 'manage', 'google', 'github', or 'custom'."
            )

    # ── List / status ─────────────────────────────────────────────────────────

    def _list_connectors(self) -> str:
        known = [
            "telegram",
            "discord",
            "whatsapp",
            "email",
            "gmail",
            "google_calendar",
            "google_drive",
            "github",
            "vercel",
            "netlify",
        ]
        lines = ["Configured connectors:\n"]
        configured = []
        for name in known:
            if name in self._creds:
                configured.append(name)
                lines.append(f"  ✓ {name}")
            else:
                lines.append(f"  ✗ {name} (not configured)")

        # Also list any custom connectors
        for key in self._creds:
            if key.startswith("custom_"):
                configured.append(key)
                lines.append(f"  ✓ {key} (custom)")

        if not configured:
            lines.append(
                "\nNo connectors configured yet. Go to the Connectors tab in the UI to set them up."
            )
        return "\n".join(lines)

    def _get_status(self, service: str) -> str:
        cfg = self._creds.get(service) or self._creds.get(f"custom_{service}")
        if cfg:
            return f"{service} is configured and ready."
        return f"{service} is NOT configured. Go to the Connectors tab in the UI to set it up."

    # ── Send message ──────────────────────────────────────────────────────────

    async def _send_message(self, service: str, message: str, **kwargs: Any) -> str:
        cfg = self._creds.get(service, {})
        if not cfg:
            return f"Error: {service} is not configured. Go to the Connectors tab to set it up."

        try:
            if service == "telegram":
                token = cfg.get("bot_token", "")
                chat_id = cfg.get("chat_id", "")
                if not token:
                    return "Error: Telegram bot_token is not configured"
                if not chat_id:
                    return (
                        "Error: Telegram chat_id is not set. "
                        "Start a conversation with your bot first so it learns your chat ID."
                    )
                parse_mode = kwargs.get("parse_mode", "HTML")
                if parse_mode == "plain":
                    parse_mode = ""
                params: dict[str, Any] = {"chat_id": chat_id, "text": message}
                if parse_mode:
                    params["parse_mode"] = parse_mode
                result = await _tg(token, "sendMessage", **params)
                if result.get("ok"):
                    return "Message sent via Telegram"
                return f"Telegram error: {result.get('description', 'Unknown error')}"

            elif service == "discord":
                token = cfg.get("bot_token", "")
                channel_id = kwargs.get("channel_id") or cfg.get("default_channel_id", "")
                if not token:
                    return "Error: Discord bot_token is not configured"
                if not channel_id:
                    return (
                        "Error: No channel_id provided and no default_channel_id configured. "
                        "Pass channel_id=<id> or set a default in the Connectors tab."
                    )
                result = await _dc(
                    "POST",
                    f"/channels/{channel_id}/messages",
                    token,
                    json_body={"content": message},
                )
                if result.get("success"):
                    return "Message sent via Discord"
                return f"Discord error: {result.get('message', 'Unknown error')}"

            elif service == "email":
                smtp_host = cfg.get("smtp_host", "smtp.gmail.com")
                smtp_port = int(cfg.get("smtp_port", 587))
                username = cfg.get("username", "")
                password = cfg.get("password", "")
                to = kwargs.get("to", "")
                subject = kwargs.get("subject", "Message from Plutus")
                if not to:
                    return "Error: 'to' (recipient email) is required for email"
                if not username or not password:
                    return "Error: Email username/password not configured"

                def _send_smtp() -> None:
                    msg = MIMEMultipart("alternative")
                    msg["Subject"] = subject
                    msg["From"] = username
                    msg["To"] = to
                    msg.attach(MIMEText(message, "plain"))
                    server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
                    server.starttls()
                    server.login(username, password)
                    server.send_message(msg)
                    server.quit()

                await asyncio.to_thread(_send_smtp)
                return f"Email sent to {to}"

            elif service == "gmail":
                # Send via Gmail API
                creds_g = self._creds.get("gmail", {})
                token = await _get_google_access_token(creds_g)
                if not token:
                    return (
                        "Error: Gmail is not authorized. "
                        "Go to the Connectors tab and click Authorize."
                    )
                to = kwargs.get("to", "")
                subject = kwargs.get("subject", "Message from Plutus")
                if not to:
                    return "Error: 'to' (recipient email) is required for Gmail"

                raw_msg = MIMEText(message, "plain")
                raw_msg["to"] = to
                raw_msg["subject"] = subject
                encoded = base64.urlsafe_b64encode(raw_msg.as_bytes()).decode()

                result = await _google_api(
                    "POST",
                    "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                    token,
                    json_body={"raw": encoded},
                )
                if result.get("success"):
                    return f"Email sent via Gmail to {to}"
                return f"Gmail error: {result.get('message', 'Unknown error')}"

            elif service == "github":
                # Create an issue as a "message"
                cfg_gh = self._creds.get("github", {})
                token = cfg_gh.get("token", "")
                if not token:
                    return "Error: GitHub token is not configured"
                owner = kwargs.get("owner") or cfg_gh.get("username", "")
                repo = kwargs.get("repo") or cfg_gh.get("default_repo", "")
                title = kwargs.get("title", message[:80])
                if not owner or not repo:
                    return (
                        "Error: 'owner' and 'repo' are required to create a GitHub issue. "
                        "Pass them as parameters or set defaults in the Connectors tab."
                    )
                result = await _gh(
                    "POST",
                    f"/repos/{owner}/{repo}/issues",
                    token,
                    json_body={"title": title, "body": message},
                )
                if result.get("success"):
                    issue = result["data"]
                    return f"GitHub issue created: {issue.get('html_url', 'OK')}"
                return f"GitHub error: {result.get('message', 'Unknown error')}"

            else:
                return (
                    f"Error: send action is not supported for '{service}'. "
                    "Supported: telegram, discord, email, gmail, github"
                )

        except Exception as exc:
            return f"Error sending via {service}: {exc}"

    # ── Discord management ────────────────────────────────────────────────────

    async def _manage_discord(self, **kwargs: Any) -> str:
        cfg = self._creds.get("discord", {})
        token = cfg.get("bot_token", "")
        if not token:
            return "Error: Discord is not configured"

        discord_action = kwargs.get("discord_action", "")
        if not discord_action:
            return "Error: 'discord_action' is required"

        target_id = kwargs.get("target_id", "")
        name = kwargs.get("name", "")
        reason = kwargs.get("reason", "")
        role_id = kwargs.get("role_id", "")
        channel_id = kwargs.get("channel_id", "")
        guild_id = cfg.get("guild_id", "")

        try:
            if discord_action == "guild_info":
                if not guild_id:
                    return "Error: guild_id not configured"
                result = await _dc("GET", f"/guilds/{guild_id}", token)
            elif discord_action == "list_channels":
                if not guild_id:
                    return "Error: guild_id not configured"
                result = await _dc("GET", f"/guilds/{guild_id}/channels", token)
            elif discord_action == "create_channel":
                if not guild_id:
                    return "Error: guild_id not configured"
                if not name:
                    return "Error: 'name' is required"
                result = await _dc(
                    "POST",
                    f"/guilds/{guild_id}/channels",
                    token,
                    json_body={"name": name},
                )
            elif discord_action == "delete_channel":
                if not target_id:
                    return "Error: 'target_id' (channel_id) is required"
                result = await _dc("DELETE", f"/channels/{target_id}", token)
            elif discord_action == "list_members":
                if not guild_id:
                    return "Error: guild_id not configured"
                result = await _dc("GET", f"/guilds/{guild_id}/members?limit=100", token)
            elif discord_action == "kick_member":
                if not guild_id or not target_id:
                    return "Error: guild_id and target_id are required"
                result = await _dc(
                    "DELETE",
                    f"/guilds/{guild_id}/members/{target_id}",
                    token,
                    json_body={"reason": reason} if reason else None,
                )
            elif discord_action == "ban_member":
                if not guild_id or not target_id:
                    return "Error: guild_id and target_id are required"
                result = await _dc(
                    "PUT",
                    f"/guilds/{guild_id}/bans/{target_id}",
                    token,
                    json_body={"reason": reason} if reason else None,
                )
            elif discord_action == "list_roles":
                if not guild_id:
                    return "Error: guild_id not configured"
                result = await _dc("GET", f"/guilds/{guild_id}/roles", token)
            elif discord_action == "create_role":
                if not guild_id or not name:
                    return "Error: guild_id and name are required"
                result = await _dc(
                    "POST",
                    f"/guilds/{guild_id}/roles",
                    token,
                    json_body={"name": name},
                )
            elif discord_action == "assign_role":
                if not guild_id or not target_id or not role_id:
                    return "Error: guild_id, target_id, and role_id are required"
                result = await _dc(
                    "PUT",
                    f"/guilds/{guild_id}/members/{target_id}/roles/{role_id}",
                    token,
                )
            elif discord_action == "remove_role":
                if not guild_id or not target_id or not role_id:
                    return "Error: guild_id, target_id, and role_id are required"
                result = await _dc(
                    "DELETE",
                    f"/guilds/{guild_id}/members/{target_id}/roles/{role_id}",
                    token,
                )
            elif discord_action == "delete_message":
                if not channel_id or not target_id:
                    return "Error: channel_id and target_id (message_id) are required"
                result = await _dc(
                    "DELETE",
                    f"/channels/{channel_id}/messages/{target_id}",
                    token,
                )
            else:
                return f"Error: Unknown discord_action '{discord_action}'"

            if result.get("success"):
                data = result.get("data", {})
                if isinstance(data, dict):
                    dumped = json.dumps(data, indent=2, default=str)[:2000]
                    return f"Discord {discord_action}: {dumped}"
                return f"Discord {discord_action}: OK"
            return f"Discord error: {result.get('message', 'Unknown error')}"

        except Exception as exc:
            return f"Error executing Discord action '{discord_action}': {exc}"

    # ── Google ────────────────────────────────────────────────────────────────

    async def _handle_google(self, service: str, **kwargs: Any) -> str:
        # Normalise service name: "gmail" → "gmail", "google_gmail" → "gmail"
        svc_key = service.replace("google_", "")  # "gmail", "calendar", "drive"
        creds_key = service  # try exact match first
        cfg = self._creds.get(creds_key) or self._creds.get(svc_key) or {}
        if not cfg:
            return (
                f"Error: {service} is not authorized. Go to the Connectors tab and click Authorize."
            )

        token = await _get_google_access_token(cfg)
        if not token:
            return (
                f"Error: {service} token is expired or missing. "
                "Go to the Connectors tab and re-authorize."
            )

        google_action = kwargs.get("google_action", "")
        if not google_action:
            return "Error: 'google_action' is required"

        try:
            # ── Gmail ──────────────────────────────────────────────────────────
            if svc_key == "gmail":
                base = "https://gmail.googleapis.com/gmail/v1/users/me"

                if google_action == "list_messages":
                    query = kwargs.get("query", "")
                    max_results = int(kwargs.get("max_results", 10))
                    params: dict[str, Any] = {"maxResults": max_results}
                    if query:
                        params["q"] = query
                    result = await _google_api("GET", f"{base}/messages", token, params=params)
                    if not result.get("success"):
                        return f"Gmail error: {result.get('message')}"
                    msgs = result["data"].get("messages", [])
                    if not msgs:
                        return "No messages found."
                    lines = [f"Found {len(msgs)} messages:"]
                    for m in msgs[:10]:
                        lines.append(f"  id={m['id']} threadId={m['threadId']}")
                    return "\n".join(lines)

                elif google_action == "get_message":
                    msg_id = kwargs.get("message_id", "")
                    if not msg_id:
                        return "Error: 'message_id' is required"
                    result = await _google_api(
                        "GET",
                        f"{base}/messages/{msg_id}",
                        token,
                        params={"format": "full"},
                    )
                    if not result.get("success"):
                        return f"Gmail error: {result.get('message')}"
                    data = result["data"]
                    headers = {
                        h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])
                    }
                    snippet = data.get("snippet", "")
                    return (
                        f"From: {headers.get('From', '?')}\n"
                        f"Subject: {headers.get('Subject', '?')}\n"
                        f"Date: {headers.get('Date', '?')}\n\n"
                        f"{snippet}"
                    )

                elif google_action == "list_labels":
                    result = await _google_api("GET", f"{base}/labels", token)
                    if not result.get("success"):
                        return f"Gmail error: {result.get('message')}"
                    labels = result["data"].get("labels", [])
                    return "\n".join(f"  {lb['name']} ({lb['id']})" for lb in labels)

                elif google_action == "send_message":
                    to = kwargs.get("to", "")
                    subject = kwargs.get("subject", "Message from Plutus")
                    body = kwargs.get("body", kwargs.get("message", ""))
                    if not to:
                        return "Error: 'to' is required"
                    raw_msg = MIMEText(body, "plain")
                    raw_msg["to"] = to
                    raw_msg["subject"] = subject
                    encoded = base64.urlsafe_b64encode(raw_msg.as_bytes()).decode()
                    result = await _google_api(
                        "POST",
                        f"{base}/messages/send",
                        token,
                        json_body={"raw": encoded},
                    )
                    if result.get("success"):
                        return f"Email sent via Gmail to {to}"
                    return f"Gmail error: {result.get('message')}"

                else:
                    return f"Error: Unknown google_action '{google_action}' for Gmail"

            # ── Google Calendar ────────────────────────────────────────────────
            elif svc_key == "calendar":
                base = "https://www.googleapis.com/calendar/v3"

                if google_action == "list_events":
                    calendar_id = kwargs.get("calendar_id", "primary")
                    max_results = int(kwargs.get("max_results", 10))
                    time_min = kwargs.get("time_min", "")
                    params = {
                        "maxResults": max_results,
                        "singleEvents": "true",
                        "orderBy": "startTime",
                    }
                    if time_min:
                        params["timeMin"] = time_min
                    result = await _google_api(
                        "GET",
                        f"{base}/calendars/{calendar_id}/events",
                        token,
                        params=params,
                    )
                    if not result.get("success"):
                        return f"Calendar error: {result.get('message')}"
                    events = result["data"].get("items", [])
                    if not events:
                        return "No upcoming events found."
                    lines = [f"Found {len(events)} events:"]
                    for ev in events:
                        start = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get(
                            "date", "?"
                        )
                        title = ev.get("summary", "(no title)")
                        lines.append(f"  [{start}] {title} — id={ev.get('id')}")
                    return "\n".join(lines)

                elif google_action == "create_event":
                    summary = kwargs.get("summary", "")
                    start = kwargs.get("start", "")
                    end = kwargs.get("end", "")
                    if not summary or not start or not end:
                        return "Error: 'summary', 'start', and 'end' are required"
                    calendar_id = kwargs.get("calendar_id", "primary")
                    body: dict[str, Any] = {
                        "summary": summary,
                        "start": {"dateTime": start, "timeZone": kwargs.get("timezone", "UTC")},
                        "end": {"dateTime": end, "timeZone": kwargs.get("timezone", "UTC")},
                    }
                    if kwargs.get("description"):
                        body["description"] = kwargs["description"]
                    if kwargs.get("location"):
                        body["location"] = kwargs["location"]
                    result = await _google_api(
                        "POST",
                        f"{base}/calendars/{calendar_id}/events",
                        token,
                        json_body=body,
                    )
                    if result.get("success"):
                        ev = result["data"]
                        return f"Event created: {ev.get('summary')} — {ev.get('htmlLink', 'OK')}"
                    return f"Calendar error: {result.get('message')}"

                elif google_action == "update_event":
                    event_id = kwargs.get("event_id", "")
                    if not event_id:
                        return "Error: 'event_id' is required"
                    calendar_id = kwargs.get("calendar_id", "primary")
                    updates = kwargs.get("updates", {})
                    result = await _google_api(
                        "PATCH",
                        f"{base}/calendars/{calendar_id}/events/{event_id}",
                        token,
                        json_body=updates,
                    )
                    if result.get("success"):
                        return f"Event {event_id} updated"
                    return f"Calendar error: {result.get('message')}"

                elif google_action == "delete_event":
                    event_id = kwargs.get("event_id", "")
                    if not event_id:
                        return "Error: 'event_id' is required"
                    calendar_id = kwargs.get("calendar_id", "primary")
                    result = await _google_api(
                        "DELETE",
                        f"{base}/calendars/{calendar_id}/events/{event_id}",
                        token,
                    )
                    if result.get("success"):
                        return f"Event {event_id} deleted"
                    return f"Calendar error: {result.get('message')}"

                else:
                    return f"Error: Unknown google_action '{google_action}' for Calendar"

            # ── Google Drive ───────────────────────────────────────────────────
            elif svc_key == "drive":
                base = "https://www.googleapis.com/drive/v3"

                if google_action == "list_files":
                    max_results = int(kwargs.get("max_results", 10))
                    query = kwargs.get("query", "")
                    params = {
                        "pageSize": max_results,
                        "fields": "files(id,name,mimeType,size,modifiedTime)",
                    }
                    if query:
                        params["q"] = query
                    result = await _google_api("GET", f"{base}/files", token, params=params)
                    if not result.get("success"):
                        return f"Drive error: {result.get('message')}"
                    files = result["data"].get("files", [])
                    if not files:
                        return "No files found."
                    lines = [f"Found {len(files)} files:"]
                    for f in files:
                        lines.append(
                            f"  {f.get('name')} ({f.get('mimeType', '?')}) — id={f.get('id')}"
                        )
                    return "\n".join(lines)

                elif google_action == "get_file":
                    file_id = kwargs.get("file_id", "")
                    if not file_id:
                        return "Error: 'file_id' is required"
                    result = await _google_api(
                        "GET",
                        f"{base}/files/{file_id}",
                        token,
                        params={"alt": "media"},
                    )
                    if not result.get("success"):
                        return f"Drive error: {result.get('message')}"
                    content = result["data"]
                    if isinstance(content, str):
                        return content[:8000]
                    return json.dumps(content, indent=2, default=str)[:8000]

                elif google_action == "get_file_metadata":
                    file_id = kwargs.get("file_id", "")
                    if not file_id:
                        return "Error: 'file_id' is required"
                    result = await _google_api(
                        "GET",
                        f"{base}/files/{file_id}",
                        token,
                        params={"fields": "id,name,mimeType,size,modifiedTime,webViewLink"},
                    )
                    if not result.get("success"):
                        return f"Drive error: {result.get('message')}"
                    return json.dumps(result["data"], indent=2, default=str)

                elif google_action == "upload_file":
                    name = kwargs.get("name", "untitled")
                    content = kwargs.get("content", "")
                    mime_type = kwargs.get("mime_type", "text/plain")
                    if not content:
                        return "Error: 'content' is required"
                    # Multipart upload
                    metadata = json.dumps({"name": name}).encode()
                    file_content = content.encode() if isinstance(content, str) else content
                    boundary = "boundary_plutus_upload"
                    body_parts = (
                        (
                            f"--{boundary}\r\n"
                            f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
                            + metadata.decode()
                            + f"\r\n--{boundary}\r\n"
                            f"Content-Type: {mime_type}\r\n\r\n"
                        ).encode()
                        + file_content
                        + f"\r\n--{boundary}--".encode()
                    )
                    result = await _google_api(
                        "POST",
                        "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
                        token,
                        data=body_parts,
                        extra_headers={"Content-Type": f"multipart/related; boundary={boundary}"},
                    )
                    if result.get("success"):
                        f_data = result["data"]
                        return f"File uploaded: {f_data.get('name')} (id={f_data.get('id')})"
                    return f"Drive error: {result.get('message')}"

                elif google_action == "read_doc":
                    file_id = kwargs.get("file_id", "")
                    if not file_id:
                        return "Error: 'file_id' is required"
                    # Export as plain text
                    result = await _google_api(
                        "GET",
                        f"{base}/files/{file_id}/export",
                        token,
                        params={"mimeType": "text/plain"},
                    )
                    if not result.get("success"):
                        # Try direct download
                        result = await _google_api(
                            "GET",
                            f"{base}/files/{file_id}",
                            token,
                            params={"alt": "media"},
                        )
                    if not result.get("success"):
                        return f"Drive error: {result.get('message')}"
                    content = result["data"]
                    if isinstance(content, str):
                        return content[:8000]
                    return json.dumps(content, indent=2, default=str)[:8000]

                else:
                    return f"Error: Unknown google_action '{google_action}' for Drive"

            else:
                return (
                    f"Error: Unknown Google service '{service}'. "
                    "Use 'gmail', 'google_calendar', or 'google_drive'."
                )

        except Exception as exc:
            return f"Error executing Google action '{google_action}' on {service}: {exc}"

    # ── GitHub ────────────────────────────────────────────────────────────────

    async def _handle_github(self, **kwargs: Any) -> str:
        cfg = self._creds.get("github", {})
        token = cfg.get("token", "")
        if not token:
            return (
                "Error: GitHub is not configured. "
                "Go to the Connectors tab to add your Personal Access Token."
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

        owner = kwargs.get("owner") or cfg.get("username", "")
        repo = kwargs.get("repo") or cfg.get("default_repo", "")

        try:
            result: dict[str, Any] = {}

            if github_action == "list_repos":
                params = {
                    "type": kwargs.get("repo_type", "owner"),
                    "sort": kwargs.get("sort", "updated"),
                    "per_page": str(kwargs.get("per_page", 30)),
                }
                result = await _gh("GET", "/user/repos", token, params=params)

            elif github_action == "get_repo":
                result = await _gh("GET", f"/repos/{owner}/{repo}", token)

            elif github_action == "create_repo":
                name = kwargs.get("name", "")
                if not name:
                    return "Error: 'name' is required"
                result = await _gh(
                    "POST",
                    "/user/repos",
                    token,
                    json_body={
                        "name": name,
                        "description": kwargs.get("description", ""),
                        "private": kwargs.get("private", True),
                        "auto_init": kwargs.get("auto_init", True),
                    },
                )

            elif github_action == "delete_repo":
                result = await _gh("DELETE", f"/repos/{owner}/{repo}", token)

            elif github_action == "fork_repo":
                result = await _gh("POST", f"/repos/{owner}/{repo}/forks", token)

            elif github_action == "list_issues":
                raw_labels = kwargs.get("labels", "")
                if isinstance(raw_labels, list):
                    raw_labels = ",".join(raw_labels)
                params = {
                    "state": kwargs.get("state", "open"),
                    "per_page": str(kwargs.get("per_page", 30)),
                }
                if raw_labels:
                    params["labels"] = raw_labels
                result = await _gh("GET", f"/repos/{owner}/{repo}/issues", token, params=params)

            elif github_action == "get_issue":
                issue_number = kwargs.get("issue_number")
                if not issue_number:
                    return "Error: 'issue_number' is required"
                result = await _gh("GET", f"/repos/{owner}/{repo}/issues/{issue_number}", token)

            elif github_action == "create_issue":
                title = kwargs.get("title", "")
                if not title:
                    return "Error: 'title' is required"
                body: dict[str, Any] = {"title": title, "body": kwargs.get("body", "")}
                if kwargs.get("labels"):
                    body["labels"] = kwargs["labels"]
                if kwargs.get("assignees"):
                    body["assignees"] = kwargs["assignees"]
                result = await _gh("POST", f"/repos/{owner}/{repo}/issues", token, json_body=body)

            elif github_action == "update_issue":
                issue_number = kwargs.get("issue_number")
                if not issue_number:
                    return "Error: 'issue_number' is required"
                update_body: dict[str, Any] = {}
                for field in ("title", "body", "state", "labels", "assignees"):
                    if kwargs.get(field) is not None:
                        update_body[field] = kwargs[field]
                result = await _gh(
                    "PATCH",
                    f"/repos/{owner}/{repo}/issues/{issue_number}",
                    token,
                    json_body=update_body,
                )

            elif github_action == "comment_on_issue":
                issue_number = kwargs.get("issue_number")
                comment_body = kwargs.get("body", "")
                if not issue_number:
                    return "Error: 'issue_number' is required"
                if not comment_body:
                    return "Error: 'body' is required"
                result = await _gh(
                    "POST",
                    f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
                    token,
                    json_body={"body": comment_body},
                )

            elif github_action == "list_pull_requests":
                params = {
                    "state": kwargs.get("state", "open"),
                    "per_page": str(kwargs.get("per_page", 30)),
                }
                result = await _gh("GET", f"/repos/{owner}/{repo}/pulls", token, params=params)

            elif github_action == "get_pull_request":
                pr_number = kwargs.get("pr_number")
                if not pr_number:
                    return "Error: 'pr_number' is required"
                result = await _gh("GET", f"/repos/{owner}/{repo}/pulls/{pr_number}", token)

            elif github_action == "create_pull_request":
                title = kwargs.get("title", "")
                head = kwargs.get("head", "")
                base_branch = kwargs.get("base", "")
                if not title or not head or not base_branch:
                    return "Error: 'title', 'head', and 'base' are required"
                result = await _gh(
                    "POST",
                    f"/repos/{owner}/{repo}/pulls",
                    token,
                    json_body={
                        "title": title,
                        "head": head,
                        "base": base_branch,
                        "body": kwargs.get("body", ""),
                        "draft": kwargs.get("draft", False),
                    },
                )

            elif github_action == "merge_pull_request":
                pr_number = kwargs.get("pr_number")
                if not pr_number:
                    return "Error: 'pr_number' is required"
                result = await _gh(
                    "PUT",
                    f"/repos/{owner}/{repo}/pulls/{pr_number}/merge",
                    token,
                    json_body={
                        "merge_method": kwargs.get("merge_method", "merge"),
                        "commit_title": kwargs.get("title", ""),
                    },
                )

            elif github_action == "list_branches":
                params = {"per_page": str(kwargs.get("per_page", 30))}
                result = await _gh("GET", f"/repos/{owner}/{repo}/branches", token, params=params)

            elif github_action == "create_branch":
                branch_name = kwargs.get("branch") or kwargs.get("name", "")
                from_branch = kwargs.get("from_branch", "main")
                if not branch_name:
                    return "Error: 'branch' is required"
                # Get SHA of from_branch
                ref_result = await _gh(
                    "GET", f"/repos/{owner}/{repo}/git/ref/heads/{from_branch}", token
                )
                if not ref_result.get("success"):
                    return f"Error: Could not get SHA of {from_branch}: {ref_result.get('message')}"
                sha = ref_result["data"]["object"]["sha"]
                result = await _gh(
                    "POST",
                    f"/repos/{owner}/{repo}/git/refs",
                    token,
                    json_body={"ref": f"refs/heads/{branch_name}", "sha": sha},
                )

            elif github_action == "delete_branch":
                branch_name = kwargs.get("branch") or kwargs.get("name", "")
                if not branch_name:
                    return "Error: 'branch' is required"
                result = await _gh(
                    "DELETE",
                    f"/repos/{owner}/{repo}/git/refs/heads/{branch_name}",
                    token,
                )

            elif github_action == "get_file":
                path = kwargs.get("path", "")
                if not path:
                    return "Error: 'path' is required"
                params = {}
                if kwargs.get("ref"):
                    params["ref"] = kwargs["ref"]
                result = await _gh(
                    "GET", f"/repos/{owner}/{repo}/contents/{path}", token, params=params
                )
                if result.get("success"):
                    data = result["data"]
                    if isinstance(data, dict) and data.get("encoding") == "base64":
                        content = base64.b64decode(data["content"]).decode(
                            "utf-8", errors="replace"
                        )
                        return f"File: {path}\nSHA: {data.get('sha')}\n\n{content[:8000]}"
                    return json.dumps(data, indent=2, default=str)[:8000]

            elif github_action == "create_or_update_file":
                path = kwargs.get("path", "")
                content = kwargs.get("content", "")
                commit_message = kwargs.get("commit_message", "")
                if not path or not content or not commit_message:
                    return "Error: 'path', 'content', and 'commit_message' are required"
                encoded_content = base64.b64encode(content.encode()).decode()
                body_data: dict[str, Any] = {
                    "message": commit_message,
                    "content": encoded_content,
                }
                if kwargs.get("branch"):
                    body_data["branch"] = kwargs["branch"]
                if kwargs.get("sha"):
                    body_data["sha"] = kwargs["sha"]
                result = await _gh(
                    "PUT",
                    f"/repos/{owner}/{repo}/contents/{path}",
                    token,
                    json_body=body_data,
                )

            elif github_action == "delete_file":
                path = kwargs.get("path", "")
                commit_message = kwargs.get("commit_message", "")
                sha = kwargs.get("sha", "")
                if not path or not commit_message or not sha:
                    return "Error: 'path', 'commit_message', and 'sha' are required"
                body_data = {"message": commit_message, "sha": sha}
                if kwargs.get("branch"):
                    body_data["branch"] = kwargs["branch"]
                result = await _gh(
                    "DELETE",
                    f"/repos/{owner}/{repo}/contents/{path}",
                    token,
                    json_body=body_data,
                )

            elif github_action == "list_commits":
                params = {"per_page": str(kwargs.get("per_page", 20))}
                if kwargs.get("branch"):
                    params["sha"] = kwargs["branch"]
                result = await _gh("GET", f"/repos/{owner}/{repo}/commits", token, params=params)

            elif github_action == "list_releases":
                params = {"per_page": str(kwargs.get("per_page", 10))}
                result = await _gh("GET", f"/repos/{owner}/{repo}/releases", token, params=params)

            elif github_action == "create_release":
                tag_name = kwargs.get("tag_name", "")
                if not tag_name:
                    return "Error: 'tag_name' is required"
                result = await _gh(
                    "POST",
                    f"/repos/{owner}/{repo}/releases",
                    token,
                    json_body={
                        "tag_name": tag_name,
                        "name": kwargs.get("name", tag_name),
                        "body": kwargs.get("body", ""),
                        "draft": kwargs.get("draft", False),
                        "prerelease": kwargs.get("prerelease", False),
                        "target_commitish": kwargs.get("target", "main"),
                    },
                )

            elif github_action == "list_workflows":
                result = await _gh("GET", f"/repos/{owner}/{repo}/actions/workflows", token)

            elif github_action == "list_workflow_runs":
                params = {"per_page": str(kwargs.get("per_page", 10))}
                if kwargs.get("workflow_id"):
                    result = await _gh(
                        "GET",
                        f"/repos/{owner}/{repo}/actions/workflows/{kwargs['workflow_id']}/runs",
                        token,
                        params=params,
                    )
                else:
                    result = await _gh(
                        "GET",
                        f"/repos/{owner}/{repo}/actions/runs",
                        token,
                        params=params,
                    )

            elif github_action == "trigger_workflow":
                workflow_id = kwargs.get("workflow_id", "")
                if not workflow_id:
                    return "Error: 'workflow_id' is required"
                result = await _gh(
                    "POST",
                    f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
                    token,
                    json_body={
                        "ref": kwargs.get("ref", "main"),
                        "inputs": kwargs.get("inputs") or {},
                    },
                )

            elif github_action == "list_collaborators":
                result = await _gh("GET", f"/repos/{owner}/{repo}/collaborators", token)

            elif github_action == "add_collaborator":
                username = kwargs.get("username", "")
                if not username:
                    return "Error: 'username' is required"
                result = await _gh(
                    "PUT",
                    f"/repos/{owner}/{repo}/collaborators/{username}",
                    token,
                    json_body={"permission": kwargs.get("permission", "push")},
                )

            elif github_action == "remove_collaborator":
                username = kwargs.get("username", "")
                if not username:
                    return "Error: 'username' is required"
                result = await _gh(
                    "DELETE",
                    f"/repos/{owner}/{repo}/collaborators/{username}",
                    token,
                )

            elif github_action == "search_repos":
                query = kwargs.get("query", "")
                if not query:
                    return "Error: 'query' is required"
                result = await _gh(
                    "GET",
                    "/search/repositories",
                    token,
                    params={"q": query, "per_page": str(kwargs.get("per_page", 10))},
                )

            elif github_action == "search_code":
                query = kwargs.get("query", "")
                if not query:
                    return "Error: 'query' is required"
                if owner and repo:
                    query = f"{query} repo:{owner}/{repo}"
                result = await _gh(
                    "GET",
                    "/search/code",
                    token,
                    params={"q": query, "per_page": str(kwargs.get("per_page", 10))},
                )

            else:
                return f"Error: Unknown github_action '{github_action}'"

            # ── Format result ──────────────────────────────────────────────────
            if result.get("success"):
                data = result.get("data", {})
                if not data:
                    return f"GitHub {github_action}: OK"
                formatted = json.dumps(data, indent=2, default=str, ensure_ascii=False)
                if len(formatted) > 8000:
                    formatted = formatted[:8000] + "\n... [truncated]"
                return formatted
            else:
                return f"GitHub error: {result.get('message', 'Unknown error')}"

        except Exception as exc:
            return f"Error executing GitHub action '{github_action}': {exc}"

    # ── Custom connectors ─────────────────────────────────────────────────────

    async def _handle_custom(self, **kwargs: Any) -> str:
        service = kwargs.get("service", "")
        if not service:
            return "Error: 'service' is required for custom action"

        # Accept both "jira" and "custom_jira"
        svc_key = service if service.startswith("custom_") else f"custom_{service}"
        cfg = self._creds.get(svc_key) or self._creds.get(service) or {}
        if not cfg:
            return (
                f"Error: Custom connector '{service}' not found. "
                "Configure it in the Connectors tab first."
            )

        base_url = cfg.get("base_url", "").rstrip("/")
        if not base_url:
            return f"Error: base_url is not configured for '{service}'"

        method = kwargs.get("method", "GET")
        endpoint = kwargs.get("endpoint", "/")
        body = kwargs.get("request_body")
        params = kwargs.get("request_params")
        extra_headers = kwargs.get("request_headers") or {}

        # Build auth headers
        auth_type = cfg.get("auth_type", "none")
        auth_headers: dict[str, str] = {}
        if auth_type == "api_key":
            key = cfg.get("api_key", "")
            header_name = cfg.get("api_key_header", "X-API-Key")
            if key:
                auth_headers[header_name] = key
        elif auth_type == "bearer_token":
            token = cfg.get("token", "")
            if token:
                auth_headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "basic_auth":
            username = cfg.get("username", "")
            password = cfg.get("password", "")
            if username and password:
                encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
                auth_headers["Authorization"] = f"Basic {encoded}"

        default_headers: dict[str, str] = cfg.get("default_headers") or {}
        all_headers = {**default_headers, **auth_headers, **extra_headers}

        url = f"{base_url}{endpoint}"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.request(
                    method, url, headers=all_headers, json=body, params=params
                )
                try:
                    resp_body = resp.json()
                    body_str = json.dumps(resp_body, indent=2)
                except Exception:
                    body_str = resp.text

                if len(body_str) > 8000:
                    body_str = body_str[:8000] + "\n... (truncated)"

                if resp.status_code >= 400:
                    return f"HTTP {resp.status_code} — Error:\n{body_str}"
                return f"HTTP {resp.status_code} — Success:\n{body_str}"

        except Exception as exc:
            return f"Error calling {service}: {exc}"
