"""
Browser Control Layer — OpenClaw-style Playwright/CDP browser automation.

KEY DESIGN: Uses Playwright's NATIVE ACCESSIBILITY TREE instead of screenshots.
The LLM sees a text-based representation of the page with numbered refs:

    [1] button "Sign In"
    [2] textbox "Email" value="" focused
    [3] textbox "Password" value=""
    [4] link "Forgot password?"
    [5] heading "Welcome back"

The LLM then says "click ref 1" or "type ref 2 hello@email.com" — precise,
deterministic, and uses 100x fewer tokens than screenshots.

This uses the same approach as OpenClaw: Playwright's page.accessibility.snapshot()
which returns the browser's own accessibility tree via the Chrome DevTools Protocol.
"""

import asyncio
import json
import logging
import re
from typing import Optional, Any
from pathlib import Path

logger = logging.getLogger("plutus.pc.browser")

# Roles considered interactive — these get ref numbers
INTERACTIVE_ROLES = frozenset({
    "link", "button", "textbox", "checkbox", "radio",
    "combobox", "searchbox", "tab", "menuitem", "option",
    "switch", "slider", "spinbutton", "treeitem",
    "gridcell", "row", "columnheader", "rowheader",
})

# Roles shown for structural context (no ref number)
STRUCTURAL_ROLES = frozenset({
    "heading", "navigation", "main", "banner", "contentinfo",
    "complementary", "form", "search", "region", "alert",
    "dialog", "alertdialog", "status", "log", "marquee",
    "timer", "toolbar", "menu", "menubar", "tablist",
    "tabpanel", "tree", "treegrid", "grid", "table",
    "list", "listitem", "group",
})


