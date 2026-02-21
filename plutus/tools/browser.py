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
            "click elements, fill forms, and run JavaScript. "
            "Operations: navigate, screenshot, extract, click, fill, evaluate, back, forward, close."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "navigate", "screenshot", "extract", "click",
                        "fill", "evaluate", "back", "forward", "close",
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
                    "description": "File path for screenshot output",
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
            self._browser = await self._pw.chromium.launch(headless=False)
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
            "fill": self._fill,
            "evaluate": self._evaluate,
            "back": self._back,
            "forward": self._forward,
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
        return f"Navigated to: {self._page.url}\nTitle: {await self._page.title()}"

    async def _screenshot(self, kwargs: dict) -> str:
        path = kwargs.get("path", "/tmp/plutus_screenshot.png")
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
        await self._page.click(selector, timeout=5000)
        return f"Clicked: {selector}"

    async def _fill(self, kwargs: dict) -> str:
        selector = kwargs.get("selector", "")
        value = kwargs.get("value", "")
        if not selector:
            return "[ERROR] Fill requires a 'selector' parameter"
        await self._page.fill(selector, value, timeout=5000)
        return f"Filled '{selector}' with value"

    async def _evaluate(self, kwargs: dict) -> str:
        code = kwargs.get("value", "")
        if not code:
            return "[ERROR] Evaluate requires a 'value' parameter with JS code"
        result = await self._page.evaluate(code)
        return str(result)

    async def _back(self, kwargs: dict) -> str:
        await self._page.go_back()
        return f"Navigated back to: {self._page.url}"

    async def _forward(self, kwargs: dict) -> str:
        await self._page.go_forward()
        return f"Navigated forward to: {self._page.url}"

    async def _close(self) -> str:
        await self._cleanup()
        return "Browser closed"
