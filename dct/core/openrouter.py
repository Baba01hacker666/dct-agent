"""
dct.core.openrouter
Low-level OpenRouter API client.
Handles streaming chat, generate, list_models.
"""

from __future__ import annotations
import json
from typing import Iterator, TYPE_CHECKING
from dct.core import http

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
    with http.client.post(
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
def chat_stream(
    srv: "Server", model: str, messages: list[dict], tools: list[dict] | None = None
) -> Iterator[str | dict]:
    """
    Yield text chunks from OpenAI-compatible /chat/completions (streaming).
    Raises on HTTP error.
    """
    url = f"{srv.base_url()}/chat/completions"
    headers = {"Authorization": f"Bearer {srv.api_key}"}
    if srv.provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/doraemon-cyber-team/dct"
        headers["X-Title"] = "DCT Agent"
    from dct.core.config import Config
    cfg = Config()
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": cfg.get("temperature", 0.7),
        "top_p": cfg.get("top_p", 0.9),
        "max_tokens": cfg.get("max_tokens", 4096),
    }
    if tools:
        payload["tools"] = tools

    tool_calls_buffer = {}

    for chunk in _post_stream(url, headers, payload, CHAT_TIMEOUT):
        if "choices" in chunk and len(chunk["choices"]) > 0:
            delta = chunk["choices"][0].get("delta", {})

            if "tool_calls" in delta:
                for tc in delta["tool_calls"]:
                    idx = tc.get("index", 0)
                    if idx not in tool_calls_buffer:
                        tool_calls_buffer[idx] = {
                            "id": tc.get("id"),
                            "function": {
                                "name": tc.get("function", {}).get("name", ""),
                                "arguments": tc.get("function", {}).get("arguments", "")
                            }
                        }
                    else:
                        if tc.get("function", {}).get("arguments"):
                            tool_calls_buffer[idx]["function"]["arguments"] += tc["function"]["arguments"]

            content = _extract_stream_text(delta)
            if content:
                yield content

    if tool_calls_buffer:
        yield {"tool_calls": list(tool_calls_buffer.values())}


def chat_once(srv: "Server", model: str, messages: list[dict], tools: list[dict] | None = None) -> str | dict:
    """Non-streaming chat — returns full reply as string."""
    url = f"{srv.base_url()}/chat/completions"
    headers = {"Authorization": f"Bearer {srv.api_key}"}
    if srv.provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/doraemon-cyber-team/dct"
        headers["X-Title"] = "DCT Agent"
    payload = {"model": model, "messages": messages, "stream": False}
    if tools:
        payload["tools"] = tools

    r = http.client.post(
        url, headers=headers, json=payload, timeout=CHAT_TIMEOUT
    )
    r.raise_for_status()
    data = r.json()
    if "choices" in data and len(data["choices"]) > 0:
        msg = data["choices"][0].get("message", {})
        if "tool_calls" in msg and msg["tool_calls"]:
            return {"tool_calls": msg["tool_calls"], "content": msg.get("content", "")}
        return msg.get("content", "")
    return ""


# ── Models ───────────────────────────────────────────────────────────────────
def list_models(srv: "Server") -> list[dict]:
    url = f"{srv.base_url()}/models"
    headers = {"Authorization": f"Bearer {srv.api_key}"} if srv.api_key else {}
    r = http.client.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
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


def get_embeddings(srv: "Server", text: str, model: str = "text-embedding-3-small") -> list[float]:
    url = f"{srv.base_url()}/embeddings"
    headers = {"Authorization": f"Bearer {srv.api_key}"}
    if srv.provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/doraemon-cyber-team/dct"
        headers["X-Title"] = "DCT Agent"
    payload = {"model": model, "input": text}
    r = http.client.post(url, headers=headers, json=payload, timeout=15)
    r.raise_for_status()
    data = r.json().get("data", [])
    if data:
        return data[0].get("embedding", [])
    return []
