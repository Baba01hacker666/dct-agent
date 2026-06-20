"""
dct.core.config
User configuration persisted to ~/.config/dct/config.json
"""

from __future__ import annotations
import os
import json
import threading

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".config", "dct", "config.json")

DEFAULTS = {
    "default_server": "",
    "default_model": "",
    "agent_enabled": True,
    "max_agent_turns": 12,
    "history_limit": 100,
    "no_probe_on_start": False,
    "auto_probe_interval": 60,
    "custom_skills": {},
    "squads": {},
    "mcp_servers": {},
    "enable_tracing": False,
    "enable_persona": True,
}


class Config:
    """Thread-safe user config backed by JSON."""

    def __init__(self, path: str = CONFIG_FILE):
        self._path = path
        self._lock = threading.Lock()
        self._data: dict = dict(DEFAULTS)
        self._load()

    def _load(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        try:
            with open(self._path) as f:
                loaded = json.load(f)
            with self._lock:
                for k, v in DEFAULTS.items():
                    if k in loaded:
                        self._data[k] = loaded[k]
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with self._lock:
            data = dict(self._data)
        with open(self._path, "w") as f:
            json.dump(data, f, indent=2)

    def get(self, key: str, default=None):
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        with self._lock:
            self._data[key] = value

    def __getitem__(self, key: str):
        return self.get(key)

    def __setitem__(self, key: str, value):
        self.set(key, value)
