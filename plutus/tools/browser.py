"""Browser tool — web navigation and automation via Playwright."""

from __future__ import annotations

from typing import Any

from plutus.tools.base import Tool


class BrowserTool(Tool):
    """Browser automation tool using Playwright.

    Supports navigation, screenshots, content extraction, form filling, and clicking.
    Lazily initializes the browser on first use.
    """

    def __init__(self) -> None:
        self._pw = None
        self._browser = None
        self._page = None

    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return (
            "Control a web browser. Navigate to URLs, take screenshots, extract page content, "
            "click elements, fill forms, run JavaScript, and upload files. "
            "Operations: navigate, screenshot, extract, click, click_text, fill, evaluate, wait, back, forward, upload_file, close.\n"
            "Use click_text to click buttons/links by their visible text (e.g. 'Accept all', 'Sign in') — "
            "this is more reliable than CSS selectors on dynamic sites.\n"
            "Use wait to wait for a selector to appear before interacting with it.\n"
            "Use upload_file to upload files via file input elements or drag-and-drop zones. "
            "Pass 'path' as the local file path and optionally 'selector' to target a specific input."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "navigate", "screenshot", "extract", "click", "click_text",
                        "fill", "evaluate", "wait", "back", "forward", "close",
                    ],
                    "description": "The browser operation to perform",
                },
                "url": {
                    "type": "string",
                    "description": "URL to navigate to (for navigate operation)",
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector for element targeting (click, fill)",
                },
                "value": {
                    "type": "string",
                    "description": "Value to fill (for fill operation) or JS code (for evaluate)",
                },
                "path": {
                    "type": "string",
                    "description": "File path for screenshot output or file to upload (upload_file operation)",
                },
            },
            "required": ["operation"],
        }

    async def _ensure_browser(self) -> None:
        """Lazily start the browser, reconnecting if the previous session died."""
        # Check if existing browser/page is still usable
        if self._page is not None:
            try:
                # Quick liveness check
                await self._page.title()
                return
            except Exception:
                # Browser or page died — tear down and relaunch
                await self._cleanup()

        try:
            from playwright.async_api import async_playwright

            self._pw = await async_playwright().start()
            # Use headless mode when no display is available (e.g. Linux servers)
            import os
            has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
            headless = not has_display
            self._browser = await self._pw.chromium.launch(headless=headless)
            self._page = await self._browser.new_page()
        except ImportError:
            raise RuntimeError(
                "Playwright is not installed. Run: pip install playwright"
            )
        except Exception as e:
            await self._cleanup()
            raise RuntimeError(
                f"Failed to launch browser: {e}. "
                "Run: playwright install chromium"
            )

    async def _cleanup(self) -> None:
        """Tear down browser resources safely."""
        for resource in (self._browser, self._pw):
            if resource is not None:
                try:
                    if hasattr(resource, "close"):
                        await resource.close()
                    elif hasattr(resource, "stop"):
                        await resource.stop()
                except Exception:
                    pass
        self._pw = None
        self._browser = None
        self._page = None

    async def execute(self, **kwargs: Any) -> str:
        operation: str = kwargs["operation"]

        if operation == "close":
            return await self._close()

        try:
            await self._ensure_browser()
        except RuntimeError as e:
            return f"[ERROR] {e}"
        assert self._page is not None

        handlers = {
            "navigate": self._navigate,
            "screenshot": self._screenshot,
            "extract": self._extract,
            "click": self._click,
            "click_text": self._click_text,
            "fill": self._fill,
            "evaluate": self._evaluate,
            "wait": self._wait,
            "back": self._back,
            "forward": self._forward,
            "upload_file": self._upload_file,
        }

        handler = handlers.get(operation)
        if not handler:
            return f"[ERROR] Unknown browser operation: {operation}"

        try:
            return await handler(kwargs)
        except Exception as e:
            return f"[ERROR] Browser {operation} failed: {e}"

    async def _navigate(self, kwargs: dict) -> str:
        url = kwargs.get("url", "")
        if not url:
            return "[ERROR] Navigate requires a 'url' parameter"
        await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        title = await self._page.title()
        # Auto-dismiss common cookie consent banners so they don't block interaction
        dismissed = await self._try_dismiss_consent()
        result = f"Navigated to: {self._page.url}\nTitle: {title}"
        if dismissed:
            result += f"\n(Auto-dismissed cookie consent dialog: clicked '{dismissed}')"
        return result

    async def _try_dismiss_consent(self) -> str | None:
        """Try to dismiss common cookie/consent banners. Returns button text if dismissed."""
        # Common consent button patterns across major sites
        consent_selectors = [
            # Text-based: most reliable across sites
            "button:has-text('Accept all')",
            "button:has-text('Accept All')",
            "button:has-text('Accept cookies')",
            "button:has-text('Accept & continue')",
            "button:has-text('I agree')",
            "button:has-text('Allow all')",
            "button:has-text('Agree')",
            "button:has-text('Got it')",
            "button:has-text('OK')",
            # Common aria-labels
            'button[aria-label="Accept all"]',
            'button[aria-label="Accept All"]',
            'button[aria-label="Accept cookies"]',
            # Common IDs/classes
            "button#L2AGLb",  # Google consent
            ".consent-bump button.yt-spec-button-shape-next--filled",  # YouTube
        ]
        for selector in consent_selectors:
            try:
                btn = self._page.locator(selector).first
                if await btn.is_visible(timeout=1500):
                    label = (await btn.text_content() or selector).strip()
                    await btn.click(timeout=3000)
                    # Small pause for page to settle after consent dismissal
                    await self._page.wait_for_timeout(500)
                    return label
            except Exception:
                continue
        return None

    async def _screenshot(self, kwargs: dict) -> str:
        import os
        from pathlib import Path

        default_path = os.path.join(
            str(Path.home() / ".plutus" / "screenshots"), "browser_screenshot.png"
        )
        os.makedirs(os.path.dirname(default_path), exist_ok=True)
        path = kwargs.get("path", default_path)
        await self._page.screenshot(path=path, full_page=True)
        return f"Screenshot saved to: {path}"

    async def _extract(self, kwargs: dict) -> str:
        selector = kwargs.get("selector")
        if selector:
            elements = await self._page.query_selector_all(selector)
            texts = []
            for el in elements[:20]:
                text = await el.text_content()
                if text and text.strip():
                    texts.append(text.strip())
            return "\n".join(texts) if texts else f"No text found for selector: {selector}"

        # Extract full page text
        text = await self._page.text_content("body") or ""
        if len(text) > 10000:
            text = text[:10000] + "\n... [truncated]"
        return text

    async def _click(self, kwargs: dict) -> str:
        selector = kwargs.get("selector", "")
        if not selector:
            return "[ERROR] Click requires a 'selector' parameter"
        await self._page.click(selector, timeout=15000)
        return f"Clicked: {selector}"

    async def _click_text(self, kwargs: dict) -> str:
        text = kwargs.get("value", "")
        if not text:
            return "[ERROR] click_text requires a 'value' parameter with the visible text to click"
        # Use Playwright's text selector — matches buttons, links, and other clickable elements
        locator = self._page.get_by_text(text, exact=False).first
        if not await locator.is_visible(timeout=5000):
            return f"[ERROR] No visible element found with text: {text}"
        await locator.click(timeout=15000)
        tag = await locator.evaluate("el => el.tagName.toLowerCase()")
        return f"Clicked {tag} with text: '{text}'"

    async def _wait(self, kwargs: dict) -> str:
        selector = kwargs.get("selector", "")
        if not selector:
            return "[ERROR] Wait requires a 'selector' parameter"
        timeout = 15000
        await self._page.wait_for_selector(selector, state="visible", timeout=timeout)
        return f"Element '{selector}' is now visible"

    async def _fill(self, kwargs: dict) -> str:
        selector = kwargs.get("selector", "")
        value = kwargs.get("value", "")
        if not selector:
            return "[ERROR] Fill requires a 'selector' parameter"
        await self._page.fill(selector, value, timeout=15000)
        return f"Filled '{selector}' with value"

    async def _evaluate(self, kwargs: dict) -> str:
        code = kwargs.get("value", "")
        if not code:
            return "[ERROR] Evaluate requires a 'value' parameter with JS code"
        result = await self._page.evaluate(code)
        output = str(result)
        # Cap output to prevent OOM from massive DOM dumps
        if len(output) > 50000:
            output = output[:50000] + "\n... [truncated at 50KB]"
        return output

    async def _back(self, kwargs: dict) -> str:
        await self._page.go_back()
        return f"Navigated back to: {self._page.url}"

    async def _forward(self, kwargs: dict) -> str:
        await self._page.go_forward()
        return f"Navigated forward to: {self._page.url}"

    async def _upload_file(self, kwargs: dict) -> str:
        """Upload a file via a file input element or drag-and-drop zone."""
        file_path = kwargs.get("path", "")
        if not file_path:
            return "[ERROR] upload_file requires a 'path' parameter with the local file path"

        import os
        if not os.path.exists(file_path):
            return f"[ERROR] File not found: {file_path}"

        selector = kwargs.get("selector", "")

        # Strategy 1: Use a specific selector if provided
        if selector:
            try:
                file_input = self._page.locator(selector)
                await file_input.set_input_files(file_path, timeout=10000)
                return f"File uploaded via selector '{selector}': {os.path.basename(file_path)}"
            except Exception as e:
                return f"[ERROR] Upload via selector '{selector}' failed: {e}"

        # Strategy 2: Auto-detect file input elements on the page
        try:
            # Find all visible file inputs
            file_inputs = self._page.locator('input[type="file"]')
            count = await file_inputs.count()
            if count > 0:
                # Use the first visible one
                for i in range(count):
                    inp = file_inputs.nth(i)
                    try:
                        await inp.set_input_files(file_path, timeout=5000)
                        return f"File uploaded via file input #{i + 1}: {os.path.basename(file_path)}"
                    except Exception:
                        continue
        except Exception:
            pass

        # Strategy 3: Drag-and-drop simulation via JavaScript
        try:
            import base64
            with open(file_path, "rb") as f:
                file_bytes = f.read()
            b64 = base64.b64encode(file_bytes).decode()
            mime = "application/octet-stream"
            ext = os.path.splitext(file_path)[1].lower()
            mime_map = {
                ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg", ".gif": "image/gif", ".txt": "text/plain",
                ".csv": "text/csv", ".json": "application/json",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                ".zip": "application/zip",
            }
            mime = mime_map.get(ext, "application/octet-stream")
            filename = os.path.basename(file_path)

            # Simulate a DataTransfer drop event on the document body
            js_result = await self._page.evaluate(f"""
                (function() {{
                    const b64 = '{b64}';
                    const mime = '{mime}';
                    const filename = '{filename}';
                    const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
                    const file = new File([bytes], filename, {{type: mime}});
                    const dt = new DataTransfer();
                    dt.items.add(file);

                    // Try to find a drop zone
                    const dropTargets = [
                        document.querySelector('[data-testid*="drop"]'),
                        document.querySelector('[class*="drop"]'),
                        document.querySelector('[class*="upload"]'),
                        document.querySelector('[aria-label*="upload"]'),
                        document.querySelector('[aria-label*="drop"]'),
                        document.body,
                    ].filter(Boolean);

                    const target = dropTargets[0];
                    if (!target) return 'no_target';

                    const events = ['dragenter', 'dragover', 'drop'];
                    for (const evtName of events) {{
                        const evt = new DragEvent(evtName, {{
                            bubbles: true, cancelable: true, dataTransfer: dt
                        }});
                        target.dispatchEvent(evt);
                    }}
                    return 'dispatched_to:' + (target.className || target.tagName);
                }})()
            """)
            return f"File upload attempted via drag-and-drop simulation: {filename} ({js_result})"
        except Exception as e:
            return f"[ERROR] All upload strategies failed for {file_path}: {e}"

    async def _close(self) -> str:
        await self._cleanup()
        return "Browser closed"
