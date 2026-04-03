"""
dct.core.openrouter
Low-level OpenRouter API client.
Handles streaming chat, generate, list_models.
"""

from __future__ import annotations
import json
from typing import Iterator, TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from dct.core.registry import Server

CHAT_TIMEOUT = 180
DEFAULT_TIMEOUT = 6


def _extract_stream_text(delta: dict) -> str:
    """
    Normalize streaming delta content from providers that may return:
    - plain string content
    - list parts (e.g. [{type: "text", text: "..."}])
    """
    content = delta.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out: list[str] = []
        for part in content:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict):
                txt = part.get("text") or part.get("content")
                if isinstance(txt, str):
                    out.append(txt)
        return "".join(out)
    return ""


def _post_stream(
    url: str, headers: dict, payload: dict, timeout: int
) -> Iterator[dict]:
    """POST with stream=True, yield parsed JSON chunks (SSE format)."""
    with requests.post(
        url, headers=headers, json=payload, stream=True, timeout=timeout
    ) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line:
                line_str = line.decode("utf-8")
                if line_str.startswith("data: "):
                    data_str = line_str[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        yield json.loads(data_str)
                    except json.JSONDecodeError:
                        continue


# ── Chat ─────────────────────────────────────────────────────────────────────
def chat_stream(srv: "Server", model: str, messages: list[dict]) -> Iterator[str]:
    """
    Yield text chunks from OpenRouter /chat/completions (streaming).
    Raises on HTTP error.
    """
    url = f"{srv.base_url()}/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {srv.api_key}",
        "HTTP-Referer": "https://github.com/doraemon-cyber-team/dct",  # Optional, but recommended
        "X-Title": "DCT Agent",  # Optional
    }
    payload = {"model": model, "messages": messages, "stream": True}

    for chunk in _post_stream(url, headers, payload, CHAT_TIMEOUT):
        if "choices" in chunk and len(chunk["choices"]) > 0:
            delta = chunk["choices"][0].get("delta", {})
            content = _extract_stream_text(delta)
            if content:
                yield content


def chat_once(srv: "Server", model: str, messages: list[dict]) -> str:
    """Non-streaming chat — returns full reply as string."""
    url = f"{srv.base_url()}/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {srv.api_key}",
        "HTTP-Referer": "https://github.com/doraemon-cyber-team/dct",
        "X-Title": "DCT Agent",
    }
    payload = {"model": model, "messages": messages, "stream": False}

    r = requests.post(url, headers=headers, json=payload, timeout=CHAT_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if "choices" in data and len(data["choices"]) > 0:
        return data["choices"][0].get("message", {}).get("content", "")
    return ""


# ── Models ───────────────────────────────────────────────────────────────────
def list_models(srv: "Server") -> list[dict]:
    url = f"{srv.base_url()}/api/v1/models"
    r = requests.get(url, timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    # OpenRouter returns { "data": [ { "id": "model/name", ... } ] }
    # Let's map it to Ollama's format { "name": "..." }
    data = r.json()
    models = data.get("data", [])
    return [{"name": m.get("id")} for m in models]


def show_model(srv: "Server", model: str) -> dict:
    # OpenRouter doesn't have a direct equivalent to `ollama show`
    return {"name": model, "details": "OpenRouter model"}


def delete_model(srv: "Server", model: str) -> bool:
    # Cannot delete models from OpenRouter
    return False


def running_models(srv: "Server") -> list[dict]:
    # OpenRouter manages instances
    return []


def get_version(srv: "Server") -> str:
    # OpenRouter doesn't have a simple version endpoint
    return "OpenRouter API v1"


# ── Pull ─────────────────────────────────────────────────────────────────────
def pull_stream(srv: "Server", model: str) -> Iterator[dict]:
    """
    OpenRouter does not support pulling models.
    Yield a single success status.
    """
    yield {"status": "success"}
