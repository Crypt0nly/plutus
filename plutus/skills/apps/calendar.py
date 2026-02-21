"""Google Calendar skills — reliable workflows via Google Calendar Web.

Strategy: Google Calendar has well-structured DOM elements that Playwright
can interact with reliably. We use the quick-add feature and direct URL
parameters for creating events.

URL scheme: https://calendar.google.com/calendar/r/eventedit?text=TITLE&dates=START/END&details=DETAILS
Date format: YYYYMMDDTHHmmSS (e.g., 20260221T140000)
"""

from __future__ import annotations
from typing import Any
from urllib.parse import quote
from plutus.skills.engine import SkillDefinition, SkillStep


class GoogleCalendarCreateEvent(SkillDefinition):
    name = "calendar_create_event"
    description = "Create a new Google Calendar event with title, date, time, and optional details"
    app = "Google Calendar"
    triggers = ["calendar event", "schedule meeting", "add to calendar", "create event",
                "book meeting", "calendar entry", "reminder", "schedule appointment"]
    category = "calendar"
    required_params = ["title"]
    optional_params = ["date", "start_time", "end_time", "description", "location"]

    def build_steps(self, params: dict[str, Any]) -> list[SkillStep]:
        title = params["title"]
        date = params.get("date", "")  # e.g., "2026-02-21" or "tomorrow"
        start_time = params.get("start_time", "")  # e.g., "14:00"
        end_time = params.get("end_time", "")  # e.g., "15:00"
        description = params.get("description", "")
        location = params.get("location", "")

        # Build the Google Calendar URL with pre-filled fields
        url_parts = [f"https://calendar.google.com/calendar/r/eventedit?text={quote(title)}"]

        if date and start_time:
            # Convert to Google Calendar date format
            # The LLM should provide dates in YYYYMMDD format or we handle common formats
            date_clean = date.replace("-", "")
            start_clean = start_time.replace(":", "") + "00"
            if end_time:
                end_clean = end_time.replace(":", "") + "00"
            else:
                # Default: 1 hour event
                end_clean = start_clean  # will be handled by Google
            url_parts.append(f"dates={date_clean}T{start_clean}/{date_clean}T{end_clean}")

        if description:
            url_parts.append(f"details={quote(description)}")
        if location:
            url_parts.append(f"location={quote(location)}")

        url = "&".join(url_parts)

        steps = [
            SkillStep(
                description=f"Open Google Calendar event creator for: {title}",
                operation="open_url",
                params={"url": url},
                wait_after=4.0,
            ),
            SkillStep(
                description="Wait for the event editor to load",
                operation="wait_for_text",
                params={"text": "Save", "timeout": 10000},
                wait_after=1.0,
                optional=True,
            ),
        ]

        # If no date/time was provided via URL, we need to fill them in manually
        if not date or not start_time:
            steps.append(SkillStep(
                description="Get the event form to check what needs to be filled",
                operation="get_page",
                params={},
                wait_after=0.5,
            ))

        steps.append(SkillStep(
            description="Click Save to create the event",
            operation="browser_click",
            params={"text": "Save"},
            wait_after=2.0,
            retry_on_fail=True,
            max_retries=2,
        ))

        return steps


class GoogleCalendarCheckSchedule(SkillDefinition):
    name = "calendar_check_schedule"
    description = "Check your Google Calendar schedule for today or a specific date"
    app = "Google Calendar"
    triggers = ["check calendar", "what's on my calendar", "schedule today", "my schedule",
                "calendar for today", "upcoming events", "what meetings"]
    category = "calendar"
    required_params = []
    optional_params = ["date"]

    def build_steps(self, params: dict[str, Any]) -> list[SkillStep]:
        date = params.get("date", "")

        if date:
            # Navigate to specific date
            date_clean = date.replace("-", "/")
            url = f"https://calendar.google.com/calendar/r/day/{date_clean}"
        else:
            # Today's schedule
            url = "https://calendar.google.com/calendar/r/day"

        return [
            SkillStep(
                description="Open Google Calendar day view",
                operation="open_url",
                params={"url": url},
                wait_after=4.0,
            ),
            SkillStep(
                description="Wait for calendar to load",
                operation="wait_for_text",
                params={"text": "Day", "timeout": 10000},
                wait_after=1.0,
                optional=True,
            ),
            SkillStep(
                description="Read the calendar content",
                operation="get_page",
                params={},
                wait_after=0.0,
            ),
        ]


class GoogleCalendarDeleteEvent(SkillDefinition):
    name = "calendar_delete_event"
    description = "Delete a Google Calendar event by clicking on it and selecting delete"
    app = "Google Calendar"
    triggers = ["delete event", "remove from calendar", "cancel meeting", "delete calendar entry"]
    category = "calendar"
    required_params = ["event_title"]
    optional_params = ["date"]

    def build_steps(self, params: dict[str, Any]) -> list[SkillStep]:
        event_title = params["event_title"]
        date = params.get("date", "")

        steps = []

        if date:
            date_clean = date.replace("-", "/")
            url = f"https://calendar.google.com/calendar/r/day/{date_clean}"
        else:
            url = "https://calendar.google.com/calendar/r/day"

        steps.extend([
            SkillStep(
                description="Open Google Calendar",
                operation="open_url",
                params={"url": url},
                wait_after=4.0,
            ),
            SkillStep(
                description="Wait for calendar to load",
                operation="wait_for_text",
                params={"text": "Day", "timeout": 10000},
                wait_after=1.0,
                optional=True,
            ),
            SkillStep(
                description=f"Click on the event: {event_title}",
                operation="browser_click",
                params={"text": event_title},
                wait_after=2.0,
                retry_on_fail=True,
            ),
            SkillStep(
                description="Click the delete button (trash icon)",
                operation="browser_click",
                params={"selector": "[aria-label='Delete event']"},
                wait_after=1.0,
                retry_on_fail=True,
                optional=True,
            ),
            # Fallback: look for "Delete" text
            SkillStep(
                description="Click Delete (fallback by text)",
                operation="browser_click",
                params={"text": "Delete"},
                wait_after=1.0,
                optional=True,
            ),
        ])

        return steps
