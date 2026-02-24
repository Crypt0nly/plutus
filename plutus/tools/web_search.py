"""Web search tool — real-time web search and page fetching.

Provides two operations:
  - search: Query the web and get summarized results (DuckDuckGo or Tavily)
  - fetch:  Retrieve and extract readable text from a specific URL

Works without any API key (DuckDuckGo) but supports Tavily for higher-quality
results when TAVILY_API_KEY is set.
"""

from __future__ import annotations

import html
import logging
import os
import re
from typing import Any

import httpx

from plutus.tools.base import Tool

logger = logging.getLogger("plutus.tools.web_search")

# Limits
MAX_FETCH_SIZE = 500_000  # 500 KB max download
MAX_TEXT_LENGTH = 15_000  # Truncate extracted text
SEARCH_TIMEOUT = 30  # seconds
FETCH_TIMEOUT = 30  # seconds
DEFAULT_NUM_RESULTS = 5

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}


def _strip_html(raw: str) -> str:
    """Remove HTML tags and decode entities, returning plain text."""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", raw, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_readable(raw_html: str) -> str:
    """Best-effort extraction of main content from HTML."""
    # Try to find <main>, <article>, or <body>
    for tag in ("main", "article"):
        pattern = re.compile(rf"<{tag}[^>]*>(.*?)</{tag}>", re.DOTALL | re.IGNORECASE)
        match = pattern.search(raw_html)
        if match:
            return _strip_html(match.group(1))

    body_match = re.search(r"<body[^>]*>(.*?)</body>", raw_html, re.DOTALL | re.IGNORECASE)
    if body_match:
        return _strip_html(body_match.group(1))

    return _strip_html(raw_html)


async def _search_duckduckgo(query: str, num_results: int) -> list[dict[str, str]]:
    """Search DuckDuckGo via its HTML endpoint and parse results."""
    url = "https://html.duckduckgo.com/html/"
    data = {"q": query}
    results: list[dict[str, str]] = []

    async with httpx.AsyncClient(headers=_HEADERS, timeout=SEARCH_TIMEOUT) as client:
        resp = await client.post(url, data=data, follow_redirects=True)
        resp.raise_for_status()
        page = resp.text

    # Parse result blocks — each is in a <div class="result ..."> ... </div>
    # Title + URL in <a class="result__a" href="...">Title</a>
    # Snippet in <a class="result__snippet" ...>Snippet</a>
    link_pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="([^"]*)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL,
    )

    links = link_pattern.findall(page)
    snippets = snippet_pattern.findall(page)

    for i, (href, title_html) in enumerate(links):
        if i >= num_results:
            break
        title = _strip_html(title_html)
        snippet = _strip_html(snippets[i]) if i < len(snippets) else ""
        # DDG wraps URLs in a redirect — extract the actual URL
        actual_url = href
        if "uddg=" in href:
            from urllib.parse import parse_qs, urlparse

            qs = parse_qs(urlparse(href).query)
            actual_url = qs.get("uddg", [href])[0]
        results.append({"title": title, "url": actual_url, "snippet": snippet})

    return results


async def _search_tavily(query: str, num_results: int, api_key: str) -> list[dict[str, str]]:
    """Search via Tavily API (higher quality, needs key)."""
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": num_results,
        "include_answer": True,
    }
    results: list[dict[str, str]] = []

    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

    answer = data.get("answer", "")
    for item in data.get("results", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("content", ""),
        })

    # Prepend the AI-generated answer summary if available
    if answer and results:
        results[0]["answer"] = answer

    return results


async def _fetch_url(url: str) -> str:
    """Fetch a URL and return extracted readable text."""
    async with httpx.AsyncClient(
        headers=_HEADERS,
        timeout=FETCH_TIMEOUT,
        follow_redirects=True,
        max_redirects=5,
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        raw = resp.text

        if len(raw) > MAX_FETCH_SIZE:
            raw = raw[:MAX_FETCH_SIZE]

    # If it's HTML, extract readable content
    if "html" in content_type.lower() or raw.strip().startswith("<"):
        text = _extract_readable(raw)
    else:
        text = raw

    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH] + "\n\n... [truncated]"

    return text


