"""
dct.tools.web
Lightweight web fetch and search tools for the coding agent.
No heavy dependencies — uses requests only.
"""

from __future__ import annotations
import re
import urllib.parse
from dataclasses import dataclass

import requests
from requests.exceptions import RequestException

FETCH_TIMEOUT = 10
UA = "Mozilla/5.0 (compatible; DCT-Agent/3.0)"


@dataclass
class WebResult:
    ok: bool
    url: str
    content: str = ""
    title: str = ""
    message: str = ""
    status: int = 0


def fetch_url(url: str, max_chars: int = 40_000) -> WebResult:
    """
    Fetch a URL and return cleaned text content.
    Strips HTML tags for readability.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        r = requests.get(
            url,
            timeout=FETCH_TIMEOUT,
            headers={"User-Agent": UA},
            allow_redirects=True,
        )
        r.raise_for_status()
        content_type = r.headers.get("content-type", "")
        if "text/html" in content_type:
            text = _strip_html(r.text)
        else:
            text = r.text
        title = _extract_title(r.text)
        return WebResult(
            ok=True,
            url=r.url,
            content=text[:max_chars],
            title=title,
            status=r.status_code,
        )
    except RequestException as e:
        return WebResult(ok=False, url=url, message=str(e))


def search_ddg(query: str, max_results: int = 8) -> list[dict]:
    """
    DuckDuckGo lite search — returns list of {title, url, snippet}.
    Uses the HTML endpoint, no API key needed.
    """
    results = []
    try:
        params = {"q": query, "kl": "wt-wt", "kp": "-2"}
        r = requests.get(
            "https://html.duckduckgo.com/html/",
            params=params,
            headers={"User-Agent": UA},
            timeout=FETCH_TIMEOUT,
        )
        r.raise_for_status()
        # Parse result blocks
        blocks = re.findall(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
            r'.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
            r.text,
            re.DOTALL,
        )
        for url, title, snippet in blocks[:max_results]:
            results.append(
                {
                    "url": _clean_ddg_url(url),
                    "title": _strip_html(title).strip(),
                    "snippet": _strip_html(snippet).strip(),
                }
            )
    except Exception:
        pass
    return results


def _strip_html(html: str) -> str:
    """Remove HTML tags and decode common entities."""
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.I)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#39;", "'", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s{3,}", "\n\n", text)
    return text.strip()


def _extract_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.I)
    return _strip_html(m.group(1)).strip() if m else ""


def _clean_ddg_url(raw: str) -> str:
    """DDG wraps URLs — extract the real one."""
    parsed = urllib.parse.urlparse(raw)
    qs = urllib.parse.parse_qs(parsed.query)
    if "uddg" in qs:
        return urllib.parse.unquote(qs["uddg"][0])
    return raw