class BrowserControl:
    """
    Playwright-based browser controller using native accessibility tree snapshots.
    
    The core loop (identical to OpenClaw):
    1. snapshot() → returns numbered accessibility tree from Playwright's native API
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
        # Ref map: ref_number -> accessibility node info + locator strategy
        self._ref_map: dict[int, dict] = {}
        self._ref_counter = 0

    async def _ensure_browser(self) -> bool:
        """Ensure Playwright browser is running. Lazy-initializes on first use.

        Respects the BrowserConfig from ~/.plutus/config.json:
          - mode="auto"     → try CDP on configured port first, fall back to headless Chromium
          - mode="user"     → launch the user's chosen browser with CDP, then connect
          - mode="headless" → always launch headless Chromium (no CDP attempt)
        """
        if self._initialized and self._browser and self._browser.is_connected():
            return True

        try:
            from playwright.async_api import async_playwright
            from plutus.config import PlutusConfig
            from plutus.pc.browser_detect import get_browser_launch_args, get_user_data_dir
            import subprocess as _sp
            import asyncio as _asyncio

            cfg = PlutusConfig.load()
            browser_cfg = cfg.browser
            mode = browser_cfg.mode          # "auto" | "user" | "headless"
            exe = browser_cfg.executable_path
            cdp_port = browser_cfg.cdp_port or 9222
            use_profile = browser_cfg.use_profile

            self._playwright = await async_playwright().start()
            cdp_connected = False

            # ── Mode: user ────────────────────────────────────────────
            # Launch the user's chosen browser with --remote-debugging-port,
            # then connect to it via CDP so we inherit their logins/cookies.
            if mode == "user" and exe:
                try:
                    args = get_browser_launch_args(exe, debug_port=cdp_port)
                    if use_profile:
                        udd = get_user_data_dir(exe)
                        if udd:
                            args.append(f"--user-data-dir={udd}")
                    _sp.Popen(args, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
                    # Wait for the debug server to start
                    await _asyncio.sleep(2.0)
                    self._browser = await self._playwright.chromium.connect_over_cdp(
                        f"http://localhost:{cdp_port}"
                    )
                    if self._browser.contexts:
                        self._context = self._browser.contexts[0]
                    else:
                        self._context = await self._browser.new_context()
                    cdp_connected = True
                    logger.info(f"Connected to user's browser via CDP (port {cdp_port})")
                except Exception as e:
                    logger.warning(f"User browser CDP connect failed: {e} — falling back to Chromium")

            # ── Mode: auto ────────────────────────────────────────────
            # Try to connect to an already-running browser on the CDP port first.
            elif mode == "auto":
                try:
                    self._browser = await self._playwright.chromium.connect_over_cdp(
                        f"http://localhost:{cdp_port}"
                    )
                    if self._browser.contexts:
                        self._context = self._browser.contexts[0]
                    else:
                        self._context = await self._browser.new_context()
                    cdp_connected = True
                    logger.info(f"Connected to existing browser via CDP (port {cdp_port})")
                except Exception:
                    pass  # fall through to Chromium launch below

            # ── Fallback / headless ───────────────────────────────────
            if not cdp_connected:
                headless = (mode == "headless")
                self._browser = await self._playwright.chromium.launch(
                    headless=headless,
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
                logger.info(f"Launched {'headless' if headless else 'visible'} Chromium browser")

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
    # CORE: Native Accessibility Tree Snapshot (OpenClaw approach)
    # ═══════════════════════════════════════════════════════════════

    def _walk_ax_tree(self, node: dict, indent: int = 0) -> list[str]:
        """
        Recursively walk the Playwright accessibility tree and build a
        numbered, text-based representation. Interactive elements get
        ref numbers; structural elements are shown for context.
        
        This mirrors OpenClaw's buildRoleSnapshotFromAriaSnapshot().
        """
        lines = []
        role = node.get("role", "")
        name = node.get("name", "")
        value = node.get("value", "")
        focused = node.get("focused", False)
        checked = node.get("checked")
        disabled = node.get("disabled", False)
        expanded = node.get("expanded")
        level = node.get("level")
        description = node.get("description", "")

        is_interactive = role in INTERACTIVE_ROLES
        is_structural = role in STRUCTURAL_ROLES

        if is_interactive:
            self._ref_counter += 1
            ref = self._ref_counter

            # Store in ref map for later interaction
            # We store the role + name so we can build a Playwright locator
            self._ref_map[ref] = {
                "role": role,
                "name": name,
                "value": value,
                "path": self._current_path[:],  # Copy of path for locator resolution
            }

            # Format the line
            parts = [f"[{ref}]", role]
            if name:
                parts.append(f'"{name}"')
            if value:
                parts.append(f'value="{value}"')
            if focused:
                parts.append("focused")
            if checked is True:
                parts.append("checked")
            elif checked == "mixed":
                parts.append("mixed")
            if disabled:
                parts.append("disabled")
            if expanded is True:
                parts.append("expanded")
            elif expanded is False:
                parts.append("collapsed")

            lines.append("  " * indent + " ".join(parts))

        elif is_structural:
            parts = [role]
            if name:
                parts.append(f'"{name}"')
            if level:
                parts.append(f"level={level}")
            lines.append("  " * indent + " ".join(parts))

        # Recurse into children
        children = node.get("children", [])
        child_indent = indent + 1 if (is_interactive or is_structural) else indent
        
        self._current_path.append({"role": role, "name": name})
        for child in children:
            lines.extend(self._walk_ax_tree(child, child_indent))
        self._current_path.pop()

        return lines

    async def snapshot(self) -> dict:
        """
        Take a native accessibility tree snapshot of the current page.
        
        Uses Playwright's page.accessibility.snapshot() which calls Chrome's
        Accessibility.getFullAXTree via CDP — the same approach as OpenClaw.
        
        Returns a numbered, text-based representation of all interactive elements.
        This is the PRIMARY way the LLM "sees" the page — not screenshots.
        
        Example output:
            Page: Google — https://www.google.com
            
            navigation
              [1] link "About"
              [2] link "Gmail"
              [3] button "Google apps"
              [4] link "Sign in"
            search
              [5] combobox "Search" focused
              [6] button "Search by voice"
              [7] button "Google Search"
              [8] button "I'm Feeling Lucky"
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

            # Use Playwright's native accessibility tree
            # This calls Chrome's Accessibility API via CDP — same as OpenClaw
            ax_tree = await page.accessibility.snapshot()

            if not ax_tree:
                # Fallback: try via CDP session directly (like OpenClaw's snapshotAriaViaPlaywright)
                try:
                    session = await page.context.new_cdp_session(page)
                    await session.send("Accessibility.enable")
                    res = await session.send("Accessibility.getFullAXTree")
                    await session.detach()
                    # Convert CDP format to our format
                    nodes = res.get("nodes", [])
                    if nodes:
                        ax_tree = self._cdp_nodes_to_tree(nodes)
                except Exception as cdp_err:
                    logger.warning(f"CDP fallback also failed: {cdp_err}")

            if not ax_tree:
                return {
                    "success": False,
                    "error": "Could not get accessibility tree. The page may be empty or loading.",
                }

            # Reset ref map and walk the tree
            self._ref_map = {}
            self._ref_counter = 0
            self._current_path = []

            lines = [f"Page: {title} — {url}", ""]
            lines.extend(self._walk_ax_tree(ax_tree))

            snapshot_text = "\n".join(lines)

            # Also get visible text for context (first 2000 chars)
            try:
                text_content = await page.evaluate("document.body?.innerText?.substring(0, 2000) || ''")
            except Exception:
                text_content = ""

            return {
                "success": True,
                "snapshot": snapshot_text,
                "url": url,
                "title": title,
                "element_count": self._ref_counter,
                "tab_id": self._active_tab,
                "text_preview": text_content[:500] if text_content else "",
                "hint": "Use ref numbers to interact: click_ref(1), type_ref(2, 'text'), etc.",
            }

        except Exception as e:
            logger.error(f"Snapshot failed: {e}")
            return {"success": False, "error": str(e)}

    def _cdp_nodes_to_tree(self, nodes: list[dict]) -> dict:
        """
        Convert CDP Accessibility.getFullAXTree nodes into a tree structure
        compatible with Playwright's accessibility.snapshot() format.
        This is the fallback when page.accessibility.snapshot() returns None.
        """
        if not nodes:
            return {}

        # Build a map of nodeId -> node
        node_map = {}
        for n in nodes:
            nid = n.get("nodeId", "")
            role = n.get("role", {}).get("value", "none")
            name = n.get("name", {}).get("value", "")
            value_obj = n.get("value", {})
            value = value_obj.get("value", "") if isinstance(value_obj, dict) else ""

            props = {}
            for prop in n.get("properties", []):
                pname = prop.get("name", "")
                pval = prop.get("value", {}).get("value", "")
                props[pname] = pval

            node_map[nid] = {
                "role": role,
                "name": name,
                "value": str(value) if value else "",
                "focused": props.get("focused", False),
                "checked": props.get("checked"),
                "disabled": props.get("disabled", False),
                "expanded": props.get("expanded"),
                "level": props.get("level"),
                "children": [],
                "childIds": n.get("childIds", []),
            }

        # Build tree from root
        root_id = nodes[0].get("nodeId", "") if nodes else ""
        if root_id not in node_map:
            return {}

        def build_tree(nid):
            node = node_map.get(nid)
            if not node:
                return None
            result = {k: v for k, v in node.items() if k not in ("childIds",)}
            result["children"] = []
            for cid in node.get("childIds", []):
                child = build_tree(cid)
                if child:
                    result["children"].append(child)
            return result

        return build_tree(root_id) or {}

    # ═══════════════════════════════════════════════════════════════
    # REF-BASED INTERACTION (the LLM uses ref numbers from snapshot)
    # ═══════════════════════════════════════════════════════════════

    async def _resolve_ref_locator(self, ref: int, page):
        """
        Resolve a ref number to a Playwright locator.
        
        Uses the role + name from the accessibility tree to build a
        get_by_role() locator — this is the most reliable way to find
        elements, and it's how OpenClaw resolves refs too.
        """
        elem = self._ref_map.get(ref)
        if not elem:
            return None

        role = elem["role"]
        name = elem["name"]

        # Map our role names to Playwright's get_by_role names
        role_map = {
            "link": "link",
            "button": "button",
            "textbox": "textbox",
            "searchbox": "searchbox",
            "combobox": "combobox",
            "checkbox": "checkbox",
            "radio": "radio",
            "tab": "tab",
            "menuitem": "menuitem",
            "option": "option",
            "switch": "switch",
            "slider": "slider",
            "spinbutton": "spinbutton",
            "treeitem": "treeitem",
            "gridcell": "gridcell",
            "row": "row",
            "columnheader": "columnheader",
            "rowheader": "rowheader",
        }

        pw_role = role_map.get(role)
        if not pw_role:
            # Fallback: try using get_by_text if we have a name
            if name:
                return page.get_by_text(name, exact=False).first
            return None

        # Build the locator using role + name (exact match first, then fuzzy)
        if name:
            locator = page.get_by_role(pw_role, name=name, exact=True)
            # Check if it exists
            try:
                count = await locator.count()
                if count > 0:
                    # If multiple matches, try to find the right one by index
                    # Walk through the ref map to count how many refs with same role+name
                    # came before this one
                    nth = 0
                    for r in range(1, ref):
                        other = self._ref_map.get(r, {})
                        if other.get("role") == role and other.get("name") == name:
                            nth += 1
                    return locator.nth(nth)
            except Exception:
                pass

            # Try fuzzy match
            locator = page.get_by_role(pw_role, name=name, exact=False)
            try:
                count = await locator.count()
                if count > 0:
                    nth = 0
                    for r in range(1, ref):
                        other = self._ref_map.get(r, {})
                        if other.get("role") == role and other.get("name") == name:
                            nth += 1
                    return locator.nth(min(nth, count - 1))
            except Exception:
                pass

        # Last resort: role only
        locator = page.get_by_role(pw_role)
        try:
            count = await locator.count()
            if count > 0:
                # Count how many refs with same role came before this one
                nth = 0
                for r in range(1, ref):
                    other = self._ref_map.get(r, {})
                    if other.get("role") == role:
                        nth += 1
                return locator.nth(min(nth, count - 1))
        except Exception:
            pass

        return None

    async def click_ref(self, ref: int, double_click: bool = False, right_click: bool = False) -> dict:
        """Click an element by its ref number from the last snapshot."""
        if ref not in self._ref_map:
            return {
                "success": False,
                "error": f"Ref [{ref}] not found. Take a new snapshot first.",
                "available_refs": list(self._ref_map.keys())[:20],
            }

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        elem = self._ref_map[ref]

        try:
            locator = await self._resolve_ref_locator(ref, page)
            if not locator:
                return {
                    "success": False,
                    "error": f"Could not resolve ref [{ref}] to a page element. Take a new snapshot.",
                }

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
            return {
                "success": False,
                "error": f"Click ref [{ref}] failed: {e}",
                "ref": ref,
                "element": f'{elem["role"]} "{elem["name"]}"',
                "suggestion": "Take a new snapshot — the page may have changed.",
            }

    async def type_ref(self, ref: int, text: str, press_enter: bool = False, clear_first: bool = True) -> dict:
        """Type text into an element by its ref number from the last snapshot."""
        if ref not in self._ref_map:
            return {
                "success": False,
                "error": f"Ref [{ref}] not found. Take a new snapshot first.",
            }

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        elem = self._ref_map[ref]

        try:
            locator = await self._resolve_ref_locator(ref, page)
            if not locator:
                return {
                    "success": False,
                    "error": f"Could not resolve ref [{ref}] to a page element.",
                }

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
                locator = await self._resolve_ref_locator(ref, page)
                if locator:
                    await locator.click(timeout=3000)
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
                pass
            return {
                "success": False,
                "error": f"Type failed: {e}",
                "ref": ref,
            }

    async def select_ref(self, ref: int, value: str) -> dict:
        """Select an option from a dropdown by ref number."""
        if ref not in self._ref_map:
            return {"success": False, "error": f"Ref [{ref}] not found."}

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            locator = await self._resolve_ref_locator(ref, page)
            if not locator:
                return {"success": False, "error": f"Could not resolve ref [{ref}]."}
            await locator.select_option(value, timeout=5000)
            return {"success": True, "action": "select", "ref": ref, "value": value}
        except Exception as e:
            return {"success": False, "error": str(e), "ref": ref}

    async def check_ref(self, ref: int, checked: bool = True) -> dict:
        """Check or uncheck a checkbox by ref number."""
        if ref not in self._ref_map:
            return {"success": False, "error": f"Ref [{ref}] not found."}

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            locator = await self._resolve_ref_locator(ref, page)
            if not locator:
                return {"success": False, "error": f"Could not resolve ref [{ref}]."}
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
                locator = await self._resolve_ref_locator(ref, page)
                if not locator:
                    return {"success": False, "error": f"Could not resolve ref [{ref}]."}
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

    async def sync_tabs(self) -> dict:
        """
        Re-sync the internal tab map with what is actually open in the browser.

        When Plutus connects to the user's real browser via CDP, tabs that were
        opened before the connection (or by the user manually) may not be in
        self._pages. This method discovers all real pages and updates the map,
        pruning stale entries and adding new ones.
        """
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        try:
            real_pages = self._context.pages if self._context else []
            new_pages: dict[str, Any] = {}
            tabs = []

            for i, page in enumerate(real_pages):
                # Try to find an existing tab_id for this page object
                existing_id = None
                for tid, p in self._pages.items():
                    if p == page:
                        existing_id = tid
                        break
                tab_id = existing_id or f"tab_{i}"
                new_pages[tab_id] = page

                try:
                    url = page.url
                    title = await page.title()
                    is_stale = url in ("about:blank", "chrome://newtab/", "")
                except Exception:
                    url = "unknown"
                    title = "(crashed or unresponsive)"
                    is_stale = True

                tabs.append({
                    "tab_id": tab_id,
                    "url": url,
                    "title": title,
                    "active": tab_id == self._active_tab,
                    "stale": is_stale,
                })

            self._pages = new_pages

            # If the current active tab is gone, switch to the last real tab
            if self._active_tab not in self._pages:
                non_stale = [t for t in tabs if not t["stale"]]
                if non_stale:
                    self._active_tab = non_stale[-1]["tab_id"]
                elif self._pages:
                    self._active_tab = list(self._pages.keys())[-1]
                else:
                    self._active_tab = None

            return {
                "success": True,
                "tabs": tabs,
                "count": len(tabs),
                "active_tab": self._active_tab,
                "hint": "Use switch_tab(tab_id) to focus the correct tab before interacting.",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def reset_browser_session(self, close_stale: bool = True, keep_tab_id: Optional[str] = None) -> dict:
        """
        Reset the browser session state.

        This is the fix for the 'stale tab / wrong session' problem:
        - Re-syncs the tab map with what's actually open in the browser
        - Optionally closes blank/new-tab pages that are just noise
        - Resets the ref map so old [ref] numbers are no longer valid
        - Switches focus to the most relevant tab (or keep_tab_id if specified)
        - Returns a fresh snapshot of the active tab

        Use this when:
        - The agent is confused about which tab is active
        - Browser was restarted and the session is stale
        - After connecting to the user's real browser via CDP
        - When structured browser tools are returning errors about wrong pages
        """
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        try:
            # Step 1: Re-sync tab map
            sync = await self.sync_tabs()
            if not sync["success"]:
                return sync

            tabs = sync["tabs"]
            closed = []

            # Step 2: Optionally close stale (blank) tabs
            if close_stale:
                for tab in tabs:
                    if tab["stale"] and tab["tab_id"] != keep_tab_id:
                        try:
                            page = self._pages.get(tab["tab_id"])
                            if page:
                                await page.close()
                                del self._pages[tab["tab_id"]]
                                closed.append(tab["tab_id"])
                        except Exception:
                            pass

            # Step 3: Switch to the requested tab or pick the best one
            if keep_tab_id and keep_tab_id in self._pages:
                self._active_tab = keep_tab_id
            else:
                # Prefer the last non-stale tab
                live_tabs = [
                    t for t in tabs
                    if t["tab_id"] in self._pages and not t["stale"]
                ]
                if live_tabs:
                    self._active_tab = live_tabs[-1]["tab_id"]
                elif self._pages:
                    self._active_tab = list(self._pages.keys())[-1]

            # Step 4: Reset ref map (old refs are invalid after session reset)
            self._ref_map = {}
            self._ref_counter = 0

            # Step 5: Take a fresh snapshot of the active tab
            snap = await self.snapshot() if self._active_tab else {"success": False, "error": "No tabs remaining"}

            active_page = self._get_active_page()
            return {
                "success": True,
                "active_tab": self._active_tab,
                "url": active_page.url if active_page else None,
                "title": await active_page.title() if active_page else None,
                "closed_stale_tabs": closed,
                "remaining_tabs": len(self._pages),
                "snapshot": snap.get("snapshot", ""),
                "hint": "Session reset complete. Use the [ref] numbers above to interact with the page.",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

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
            screenshot_bytes = await page.screenshot(full_page=full_page, type="png")
            screenshot_dir = Path.home() / ".plutus" / "screenshots"
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            path = screenshot_dir / f"screenshot_{int(time.time())}.png"
            path.write_bytes(screenshot_bytes)

            # Also return the accessibility tree snapshot so the agent can continue
            # without needing to call snapshot() separately.
            try:
                snap_result = await self.snapshot()
                snapshot_text = snap_result.get("snapshot") if isinstance(snap_result, dict) else None
            except Exception:
                snapshot_text = None

            result: dict = {
                "success": True,
                "saved_to": str(path),
                "url": page.url,
                "title": await page.title(),
                "ACTION_REQUIRED": "DO NOT call browser_screenshot again. Use snapshot() to read the page. The accessibility tree is included below — use the [ref] numbers to interact.",
            }
            if snapshot_text:
                result["snapshot"] = snapshot_text
            return result
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

    # ═══════════════════════════════════════════════════════════════
    # OPENCLAW-PARITY: New capabilities matching chrome-mcp.ts
    # ═══════════════════════════════════════════════════════════════

    async def drag_ref(self, from_ref: int, to_ref: int) -> dict:
        """Drag one element onto another by ref numbers (OpenClaw: drag from_uid → to_uid)."""
        if from_ref not in self._ref_map:
            return {"success": False, "error": f"Source ref [{from_ref}] not found. Take a new snapshot first."}
        if to_ref not in self._ref_map:
            return {"success": False, "error": f"Target ref [{to_ref}] not found. Take a new snapshot first."}

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            src_locator = await self._resolve_ref_locator(from_ref, page)
            dst_locator = await self._resolve_ref_locator(to_ref, page)
            if not src_locator or not dst_locator:
                return {"success": False, "error": "Could not resolve one or both refs to page elements."}

            src_box = await src_locator.bounding_box()
            dst_box = await dst_locator.bounding_box()
            if not src_box or not dst_box:
                return {"success": False, "error": "Could not get bounding boxes for drag source or target."}

            sx = src_box["x"] + src_box["width"] / 2
            sy = src_box["y"] + src_box["height"] / 2
            dx = dst_box["x"] + dst_box["width"] / 2
            dy = dst_box["y"] + dst_box["height"] / 2

            await page.mouse.move(sx, sy)
            await page.mouse.down()
            await asyncio.sleep(0.1)
            # Move in steps for smoother drag (required by some apps)
            steps = 10
            for i in range(1, steps + 1):
                await page.mouse.move(sx + (dx - sx) * i / steps, sy + (dy - sy) * i / steps)
                await asyncio.sleep(0.02)
            await page.mouse.up()

            from_elem = self._ref_map[from_ref]
            to_elem = self._ref_map[to_ref]
            return {
                "success": True,
                "action": "drag",
                "from": f'{from_elem["role"]} "{from_elem["name"]}"',
                "to": f'{to_elem["role"]} "{to_elem["name"]}"',
            }
        except Exception as e:
            return {"success": False, "error": f"Drag failed: {e}"}

    async def handle_dialog(self, action: str = "accept", prompt_text: str = "") -> dict:
        """
        Accept or dismiss a browser dialog (alert/confirm/prompt).
        OpenClaw equivalent: handle_dialog(action, promptText).
        Must be called BEFORE the dialog appears (register handler first).
        """
        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            def _on_dialog(dialog):
                asyncio.ensure_future(
                    dialog.accept(prompt_text) if action == "accept" else dialog.dismiss()
                )

            page.once("dialog", _on_dialog)
            return {
                "success": True,
                "action": "handle_dialog",
                "registered": action,
                "hint": "Dialog handler registered. Trigger the action that causes the dialog now.",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def upload_file_ref(self, ref: int, file_path: str) -> dict:
        """
        Upload a file to a file input element by its ref number.
        OpenClaw equivalent: upload_file(uid, filePath).
        """
        import os
        if not os.path.exists(file_path):
            return {"success": False, "error": f"File not found: {file_path}"}

        if ref not in self._ref_map:
            return {"success": False, "error": f"Ref [{ref}] not found. Take a new snapshot first."}

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            locator = await self._resolve_ref_locator(ref, page)
            if not locator:
                return {"success": False, "error": f"Could not resolve ref [{ref}] to a page element."}

            await locator.set_input_files(file_path, timeout=10000)
            return {
                "success": True,
                "action": "upload_file",
                "ref": ref,
                "file": os.path.basename(file_path),
            }
        except Exception as e:
            # Fallback: find nearest file input
            try:
                file_inputs = page.locator('input[type="file"]')
                count = await file_inputs.count()
                for i in range(count):
                    try:
                        await file_inputs.nth(i).set_input_files(file_path, timeout=5000)
                        return {
                            "success": True,
                            "action": "upload_file",
                            "method": "fallback_file_input",
                            "file": os.path.basename(file_path),
                        }
                    except Exception:
                        continue
            except Exception:
                pass
            return {"success": False, "error": f"Upload failed: {e}"}

    async def get_page_content(self, max_chars: int = 20000) -> dict:
        """
        Extract the full readable text content of the current page.
        Useful for scraping, reading articles, extracting data.
        Returns both the raw text and a Markdown-formatted version.
        """
        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            title = await page.title()
            url = page.url

            # Get inner text (strips HTML tags, preserves structure)
            inner_text = await page.evaluate("""
                () => {
                    // Remove script, style, nav, footer, header elements
                    const clone = document.body.cloneNode(true);
                    const remove = clone.querySelectorAll(
                        'script, style, noscript, nav, footer, header, aside, [aria-hidden="true"]'
                    );
                    remove.forEach(el => el.remove());
                    return clone.innerText || clone.textContent || '';
                }
            """)

            # Also get page metadata
            meta = await page.evaluate("""
                () => ({
                    description: document.querySelector('meta[name="description"]')?.content || '',
                    og_title: document.querySelector('meta[property="og:title"]')?.content || '',
                    og_description: document.querySelector('meta[property="og:description"]')?.content || '',
                    canonical: document.querySelector('link[rel="canonical"]')?.href || '',
                    h1: Array.from(document.querySelectorAll('h1')).map(h => h.innerText.trim()).filter(Boolean),
                    h2: Array.from(document.querySelectorAll('h2')).map(h => h.innerText.trim()).filter(Boolean).slice(0, 10),
                    links: Array.from(document.querySelectorAll('a[href]')).map(a => ({
                        text: a.innerText.trim(),
                        href: a.href
                    })).filter(l => l.text).slice(0, 30),
                })
            """)

            text = (inner_text or "").strip()
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n... [truncated at {max_chars} chars]"

            return {
                "success": True,
                "url": url,
                "title": title,
                "content": text,
                "meta": meta,
                "char_count": len(inner_text or ""),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_cookies(self, url: str = "") -> dict:
        """Get cookies for the current page or a specific URL."""
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        try:
            if url:
                cookies = await self._context.cookies([url])
            else:
                page = self._get_active_page()
                cookies = await self._context.cookies([page.url] if page else [])
            return {"success": True, "cookies": cookies, "count": len(cookies)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def set_cookies(self, cookies: list[dict]) -> dict:
        """
        Set cookies in the browser context.
        Each cookie dict: {name, value, url?, domain?, path?, httpOnly?, secure?, sameSite?, expires?}
        """
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        try:
            await self._context.add_cookies(cookies)
            return {"success": True, "action": "set_cookies", "count": len(cookies)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def clear_storage(self, storage_type: str = "all") -> dict:
        """
        Clear browser storage: cookies, localStorage, sessionStorage, or all.
        storage_type: 'cookies' | 'local_storage' | 'session_storage' | 'all'
        """
        if not await self._ensure_browser():
            return {"success": False, "error": "Browser not available"}

        page = self._get_active_page()
        cleared = []

        try:
            if storage_type in ("cookies", "all"):
                await self._context.clear_cookies()
                cleared.append("cookies")

            if storage_type in ("local_storage", "all") and page:
                await page.evaluate("localStorage.clear()")
                cleared.append("localStorage")

            if storage_type in ("session_storage", "all") and page:
                await page.evaluate("sessionStorage.clear()")
                cleared.append("sessionStorage")

            return {"success": True, "action": "clear_storage", "cleared": cleared}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def scroll_to_ref(self, ref: int) -> dict:
        """Scroll a specific element into view by its ref number."""
        if ref not in self._ref_map:
            return {"success": False, "error": f"Ref [{ref}] not found. Take a new snapshot first."}

        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            locator = await self._resolve_ref_locator(ref, page)
            if not locator:
                return {"success": False, "error": f"Could not resolve ref [{ref}] to a page element."}

            await locator.scroll_into_view_if_needed(timeout=5000)
            elem = self._ref_map[ref]
            return {
                "success": True,
                "action": "scroll_to_ref",
                "ref": ref,
                "element": f'{elem["role"]} "{elem["name"]}"',
            }
        except Exception as e:
            return {"success": False, "error": f"Scroll to ref [{ref}] failed: {e}"}

    async def wait_for_any(self, texts: list[str], timeout: int = 15000) -> dict:
        """
        Wait for any of several text strings to appear on the page.
        OpenClaw equivalent: wait_for(text=[...], timeoutMs).
        Returns which text was found first.
        """
        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        if not texts:
            return {"success": False, "error": "Provide at least one text string to wait for"}

        try:
            import asyncio
            tasks = [
                asyncio.ensure_future(
                    page.get_by_text(t, exact=False).first.wait_for(timeout=timeout)
                )
                for t in texts
            ]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()

            # Find which text was found
            for i, task in enumerate(tasks):
                if task in done and not task.exception():
                    return {"success": True, "found": texts[i], "all_texts": texts}

            return {"success": False, "error": "None of the texts appeared within the timeout", "texts": texts}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def resize_viewport(self, width: int, height: int) -> dict:
        """
        Resize the browser viewport.
        OpenClaw equivalent: resize_page(width, height).
        """
        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            await page.set_viewport_size({"width": width, "height": height})
            return {"success": True, "action": "resize_viewport", "width": width, "height": height}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def iframe_snapshot(self, frame_selector: str = "", frame_index: int = 0) -> dict:
        """
        Take an accessibility tree snapshot of content inside an iframe.
        Use frame_selector (CSS selector for the iframe element) or frame_index (0-based).
        """
        page = self._get_active_page()
        if not page:
            return {"success": False, "error": "No active tab"}

        try:
            frames = page.frames
            # frames[0] is always the main frame — skip it
            inner_frames = [f for f in frames if f != page.main_frame]

            if not inner_frames:
                return {"success": False, "error": "No iframes found on this page"}

            if frame_selector:
                # Find frame by its src URL or name
                frame = next(
                    (f for f in inner_frames if frame_selector in (f.url or "") or frame_selector in (f.name or "")),
                    None
                )
                if not frame:
                    return {"success": False, "error": f"No iframe matching '{frame_selector}' found"}
            else:
                if frame_index >= len(inner_frames):
                    return {"success": False, "error": f"Frame index {frame_index} out of range (found {len(inner_frames)} iframes)"}
                frame = inner_frames[frame_index]

            # Get accessibility tree of the frame
            ax_tree = await frame.accessibility.snapshot()
            if not ax_tree:
                return {"success": False, "error": "Could not get accessibility tree from iframe"}

            # Reset ref map and walk the frame's tree
            self._ref_map = {}
            self._ref_counter = 0
            self._current_path = []
            lines = [f"IFrame: {frame.url}", ""]
            lines.extend(self._walk_ax_tree(ax_tree))

            return {
                "success": True,
                "snapshot": "\n".join(lines),
                "frame_url": frame.url,
                "element_count": self._ref_counter,
                "hint": "Refs from this snapshot are now active. Use click_ref/type_ref to interact.",
            }
        except Exception as e:
            return {"success": False, "error": f"iframe_snapshot failed: {e}"}

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
