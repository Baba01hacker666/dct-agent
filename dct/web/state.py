"""
dct.web.state
Core shared state for the web server: registry, session and routing.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from aiohttp import web

from dct.core.registry import ServerRegistry, Server
from dct.agent.session import Session
from dct.agent.codeagent import CodeAgent
from dct.tools.tasks import get_tracker


class WebState:
    """Holds mutable server-wide state shared by all handler mixins."""

    def __init__(self, registry: Optional[ServerRegistry] = None):
        self.registry = registry or ServerRegistry()
        self.session = Session()
        self.active_server: Optional[Server] = None
        self.active_model: str = ""
        self.agent_mode: bool = True
        self._ask_user_future: Optional[asyncio.Future] = None
        self._current_agent: Optional[CodeAgent] = None
        self._init_server()

    def _init_server(self):
        route = self.registry.route()
        if route:
            self.active_server, self.active_model = route
        elif self.registry.servers:
            self.active_server = self.registry.servers[0]
            self.active_model = (
                self.active_server.models[0]
                if self.active_server.models
                else ""
            )

    def get_status_dict(self) -> dict[str, Any]:
        tasks = [
            {
                "id": t.id,
                "subject": t.subject,
                "description": t.description,
                "status": t.status,
                "active_form": t.active_form,
            }
            for t in get_tracker().get_all()
        ]
        return {
            "active_server": (
                {
                    "alias": self.active_server.alias,
                    "host": self.active_server.host,
                    "port": self.active_server.port,
                    "status": self.active_server.status,
                    "latency_ms": self.active_server.latency_ms,
                    "models": self.active_server.models,
                }
                if self.active_server
                else None
            ),
            "active_model": self.active_model,
            "agent_mode": self.agent_mode,
            "session_mode": self.session.mode,
            "user_turns": self.session.user_turns,
            "token_estimate": self.session.token_estimate,
            "servers_count": len(self.registry.servers),
            "online_servers_count": len(self.registry.online()),
            "tasks": tasks,
        }

    @staticmethod
    def invalid_json() -> web.Response:
        return web.json_response(
            {"ok": False, "error": "Invalid JSON"}, status=400
        )
