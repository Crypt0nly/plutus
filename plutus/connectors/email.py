"""Email connector for Plutus.

Allows Plutus to send emails via SMTP and optionally read emails via IMAP.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import smtplib
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email import encoders
from typing import Any

from plutus.connectors.base import BaseConnector

logger = logging.getLogger("plutus.connectors.email")


class EmailConnector(BaseConnector):
    name = "email"
    display_name = "Email"
    description = "Send emails via SMTP (Gmail, Outlook, custom)"
    icon = "Mail"

    def _sensitive_fields(self) -> list[str]:
        return ["password"]

    def config_schema(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "email",
                "label": "Email Address",
                "type": "text",
                "required": True,
                "placeholder": "plutus@gmail.com",
                "help": "The email address Plutus will send from",
            },
            {
                "name": "password",
                "label": "App Password",
                "type": "password",
                "required": True,
                "placeholder": "xxxx xxxx xxxx xxxx",
                "help": "For Gmail: generate at myaccount.google.com/apppasswords",
            },
            {
                "name": "smtp_server",
                "label": "SMTP Server",
                "type": "text",
                "required": False,
                "placeholder": "smtp.gmail.com",
                "help": "Auto-detected for Gmail and Outlook",
            },
            {
                "name": "smtp_port",
                "label": "SMTP Port",
                "type": "number",
                "required": False,
                "placeholder": "587",
                "help": "Default: 587 (TLS)",
            },
        ]

    async def test_connection(self) -> dict[str, Any]:
        """Test SMTP connection."""
        email = self._config.get("email", "")
        password = self._config.get("password", "")
        smtp_server = self._config.get("smtp_server", "")
        smtp_port = int(self._config.get("smtp_port", 587))

        if not email or not password:
            return {"success": False, "message": "Email and password are required"}

        # Auto-detect SMTP server
        if not smtp_server:
            domain = email.split("@")[-1].lower()
            smtp_map = {
                "gmail.com": "smtp.gmail.com",
                "outlook.com": "smtp-mail.outlook.com",
                "hotmail.com": "smtp-mail.outlook.com",
                "yahoo.com": "smtp.mail.yahoo.com",
                "gmx.de": "mail.gmx.net",
                "gmx.com": "mail.gmx.net",
                "web.de": "smtp.web.de",
            }
            smtp_server = smtp_map.get(domain, f"smtp.{domain}")
            self._config["smtp_server"] = smtp_server
            self._config_store.save(self._config)

        try:
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
            server.starttls()
            server.login(email, password)
            server.quit()
            return {
                "success": True,
                "message": f"Connected to {smtp_server}:{smtp_port} as {email}",
            }
        except Exception as e:
            return {"success": False, "message": f"SMTP connection failed: {str(e)}"}

    async def send_message(self, text: str, **kwargs: Any) -> dict[str, Any]:
        """Send an email."""
        to = kwargs.get("to", "")
        subject = kwargs.get("subject", "Message from Plutus")
        html = kwargs.get("html", False)

        if not to:
            return {"success": False, "message": "Recipient ('to') is required"}

        email = self._config.get("email", "")
        password = self._config.get("password", "")
        smtp_server = self._config.get("smtp_server", "smtp.gmail.com")
        smtp_port = int(self._config.get("smtp_port", 587))

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = email
            msg["To"] = to

            content_type = "html" if html else "plain"
            msg.attach(MIMEText(text, content_type))

            server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
            server.starttls()
            server.login(email, password)
            server.send_message(msg)
            server.quit()

            return {"success": True, "message": f"Email sent to {to}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to send email: {str(e)}"}

    async def send_file(
        self,
        file_path: str,
        caption: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send an email with a file attachment.

        Args:
            file_path: Absolute path to the file to attach.
            caption: Optional message body text to include alongside the attachment.
            to: Recipient email address (required).
            subject: Email subject line (defaults to the filename).
        """
        to = kwargs.get("to", "")
        if not to:
            return {"success": False, "message": "Recipient ('to') is required for email file sending"}

        if not os.path.isfile(file_path):
            return {"success": False, "message": f"File not found: {file_path}"}

        file_name = os.path.basename(file_path)
        subject = kwargs.get("subject", f"File from Plutus: {file_name}")

        email_addr = self._config.get("email", "")
        password = self._config.get("password", "")
        smtp_server = self._config.get("smtp_server", "smtp.gmail.com")
        smtp_port = int(self._config.get("smtp_port", 587))

        try:
            msg = MIMEMultipart()
            msg["Subject"] = subject
            msg["From"] = email_addr
            msg["To"] = to

            # Add body text if provided
            body = caption or f"Please find the attached file: {file_name}"
            msg.attach(MIMEText(body, "plain"))

            # Detect MIME type
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type:
                main_type, sub_type = mime_type.split("/", 1)
            else:
                main_type, sub_type = "application", "octet-stream"

            with open(file_path, "rb") as f:
                part = MIMEBase(main_type, sub_type)
                part.set_payload(f.read())

            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                "attachment",
                filename=file_name,
            )
            msg.attach(part)

            server = smtplib.SMTP(smtp_server, smtp_port, timeout=15)
            server.starttls()
            server.login(email_addr, password)
            server.send_message(msg)
            server.quit()

            return {"success": True, "message": f"Email with attachment '{file_name}' sent to {to}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to send email with attachment: {str(e)}"}
