"""
dct.core.registry
Persistent server registry. Manages the list of Ollama servers,
their aliases, status, cached model lists, and metadata.
"""

from __future__ import annotations
import os
import json
import threading
from typing import Optional

REGISTRY_FILE = os.path.join(
    os.path.expanduser("~"), ".config", "dct", "servers.json"
)


class Server:
    """Represents one Ollama server entry."""

    __slots__ = (
        "alias",
        "host",
        "port",
        "note",
        "models",
        "status",
        "version",
        "latency_ms",
    )

    def __init__(
        self,
        alias: str,
        host: str,
        port: int,
        note: str = "",
        models: list | None = None,
        status: str = "unknown",
        version: str = "",
        latency_ms: int = -1,
    ):
        self.alias = alias
        self.host = host
        self.port = port
        self.note = note
        self.models = models or []
        self.status = status  # "online" | "offline" | "unknown"
        self.version = version
        self.latency_ms = latency_ms

    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def to_dict(self) -> dict:
        return {
            "alias": self.alias,
            "host": self.host,
            "port": self.port,
            "note": self.note,
            "models": self.models,
            "status": self.status,
            "version": self.version,
            "latency_ms": self.latency_ms,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Server":
        return cls(
            alias=d.get("alias", f"{d['host']}:{d['port']}"),
            host=d["host"],
            port=d["port"],
            note=d.get("note", ""),
            models=d.get("models", []),
            status=d.get("status", "unknown"),
            version=d.get("version", ""),
            latency_ms=d.get("latency_ms", -1),
        )

    def has_model(self, model: str) -> bool:
        return any(
            m == model or m.startswith(model + ":") for m in self.models
        )

    def best_model(self, preferred: str = "") -> str:
        if preferred and self.has_model(preferred):
            return preferred
        return self.models[0] if self.models else preferred or "llama3.2"


class ServerRegistry:
    """
    Thread-safe server registry backed by ~/.config/dct/servers.json
    """

    def __init__(self, path: str = REGISTRY_FILE):
        self._path = path
        self._lock = threading.Lock()
        self.servers: list[Server] = []
        self._load()

    # ── Persistence ──────────────────────────────────────────────────────────
    def _load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path) as f:
                    data = json.load(f)
                with self._lock:
                    self.servers = [
                        Server.from_dict(s) for s in data.get("servers", [])
                    ]
            except Exception:
                self.servers = []

    def save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        try:
            with self._lock:
                data = {"servers": [s.to_dict() for s in self.servers]}
            with open(self._path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    # ── CRUD ─────────────────────────────────────────────────────────────────
    def add(
        self, host: str, port: int, alias: str = "", note: str = ""
    ) -> Server:
        alias = alias or f"{host}:{port}"
        # Deduplicate by host+port
        for s in self.servers:
            if s.host == host and s.port == port:
                s.alias = alias
                s.note = note or s.note
                self.save()
                return s
        srv = Server(alias=alias, host=host, port=port, note=note)
        with self._lock:
            self.servers.append(srv)
        self.save()
        return srv

    def remove(self, srv: Server) -> bool:
        with self._lock:
            if srv in self.servers:
                self.servers.remove(srv)
                self.save()
                return True
        return False

    def resolve(self, token: str) -> Optional[Server]:
        """Find by alias, index (1-based), or host:port."""
        t = token.strip()
        if t.isdigit():
            idx = int(t) - 1
            if 0 <= idx < len(self.servers):
                return self.servers[idx]
        for s in self.servers:
            if s.alias == t:
                return s
        if ":" in t:
            parts = t.rsplit(":", 1)
            if len(parts) == 2 and parts[1].isdigit():
                h, p = parts[0], int(parts[1])
                for s in self.servers:
                    if s.host == h and s.port == p:
                        return s
        return None

    # ── Queries ──────────────────────────────────────────────────────────────
    def online(self) -> list[Server]:
        return [s for s in self.servers if s.status == "online"]

    def first_online(self) -> Optional[Server]:
        for s in self.servers:
            if s.status == "online":
                return s
        return None

    def all_model_pairs(self) -> list[tuple[Server, str]]:
        """All (server, model) pairs across online servers."""
        return [(s, m) for s in self.servers for m in s.models]

    def best_server_for_model(self, model: str) -> Optional[Server]:
        """Find the fastest online server that has a given model."""
        candidates = [s for s in self.online() if s.has_model(model)]
        if not candidates:
            return None
        # Sort by latency (lower = better), unknowns last
        candidates.sort(
            key=lambda s: s.latency_ms if s.latency_ms >= 0 else 99999
        )
        return candidates[0]

    def route(
        self, model: str = "", preferred_alias: str = ""
    ) -> Optional[tuple[Server, str]]:
        """
        Model router: returns (Server, resolved_model_name).
        Priority:
          1. preferred_alias + model if both specified and online
          2. any online server with the model (fastest)
          3. any online server (use its best model)
        """
        # 1. Preferred alias + model
        if preferred_alias:
            s = self.resolve(preferred_alias)
            if s and s.status == "online":
                return (s, s.best_model(model))

        # 2. Any server with the requested model
        if model:
            s = self.best_server_for_model(model)
            if s:
                return (s, model)

        # 3. Any online server
        s = self.first_online()
        if s:
            return (s, s.best_model(model))

        return None
