"""Gmail skills — reliable workflows via Gmail Web.

Strategy: Gmail has well-known URL schemes and DOM structure.
Compose URL: https://mail.google.com/mail/?view=cm&to=EMAIL&su=SUBJECT&body=BODY
Inbox: https://mail.google.com/mail/u/0/#inbox
Search: https://mail.google.com/mail/u/0/#search/QUERY
"""

from __future__ import annotations
from typing import Any
from urllib.parse import quote
from plutus.skills.engine import SkillDefinition, SkillStep


class GmailSendEmail(SkillDefinition):
    name = "gmail_send_email"
    description = "Send an email via Gmail with recipient, subject, and body"
    app = "Gmail"
    triggers = ["send email", "send mail", "email someone", "compose email",
                "write email", "gmail send", "send a mail"]
    category = "email"
    required_params = ["to", "subject", "body"]
    optional_params = ["cc", "bcc"]

    def build_steps(self, params: dict[str, Any]) -> list[SkillStep]:
        to = params["to"]
        subject = params["subject"]
        body = params["body"]
        cc = params.get("cc", "")
        bcc = params.get("bcc", "")

        # Build Gmail compose URL
        url = f"https://mail.google.com/mail/?view=cm&to={quote(to)}&su={quote(subject)}&body={quote(body)}"
        if cc:
            url += f"&cc={quote(cc)}"
        if bcc:
            url += f"&bcc={quote(bcc)}"

        return [
            SkillStep(
                description=f"Open Gmail compose window for {to}",
                operation="open_url",
                params={"url": url},
                wait_after=4.0,
            ),
            SkillStep(
                description="Wait for compose window to load",
                operation="wait_for_text",
                params={"text": "Send", "timeout": 10000},
                wait_after=1.0,
                optional=True,
            ),
            SkillStep(
                description="Get the compose form to verify fields",
                operation="get_page",
                params={},
                wait_after=0.5,
            ),
            SkillStep(
                description="Click Send to send the email",
                operation="browser_click",
                params={"selector": "[aria-label*='Send']"},
                wait_after=2.0,
                retry_on_fail=True,
                max_retries=2,
            ),
        ]


class GmailReadInbox(SkillDefinition):
    name = "gmail_read_inbox"
    description = "Read your Gmail inbox — see recent emails and subjects"
    app = "Gmail"
    triggers = ["check email", "read email", "check inbox", "gmail inbox",
                "any new emails", "read mail", "check my mail"]
    category = "email"
    required_params = []
    optional_params = []

    def build_steps(self, params: dict[str, Any]) -> list[SkillStep]:
        return [
            SkillStep(
                description="Open Gmail inbox",
                operation="open_url",
                params={"url": "https://mail.google.com/mail/u/0/#inbox"},
                wait_after=4.0,
            ),
            SkillStep(
                description="Wait for inbox to load",
                operation="wait_for_text",
                params={"text": "Inbox", "timeout": 10000},
                wait_after=1.0,
                optional=True,
            ),
            SkillStep(
                description="Read inbox content",
                operation="get_page",
                params={},
                wait_after=0.0,
            ),
        ]


class GmailSearchEmail(SkillDefinition):
    name = "gmail_search_email"
    description = "Search for emails in Gmail by keyword, sender, or subject"
    app = "Gmail"
    triggers = ["search email", "find email", "search gmail", "email from",
                "find mail from"]
    category = "email"
    required_params = ["query"]
    optional_params = []

    def build_steps(self, params: dict[str, Any]) -> list[SkillStep]:
        query = params["query"]
        url = f"https://mail.google.com/mail/u/0/#search/{quote(query)}"

        return [
            SkillStep(
                description=f"Search Gmail for: {query}",
                operation="open_url",
                params={"url": url},
                wait_after=4.0,
            ),
            SkillStep(
                description="Wait for search results to load",
                operation="wait_for_text",
                params={"text": "Search results", "timeout": 10000},
                wait_after=1.0,
                optional=True,
            ),
            SkillStep(
                description="Read search results",
                operation="get_page",
                params={},
                wait_after=0.0,
            ),
        ]
