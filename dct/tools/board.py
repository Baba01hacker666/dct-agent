"""
dct.tools.board
AI Agents Chat Board & Discussion Group.
Allows autonomous AI sub-agents and humans to post, read, discuss, debate,
and coordinate asynchronously across topics and channels.
"""

from __future__ import annotations
import os
import json
import time
import threading
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any
from dct.core.logging import get_logger

logger = get_logger("dct.tools.board")

BOARD_FILE = os.path.join(os.path.expanduser("~"), ".config", "dct", "board.json")


@dataclass
class BoardMessage:
    id: str
    sender: str
    channel: str
    content: str
    timestamp: float = field(default_factory=time.time)
    reply_to: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BoardMessage":
        return cls(
            id=str(data.get("id", "")),
            sender=str(data.get("sender", "agent")),
            channel=str(data.get("channel", "general")).lower().strip() or "general",
            content=str(data.get("content", "")),
            timestamp=float(data.get("timestamp", time.time())),
            reply_to=data.get("reply_to"),
            tags=list(data.get("tags", [])),
        )


class AgentBoard:
    """Thread-safe discussion board and message bus for AI agents and users."""

    def __init__(self, path: Optional[str] = None, storage_path: Optional[str] = None):
        self.path = storage_path or path or BOARD_FILE
        self.messages: List[BoardMessage] = []
        self._lock = threading.Lock()
        self._next_id = 1
        self.load()

    def load(self) -> None:
        with self._lock:
            if os.path.exists(self.path):
                try:
                    with open(self.path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.messages = [BoardMessage.from_dict(m) for m in data.get("messages", [])]
                    if self.messages:
                        max_num = 0
                        for m in self.messages:
                            if m.id.startswith("msg_") and m.id[4:].isdigit():
                                max_num = max(max_num, int(m.id[4:]))
                        self._next_id = max_num + 1
                except Exception:
                    logger.exception("Failed to load agent board from %s", self.path)
                    self.messages = []

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        try:
            with self._lock:
                snapshot = [m.to_dict() for m in self.messages]
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"messages": snapshot, "saved_at": time.time()}, f, indent=2)
        except Exception:
            logger.exception("Failed to save agent board to %s", self.path)

    def post(
        self,
        sender: str,
        content: str,
        channel: str = "general",
        reply_to: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> BoardMessage:
        """Post a new message to a channel."""
        clean_channel = (channel or "general").strip().lower() or "general"
        clean_sender = (sender or "agent").strip() or "agent"
        clean_content = (content or "").strip()

        with self._lock:
            msg_id = f"msg_{self._next_id}"
            self._next_id += 1

            msg = BoardMessage(
                id=msg_id,
                sender=clean_sender,
                channel=clean_channel,
                content=clean_content,
                timestamp=time.time(),
                reply_to=reply_to,
                tags=tags or [],
            )
            # Retain up to 1000 messages total to prevent unbounded growth
            if len(self.messages) >= 1000:
                self.messages.pop(0)
            self.messages.append(msg)

        self.save()
        return msg

    def read(
        self,
        channel: str = "general",
        limit: int = 10,
        since_id: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Read recent messages from a channel with optional filtering."""
        clean_channel = (channel or "general").strip().lower()

        with self._lock:
            msgs = list(self.messages)

        # Channel filter (support "*" to read across all channels)
        if clean_channel != "*":
            filtered = [m for m in msgs if m.channel == clean_channel]
        else:
            filtered = msgs

        # Since ID filter
        if since_id:
            idx = -1
            for i, m in enumerate(filtered):
                if m.id == since_id:
                    idx = i
                    break
            if idx != -1:
                filtered = filtered[idx + 1:]

        # Search filter
        if search:
            q = search.lower()
            filtered = [m for m in filtered if q in m.content.lower() or q in m.sender.lower()]

        # Limit to most recent
        res = filtered[-limit:] if limit > 0 else filtered
        return [m.to_dict() for m in res]

    def list_channels(self) -> List[Dict[str, Any]]:
        """List active discussion channels with message count and last active time."""
        with self._lock:
            msgs = list(self.messages)

        channel_stats: Dict[str, Dict[str, Any]] = {}
        for m in msgs:
            ch = m.channel
            if ch not in channel_stats:
                channel_stats[ch] = {
                    "channel": ch,
                    "message_count": 0,
                    "last_activity": 0.0,
                    "latest_sender": "",
                    "latest_preview": "",
                }
            channel_stats[ch]["message_count"] += 1
            if m.timestamp > channel_stats[ch]["last_activity"]:
                channel_stats[ch]["last_activity"] = m.timestamp
                channel_stats[ch]["latest_sender"] = m.sender
                channel_stats[ch]["latest_preview"] = m.content[:60]

        # Always ensure 'general' exists
        if "general" not in channel_stats:
            channel_stats["general"] = {
                "channel": "general",
                "message_count": 0,
                "last_activity": time.time(),
                "latest_sender": "system",
                "latest_preview": "Default discussion channel",
            }

        return sorted(
            channel_stats.values(),
            key=lambda x: x["last_activity"],
            reverse=True,
        )

    def clear(self, channel: Optional[str] = None) -> None:
        """Clear messages in a specific channel, or entire board if None."""
        with self._lock:
            if channel:
                clean_channel = channel.strip().lower()
                self.messages = [m for m in self.messages if m.channel != clean_channel]
            else:
                self.messages = []
                self._next_id = 1
        self.save()

    def format_for_prompt(self, channel: str = "general", limit: int = 8) -> str:
        """Format recent messages into a clean block suitable for agent reasoning."""
        msgs = self.read(channel=channel, limit=limit)
        if not msgs:
            return f"(No messages on discussion board in #{channel})"

        lines = [f"[AGENT DISCUSSION BOARD #{channel}]"]
        for m in msgs:
            t_str = time.strftime("%H:%M:%S", time.localtime(m["timestamp"]))
            reply_info = f" (reply to {m['reply_to']})" if m.get("reply_to") else ""
            lines.append(f"- [{m['id']}] [{t_str}] @{m['sender']}{reply_info}: {m['content']}")
        return "\n".join(lines)


_global_board: Optional[AgentBoard] = None
_board_lock = threading.Lock()


def get_board() -> AgentBoard:
    """Return singleton AgentBoard instance."""
    global _global_board
    if _global_board is None:
        with _board_lock:
            if _global_board is None:
                _global_board = AgentBoard()
    return _global_board
