"""
Moodle Assignment Monitor — Automated assignment detection, completion, and submission.

This module provides:
  - MoodleClient: Browser-based Moodle interaction (login, scrape, submit)
  - AssignmentChecker: Scans courses for new/pending assignments
  - AssignmentCompleter: Uses LLM to generate assignment responses
  - MoodleMonitor: Orchestrates the full check → complete → submit pipeline
"""

from plutus.moodle.monitor import MoodleMonitor

__all__ = ["MoodleMonitor"]
