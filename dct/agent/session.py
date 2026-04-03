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
