"""WhatsApp connector for Plutus.

Uses WhatsApp Web via the existing browser control system.
The user must be logged into WhatsApp Web in the Plutus-controlled browser.
This connector provides a programmatic interface for the agent to send messages.
"""

from __future__ import annotations

import logging
from typing import Any

from plutus.connectors.base import BaseConnector

logger = logging.getLogger("plutus.connectors.whatsapp")


class WhatsAppConnector(BaseConnector):
    name = "whatsapp"
    display_name = "WhatsApp"
    description = "Send messages via WhatsApp Web (browser-based)"
    icon = "MessageCircle"

    def _sensitive_fields(self) -> list[str]:
        return []

    def config_schema(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "default_contact",
                "label": "Default Contact",
                "type": "text",
                "required": False,
                "placeholder": "e.g. Mom, John Smith",
                "help": "Default contact to message (can be overridden per message)",
            },
            {
                "name": "phone_number",
                "label": "Your Phone Number",
                "type": "text",
                "required": False,
                "placeholder": "+1234567890",
                "help": "Your WhatsApp phone number (for reference only)",
            },
        ]

    async def test_connection(self) -> dict[str, Any]:
        """Check if WhatsApp Web is accessible."""
        try:
            # Try to import browser control
            from plutus.pc.browser_control import BrowserControl
            browser = BrowserControl()
            connected = await browser.is_connected()

            if connected:
                return {
                    "success": True,
                    "message": (
                        "Browser connected. To use WhatsApp, make sure you're logged "
                        "into WhatsApp Web (web.whatsapp.com) in the Plutus browser."
                    ),
                }
            else:
                return {
                    "success": False,
                    "message": (
                        "Browser not connected. Start Plutus with a Chromium browser "
                        "running with --remote-debugging-port=9222, then log into "
                        "WhatsApp Web."
                    ),
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"WhatsApp check failed: {str(e)}. Make sure the browser is running.",
            }

    async def send_message(self, text: str, **kwargs: Any) -> dict[str, Any]:
        """Send a WhatsApp message via browser automation.

        This creates a task for the agent to execute using the WhatsApp Web skill.
        """
        contact = kwargs.get("contact", self._config.get("default_contact", ""))
        if not contact:
            return {"success": False, "message": "Contact name is required"}

        # This will be handled by the agent using the whatsapp_send_message skill
        return {
            "success": True,
            "message": f"WhatsApp message queued for {contact}",
            "action_required": True,
            "skill": "whatsapp_send_message",
            "params": {"contact": contact, "message": text},
        }

    async def send_file(
        self,
        file_path: str,
        caption: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a file via WhatsApp Web using browser automation.

        Uses the WhatsApp Web file attachment flow:
        1. Navigate to the contact's chat
        2. Click the paperclip / attachment icon
        3. Upload the file via the hidden file input
        4. Optionally add a caption
        5. Click Send

        Args:
            file_path: Absolute path to the file to send.
            caption: Optional caption to include with the file.
            contact: Contact name or phone number (falls back to default_contact).
        """
        import os
        contact = kwargs.get("contact", self._config.get("default_contact", ""))
        if not contact:
            return {"success": False, "message": "Contact name is required for WhatsApp file sending"}

        if not os.path.isfile(file_path):
            return {"success": False, "message": f"File not found: {file_path}"}

        file_name = os.path.basename(file_path)

        # Delegate to the agent via action_required — the agent will use browser
        # automation to open WhatsApp Web, navigate to the contact, attach the file
        # and send it.
        return {
            "success": True,
            "message": f"WhatsApp file send queued for {contact}: {file_name}",
            "action_required": True,
            "skill": "whatsapp_send_file",
            "params": {
                "contact": contact,
                "file_path": file_path,
                "caption": caption,
            },
        }