class WebSearchTool(Tool):
    """Web search and URL fetching tool for real-time information access."""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "Search the web for real-time information or fetch the content of a URL. "
            "Use operation='search' to find information on any topic (news, facts, docs, "
            "prices, weather, etc.). Use operation='fetch' to retrieve and read the full "
            "text content of a specific webpage. This tool gives you access to live, "
            "up-to-date information from the internet."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["search", "fetch"],
                    "description": (
                        "The operation to perform: "
                        "'search' to query the web and get results, "
                        "'fetch' to retrieve the text content of a specific URL"
                    ),
                },
                "query": {
                    "type": "string",
                    "description": (
                        "The search query (for operation='search'). "
                        "Be specific and descriptive for best results."
                    ),
                },
                "url": {
                    "type": "string",
                    "description": (
                        "The URL to fetch (for operation='fetch'). "
                        "Must be a full URL including https://"
                    ),
                },
                "num_results": {
                    "type": "integer",
                    "description": (
                        "Number of search results to return (default: 5, max: 10). "
                        "Only used with operation='search'."
                    ),
                },
            },
            "required": ["operation"],
        }

    async def execute(self, **kwargs: Any) -> str:
        operation = kwargs.get("operation", "search")

        if operation == "search":
            return await self._search(kwargs)
        elif operation == "fetch":
            return await self._fetch(kwargs)
        else:
            return f"[ERROR] Unknown operation: {operation}. Use 'search' or 'fetch'."

    async def _search(self, kwargs: dict[str, Any]) -> str:
        query = kwargs.get("query", "")
        if not query:
            return "[ERROR] 'query' parameter is required for search operation."

        num_results = min(kwargs.get("num_results", DEFAULT_NUM_RESULTS), 10)

        try:
            # Use Tavily if API key is available, otherwise DuckDuckGo
            tavily_key = os.environ.get("TAVILY_API_KEY", "")
            if tavily_key:
                results = await _search_tavily(query, num_results, tavily_key)
                provider = "Tavily"
            else:
                results = await _search_duckduckgo(query, num_results)
                provider = "DuckDuckGo"

            if not results:
                return f"No results found for: {query}"

            # Format results
            lines = [f"Web search results for: {query} (via {provider})\n"]

            # Include AI answer if present (Tavily)
            answer = results[0].get("answer") if results else None
            if answer:
                lines.append(f"Summary: {answer}\n")

            for i, r in enumerate(results, 1):
                lines.append(f"{i}. {r['title']}")
                lines.append(f"   URL: {r['url']}")
                if r.get("snippet"):
                    lines.append(f"   {r['snippet']}")
                lines.append("")

            return "\n".join(lines)

        except httpx.HTTPStatusError as e:
            return f"[ERROR] Search request failed (HTTP {e.response.status_code}): {e}"
        except httpx.TimeoutException:
            return f"[ERROR] Search timed out after {SEARCH_TIMEOUT}s for: {query}"
        except Exception as e:
            logger.exception(f"Web search failed for query: {query}")
            return f"[ERROR] Search failed: {e}"

    async def _fetch(self, kwargs: dict[str, Any]) -> str:
        url = kwargs.get("url", "")
        if not url:
            return "[ERROR] 'url' parameter is required for fetch operation."

        # Basic URL validation
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            text = await _fetch_url(url)
            if not text or not text.strip():
                return f"Fetched {url} but no readable text content was found."

            return f"Content from {url}:\n\n{text}"

        except httpx.HTTPStatusError as e:
            return f"[ERROR] Fetch failed (HTTP {e.response.status_code}): {url}"
        except httpx.TimeoutException:
            return f"[ERROR] Fetch timed out after {FETCH_TIMEOUT}s: {url}"
        except Exception as e:
            logger.exception(f"URL fetch failed for: {url}")
            return f"[ERROR] Fetch failed: {e}"
