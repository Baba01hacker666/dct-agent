"""
dct.tools.web
Lightweight web fetch and search tools for the coding agent.
No heavy dependencies — uses requests only.
"""

from __future__ import annotations
from html import unescape
import re
import urllib.parse
from dataclasses import dataclass

import requests
from requests.exceptions import RequestException

from dct.tools.url_validator import validate_url

FETCH_TIMEOUT = 10
MAX_REDIRECTS = 5
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
    err = validate_url(url)
    if err:
        return WebResult(ok=False, url=url, message=err)
    try:
        r = _get_validated_response(url)
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


def _get_validated_response(url: str) -> requests.Response:
    headers = {"User-Agent": UA}
    with requests.Session() as session:
        for _ in range(MAX_REDIRECTS + 1):
            r = session.get(
                url,
                timeout=FETCH_TIMEOUT,
                headers=headers,
                allow_redirects=False,
            )
            if not r.is_redirect:
                return r

            location = r.headers.get("location")
            if not location:
                return r

            url = urllib.parse.urljoin(r.url, location)
            err = validate_url(url)
            if err:
                raise RequestException(err)

        raise RequestException("Too many redirects")


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
    """Remove HTML tags and decode common entities using BeautifulSoup4, falling back to regex."""
    if not html:
        return ""

    # If there are no HTML tags, we can skip BeautifulSoup parsing entirely
    if "<" not in html or ">" not in html:
        text = html
    else:
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")

            # Decompose non-content / UI / layout elements
            for element in soup(
                [
                    "script",
                    "style",
                    "nav",
                    "footer",
                    "header",
                    "noscript",
                    "iframe",
                    "aside",
                    "form",
                ]
            ):
                element.decompose()

            text = soup.get_text(separator="\n")
        except Exception:
            # Fallback to regex-based extraction
            text = re.sub(
                r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.I
            )
            text = re.sub(
                r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.I
            )
            text = re.sub(r"<[^>]+>", " ", text)

    # Decode HTML entities
    text = unescape(text).replace("\xa0", " ")

    # Process lines: strip each line and discard excess blank lines
    cleaned_lines = []
    for line in text.splitlines():
        line_strip = line.strip()
        if line_strip:
            cleaned_lines.append(line_strip)
        elif cleaned_lines and cleaned_lines[-1] != "":
            cleaned_lines.append("")

    return "\n".join(cleaned_lines).strip()


def _extract_title(html: str) -> str:
    """Extract page title, preferably using BeautifulSoup."""
    if not html:
        return ""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        if soup.title:
            title_text = soup.title.get_text()
            if title_text:
                return unescape(title_text).strip()
    except Exception:
        pass
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.I)
    return _strip_html(m.group(1)).strip() if m else ""


def _clean_ddg_url(raw: str) -> str:
    """DDG wraps URLs — extract the real one."""
    parsed = urllib.parse.urlparse(raw)
    qs = urllib.parse.parse_qs(parsed.query)
    if "uddg" in qs:
        return urllib.parse.unquote(qs["uddg"][0])
    return raw
