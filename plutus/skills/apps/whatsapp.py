"""WhatsApp skills — reliable workflows for WhatsApp Web.

Strategy: WhatsApp Web (web.whatsapp.com) is the most reliable way to
automate WhatsApp because we can use Playwright/CDP to interact with
DOM elements directly. No pixel guessing.

The URL scheme `https://web.whatsapp.com/send?phone=NUMBER&text=MESSAGE`
can be used to open a chat with a specific contact and pre-fill a message.

For searching contacts, we use the search bar at the top of WhatsApp Web.
"""

from __future__ import annotations
from typing import Any
from plutus.skills.engine import SkillDefinition, SkillStep


class WhatsAppSendMessage(SkillDefinition):
    name = "whatsapp_send_message"
    description = "Send a WhatsApp message to a contact by name or phone number"
    app = "WhatsApp"
    triggers = ["whatsapp", "send message", "text someone", "message on whatsapp", "whatsapp message"]
    category = "messaging"
    required_params = ["contact", "message"]
    optional_params = ["phone_number"]

    def build_steps(self, params: dict[str, Any]) -> list[SkillStep]:
        contact = params["contact"]
        message = params["message"]
        phone = params.get("phone_number")

        steps = []

        if phone:
            # Direct link with phone number — most reliable
            url = f"https://web.whatsapp.com/send?phone={phone}&text={message}"
            steps.append(SkillStep(
                description=f"Open WhatsApp Web chat with {contact}",
                operation="open_url",
                params={"url": url},
                wait_after=5.0,  # WhatsApp Web takes time to load
            ))
            steps.append(SkillStep(
                description="Wait for WhatsApp Web to fully load",
                operation="wait_for_text",
                params={"text": "Type a message", "timeout": 15000},
                wait_after=1.0,
                optional=True,
            ))
            steps.append(SkillStep(
                description=f"Press Enter to send the message",
                operation="browser_press",
                params={"key": "Enter"},
                wait_after=1.0,
            ))
        else:
            # Search by contact name
            steps.append(SkillStep(
                description="Open WhatsApp Web",
                operation="open_url",
                params={"url": "https://web.whatsapp.com"},
                wait_after=5.0,
            ))
            steps.append(SkillStep(
                description="Wait for WhatsApp Web to load",
                operation="wait_for_text",
                params={"text": "Search or start new chat", "timeout": 20000},
                wait_after=2.0,
                retry_on_fail=True,
                max_retries=3,
                optional=True,
            ))
            steps.append(SkillStep(
                description=f"Click the search bar",
                operation="browser_click",
                params={"selector": "[data-testid='chat-list-search']"},
                wait_after=0.5,
                retry_on_fail=True,
                optional=True,
            ))
            # Fallback: click by placeholder text
            steps.append(SkillStep(
                description=f"Click search bar (fallback by placeholder)",
                operation="browser_click",
                params={"placeholder": "Search or start new chat"},
                wait_after=0.5,
                optional=True,
            ))
            steps.append(SkillStep(
                description=f"Type contact name: {contact}",
                operation="keyboard_type",
                params={"text": contact},
                wait_after=2.0,
            ))
            steps.append(SkillStep(
                description=f"Click on contact: {contact}",
                operation="browser_click",
                params={"text": contact},
                wait_after=1.5,
                retry_on_fail=True,
                max_retries=2,
            ))
            steps.append(SkillStep(
                description=f"Click the message input box",
                operation="browser_click",
                params={"selector": "[data-testid='conversation-compose-box-input']"},
                wait_after=0.5,
                retry_on_fail=True,
                optional=True,
            ))
            # Fallback: click by placeholder
            steps.append(SkillStep(
                description=f"Click message input (fallback)",
                operation="browser_click",
                params={"placeholder": "Type a message"},
                wait_after=0.5,
                optional=True,
            ))
            steps.append(SkillStep(
                description=f"Type the message",
                operation="keyboard_type",
                params={"text": message},
                wait_after=0.5,
            ))
            steps.append(SkillStep(
                description="Send the message",
                operation="browser_press",
                params={"key": "Enter"},
                wait_after=1.0,
            ))

        return steps


class WhatsAppReadMessages(SkillDefinition):
    name = "whatsapp_read_messages"
    description = "Read recent messages from a WhatsApp contact"
    app = "WhatsApp"
    triggers = ["read whatsapp", "check whatsapp", "whatsapp messages from", "unread messages"]
    category = "messaging"
    required_params = ["contact"]
    optional_params = []

    def build_steps(self, params: dict[str, Any]) -> list[SkillStep]:
        contact = params["contact"]
        return [
            SkillStep(
                description="Open WhatsApp Web",
                operation="open_url",
                params={"url": "https://web.whatsapp.com"},
                wait_after=5.0,
            ),
            SkillStep(
                description="Wait for WhatsApp Web to load",
                operation="wait_for_text",
                params={"text": "Search or start new chat", "timeout": 20000},
                wait_after=2.0,
                optional=True,
            ),
            SkillStep(
                description="Click the search bar",
                operation="browser_click",
                params={"placeholder": "Search or start new chat"},
                wait_after=0.5,
                optional=True,
            ),
            SkillStep(
                description=f"Search for contact: {contact}",
                operation="keyboard_type",
                params={"text": contact},
                wait_after=2.0,
            ),
            SkillStep(
                description=f"Click on contact: {contact}",
                operation="browser_click",
                params={"text": contact},
                wait_after=2.0,
                retry_on_fail=True,
            ),
            SkillStep(
                description="Read the conversation content",
                operation="get_page",
                params={},
                wait_after=0.0,
            ),
        ]


class WhatsAppSearchContact(SkillDefinition):
    name = "whatsapp_search_contact"
    description = "Search for a contact in WhatsApp"
    app = "WhatsApp"
    triggers = ["find contact whatsapp", "search whatsapp contact"]
    category = "messaging"
    required_params = ["contact"]
    optional_params = []

    def build_steps(self, params: dict[str, Any]) -> list[SkillStep]:
        contact = params["contact"]
        return [
            SkillStep(
                description="Open WhatsApp Web",
                operation="open_url",
                params={"url": "https://web.whatsapp.com"},
                wait_after=5.0,
            ),
            SkillStep(
                description="Wait for WhatsApp Web to load",
                operation="wait_for_text",
                params={"text": "Search or start new chat", "timeout": 20000},
                wait_after=2.0,
                optional=True,
            ),
            SkillStep(
                description="Click the search bar",
                operation="browser_click",
                params={"placeholder": "Search or start new chat"},
                wait_after=0.5,
                optional=True,
            ),
            SkillStep(
                description=f"Search for: {contact}",
                operation="keyboard_type",
                params={"text": contact},
                wait_after=2.0,
            ),
            SkillStep(
                description="Read search results",
                operation="get_page",
                params={},
                wait_after=0.0,
            ),
        ]
