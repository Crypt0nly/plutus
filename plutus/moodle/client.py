"""
MoodleClient — Browser-based Moodle interaction layer.

Uses Playwright directly (not through PCControlTool) for reliable, 
headless automation. Handles login, course scraping, assignment detection,
and file submission.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("plutus.moodle.client")


@dataclass
class Assignment:
    """Represents a Moodle assignment."""
    id: int                          # Moodle activity ID (from URL)
    course_id: int                   # Course ID
    course_name: str                 # e.g. "Organizational Behavior"
    title: str                       # e.g. "Week 2 Class Participation"
    url: str                         # Full URL to assignment page
    opened: Optional[str] = None     # When it opened
    due: Optional[str] = None        # Due date string
    status: str = "unknown"          # "not_submitted", "submitted", "graded", "overdue"
    grade: Optional[str] = None      # e.g. "90.0 % (A-)"
    description: str = ""            # Assignment instructions
    submission_type: str = "file"    # "file", "online_text", "both"
    is_overdue: bool = False
    needs_action: bool = False       # True if unsubmitted and not yet graded


@dataclass
class Course:
    """Represents a Moodle course."""
    id: int
    name: str
    url: str
    semester: str = ""
    instructor: str = ""
    assignments: list[Assignment] = field(default_factory=list)


class MoodleClient:
    """
    Browser-based Moodle client using Playwright.
    
    Handles the full lifecycle:
    1. Login via Microsoft OAuth
    2. Scrape courses and assignments
    3. Read assignment details
    4. Submit completed work
    """

    def __init__(self, base_url: str = "https://elearning.unyp.cz"):
        self.base_url = base_url.rstrip("/")
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._logged_in = False
        self._storage_path = Path.home() / ".plutus" / "moodle_session.json"

    async def _ensure_browser(self) -> bool:
        """Initialize Playwright browser if not already running."""
        if self._page and not self._page.is_closed():
            return True

        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            
            # Launch browser (headless for server, headed for debugging)
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-blink-features=AutomationControlled",
                ],
            )

            # Try to restore saved session
            if self._storage_path.exists():
                try:
                    storage = json.loads(self._storage_path.read_text())
                    self._context = await self._browser.new_context(
                        storage_state=storage,
                        viewport={"width": 1280, "height": 720},
                    )
                    logger.info("Restored saved Moodle session")
                except Exception:
                    self._context = await self._browser.new_context(
                        viewport={"width": 1280, "height": 720},
                    )
            else:
                self._context = await self._browser.new_context(
                    viewport={"width": 1280, "height": 720},
                )

            self._page = await self._context.new_page()
            return True

        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return False
        except Exception as e:
            logger.error(f"Browser init failed: {e}")
            return False

    async def _save_session(self):
        """Save browser session state for reuse."""
        if self._context:
            try:
                self._storage_path.parent.mkdir(parents=True, exist_ok=True)
                storage = await self._context.storage_state()
                self._storage_path.write_text(json.dumps(storage))
                logger.info("Saved Moodle session state")
            except Exception as e:
                logger.warning(f"Failed to save session: {e}")

    async def login(self, email: str, password: str) -> bool:
        """
        Log into Moodle via Microsoft OAuth.
        
        Returns True if login was successful.
        """
        if not await self._ensure_browser():
            return False

        try:
            # Navigate to Moodle login
            await self._page.goto(
                f"{self.base_url}/login/index.php",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            await asyncio.sleep(1)

            # Check if already logged in (session restored)
            if await self._check_logged_in():
                logger.info("Already logged in via saved session")
                self._logged_in = True
                return True

            # Click the Microsoft login button
            try:
                ms_button = self._page.locator('a[href*="microsoft"], a[title*="Microsoft"], .login-identityprovider-btn, a:has-text("Microsoft")')
                await ms_button.first.click(timeout=5000)
            except Exception:
                # Try alternative selectors
                await self._page.click('text="Log in with"', timeout=5000)

            await asyncio.sleep(2)

            # Microsoft OAuth flow — enter email
            try:
                email_input = self._page.locator('input[type="email"], input[name="loginfmt"]')
                await email_input.first.fill(email, timeout=10000)
                await self._page.click('input[type="submit"], button[type="submit"]')
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Failed to enter email: {e}")
                return False

            # Enter password
            try:
                pwd_input = self._page.locator('input[type="password"], input[name="passwd"]')
                await pwd_input.first.fill(password, timeout=10000)
                await self._page.click('input[type="submit"], button[type="submit"]')
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Failed to enter password: {e}")
                return False

            # Handle "Stay signed in?" prompt
            try:
                stay_signed_in = self._page.locator('input[type="submit"][value="Yes"], button:has-text("Yes")')
                await stay_signed_in.first.click(timeout=5000)
                await asyncio.sleep(2)
            except Exception:
                pass  # May not appear

            # Wait for redirect back to Moodle
            try:
                await self._page.wait_for_url(f"{self.base_url}/**", timeout=15000)
            except Exception:
                pass

            # Verify login
            if await self._check_logged_in():
                self._logged_in = True
                await self._save_session()
                logger.info("Successfully logged into Moodle")
                return True
            else:
                logger.error("Login flow completed but not logged in")
                return False

        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    async def _check_logged_in(self) -> bool:
        """Check if currently logged into Moodle."""
        try:
            url = self._page.url
            if "login" in url and "index.php" in url:
                # Try navigating to dashboard
                await self._page.goto(f"{self.base_url}/my/", timeout=10000)
                await asyncio.sleep(1)
                url = self._page.url
            
            # If we're on the dashboard or any non-login page, we're logged in
            if "login" not in url or "my" in url:
                # Double-check by looking for user menu
                try:
                    await self._page.locator('#user-menu-toggle, .usermenu, [data-region="drawer"]').first.wait_for(timeout=3000)
                    return True
                except Exception:
                    return "my" in url or "course" in url
            return False
        except Exception:
            return False

    async def get_courses(self, current_semester_only: bool = True) -> list[Course]:
        """
        Get all enrolled courses from the Moodle dashboard.
        
        If current_semester_only is True, only returns courses from the
        most recent semester (e.g. SPRING/2025-2026).
        """
        if not await self._ensure_browser():
            return []

        try:
            await self._page.goto(
                f"{self.base_url}/my/courses.php",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            await asyncio.sleep(1)

            # Extract course links via JavaScript
            courses_data = await self._page.evaluate("""() => {
                const cards = document.querySelectorAll('.card a[href*="course/view.php"]');
                const courses = [];
                cards.forEach(c => {
                    const match = c.href.match(/id=(\\d+)/);
                    if (match) {
                        const name = c.textContent.trim();
                        courses.push({
                            id: parseInt(match[1]),
                            name: name,
                            url: c.href,
                        });
                    }
                });
                return courses;
            }""")

            courses = []
            for cd in courses_data:
                name = cd["name"]
                # Parse semester and instructor from name
                semester_match = re.search(r'\(((?:SPRING|FALL|SUMMER)/\d{4}-\d{4})\)', name)
                instructor_match = re.search(r'- ([A-Z\'\s]+(?:\s[A-Za-z]+)?)\s*$', name)
                
                course = Course(
                    id=cd["id"],
                    name=name.split("(")[0].strip() if "(" in name else name,
                    url=cd["url"],
                    semester=semester_match.group(1) if semester_match else "",
                    instructor=instructor_match.group(1).strip() if instructor_match else "",
                )
                courses.append(course)

            logger.info(f"Found {len(courses)} total courses")

            # Filter to current semester only
            if current_semester_only and courses:
                # Find the most recent semester
                semester_order = {"SPRING": 1, "SUMMER": 2, "FALL": 3}
                courses_with_semester = [c for c in courses if c.semester]
                if courses_with_semester:
                    def semester_sort_key(c):
                        parts = c.semester.split("/")
                        season = parts[0] if parts else ""
                        year = parts[1].split("-")[0] if len(parts) > 1 else "0"
                        return (int(year), semester_order.get(season, 0))
                    
                    courses_with_semester.sort(key=semester_sort_key, reverse=True)
                    latest_semester = courses_with_semester[0].semester
                    courses = [c for c in courses if c.semester == latest_semester]
                    logger.info(f"Filtered to {len(courses)} courses in {latest_semester}")
                else:
                    # No semester info — return first 5 courses (most recent)
                    courses = courses[:5]

            return courses

        except Exception as e:
            logger.error(f"Failed to get courses: {e}")
            return []

    async def get_assignments(self, course: Course) -> list[Assignment]:
        """
        Get all assignments for a specific course.
        
        Navigates to the course page and extracts assignment links.
        """
        if not await self._ensure_browser():
            return []

        try:
            await self._page.goto(
                course.url,
                wait_until="domcontentloaded",
                timeout=15000,
            )
            await asyncio.sleep(1)

            # Extract assignment links
            assignments_data = await self._page.evaluate("""() => {
                const links = document.querySelectorAll('a[href*="mod/assign/view.php"]');
                const assignments = [];
                links.forEach(l => {
                    const match = l.href.match(/id=(\\d+)/);
                    if (match) {
                        assignments.push({
                            id: parseInt(match[1]),
                            title: l.textContent.trim(),
                            url: l.href,
                        });
                    }
                });
                return assignments;
            }""")

            # Deduplicate by assignment ID (Moodle pages often have duplicate links)
            seen_ids = set()
            assignments = []
            for ad in assignments_data:
                aid = ad["id"]
                if aid in seen_ids:
                    continue
                seen_ids.add(aid)
                assignment = Assignment(
                    id=aid,
                    course_id=course.id,
                    course_name=course.name,
                    title=ad["title"].replace("  Assignment", "").strip(),
                    url=ad["url"],
                )
                assignments.append(assignment)

            logger.info(f"Found {len(assignments)} assignments in {course.name}")
            return assignments

        except Exception as e:
            logger.error(f"Failed to get assignments for {course.name}: {e}")
            return []

    async def get_assignment_details(self, assignment: Assignment) -> Assignment:
        """
        Get detailed info for a specific assignment.
        
        Navigates to the assignment page and extracts:
        - Due date
        - Submission status
        - Grade (if graded)
        - Description/instructions
        """
        if not await self._ensure_browser():
            return assignment

        try:
            await self._page.goto(
                assignment.url,
                wait_until="domcontentloaded",
                timeout=15000,
            )
            await asyncio.sleep(1)

            # Extract assignment details via JavaScript
            details = await self._page.evaluate("""() => {
                const result = {
                    opened: '',
                    due: '',
                    status: 'unknown',
                    grade: '',
                    description: '',
                    is_overdue: false,
                    has_submission_button: false,
                };
                
                // Get dates
                const text = document.body.innerText;
                const openedMatch = text.match(/Opened:\\s*(.+?)\\n/);
                const dueMatch = text.match(/Due:\\s*(.+?)\\n/);
                if (openedMatch) result.opened = openedMatch[1].trim();
                if (dueMatch) result.due = dueMatch[1].trim();
                
                // Get submission status
                const statusCells = document.querySelectorAll('td');
                for (const cell of statusCells) {
                    const cellText = cell.textContent.trim();
                    if (cellText.includes('No submissions have been made yet')) {
                        result.status = 'not_submitted';
                    } else if (cellText.includes('Submitted for grading')) {
                        result.status = 'submitted';
                    }
                    if (cellText.includes('Graded')) {
                        result.status = 'graded';
                    }
                    if (cellText.includes('overdue')) {
                        result.is_overdue = true;
                    }
                }
                
                // Get grade
                const gradeMatch = text.match(/Grade\\s+([\\d.]+\\s*%[^\\n]*)/);
                if (gradeMatch) result.grade = gradeMatch[1].trim();
                
                // Get description (assignment instructions)
                const introDiv = document.querySelector('.activity-description, .no-overflow, [data-region="intro"]');
                if (introDiv) {
                    result.description = introDiv.innerText.trim().substring(0, 2000);
                }
                
                // Also get any text between the title and the submission status
                const mainContent = document.querySelector('#region-main, [role="main"]');
                if (mainContent && !result.description) {
                    const allText = mainContent.innerText;
                    // Extract text before "Submission status"
                    const beforeSubmission = allText.split('Submission status')[0];
                    // Remove the title and dates
                    const lines = beforeSubmission.split('\\n').filter(l => 
                        l.trim() && 
                        !l.includes('Opened:') && 
                        !l.includes('Due:') && 
                        !l.includes('Mark as done') &&
                        !l.includes('Completion requirements')
                    );
                    if (lines.length > 1) {
                        result.description = lines.slice(1).join('\\n').trim().substring(0, 2000);
                    }
                }
                
                // Check for submission button/form (use text matching, not :has-text)
                let hasSubmitBtn = false;
                document.querySelectorAll('button, a, input[type="submit"]').forEach(el => {
                    const t = el.textContent.trim().toLowerCase();
                    if (t.includes('add submission') || t.includes('edit submission')) {
                        hasSubmitBtn = true;
                    }
                });
                if (document.querySelector('[data-action="submit-form"]')) hasSubmitBtn = true;
                result.has_submission_button = hasSubmitBtn;
                
                return result;
            }""")

            assignment.opened = details.get("opened", "")
            assignment.due = details.get("due", "")
            assignment.status = details.get("status", "unknown")
            assignment.grade = details.get("grade", "")
            assignment.description = details.get("description", "")
            assignment.is_overdue = details.get("is_overdue", False)
            
            # Determine if action is needed
            assignment.needs_action = (
                assignment.status == "not_submitted" and 
                assignment.grade == ""  # Not graded without submission (participation)
            )

            return assignment

        except Exception as e:
            logger.error(f"Failed to get details for {assignment.title}: {e}")
            return assignment

    async def submit_file(self, assignment: Assignment, file_path: str) -> dict:
        """
        Submit a file to a Moodle assignment.
        
        Navigates to the assignment, clicks "Add submission", 
        uploads the file, and confirms.
        """
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        try:
            await self._page.goto(
                assignment.url,
                wait_until="domcontentloaded",
                timeout=15000,
            )
            await asyncio.sleep(1)

            # Click "Add submission" button
            try:
                add_btn = self._page.locator(
                    'button:has-text("Add submission"), '
                    'a:has-text("Add submission"), '
                    'button:has-text("Edit submission")'
                )
                await add_btn.first.click(timeout=5000)
                await asyncio.sleep(2)
            except Exception as e:
                return {"success": False, "error": f"No submission button found: {e}"}

            # Look for file upload area
            try:
                # Moodle uses a file picker — look for the file input or drag area
                file_input = self._page.locator('input[type="file"]')
                await file_input.first.set_input_files(file_path, timeout=10000)
                await asyncio.sleep(2)
            except Exception:
                # Try the Moodle file picker button
                try:
                    file_picker = self._page.locator(
                        '.fp-btn-add, '
                        'a:has-text("Add..."), '
                        '.dndupload-arrow, '
                        '[data-fieldtype="filemanager"] .fp-btn-add'
                    )
                    await file_picker.first.click(timeout=5000)
                    await asyncio.sleep(1)
                    
                    # Click "Upload a file" in the file picker dialog
                    upload_option = self._page.locator(
                        '.fp-repo-area a:has-text("Upload a file"), '
                        '.fp-repo:has-text("Upload") a'
                    )
                    await upload_option.first.click(timeout=5000)
                    await asyncio.sleep(1)
                    
                    # Now find the file input in the dialog
                    file_input = self._page.locator('input[type="file"]')
                    await file_input.first.set_input_files(file_path, timeout=10000)
                    await asyncio.sleep(1)
                    
                    # Click "Upload this file"
                    upload_btn = self._page.locator('button:has-text("Upload this file")')
                    await upload_btn.first.click(timeout=5000)
                    await asyncio.sleep(2)
                except Exception as e2:
                    return {"success": False, "error": f"File upload failed: {e2}"}

            # Click "Save changes" to confirm submission
            try:
                save_btn = self._page.locator(
                    'button:has-text("Save changes"), '
                    'input[type="submit"][value="Save changes"]'
                )
                await save_btn.first.click(timeout=5000)
                await asyncio.sleep(2)
            except Exception as e:
                return {"success": False, "error": f"Save changes failed: {e}"}

            # Verify submission
            page_text = await self._page.evaluate("() => document.body.innerText")
            if "Submitted for grading" in page_text or "File submissions" in page_text:
                logger.info(f"Successfully submitted {file_path} to {assignment.title}")
                return {"success": True, "assignment": assignment.title}
            else:
                return {
                    "success": False,
                    "error": "Submission may not have been saved — could not verify",
                    "page_text": page_text[:500],
                }

        except Exception as e:
            logger.error(f"Submission failed for {assignment.title}: {e}")
            return {"success": False, "error": str(e)}

    async def submit_online_text(self, assignment: Assignment, text: str) -> dict:
        """
        Submit online text to a Moodle assignment.
        """
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        try:
            await self._page.goto(
                assignment.url,
                wait_until="domcontentloaded",
                timeout=15000,
            )
            await asyncio.sleep(1)

            # Click "Add submission"
            add_btn = self._page.locator(
                'button:has-text("Add submission"), a:has-text("Add submission")'
            )
            await add_btn.first.click(timeout=5000)
            await asyncio.sleep(2)

            # Find the text editor (Moodle uses TinyMCE or Atto)
            try:
                # Try iframe-based editor (TinyMCE)
                editor_frame = self._page.frame_locator('iframe.tox-edit-area__iframe, iframe[id*="editable"]')
                await editor_frame.locator('body').fill(text, timeout=5000)
            except Exception:
                # Try contenteditable div (Atto)
                try:
                    editor = self._page.locator('[contenteditable="true"], .editor_atto_content')
                    await editor.first.fill(text, timeout=5000)
                except Exception:
                    # Try textarea fallback
                    textarea = self._page.locator('textarea[name*="onlinetext"]')
                    await textarea.first.fill(text, timeout=5000)

            # Save changes
            save_btn = self._page.locator(
                'button:has-text("Save changes"), input[type="submit"][value="Save changes"]'
            )
            await save_btn.first.click(timeout=5000)
            await asyncio.sleep(2)

            return {"success": True, "assignment": assignment.title}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_course_materials(self, course: Course, week: Optional[int] = None) -> list[dict]:
        """
        Get course materials (files, URLs) for context when completing assignments.
        
        If week is specified, only get materials for that week.
        """
        if not await self._ensure_browser():
            return []

        try:
            await self._page.goto(
                course.url,
                wait_until="domcontentloaded",
                timeout=15000,
            )
            await asyncio.sleep(1)

            materials = await self._page.evaluate("""(weekFilter) => {
                const materials = [];
                const sections = document.querySelectorAll('.section, [data-region="section"]');
                
                sections.forEach((section, idx) => {
                    const heading = section.querySelector('h3, .sectionname');
                    const sectionName = heading ? heading.textContent.trim() : `Section ${idx}`;
                    
                    // Check week filter
                    if (weekFilter) {
                        const weekMatch = sectionName.match(/Week\\s*(\\d+)/i);
                        if (weekMatch && parseInt(weekMatch[1]) !== weekFilter) return;
                    }
                    
                    // Get file links
                    const links = section.querySelectorAll('a[href*="mod/resource"], a[href*="mod/url"], a[href*="mod/page"]');
                    links.forEach(l => {
                        materials.push({
                            section: sectionName,
                            title: l.textContent.trim(),
                            url: l.href,
                            type: l.href.includes('resource') ? 'file' : 
                                  l.href.includes('url') ? 'url' : 'page',
                        });
                    });
                });
                
                return materials;
            }""", week)

            return materials

        except Exception as e:
            logger.error(f"Failed to get materials for {course.name}: {e}")
            return []

    async def close(self):
        """Close the browser and save session."""
        await self._save_session()
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
