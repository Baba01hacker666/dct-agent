"""
dct.skills.web
Extended web research skill for deeper data extraction.
"""
from __future__ import annotations
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass

@dataclass
class WebResult:
    ok: bool
    url: str
    content: str
    message: str = ""

def fetch_and_extract(url: str, selector: str = None) -> WebResult:
    """Fetch URL and extract main content or specific CSS selector."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        if selector:
            elements = soup.select(selector)
            if not elements:
                return WebResult(False, url, "", f"Selector '{selector}' not found")
            text = "\n\n".join(el.get_text(strip=True, separator='\n') for el in elements)
        else:
            # Extract main readable text
            for script in soup(["script", "style", "nav", "footer", "iframe"]):
                script.decompose()
            text = soup.get_text(separator='\n', strip=True)
            
        # truncate if huge
        if len(text) > 100000:
            text = text[:100000] + "\n...[TRUNCATED]..."
            
        return WebResult(True, url, text)
    except Exception as e:
        return WebResult(False, url, "", str(e))
