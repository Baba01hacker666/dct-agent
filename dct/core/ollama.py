"""
dct.core.ollama
Low-level Ollama API client.
Handles streaming chat, generate, pull, delete, show, ps, version.
"""

from __future__ import annotations
import json
from typing import Iterator, TYPE_CHECKING, Any
from dct.core import http

if TYPE_CHECKING:
    from dct.core.registry import Server  # noqa: F401

CHAT_TIMEOUT = 180
PULL_TIMEOUT = 600
DEFAULT_TIMEOUT = 6


def _auth_headers(srv: "Server") -> dict:
    """Build auth + TLS headers for an Ollama server."""
    headers = {}
    if srv.api_key:
        headers["Authorization"] = f"Bearer {srv.api_key}"
    return headers


def _request_kwargs(srv: "Server", extra: dict | None = None) -> dict:
    """Merge auth headers and TLS verify into request kwargs."""
    kwargs: dict[str, Any] = {"headers": _auth_headers(srv)}
    if not srv.tls_verify:
        kwargs["verify"] = False
    if extra:
        kwargs.update(extra)
    return kwargs


def _post_stream(
    url: str, payload: dict, timeout: int, srv: "Server" | None = None
) -> Iterator[dict]:
    """POST with stream=True, yield parsed JSON lines."""
    kwargs = _request_kwargs(srv) if srv else {}
    kwargs["json"] = payload
    kwargs["timeout"] = timeout
    with http.client.stream("POST", url, **kwargs) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line:
                try:
                    yield json.loads(line)
                except Exception:
                    continue


# ── Chat ─────────────────────────────────────────────────────────────────────
def chat_stream(
    srv: "Server",
    model: str,
    messages: list[dict],
    images: list[str] | None = None,
    tools: list[dict] | None = None,
) -> Iterator[str | dict]:
    """
    Yield text chunks from /api/chat (streaming).
    Raises on HTTP error.
    """
    if tools:
        # Ollama does not fully support streaming tool_calls yet.
        # Fall back to a blocking call to reliably receive tool_calls.
        res = chat_once(srv, model, messages, images, tools)
        if isinstance(res, dict) and "tool_calls" in res:
            yield res
        elif isinstance(res, str) and res:
            yield res
        return

    url = f"{srv.base_url()}/api/chat"
    from dct.core.config import Config
    cfg = Config()
    payload: dict = {
        "model": model,
        "messages": list(messages),
        "stream": True,
        "options": {
            "temperature": cfg.get("temperature", 0.7),
            "top_p": cfg.get("top_p", 0.9),
            "num_predict": cfg.get("max_tokens", 4096),
        },
    }
    if tools:
        payload["tools"] = tools
    if images:
        # Attach images to the last user message (Ollama convention)
        for i in range(len(payload["messages"]) - 1, -1, -1):
            if payload["messages"][i]["role"] == "user":
                msg = dict(payload["messages"][i])
                msg["images"] = images
                payload["messages"][i] = msg
                break
    for chunk in _post_stream(url, payload, CHAT_TIMEOUT, srv):
        msg = chunk.get("message", {})
        if "tool_calls" in msg and msg["tool_calls"]:
            yield {"tool_calls": msg["tool_calls"]}
        content = msg.get("content", "")
        if content:
            yield content
        if chunk.get("done"):
            return


def chat_once(
    srv: "Server",
    model: str,
    messages: list[dict],
    images: list[str] | None = None,
    tools: list[dict] | None = None,
) -> str | dict:
    """Non-streaming chat — returns full reply as string."""
    url = f"{srv.base_url()}/api/chat"
    payload: dict = {
        "model": model,
        "messages": list(messages),
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
    if images:
        for i in range(len(payload["messages"]) - 1, -1, -1):
            if payload["messages"][i]["role"] == "user":
                msg = dict(payload["messages"][i])
                msg["images"] = images
                payload["messages"][i] = msg
                break
    r = http.client.post(
        url, **_request_kwargs(srv, {"json": payload, "timeout": CHAT_TIMEOUT})
    )
    r.raise_for_status()
    msg = r.json().get("message", {})
    if "tool_calls" in msg and msg["tool_calls"]:
        return {"tool_calls": msg["tool_calls"], "content": msg.get("content", "")}
    return msg.get("content", "")


# ── Models ───────────────────────────────────────────────────────────────────
def list_models(srv: "Server") -> list[dict]:
    r = http.client.get(
        f"{srv.base_url()}/api/tags",
        **_request_kwargs(srv, {"timeout": DEFAULT_TIMEOUT}),
    )
    r.raise_for_status()
    return r.json().get("models", [])


def show_model(srv: "Server", model: str) -> dict:
    r = http.client.post(
        f"{srv.base_url()}/api/show",
        **_request_kwargs(
            srv, {"json": {"name": model}, "timeout": DEFAULT_TIMEOUT}
        ),
    )
    r.raise_for_status()
    return r.json()


def delete_model(srv: "Server", model: str) -> bool:
    try:
        r = http.client.request(
            "DELETE",
            f"{srv.base_url()}/api/delete",
            **_request_kwargs(
                srv, {"json": {"name": model}, "timeout": DEFAULT_TIMEOUT}
            ),
        )
        return r.is_success
    except Exception as e:
        logger.error(f"Failed to delete model {model}: {e}")
        return False


def running_models(srv: "Server") -> list[dict]:
    r = http.client.get(
        f"{srv.base_url()}/api/ps",
        **_request_kwargs(srv, {"timeout": DEFAULT_TIMEOUT}),
    )
    r.raise_for_status()
    return r.json().get("models", [])


def get_version(srv: "Server") -> str:
    r = http.client.get(
        f"{srv.base_url()}/api/version",
        **_request_kwargs(srv, {"timeout": DEFAULT_TIMEOUT}),
    )
    r.raise_for_status()
    return r.json().get("version", "?")


# ── Pull ─────────────────────────────────────────────────────────────────────
def pull_stream(srv: "Server", model: str) -> Iterator[dict]:
    """Yield pull progress dictionaries."""
    url = f"{srv.base_url()}/api/pull"
    payload = {"name": model, "stream": True}
    yield from _post_stream(url, payload, PULL_TIMEOUT, srv)


def get_embeddings(srv: "Server", text: str, model: str = "nomic-embed-text") -> list[float]:
    kwargs = _request_kwargs(srv)
    kwargs["json"] = {"model": model, "prompt": text}
    kwargs["timeout"] = 15
    url = f"{srv.base_url()}/api/embeddings"
    r = http.client.post(url, **kwargs)
    r.raise_for_status()
    return r.json().get("embedding", [])
