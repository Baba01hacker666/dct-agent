"""
dct.agent.session
Conversation session: message history, system prompt, metadata.
"""

from __future__ import annotations
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Session:
    system_prompt: Optional[str] = None
    messages: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    name: str = ""
    mode: str = "execute"  # 'execute' or 'plan'

    @property
    def agent_plan_file(self) -> str:
        import os

        return os.path.abspath(
            os.path.join(os.getcwd(), ".dct", "plans", "current_plan.md")
        )

    # ── Messages ─────────────────────────────────────────────────────────────
    def add(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})

    def clear(self, keep_system: bool = True):
        self.messages = []
        if keep_system and self.system_prompt:
            self.messages.append({"role": "system", "content": self.system_prompt})

    def set_system(self, prompt: str):
        self.system_prompt = prompt
        # Replace or prepend system message
        self.messages = [m for m in self.messages if m["role"] != "system"]
        if prompt:
            self.messages.insert(0, {"role": "system", "content": prompt})

    def as_messages(self) -> list[dict]:
        """Full message list ready to send to Ollama."""
        return list(self.messages)

    def rewind(self) -> bool:
        """Remove the last user message and all subsequent messages."""
        for i in range(len(self.messages) - 1, -1, -1):
            if self.messages[i].get("role") == "user":
                self.messages = self.messages[:i]
                return True
        return False

    def transcript(self, include_system: bool = False) -> str:
        """Render chat history as readable plain text."""
        lines: list[str] = []
        for msg in self.messages:
            role = msg.get("role", "unknown")
            if role == "system" and not include_system:
                continue
            content = msg.get("content", "")
            lines.append(f"{role.upper()}:")
            lines.append(content)
            lines.append("")
        return "\n".join(lines).strip()

    # ── Stats ───────────────────────────────────────────────────────────────
    @property
    def user_turns(self) -> int:
        return sum(1 for m in self.messages if m["role"] == "user")

    @property
    def token_estimate(self) -> int:
        total = sum(len(m["content"]) for m in self.messages)
        return total // 4  # rough 4-chars-per-token estimate

    # ── Persistence ─────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "system_prompt": self.system_prompt,
            "messages": self.messages,
            "created_at": self.created_at,
            "saved_at": time.time(),
            "mode": self.mode,
        }

    def save(self, path: str):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "Session":
        with open(path) as f:
            d = json.load(f)
        s = cls(
            system_prompt=d.get("system_prompt"),
            messages=d.get("messages", []),
            created_at=d.get("created_at", time.time()),
            name=d.get("name", ""),
            mode=d.get("mode", "execute"),
        )
        return s


_cfg = None  # Module-level config cache to avoid repeated disk reads


def _get_cfg():
    """Return a cached Config instance (loaded once per process)."""
    global _cfg
    if _cfg is None:
        try:
            from dct.core.config import Config

            _cfg = Config()
        except Exception:
            pass
    return _cfg


def write_trace_entry(session: "Session", entry_type: str, data: dict):
    """Write a structured trace entry to session JSONL log if enabled."""
    try:
        cfg = _get_cfg()
        if cfg is None or not cfg.get("enable_tracing", False):
            return
    except Exception:
        return

    import os
    import json

    log_dir = os.path.expanduser("~/.config/dct/transcripts")
    os.makedirs(log_dir, exist_ok=True)

    session_id = session.name or f"session_{int(session.created_at)}"
    # Sanitize filename
    session_id = "".join(c for c in session_id if c.isalnum() or c in ("-", "_"))
    log_file = os.path.join(log_dir, f"{session_id}.jsonl")

    trace_data = {
        "timestamp": time.time(),
        "type": entry_type,
        "session_name": session.name,
        **data,
    }

    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(trace_data) + "\n")
    except Exception:
        pass
