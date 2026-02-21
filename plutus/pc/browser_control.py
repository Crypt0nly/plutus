"""
Browser Control Layer — Playwright/CDP-based browser automation.

This matches OpenClaw's approach: interact with web pages via DOM element references,
NOT screenshots and pixel coordinates. This is dramatically more reliable.

Uses Playwright to control a real Chrome/Chromium browser with:
- Element-based clicking (by selector/text, not coordinates)
- Form filling by label/placeholder
- Tab management
- Page snapshots (structured DOM, not just screenshots)
- JavaScript evaluation
"""

import asyncio
import json
import os
import base64
from typing import Optional, Any
from pathlib import Path


class BrowserControl:
    """
    Playwright-based browser controller.
    
    Interacts with web pages using DOM element references (selectors, text, roles)
    instead of pixel coordinates. This is the same approach OpenClaw uses.
    """

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._pages: dict[str, Any] = {}  # tab_id -> page
        self._active_tab: Optional[str] = None
        self._initialized = False

    async def _ensure_browser(self) -> bool:
        """Ensure Playwright browser is running. Lazy-initializes on first use."""
        if self._initialized and self._browser and self._browser.is_connected():
            return True

        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()

            # Try to connect to existing Chrome first (user's browser)
            try:
                self._browser = await self._playwright.chromium.connect_over_cdp(
                    "http://localhost:9222"
                )
                self._context = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context()
            except Exception:
                # Launch a new browser instance
                self._browser = await self._playwright.chromium.launch(
                    headless=False,
                    args=[
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--disable-blink-features=AutomationControlled",
                    ],
                )
                self._context = await self._browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )

            # Index existing pages
            for i, page in enumerate(self._context.pages):
                tab_id = f"tab_{i}"
                self._pages[tab_id] = page
                self._active_tab = tab_id

            self._initialized = True
            return True

        except ImportError:
            return False
        except Exception as e:
            return False

    def _get_active_page(self):
        """Get the currently active page/tab."""
        if self._active_tab and self._active_tab in self._pages:
            return self._pages[self._active_tab]
        return None

    # ─── Navigation ───

    async def navigate(self, url: str, tab_id: Optional[str] = None) -> dict:
        """Navigate to a URL in the active or specified tab."""
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available. Install playwright: pip install playwright && playwright install chromium"}

        try:
            page = self._pages.get(tab_id) if tab_id else self._get_active_page()

            if not page:
                page = await self._context.new_page()
                new_id = f"tab_{len(self._pages)}"
                self._pages[new_id] = page
                self._active_tab = new_id

            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            return {
                "success": True,
                "url": page.url,
                "title": await page.title(),
                "tab_id": self._active_tab,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Element Interaction (OpenClaw-style) ───

    async def click(
        self,
        selector: Optional[str] = None,
        text: Optional[str] = None,
        role: Optional[str] = None,
        role_name: Optional[str] = None,
        double_click: bool = False,
        right_click: bool = False,
        timeout: int = 5000,
    ) -> dict:
        """
        Click an element by selector, text content, or ARIA role.
        This is the OpenClaw approach — target elements by their DOM properties,
        not by pixel coordinates.
        """
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            locator = self._build_locator(page, selector, text, role, role_name)

            if double_click:
                await locator.dblclick(timeout=timeout)
            elif right_click:
                await locator.click(button="right", timeout=timeout)
            else:
                await locator.click(timeout=timeout)

            return {
                "success": True,
                "action": "click",
                "target": selector or text or f"role={role}",
                "url": page.url,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "suggestion": "Element not found. Try using get_page_elements() to see available elements.",
            }

    async def type_text(
        self,
        text: str,
        selector: Optional[str] = None,
        label: Optional[str] = None,
        placeholder: Optional[str] = None,
        press_enter: bool = False,
        slowly: bool = False,
        timeout: int = 5000,
    ) -> dict:
        """
        Type text into an input field, found by selector, label, or placeholder.
        """
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            if selector:
                locator = page.locator(selector)
            elif label:
                locator = page.get_by_label(label)
            elif placeholder:
                locator = page.get_by_placeholder(placeholder)
            else:
                # Type into the focused element
                locator = page.locator(":focus")

            await locator.fill("", timeout=timeout)  # Clear first

            if slowly:
                await locator.type(text, delay=50)
            else:
                await locator.fill(text, timeout=timeout)

            if press_enter:
                await locator.press("Enter")

            return {
                "success": True,
                "action": "type",
                "text": text[:50] + "..." if len(text) > 50 else text,
                "target": selector or label or placeholder or "focused element",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def press_key(self, key: str) -> dict:
        """Press a keyboard key (Enter, Tab, Escape, ArrowDown, etc.)."""
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            await page.keyboard.press(key)
            return {"success": True, "action": "press", "key": key}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def fill_form(self, fields: list[dict]) -> dict:
        """
        Fill multiple form fields at once.
        Each field: {selector?, label?, placeholder?, value}
        """
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        results = []
        for field in fields:
            try:
                value = field.get("value", "")
                if field.get("selector"):
                    locator = page.locator(field["selector"])
                elif field.get("label"):
                    locator = page.get_by_label(field["label"])
                elif field.get("placeholder"):
                    locator = page.get_by_placeholder(field["placeholder"])
                else:
                    results.append({"field": field, "success": False, "error": "No selector"})
                    continue

                await locator.fill(str(value), timeout=5000)
                results.append({"field": field.get("label") or field.get("selector") or field.get("placeholder"), "success": True})
            except Exception as e:
                results.append({"field": str(field), "success": False, "error": str(e)})

        return {
            "success": all(r["success"] for r in results),
            "action": "fill_form",
            "results": results,
        }

    async def select_option(
        self,
        value: str,
        selector: Optional[str] = None,
        label: Optional[str] = None,
    ) -> dict:
        """Select an option from a dropdown."""
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            if selector:
                locator = page.locator(selector)
            elif label:
                locator = page.get_by_label(label)
            else:
                return {"success": False, "error": "Provide selector or label"}

            await locator.select_option(value, timeout=5000)
            return {"success": True, "action": "select", "value": value}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def hover(self, selector: Optional[str] = None, text: Optional[str] = None) -> dict:
        """Hover over an element."""
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            locator = self._build_locator(page, selector, text)
            await locator.hover(timeout=5000)
            return {"success": True, "action": "hover", "target": selector or text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def scroll(self, direction: str = "down", amount: int = 500) -> dict:
        """Scroll the page."""
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            delta = amount if direction == "down" else -amount
            await page.mouse.wheel(0, delta)
            return {"success": True, "action": "scroll", "direction": direction, "amount": amount}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Page State (OpenClaw's "snapshot" approach) ───

    async def get_page_snapshot(self) -> dict:
        """
        Get a structured snapshot of the current page — text content, links, forms, buttons.
        This is OpenClaw's approach: understand the page via DOM, not screenshots.
        """
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            snapshot = await page.evaluate("""() => {
                const result = {
                    title: document.title,
                    url: window.location.href,
                    text: '',
                    links: [],
                    buttons: [],
                    inputs: [],
                    headings: [],
                };

                // Get visible text (truncated)
                result.text = document.body?.innerText?.substring(0, 3000) || '';

                // Get clickable links
                document.querySelectorAll('a[href]').forEach((a, i) => {
                    if (i < 30 && a.innerText.trim()) {
                        result.links.push({
                            text: a.innerText.trim().substring(0, 80),
                            href: a.href,
                            selector: `a:has-text("${a.innerText.trim().substring(0, 40)}")`,
                        });
                    }
                });

                // Get buttons
                document.querySelectorAll('button, [role="button"], input[type="submit"], input[type="button"]').forEach((btn, i) => {
                    if (i < 20) {
                        const text = btn.innerText?.trim() || btn.value || btn.getAttribute('aria-label') || '';
                        if (text) {
                            result.buttons.push({
                                text: text.substring(0, 80),
                                selector: btn.id ? `#${btn.id}` : `button:has-text("${text.substring(0, 40)}")`,
                            });
                        }
                    }
                });

                // Get input fields
                document.querySelectorAll('input, textarea, select').forEach((input, i) => {
                    if (i < 20) {
                        const label = input.getAttribute('aria-label') || input.placeholder || input.name || input.id || '';
                        result.inputs.push({
                            type: input.type || input.tagName.toLowerCase(),
                            label: label,
                            value: input.value?.substring(0, 50) || '',
                            selector: input.id ? `#${input.id}` : `[name="${input.name}"]`,
                            placeholder: input.placeholder || '',
                        });
                    }
                });

                // Get headings
                document.querySelectorAll('h1, h2, h3').forEach((h, i) => {
                    if (i < 10 && h.innerText.trim()) {
                        result.headings.push(h.innerText.trim().substring(0, 100));
                    }
                });

                return result;
            }""")

            return {
                "success": True,
                "snapshot": snapshot,
                "tab_id": self._active_tab,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_page_elements(self, filter_type: Optional[str] = None) -> dict:
        """
        Get interactive elements on the page. 
        filter_type: 'links', 'buttons', 'inputs', 'all'
        """
        snapshot = await self.get_page_snapshot()
        if not snapshot.get("success"):
            return snapshot

        s = snapshot["snapshot"]
        result = {"success": True, "url": s.get("url"), "title": s.get("title")}

        if filter_type == "links" or filter_type == "all" or not filter_type:
            result["links"] = s.get("links", [])
        if filter_type == "buttons" or filter_type == "all" or not filter_type:
            result["buttons"] = s.get("buttons", [])
        if filter_type == "inputs" or filter_type == "all" or not filter_type:
            result["inputs"] = s.get("inputs", [])

        return result

    async def screenshot(self, full_page: bool = False) -> dict:
        """Take a screenshot of the current page. Returns base64-encoded image."""
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            screenshot_bytes = await page.screenshot(full_page=full_page, type="png")
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode()

            # Also save to file
            screenshot_dir = Path.home() / ".plutus" / "screenshots"
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            import time
            path = screenshot_dir / f"screenshot_{int(time.time())}.png"
            path.write_bytes(screenshot_bytes)

            return {
                "success": True,
                "screenshot_base64": screenshot_b64[:100] + "...",  # Truncated for display
                "saved_to": str(path),
                "url": page.url,
                "title": await page.title(),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Tab Management ───

    async def new_tab(self, url: Optional[str] = None) -> dict:
        """Open a new browser tab."""
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        try:
            page = await self._context.new_page()
            tab_id = f"tab_{len(self._pages)}"
            self._pages[tab_id] = page
            self._active_tab = tab_id

            if url:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            return {
                "success": True,
                "tab_id": tab_id,
                "url": page.url,
                "title": await page.title() if url else "New Tab",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def close_tab(self, tab_id: Optional[str] = None) -> dict:
        """Close a browser tab."""
        target = tab_id or self._active_tab
        if target and target in self._pages:
            try:
                await self._pages[target].close()
                del self._pages[target]
                # Switch to another tab
                if self._pages:
                    self._active_tab = list(self._pages.keys())[-1]
                else:
                    self._active_tab = None
                return {"success": True, "closed": target}
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": False, "error": f"Tab {target} not found"}

    async def switch_tab(self, tab_id: str) -> dict:
        """Switch to a different tab."""
        if tab_id in self._pages:
            self._active_tab = tab_id
            page = self._pages[tab_id]
            try:
                await page.bring_to_front()
                return {
                    "success": True,
                    "tab_id": tab_id,
                    "url": page.url,
                    "title": await page.title(),
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": False, "error": f"Tab {tab_id} not found"}

    async def list_tabs(self) -> dict:
        """List all open browser tabs."""
        tabs = []
        for tab_id, page in self._pages.items():
            try:
                tabs.append({
                    "tab_id": tab_id,
                    "url": page.url,
                    "title": await page.title(),
                    "active": tab_id == self._active_tab,
                })
            except Exception:
                tabs.append({"tab_id": tab_id, "url": "unknown", "active": tab_id == self._active_tab})

        return {"success": True, "tabs": tabs, "count": len(tabs)}

    # ─── JavaScript Evaluation ───

    async def evaluate(self, js_code: str) -> dict:
        """Evaluate JavaScript on the current page."""
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            result = await page.evaluate(js_code)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Wait Operations ───

    async def wait_for_text(self, text: str, timeout: int = 10000) -> dict:
        """Wait for specific text to appear on the page."""
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            await page.get_by_text(text).wait_for(timeout=timeout)
            return {"success": True, "text": text, "found": True}
        except Exception as e:
            return {"success": False, "text": text, "found": False, "error": str(e)}

    async def wait_for_navigation(self, timeout: int = 30000) -> dict:
        """Wait for the page to finish navigating."""
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            await page.wait_for_load_state("domcontentloaded", timeout=timeout)
            return {"success": True, "url": page.url, "title": await page.title()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Helpers ───

    def _build_locator(self, page, selector=None, text=None, role=None, role_name=None):
        """Build a Playwright locator from various targeting options."""
        if selector:
            return page.locator(selector)
        elif text:
            return page.get_by_text(text, exact=False)
        elif role and role_name:
            return page.get_by_role(role, name=role_name)
        elif role:
            return page.get_by_role(role)
        else:
            raise ValueError("Provide selector, text, or role to target an element")

    async def close(self):
        """Close the browser and cleanup."""
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            self._initialized = False
        except Exception:
            pass
