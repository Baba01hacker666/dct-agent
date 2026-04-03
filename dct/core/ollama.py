"""
dct.core.ollama
Low-level Ollama API client.
Handles streaming chat, generate, pull, delete, show, ps, version.
"""

from __future__ import annotations
import json
from typing import Iterator, TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from dct.core.registry import Server

CHAT_TIMEOUT = 180
PULL_TIMEOUT = 600
DEFAULT_TIMEOUT = 6


def _post_stream(url: str, payload: dict, timeout: int) -> Iterator[dict]:
    """POST with stream=True, yield parsed JSON lines."""
    with requests.post(url, json=payload, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line:
                try:
                    yield json.loads(line)
                except Exception:
                    continue


# ── Chat ─────────────────────────────────────────────────────────────────────
def chat_stream(srv: "Server", model: str, messages: list[dict]) -> Iterator[str]:
    """
    Yield text chunks from /api/chat (streaming).
    Raises on HTTP error.
    """
    url = f"{srv.base_url()}/api/chat"
    payload = {"model": model, "messages": messages, "stream": True}
    for chunk in _post_stream(url, payload, CHAT_TIMEOUT):
        content = chunk.get("message", {}).get("content", "")
        if content:
            yield content
        if chunk.get("done"):
            return


def chat_once(srv: "Server", model: str, messages: list[dict]) -> str:
    """Non-streaming chat — returns full reply as string."""
    url = f"{srv.base_url()}/api/chat"
    payload = {"model": model, "messages": messages, "stream": False}
    r = requests.post(url, json=payload, timeout=CHAT_TIMEOUT)
    r.raise_for_status()
    return r.json().get("message", {}).get("content", "")


# ── Models ───────────────────────────────────────────────────────────────────
def list_models(srv: "Server") -> list[dict]:
    r = requests.get(f"{srv.base_url()}/api/tags", timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    return r.json().get("models", [])


def show_model(srv: "Server", model: str) -> dict:
    r = requests.post(
        f"{srv.base_url()}/api/show",
        json={"name": model},
        timeout=DEFAULT_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def delete_model(srv: "Server", model: str) -> bool:
    r = requests.delete(
        f"{srv.base_url()}/api/delete",
        json={"name": model},
        timeout=DEFAULT_TIMEOUT,
    )
    return r.ok


def running_models(srv: "Server") -> list[dict]:
    r = requests.get(f"{srv.base_url()}/api/ps", timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    return r.json().get("models", [])


def get_version(srv: "Server") -> str:
    r = requests.get(f"{srv.base_url()}/api/version", timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    return r.json().get("version", "?")


# ── Pull ─────────────────────────────────────────────────────────────────────
def pull_stream(srv: "Server", model: str) -> Iterator[dict]:
    """
    Yield progress dicts from /api/pull:
    {"status": str, "total": int, "completed": int, "done": bool}
    """
    url = f"{srv.base_url()}/api/pull"
    payload = {"name": model, "stream": True}
    for chunk in _post_stream(url, payload, PULL_TIMEOUT):
        yield chunk
