"""Localhost site crawler — visits a running local web server page by page.

Uses only httpx (already in requirements) + stdlib html.parser.
Does not render JavaScript — works well for static HTML sites and
server-rendered (SSR) apps.  For React/Vue SPAs you may need to
increase wait_seconds or install Playwright separately.

Ported from LyraScan feature/localhost (Swift WKWebView crawler).
Python equivalent uses httpx + html.parser instead of WKWebView.
"""

from __future__ import annotations

import time
import urllib.parse
import uuid
import tempfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Optional

import httpx


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class CrawlConfig:
    """User-configurable limits for the localhost site crawler.

    Persisted in ConfigManager under key "crawl_config".
    """
    max_pages: int = 50
    max_depth: int = 3
    # Seconds to pause between requests — politeness / JS render wait.
    wait_seconds: float = 0.5
    # Per-page HTTP timeout.
    timeout: float = 10.0

    def to_dict(self) -> dict:
        return {
            "max_pages":    self.max_pages,
            "max_depth":    self.max_depth,
            "wait_seconds": self.wait_seconds,
            "timeout":      self.timeout,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CrawlConfig":
        cfg = cls()
        cfg.max_pages    = int(d.get("max_pages",    cfg.max_pages))
        cfg.max_depth    = int(d.get("max_depth",    cfg.max_depth))
        cfg.wait_seconds = float(d.get("wait_seconds", cfg.wait_seconds))
        cfg.timeout      = float(d.get("timeout",      cfg.timeout))
        return cfg


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class CrawledPage:
    url: str
    title: str
    html: str            # full HTML of the page as returned by the server
    depth: int           # link depth from the starting URL


# ── Crawler ───────────────────────────────────────────────────────────────────

class LocalhostCrawler:
    """Fetch a running local web app page by page.

    Thread-safe: cancel() can be called from any thread.

    Usage:
        crawler = LocalhostCrawler(config)
        crawler.on_progress = lambda visited, total, url: ...
        pages = crawler.crawl("http://localhost:3000")
        save_dir = save_crawl_to_temp(pages)
    """

    def __init__(self, config: CrawlConfig) -> None:
        self.config = config
        self._cancelled: bool = False
        self.on_progress: Optional[Callable[[int, int, str], None]] = None

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def crawl(self, start_url: str) -> list[CrawledPage]:
        """Crawl from start_url, returning a list of CrawledPage objects.

        Blocks until complete (or cancelled). Call from a background thread.
        """
        self._cancelled = False
        origin = _origin(start_url)

        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(start_url, 0)]
        results: list[CrawledPage] = []

        headers = {
            "User-Agent": "UIAnalyzer/1.0 (localhost crawler; accessibility analysis)",
            "Accept":     "text/html,application/xhtml+xml",
        }

        with httpx.Client(
            timeout=self.config.timeout,
            follow_redirects=True,
            headers=headers,
        ) as client:
            while queue and not self._cancelled and len(results) < self.config.max_pages:
                url, depth = queue.pop(0)
                key = _normalize_url(url)
                if key in visited:
                    continue
                visited.add(key)

                total_known = len(visited) + len(queue)
                if self.on_progress:
                    self.on_progress(len(results) + 1, total_known, url)

                page = _fetch_page(client, url, depth)
                if page is None:
                    continue
                results.append(page)

                if depth < self.config.max_depth:
                    links = _extract_links(page.html, url, origin)
                    for link in links:
                        norm = _normalize_url(link)
                        if norm not in visited:
                            queue.append((link, depth + 1))

                if self.config.wait_seconds > 0:
                    time.sleep(self.config.wait_seconds)

        return results


# ── Page fetching ─────────────────────────────────────────────────────────────

def _fetch_page(client: httpx.Client, url: str, depth: int) -> Optional[CrawledPage]:
    """Fetch one URL and return a CrawledPage, or None on failure."""
    try:
        resp = client.get(url)
    except Exception:
        return None

    if resp.status_code >= 400:
        return None

    ct = resp.headers.get("content-type", "")
    if "html" not in ct.lower():
        return None

    html = resp.text
    title = _extract_title(html)
    if not title:
        title = url.rstrip("/").rsplit("/", 1)[-1] or "index"

    return CrawledPage(url=url, title=title, html=html, depth=depth)


# ── HTML parsing helpers ──────────────────────────────────────────────────────

class _TitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_title = False
        self.title = ""
        self._done = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag.lower() == "title":
            self._in_title = True

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False
            self._done = True


def _extract_title(html: str) -> str:
    p = _TitleParser()
    # Only scan the head section — faster and avoids false positives
    p.feed(html[:8_000])
    return p.title.strip()


class _LinkParser(HTMLParser):
    def __init__(self, base_url: str, origin: str) -> None:
        super().__init__()
        self._base   = base_url
        self._origin = origin
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag.lower() != "a":
            return
        for name, val in attrs:
            if name == "href" and val:
                abs_url = urllib.parse.urljoin(self._base, val)
                # Same-origin only; no fragment-only links; no binary files
                if (abs_url.startswith(self._origin)
                        and "#" not in abs_url
                        and not _is_non_html_extension(abs_url)):
                    self.links.append(abs_url)


def _extract_links(html: str, base_url: str, origin: str) -> list[str]:
    p = _LinkParser(base_url, origin)
    try:
        p.feed(html)
    except Exception:
        pass
    return p.links


_NON_HTML_EXTS = {
    ".pdf", ".zip", ".tar", ".gz", ".rar",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
    ".mp4", ".mp3", ".wav", ".ogg",
    ".json", ".xml", ".csv", ".xlsx", ".docx",
    ".js", ".css", ".woff", ".woff2", ".ttf", ".eot",
}


def _is_non_html_extension(url: str) -> bool:
    path = urllib.parse.urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in _NON_HTML_EXTS)


# ── URL helpers ───────────────────────────────────────────────────────────────

def _origin(url: str) -> str:
    """Return scheme://host:port (no path) for same-origin filtering."""
    p = urllib.parse.urlparse(url)
    port = f":{p.port}" if p.port else ""
    return f"{p.scheme}://{p.hostname}{port}"


def _normalize_url(url: str) -> str:
    """Canonical form for deduplication: strip trailing slash and fragment."""
    p = urllib.parse.urlparse(url)
    path = p.path.rstrip("/") or "/"
    return f"{p.scheme}://{p.netloc}{path}"


# ── Temp directory persistence ────────────────────────────────────────────────

def save_crawl_to_temp(pages: list[CrawledPage]) -> Path:
    """Write each crawled page as an HTML file in a unique temp directory.

    Returns the directory path.  The caller (main_frame) passes it to
    scan_folder() to populate the sidebar with the crawled files.
    """
    crawl_dir = Path(tempfile.gettempdir()) / f"ui-analyzer-crawl-{uuid.uuid4().hex[:8]}"
    crawl_dir.mkdir(parents=True, exist_ok=True)

    used_names: set[str] = set()

    for page in pages:
        parsed = urllib.parse.urlparse(page.url)
        slug = parsed.path.strip("/").replace("/", "_") or "index"
        # Keep slug short and filesystem-safe
        slug = slug[:80]
        for ch in r'\:*?"<>|':
            slug = slug.replace(ch, "_")
        if not slug:
            slug = "page"

        name = f"{slug}.html"
        # Avoid collisions
        if name in used_names:
            i = 2
            while f"{slug}_{i}.html" in used_names:
                i += 1
            name = f"{slug}_{i}.html"
        used_names.add(name)

        (crawl_dir / name).write_text(page.html, encoding="utf-8")

    return crawl_dir
