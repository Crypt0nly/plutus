"""Google Workspace connectors — Gmail, Calendar, and Drive.

Uses OAuth 2.0 PKCE flow (no client secret needed). The user provides their
Google Cloud Console OAuth client ID, authorizes via their browser, and tokens
are stored locally at ~/.plutus/connectors/google_<service>.json.

These connectors give Plutus full read/write access to the user's:
  - Gmail: list, read, and send emails
  - Calendar: list, create, update, and delete events
  - Drive: list, read, upload, and manage files
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import UTC, datetime
from email.mime.text import MIMEText
from typing import Any

from plutus.connectors.base import BaseConnector
from plutus.connectors.google_auth import (
    SCOPES,
    clear_tokens,
    get_valid_access_token,
    load_tokens,
    start_oauth_flow,
)

logger = logging.getLogger("plutus.connectors.google")

# ── Base class ───────────────────────────────────────────────────────────────


class GoogleConnector(BaseConnector):
    """Base class for Google Workspace connectors using OAuth PKCE."""

    category = "google"
    service: str = ""  # "gmail", "calendar", "drive"
    features: list[str] = []
    oauth_scopes: list[str] = []

    @property
    def is_configured(self) -> bool:
        tokens = load_tokens(self.service)
        return bool(tokens.get("access_token"))

    def _sensitive_fields(self) -> list[str]:
        return ["client_id", "client_secret"]

    def config_schema(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "client_id",
                "label": "OAuth Client ID",
                "type": "text",
                "required": True,
                "placeholder": "123456789.apps.googleusercontent.com",
                "help": (
                    "Create at console.cloud.google.com → APIs & Services → "
                    "Credentials → OAuth 2.0 Client ID (Desktop app type)"
                ),
            },
            {
                "name": "client_secret",
                "label": "Client Secret",
                "type": "password",
                "required": True,
                "placeholder": "GOCSPX-...",
                "help": (
                    "Found alongside the Client ID in Google Cloud Console → "
                    "Credentials → your OAuth 2.0 client"
                ),
            },
        ]

    def get_config(self) -> dict[str, Any]:
        config = dict(self._config)
        # Clear sensitive fields — only send flags so the UI knows they're set
        for field in ("client_id", "client_secret"):
            val = config.get(field, "")
            config[f"_has_{field}"] = bool(val)
            config[field] = ""
        # Show token status
        tokens = load_tokens(self.service)
        if tokens.get("access_token"):
            config["auth_status"] = "authorized"
        return config

    def save_config(self, data: dict[str, Any]) -> None:
        """Save OAuth credentials, ignoring masked values from the UI."""
        # Don't overwrite real credentials with masked values
        for field in ("client_id", "client_secret"):
            val = data.get(field, "")
            if not val or "••" in val:
                data.pop(field, None)
        self._config.update(data)
        self._config["configured"] = True
        self._config_store.save(self._config)

    def clear_config(self) -> None:
        clear_tokens(self.service)
        super().clear_config()

    async def _get_client_id(self) -> str:
        return self._config.get("client_id", "")

    async def _get_client_secret(self) -> str:
        return self._config.get("client_secret", "")

    async def authorize(self) -> dict[str, Any]:
        """Start the OAuth PKCE flow — opens the user's browser."""
        client_id = await self._get_client_id()
        if not client_id:
            return {"success": False, "message": "Set your OAuth Client ID first"}
        client_secret = await self._get_client_secret()
        if not client_secret:
            return {"success": False, "message": "Set your Client Secret first"}
        return await start_oauth_flow(
            service=self.service,
            client_id=client_id,
            client_secret=client_secret,
            scopes=self.oauth_scopes or SCOPES.get(self.service, []),
        )

    async def _get_token(self) -> str | None:
        """Get a valid access token, refreshing if needed."""
        client_id = await self._get_client_id()
        if not client_id:
            return None
        client_secret = await self._get_client_secret()
        return await get_valid_access_token(self.service, client_id, client_secret)

    async def _api_request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated Google API request."""
        token = await self._get_token()
        if not token:
            return {"success": False, "message": "Not authorized — run OAuth flow first"}

        import httpx
        req_headers = {
            "Authorization": f"Bearer {token}",
            **(headers or {}),
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method, url, headers=req_headers, json=json_body,
                content=data, params=params,
            )
            if resp.status_code == 401:
                return {"success": False, "message": "Token expired or revoked — re-authorize"}
            if resp.status_code >= 400:
                return {
                    "success": False,
                    "message": f"API error {resp.status_code}: {resp.text[:300]}",
                }
            try:
                return {"success": True, "data": resp.json()}
            except Exception:
                return {"success": True, "data": resp.text}

    async def test_connection(self) -> dict[str, Any]:
        """Test by checking if we have a valid token."""
        token = await self._get_token()
        if token:
            return {"success": True, "message": f"Google {self.service.title()} is authorized"}
        tokens = load_tokens(self.service)
        if tokens:
            return {"success": False, "message": "Token expired — click 'Authorize' to reconnect"}
        return {"success": False, "message": "Not authorized yet — click 'Authorize' to connect"}

    def status(self) -> dict[str, Any]:
        base = super().status()
        base["features"] = self.features
        base["auth_type"] = "oauth"
        return base

    async def send_message(self, text: str, **kwargs: Any) -> dict[str, Any]:
        return {"success": False, "message": "Use service-specific methods instead"}


# ── Gmail ────────────────────────────────────────────────────────────────────

GMAIL_API = "https://gmail.googleapis.com/gmail/v1"


class GmailConnector(GoogleConnector):
    name = "google_gmail"
    display_name = "Gmail"
    description = "Read, search, and send emails from your Gmail account"
    icon = "Mail"
    service = "gmail"
    features = ["Read Emails", "Send Emails", "Search", "Labels"]
    oauth_scopes = SCOPES["gmail"]

    async def test_connection(self) -> dict[str, Any]:
        token = await self._get_token()
        if not token:
            tokens = load_tokens(self.service)
            if tokens:
                return {
                    "success": False,
                    "message": "Token expired — click 'Authorize' to reconnect",
                }
            return {
                "success": False,
                "message": "Not authorized yet — click 'Authorize' to connect",
            }
        # Verify by fetching profile
        result = await self._api_request("GET", f"{GMAIL_API}/users/me/profile")
        if result["success"]:
            email = result["data"].get("emailAddress", "unknown")
            return {"success": True, "message": f"Connected as {email}"}
        return result

    async def send_message(self, text: str, **kwargs: Any) -> dict[str, Any]:
        """Send an email via Gmail API."""
        to = kwargs.get("to", "")
        subject = kwargs.get("subject", "Message from Plutus")

        if not to:
            return {"success": False, "message": "Recipient ('to') is required"}

        msg = MIMEText(text)
        msg["to"] = to
        msg["subject"] = subject

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
        result = await self._api_request(
            "POST",
            f"{GMAIL_API}/users/me/messages/send",
            json_body={"raw": raw},
        )
        if result["success"]:
            return {"success": True, "message": f"Email sent to {to}"}
        return result

    async def list_messages(
        self, query: str = "", max_results: int = 10
    ) -> dict[str, Any]:
        """List Gmail messages matching a query."""
        params = {"maxResults": str(max_results)}
        if query:
            params["q"] = query
        return await self._api_request(
            "GET", f"{GMAIL_API}/users/me/messages", params=params
        )

    async def get_message(self, message_id: str) -> dict[str, Any]:
        """Get a single message by ID."""
        return await self._api_request(
            "GET",
            f"{GMAIL_API}/users/me/messages/{message_id}",
            params={"format": "full"},
        )

    async def list_labels(self) -> dict[str, Any]:
        """List all Gmail labels."""
        return await self._api_request("GET", f"{GMAIL_API}/users/me/labels")


# ── Google Calendar ──────────────────────────────────────────────────────────

CALENDAR_API = "https://www.googleapis.com/calendar/v3"


class GoogleCalendarConnector(GoogleConnector):
    name = "google_calendar"
    display_name = "Google Calendar"
    description = "View, create, and manage your calendar events"
    icon = "Calendar"
    service = "calendar"
    features = ["View Events", "Create Events", "Update Events", "Multiple Calendars"]
    oauth_scopes = SCOPES["calendar"]

    async def test_connection(self) -> dict[str, Any]:
        token = await self._get_token()
        if not token:
            tokens = load_tokens(self.service)
            if tokens:
                return {
                    "success": False,
                    "message": "Token expired — click 'Authorize' to reconnect",
                }
            return {
                "success": False,
                "message": "Not authorized yet — click 'Authorize' to connect",
            }
        # Verify by listing calendars
        result = await self._api_request(
            "GET", f"{CALENDAR_API}/users/me/calendarList", params={"maxResults": "1"}
        )
        if result["success"]:
            return {"success": True, "message": "Connected to Google Calendar"}
        return result

    async def list_events(
        self,
        calendar_id: str = "primary",
        time_min: str | None = None,
        time_max: str | None = None,
        max_results: int = 10,
    ) -> dict[str, Any]:
        """List upcoming events."""
        params: dict[str, str] = {
            "maxResults": str(max_results),
            "singleEvents": "true",
            "orderBy": "startTime",
        }
        if time_min:
            params["timeMin"] = time_min
        else:
            params["timeMin"] = datetime.now(UTC).isoformat()
        if time_max:
            params["timeMax"] = time_max

        return await self._api_request(
            "GET", f"{CALENDAR_API}/calendars/{calendar_id}/events", params=params
        )

    async def create_event(
        self,
        summary: str,
        start: str,
        end: str,
        calendar_id: str = "primary",
        description: str = "",
        location: str = "",
    ) -> dict[str, Any]:
        """Create a calendar event."""
        event_body: dict[str, Any] = {
            "summary": summary,
            "start": {"dateTime": start},
            "end": {"dateTime": end},
        }
        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location

        return await self._api_request(
            "POST", f"{CALENDAR_API}/calendars/{calendar_id}/events",
            json_body=event_body,
        )

    async def update_event(
        self,
        event_id: str,
        updates: dict[str, Any],
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        """Update an existing event."""
        return await self._api_request(
            "PATCH", f"{CALENDAR_API}/calendars/{calendar_id}/events/{event_id}",
            json_body=updates,
        )

    async def delete_event(
        self, event_id: str, calendar_id: str = "primary"
    ) -> dict[str, Any]:
        """Delete a calendar event."""
        return await self._api_request(
            "DELETE", f"{CALENDAR_API}/calendars/{calendar_id}/events/{event_id}"
        )

    async def send_message(self, text: str, **kwargs: Any) -> dict[str, Any]:
        """Quick-create an event from natural language (simplified)."""
        # For test messages, create a quick event
        result = await self.create_event(
            summary=text,
            start=datetime.now(UTC).isoformat(),
            end=datetime.now(UTC).isoformat(),
        )
        if result["success"]:
            return {"success": True, "message": "Calendar event created"}
        return result


# ── Google Drive ─────────────────────────────────────────────────────────────

DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"


class GoogleDriveConnector(GoogleConnector):
    name = "google_drive"
    display_name = "Google Drive"
    description = "Browse, read, and upload files in your Google Drive"
    icon = "HardDrive"
    service = "drive"
    features = ["List Files", "Read Files", "Upload Files", "Search"]
    oauth_scopes = SCOPES["drive"]

    async def test_connection(self) -> dict[str, Any]:
        token = await self._get_token()
        if not token:
            tokens = load_tokens(self.service)
            if tokens:
                return {
                    "success": False,
                    "message": "Token expired — click 'Authorize' to reconnect",
                }
            return {
                "success": False,
                "message": "Not authorized yet — click 'Authorize' to connect",
            }
        # Verify by checking storage quota
        result = await self._api_request(
            "GET", f"{DRIVE_API}/about", params={"fields": "user,storageQuota"}
        )
        if result["success"]:
            user = result["data"].get("user", {})
            email = user.get("emailAddress", "unknown")
            return {"success": True, "message": f"Connected to Drive as {email}"}
        return result

    async def list_files(
        self,
        query: str = "",
        max_results: int = 20,
        order_by: str = "modifiedTime desc",
    ) -> dict[str, Any]:
        """List files in Drive."""
        params: dict[str, str] = {
            "pageSize": str(max_results),
            "orderBy": order_by,
            "fields": "files(id,name,mimeType,size,modifiedTime,webViewLink,shared,owners)",
            "includeItemsFromAllDrives": "true",
            "supportsAllDrives": "true",
            "corpora": "allDrives",
        }
        if query:
            params["q"] = query
        return await self._api_request("GET", f"{DRIVE_API}/files", params=params)

    async def get_file_content(self, file_id: str) -> dict[str, Any]:
        """Download a file's content."""
        return await self._api_request(
            "GET", f"{DRIVE_API}/files/{file_id}", params={"alt": "media"}
        )

    async def get_file_metadata(self, file_id: str) -> dict[str, Any]:
        """Get file metadata."""
        return await self._api_request(
            "GET", f"{DRIVE_API}/files/{file_id}",
            params={"fields": "id,name,mimeType,size,modifiedTime,webViewLink,parents"},
        )

    async def upload_file(
        self,
        name: str,
        content: str | bytes,
        mime_type: str = "text/plain",
        folder_id: str | None = None,
    ) -> dict[str, Any]:
        """Upload a file to Drive using simple upload."""
        metadata: dict[str, Any] = {"name": name, "mimeType": mime_type}
        if folder_id:
            metadata["parents"] = [folder_id]

        token = await self._get_token()
        if not token:
            return {"success": False, "message": "Not authorized"}

        import httpx

        # Multipart upload: metadata + content
        boundary = "plutus_upload_boundary"
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        else:
            content_bytes = content

        body = (
            f"--{boundary}\r\n"
            f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{json.dumps(metadata)}\r\n"
            f"--{boundary}\r\n"
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode() + content_bytes + f"\r\n--{boundary}--".encode()

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{DRIVE_UPLOAD_API}/files?uploadType=multipart",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": f"multipart/related; boundary={boundary}",
                },
                content=body,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                return {
                    "success": True,
                    "message": f"Uploaded '{name}' to Drive",
                    "data": data,
                }
            return {
                "success": False,
                "message": f"Upload failed: {resp.status_code} — {resp.text[:300]}",
            }

    async def read_doc(self, file_id: str, mime_type: str = "") -> dict[str, Any]:
        """Export a Google Doc, Sheet, or Slides file as plain text.

        Google Workspace files (Docs, Sheets, Slides) cannot be downloaded
        directly — they must be exported via the Drive export endpoint.
        Binary Office files (.docx, .pptx, .xlsx) are downloaded and parsed
        locally using python-docx / python-pptx.

        Args:
            file_id: The Drive file ID.
            mime_type: The file's mimeType (optional, auto-detected if empty).

        Returns:
            {"success": True, "data": {"text": "...", "mime_type": "..."}}
        """
        # Auto-detect mime type if not provided
        if not mime_type:
            meta = await self.get_file_metadata(file_id)
            if not meta.get("success"):
                return meta
            mime_type = meta["data"].get("mimeType", "")

        GOOGLE_DOC_TYPES = {
            "application/vnd.google-apps.document": "text/plain",
            "application/vnd.google-apps.spreadsheet": "text/csv",
            "application/vnd.google-apps.presentation": "text/plain",
        }

        OFFICE_TYPES = {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }

        # ── Google Workspace files: export as plain text ─────────────────────
        if mime_type in GOOGLE_DOC_TYPES:
            export_mime = GOOGLE_DOC_TYPES[mime_type]
            token = await self._get_token()
            if not token:
                return {"success": False, "message": "Not authorized"}
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{DRIVE_API}/files/{file_id}/export",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"mimeType": export_mime},
                )
                if resp.status_code >= 400:
                    return {
                        "success": False,
                        "message": f"Export failed: {resp.status_code} — {resp.text[:300]}",
                    }
                text = resp.text
                if len(text) > 50_000:
                    text = text[:50_000] + "\n... [truncated]"
                return {
                    "success": True,
                    "data": {"text": text, "mime_type": mime_type},
                }

        # ── Office binary files: download then parse locally ──────────────────
        if mime_type in OFFICE_TYPES:
            import tempfile, os
            token = await self._get_token()
            if not token:
                return {"success": False, "message": "Not authorized"}
            import httpx
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(
                    f"{DRIVE_API}/files/{file_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"alt": "media"},
                )
                if resp.status_code >= 400:
                    return {
                        "success": False,
                        "message": f"Download failed: {resp.status_code}",
                    }
                # Write to a temp file and parse
                suffix = (
                    ".docx" if "word" in mime_type
                    else ".pptx" if "presentation" in mime_type
                    else ".xlsx"
                )
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                    f.write(resp.content)
                    tmp_path = f.name
            try:
                from pathlib import Path as _Path
                from plutus.tools.filesystem import FilesystemTool
                fs = FilesystemTool()
                if suffix == ".docx":
                    text = fs._read_docx(_Path(tmp_path))
                elif suffix == ".pptx":
                    text = fs._read_pptx(_Path(tmp_path))
                else:
                    # xlsx: return CSV export instead
                    return await self.read_doc(file_id,
                        "application/vnd.google-apps.spreadsheet")
                return {
                    "success": True,
                    "data": {"text": text, "mime_type": mime_type},
                }
            finally:
                os.unlink(tmp_path)

        # ── Plain text / other: try direct download ─────────────────────────
        result = await self.get_file_content(file_id)
        if result.get("success"):
            text = str(result.get("data", ""))
            if len(text) > 50_000:
                text = text[:50_000] + "\n... [truncated]"
            return {"success": True, "data": {"text": text, "mime_type": mime_type}}
        return result

    async def send_message(self, text: str, **kwargs: Any) -> dict[str, Any]:
        """Upload text as a file to Drive (for test messages)."""
        filename = kwargs.get("filename", "plutus_message.txt")
        result = await self.upload_file(name=filename, content=text)
        if result["success"]:
            return {"success": True, "message": f"File '{filename}' uploaded to Drive"}
        return result
