"""
dct.core.client
Unified wrapper around Ollama and OpenRouter API clients.
"""

from __future__ import annotations
from typing import Iterator, TYPE_CHECKING

from dct.core import ollama
from dct.core import openrouter

if TYPE_CHECKING:
    from dct.core.registry import Server


def chat_stream(srv: "Server", model: str, messages: list[dict]) -> Iterator[str]:
    if srv.provider == "openrouter":
        yield from openrouter.chat_stream(srv, model, messages)
    else:
        yield from ollama.chat_stream(srv, model, messages)


def chat_once(srv: "Server", model: str, messages: list[dict]) -> str:
    if srv.provider == "openrouter":
        return openrouter.chat_once(srv, model, messages)
    return ollama.chat_once(srv, model, messages)


def list_models(srv: "Server") -> list[dict]:
    if srv.provider == "openrouter":
        return openrouter.list_models(srv)
    return ollama.list_models(srv)


def show_model(srv: "Server", model: str) -> dict:
    if srv.provider == "openrouter":
        return openrouter.show_model(srv, model)
    return ollama.show_model(srv, model)


def delete_model(srv: "Server", model: str) -> bool:
    if srv.provider == "openrouter":
        return openrouter.delete_model(srv, model)
    return ollama.delete_model(srv, model)


def running_models(srv: "Server") -> list[dict]:
    if srv.provider == "openrouter":
        return openrouter.running_models(srv)
    return ollama.running_models(srv)


def get_version(srv: "Server") -> str:
    if srv.provider == "openrouter":
        return openrouter.get_version(srv)
    return ollama.get_version(srv)


def pull_stream(srv: "Server", model: str) -> Iterator[dict]:
    if srv.provider == "openrouter":
        yield from openrouter.pull_stream(srv, model)
    else:
        yield from ollama.pull_stream(srv, model)
