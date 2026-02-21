"""
Browser Control Layer — OpenClaw-style Playwright/CDP browser automation.

KEY DESIGN: Uses ACCESSIBILITY TREE SNAPSHOTS instead of screenshots.
The LLM sees a text-based representation of the page with numbered refs:

    [1] button "Sign In"
    [2] textbox "Email" value=""
    [3] textbox "Password" value=""
    [4] link "Forgot password?"
    [5] heading "Welcome back"

The LLM then says "click ref 1" or "type ref 2 hello@email.com" — precise,
deterministic, and uses 100x fewer tokens than screenshots.

This is exactly how OpenClaw navigates the web.
"""

import asyncio
import json
import logging
import re
from typing import Optional, Any
from pathlib import Path

logger = logging.getLogger("plutus.pc.browser")


class BrowserControl:
    """
    Playwright-based browser controller using accessibility tree snapshots.
    
    The core loop:
    1. snapshot() → returns numbered accessibility tree
    2. LLM reads the tree, decides what to do
    3. click_ref(3) / type_ref(2, "hello") / etc.
    4. snapshot() again to verify
    """

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._pages: dict[str, Any] = {}
        self._active_tab: Optional[str] = None
        self._initialized = False
        # Ref map: ref_number -> element locator info
        self._ref_map: dict[int, dict] = {}
        self._ref_counter = 0

    async def _ensure_browser(self) -> bool:
        """Ensure Playwright browser is running. Lazy-initializes on first use."""
        if self._initialized and self._browser and self._browser.is_connected():
            return True

        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()

            # Try to connect to existing Chrome first (user's browser via CDP)
            cdp_connected = False
            try:
                self._browser = await self._playwright.chromium.connect_over_cdp(
                    "http://localhost:9222"
                )
                if self._browser.contexts:
                    self._context = self._browser.contexts[0]
                else:
                    self._context = await self._browser.new_context()
                cdp_connected = True
                logger.info("Connected to existing Chrome via CDP")
            except Exception:
                pass

            if not cdp_connected:
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
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                )
                logger.info("Launched new Chromium browser")

            # Index existing pages
            for i, page in enumerate(self._context.pages):
                tab_id = f"tab_{i}"
                self._pages[tab_id] = page
                self._active_tab = tab_id

            self._initialized = True
            return True

        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return False
        except Exception as e:
            logger.error(f"Browser init failed: {e}")
            return False

    def _get_active_page(self):
        """Get the currently active page/tab."""
        if self._active_tab and self._active_tab in self._pages:
            return self._pages[self._active_tab]
        return None

    # ═══════════════════════════════════════════════════════════════
    # CORE: Accessibility Tree Snapshot (OpenClaw's key innovation)
    # ═══════════════════════════════════════════════════════════════

    async def snapshot(self) -> dict:
        """
        Take an accessibility tree snapshot of the current page.
        
        Returns a numbered, text-based representation of all interactive elements.
        This is the PRIMARY way the LLM "sees" the page — not screenshots.
        
        Example output:
            Page: Google - https://www.google.com
            
            [1] textbox "Search" value="" focused
            [2] button "Google Search"
            [3] button "I'm Feeling Lucky"
            [4] link "Gmail"
            [5] link "Images"
            [6] link "About"
            [7] link "Store"
        """
        if not await self._ensure_browser():
            return {
                "success": False,
                "error": "Browser not available. Install: pip install playwright && playwright install chromium",
            }

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab. Use navigate to open a page."}

        try:
            # Get page info
            title = await page.title()
            url = page.url

            # Build the accessibility tree snapshot using JavaScript
            # This extracts ALL interactive elements with their roles, names, and values
            elements = await page.evaluate("""() => {
                const results = [];
                const seen = new Set();
                
                // Helper: get accessible name for an element
                function getAccessibleName(el) {
                    return (
                        el.getAttribute('aria-label') ||
                        el.getAttribute('aria-labelledby') && document.getElementById(el.getAttribute('aria-labelledby'))?.textContent ||
                        el.getAttribute('title') ||
                        el.getAttribute('alt') ||
                        el.getAttribute('placeholder') ||
                        el.labels?.[0]?.textContent?.trim() ||
                        el.textContent?.trim()?.substring(0, 80) ||
                        ''
                    );
                }
                
                // Helper: get element value
                function getValue(el) {
                    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
                        return el.value || '';
                    }
                    if (el.tagName === 'SELECT') {
                        return el.options[el.selectedIndex]?.text || '';
                    }
                    return '';
                }
                
                // Helper: get role
                function getRole(el) {
                    const explicit = el.getAttribute('role');
                    if (explicit) return explicit;
                    
                    const tag = el.tagName.toLowerCase();
                    const type = (el.getAttribute('type') || '').toLowerCase();
                    
                    const roleMap = {
                        'a': 'link',
                        'button': 'button',
                        'input': type === 'submit' ? 'button' :
                                 type === 'checkbox' ? 'checkbox' :
                                 type === 'radio' ? 'radio' :
                                 type === 'search' ? 'searchbox' :
                                 'textbox',
                        'textarea': 'textbox',
                        'select': 'combobox',
                        'img': 'img',
                        'h1': 'heading',
                        'h2': 'heading',
                        'h3': 'heading',
                        'h4': 'heading',
                        'nav': 'navigation',
                        'main': 'main',
                        'form': 'form',
                        'table': 'table',
                        'li': 'listitem',
                        'ul': 'list',
                        'ol': 'list',
                    };
                    
                    return roleMap[tag] || '';
                }
                
                // Helper: is element visible and interactive?
                function isVisible(el) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 && rect.height === 0) return false;
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden') return false;
                    if (parseFloat(style.opacity) === 0) return false;
                    return true;
                }
                
                // Collect interactive elements
                const selectors = [
                    'a[href]',
                    'button',
                    'input:not([type="hidden"])',
                    'textarea',
                    'select',
                    '[role="button"]',
                    '[role="link"]',
                    '[role="textbox"]',
                    '[role="checkbox"]',
                    '[role="radio"]',
                    '[role="tab"]',
                    '[role="menuitem"]',
                    '[role="option"]',
                    '[role="switch"]',
                    '[role="combobox"]',
                    '[role="searchbox"]',
                    '[contenteditable="true"]',
                    '[tabindex]:not([tabindex="-1"])',
                    '[onclick]',
                ];
                
                const allElements = document.querySelectorAll(selectors.join(','));
                
                allElements.forEach(el => {
                    if (!isVisible(el)) return;
                    
                    // Deduplicate by position
                    const rect = el.getBoundingClientRect();
                    const key = `${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)}`;
                    if (seen.has(key)) return;
                    seen.add(key);
                    
                    const role = getRole(el);
                    const name = getAccessibleName(el);
                    const value = getValue(el);
                    
                    // Skip empty/useless elements
                    if (!role && !name) return;
                    
                    // Build a unique CSS selector for this element
                    let cssSelector = '';
                    if (el.id) {
                        cssSelector = '#' + CSS.escape(el.id);
                    } else if (el.getAttribute('data-testid')) {
                        cssSelector = `[data-testid="${el.getAttribute('data-testid')}"]`;
                    } else if (el.getAttribute('name')) {
                        cssSelector = `${el.tagName.toLowerCase()}[name="${el.getAttribute('name')}"]`;
                    } else if (el.getAttribute('aria-label')) {
                        cssSelector = `[aria-label="${el.getAttribute('aria-label')}"]`;
                    } else {
                        // Fallback: use tag + nth-of-type
                        const parent = el.parentElement;
                        if (parent) {
                            const siblings = Array.from(parent.children).filter(c => c.tagName === el.tagName);
                            const idx = siblings.indexOf(el) + 1;
                            cssSelector = `${el.tagName.toLowerCase()}:nth-of-type(${idx})`;
                            // Walk up to make it more specific
                            if (parent.id) {
                                cssSelector = '#' + CSS.escape(parent.id) + ' > ' + cssSelector;
                            } else if (parent.className && typeof parent.className === 'string') {
                                const cls = parent.className.trim().split(/\\s+/)[0];
                                if (cls) cssSelector = '.' + CSS.escape(cls) + ' > ' + cssSelector;
                            }
                        }
                    }
                    
                    results.push({
                        role: role,
                        name: name.substring(0, 100),
                        value: value.substring(0, 100),
                        selector: cssSelector,
                        tag: el.tagName.toLowerCase(),
                        type: el.getAttribute('type') || '',
                        href: el.getAttribute('href') || '',
                        checked: el.checked || false,
                        disabled: el.disabled || false,
                        focused: document.activeElement === el,
                        rect: {
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height),
                        },
                    });
                });
                
                // Also get headings for page structure context
                const headings = [];
                document.querySelectorAll('h1, h2, h3').forEach((h, i) => {
                    if (i < 15 && h.textContent?.trim()) {
                        headings.push({
                            level: parseInt(h.tagName[1]),
                            text: h.textContent.trim().substring(0, 120),
                        });
                    }
                });
                
                // Get visible text summary (first 2000 chars)
                const textContent = document.body?.innerText?.substring(0, 2000) || '';
                
                return { elements, headings, textContent };
            }""")

            # Build the ref map and formatted snapshot
            self._ref_map = {}
            self._ref_counter = 0
            
            lines = []
            lines.append(f"Page: {title} — {url}")
            lines.append("")
            
            # Add headings for context
            if elements.get("headings"):
                for h in elements["headings"]:
                    prefix = "#" * h["level"]
                    lines.append(f"  {prefix} {h['text']}")
                lines.append("")

            # Add interactive elements with ref numbers
            for elem in elements.get("elements", []):
                self._ref_counter += 1
                ref = self._ref_counter
                
                # Store in ref map for later interaction
                self._ref_map[ref] = {
                    "selector": elem["selector"],
                    "role": elem["role"],
                    "name": elem["name"],
                    "tag": elem["tag"],
                    "rect": elem["rect"],
                }
                
                # Format the line
                role = elem["role"] or elem["tag"]
                name = elem["name"]
                value = elem.get("value", "")
                
                parts = [f"[{ref}]", role]
                if name:
                    parts.append(f'"{name}"')
                if value:
                    parts.append(f'value="{value}"')
                if elem.get("checked"):
                    parts.append("checked")
                if elem.get("disabled"):
                    parts.append("disabled")
                if elem.get("focused"):
                    parts.append("focused")
                if elem.get("href") and elem["role"] == "link":
                    href = elem["href"]
                    if len(href) > 60:
                        href = href[:57] + "..."
                    parts.append(f"→ {href}")
                
                lines.append("  " + " ".join(parts))

            snapshot_text = "\n".join(lines)
            
            # Also get a short text summary for context
            text_preview = elements.get("textContent", "")[:500]

            return {
                "success": True,
                "snapshot": snapshot_text,
                "url": url,
                "title": title,
                "element_count": len(elements.get("elements", [])),
                "tab_id": self._active_tab,
                "text_preview": text_preview,
                "hint": "Use ref numbers to interact: click_ref(1), type_ref(2, 'text'), etc.",
            }

        except Exception as e:
            logger.error(f"Snapshot failed: {e}")
            return {"success": False, "error": str(e)}

    # ═══════════════════════════════════════════════════════════════
    # REF-BASED INTERACTION (the LLM uses ref numbers from snapshot)
    # ═══════════════════════════════════════════════════════════════

    async def click_ref(self, ref: int, double_click: bool = False, right_click: bool = False) -> dict:
        """Click an element by its ref number from the last snapshot."""
        if ref not in self._ref_map:
            return {
                "success": False,
                "error": f"Ref [{ref}] not found. Take a new snapshot first.",
                "available_refs": list(self._ref_map.keys())[:20],
            }

        elem = self._ref_map[ref]
        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            locator = page.locator(elem["selector"]).first

            if double_click:
                await locator.dblclick(timeout=5000)
            elif right_click:
                await locator.click(button="right", timeout=5000)
            else:
                await locator.click(timeout=5000)

            return {
                "success": True,
                "action": "click",
                "ref": ref,
                "element": f'{elem["role"]} "{elem["name"]}"',
                "hint": "Take a snapshot to see the updated page state.",
            }
        except Exception as e:
            # Fallback: try clicking by coordinates from the rect
            try:
                rect = elem.get("rect", {})
                x = rect.get("x", 0) + rect.get("width", 0) // 2
                y = rect.get("y", 0) + rect.get("height", 0) // 2
                await page.mouse.click(x, y)
                return {
                    "success": True,
                    "action": "click (coordinate fallback)",
                    "ref": ref,
                    "element": f'{elem["role"]} "{elem["name"]}"',
                    "coordinates": {"x": x, "y": y},
                }
            except Exception as e2:
                return {
                    "success": False,
                    "error": f"Click failed: {e}. Coordinate fallback also failed: {e2}",
                    "ref": ref,
                    "suggestion": "Take a new snapshot — the page may have changed.",
                }

    async def type_ref(self, ref: int, text: str, press_enter: bool = False, clear_first: bool = True) -> dict:
        """Type text into an element by its ref number from the last snapshot."""
        if ref not in self._ref_map:
            return {
                "success": False,
                "error": f"Ref [{ref}] not found. Take a new snapshot first.",
            }

        elem = self._ref_map[ref]
        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            locator = page.locator(elem["selector"]).first

            if clear_first:
                await locator.fill("", timeout=3000)
            
            await locator.fill(text, timeout=5000)

            if press_enter:
                await locator.press("Enter")

            return {
                "success": True,
                "action": "type",
                "ref": ref,
                "element": f'{elem["role"]} "{elem["name"]}"',
                "text": text[:50] + "..." if len(text) > 50 else text,
                "pressed_enter": press_enter,
            }
        except Exception as e:
            # Fallback: click the element first, then type via keyboard
            try:
                rect = elem.get("rect", {})
                x = rect.get("x", 0) + rect.get("width", 0) // 2
                y = rect.get("y", 0) + rect.get("height", 0) // 2
                await page.mouse.click(x, y)
                await asyncio.sleep(0.2)
                if clear_first:
                    await page.keyboard.press("Control+a")
                    await page.keyboard.press("Backspace")
                await page.keyboard.type(text, delay=30)
                if press_enter:
                    await page.keyboard.press("Enter")
                return {
                    "success": True,
                    "action": "type (keyboard fallback)",
                    "ref": ref,
                    "text": text[:50] + "..." if len(text) > 50 else text,
                }
            except Exception as e2:
                return {
                    "success": False,
                    "error": f"Type failed: {e}. Keyboard fallback also failed: {e2}",
                    "ref": ref,
                }

    async def select_ref(self, ref: int, value: str) -> dict:
        """Select an option from a dropdown by ref number."""
        if ref not in self._ref_map:
            return {"success": False, "error": f"Ref [{ref}] not found."}

        elem = self._ref_map[ref]
        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            locator = page.locator(elem["selector"]).first
            await locator.select_option(value, timeout=5000)
            return {"success": True, "action": "select", "ref": ref, "value": value}
        except Exception as e:
            return {"success": False, "error": str(e), "ref": ref}

    async def check_ref(self, ref: int, checked: bool = True) -> dict:
        """Check or uncheck a checkbox by ref number."""
        if ref not in self._ref_map:
            return {"success": False, "error": f"Ref [{ref}] not found."}

        elem = self._ref_map[ref]
        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            locator = page.locator(elem["selector"]).first
            if checked:
                await locator.check(timeout=5000)
            else:
                await locator.uncheck(timeout=5000)
            return {"success": True, "action": "check", "ref": ref, "checked": checked}
        except Exception as e:
            return {"success": False, "error": str(e), "ref": ref}

    # ═══════════════════════════════════════════════════════════════
    # LEGACY INTERACTION (selector/text-based — still useful)
    # ═══════════════════════════════════════════════════════════════

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
        """Click an element by selector, text, or role. Prefer click_ref when possible."""
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
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "suggestion": "Use snapshot() to see available elements, then use click_ref().",
            }

    async def type_text(
        self,
        text: str,
        selector: Optional[str] = None,
        label: Optional[str] = None,
        placeholder: Optional[str] = None,
        press_enter: bool = False,
        timeout: int = 5000,
    ) -> dict:
        """Type text into a field by selector/label/placeholder. Prefer type_ref when possible."""
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
                locator = page.locator(":focus")

            await locator.fill("", timeout=timeout)
            await locator.fill(text, timeout=timeout)

            if press_enter:
                await locator.press("Enter")

            return {
                "success": True,
                "action": "type",
                "text": text[:50] + "..." if len(text) > 50 else text,
                "target": selector or label or placeholder or "focused",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def press_key(self, key: str) -> dict:
        """Press a keyboard key in the browser."""
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
        """Fill multiple form fields at once."""
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        results = []
        for field in fields:
            try:
                value = field.get("value", "")
                if field.get("ref"):
                    r = await self.type_ref(int(field["ref"]), value)
                    results.append({"ref": field["ref"], "success": r.get("success", False)})
                elif field.get("selector"):
                    await page.locator(field["selector"]).fill(str(value), timeout=5000)
                    results.append({"selector": field["selector"], "success": True})
                elif field.get("label"):
                    await page.get_by_label(field["label"]).fill(str(value), timeout=5000)
                    results.append({"label": field["label"], "success": True})
                elif field.get("placeholder"):
                    await page.get_by_placeholder(field["placeholder"]).fill(str(value), timeout=5000)
                    results.append({"placeholder": field["placeholder"], "success": True})
                else:
                    results.append({"field": str(field), "success": False, "error": "No ref/selector/label"})
            except Exception as e:
                results.append({"field": str(field), "success": False, "error": str(e)})

        return {
            "success": all(r.get("success") for r in results),
            "action": "fill_form",
            "results": results,
        }

    # ═══════════════════════════════════════════════════════════════
    # NAVIGATION
    # ═══════════════════════════════════════════════════════════════

    async def navigate(self, url: str, tab_id: Optional[str] = None) -> dict:
        """Navigate to a URL. Auto-takes a snapshot after loading."""
        if not await self._ensure_browser():
            return {
                "success": False,
                "error": "Browser not available. Install: pip install playwright && playwright install chromium",
            }

        try:
            page = self._pages.get(tab_id) if tab_id else self._get_active_page()

            if not page:
                page = await self._context.new_page()
                new_id = f"tab_{len(self._pages)}"
                self._pages[new_id] = page
                self._active_tab = new_id

            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            # Auto-snapshot after navigation
            snapshot_result = await self.snapshot()

            return {
                "success": True,
                "url": page.url,
                "title": await page.title(),
                "tab_id": self._active_tab,
                "snapshot": snapshot_result.get("snapshot", ""),
                "element_count": snapshot_result.get("element_count", 0),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def scroll(self, direction: str = "down", amount: int = 500) -> dict:
        """Scroll the page, then auto-snapshot."""
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            delta = amount if direction == "down" else -amount
            await page.mouse.wheel(0, delta)
            await asyncio.sleep(0.5)  # Wait for scroll to settle
            
            # Auto-snapshot after scroll
            snapshot_result = await self.snapshot()

            return {
                "success": True,
                "action": "scroll",
                "direction": direction,
                "snapshot": snapshot_result.get("snapshot", ""),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def hover(self, selector: Optional[str] = None, text: Optional[str] = None, ref: Optional[int] = None) -> dict:
        """Hover over an element."""
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            if ref and ref in self._ref_map:
                elem = self._ref_map[ref]
                locator = page.locator(elem["selector"]).first
            else:
                locator = self._build_locator(page, selector, text)
            
            await locator.hover(timeout=5000)
            return {"success": True, "action": "hover", "target": ref or selector or text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ═══════════════════════════════════════════════════════════════
    # TAB MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    async def new_tab(self, url: Optional[str] = None) -> dict:
        """Open a new browser tab, optionally navigating to a URL."""
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        try:
            page = await self._context.new_page()
            tab_id = f"tab_{len(self._pages)}"
            self._pages[tab_id] = page
            self._active_tab = tab_id

            result = {
                "success": True,
                "tab_id": tab_id,
            }

            if url:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                result["url"] = page.url
                result["title"] = await page.title()
                # Auto-snapshot
                snap = await self.snapshot()
                result["snapshot"] = snap.get("snapshot", "")
            else:
                result["url"] = "about:blank"
                result["title"] = "New Tab"

            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def close_tab(self, tab_id: Optional[str] = None) -> dict:
        """Close a browser tab."""
        target = tab_id or self._active_tab
        if target and target in self._pages:
            try:
                await self._pages[target].close()
                del self._pages[target]
                if self._pages:
                    self._active_tab = list(self._pages.keys())[-1]
                else:
                    self._active_tab = None
                return {"success": True, "closed": target}
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": False, "error": f"Tab {target} not found"}

    async def switch_tab(self, tab_id: str) -> dict:
        """Switch to a different tab and auto-snapshot."""
        if tab_id in self._pages:
            self._active_tab = tab_id
            page = self._pages[tab_id]
            try:
                await page.bring_to_front()
                snap = await self.snapshot()
                return {
                    "success": True,
                    "tab_id": tab_id,
                    "url": page.url,
                    "title": await page.title(),
                    "snapshot": snap.get("snapshot", ""),
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

    # ═══════════════════════════════════════════════════════════════
    # JAVASCRIPT & WAIT
    # ═══════════════════════════════════════════════════════════════

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
        """Wait for page navigation to complete."""
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

    async def screenshot(self, full_page: bool = False) -> dict:
        """Take a screenshot (use snapshot() instead for LLM interaction)."""
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            import time
            import base64
            screenshot_bytes = await page.screenshot(full_page=full_page, type="png")
            screenshot_dir = Path.home() / ".plutus" / "screenshots"
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            path = screenshot_dir / f"screenshot_{int(time.time())}.png"
            path.write_bytes(screenshot_bytes)

            return {
                "success": True,
                "saved_to": str(path),
                "url": page.url,
                "title": await page.title(),
                "note": "For LLM interaction, use snapshot() instead — it's text-based and much more efficient.",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ═══════════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════════

    def _build_locator(self, page, selector=None, text=None, role=None, role_name=None):
        """Build a Playwright locator from various targeting options."""
        if selector:
            return page.locator(selector).first
        elif text:
            return page.get_by_text(text, exact=False).first
        elif role and role_name:
            return page.get_by_role(role, name=role_name).first
        elif role:
            return page.get_by_role(role).first
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
