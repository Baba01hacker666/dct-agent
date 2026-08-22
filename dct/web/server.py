"""
dct.web.server
Composed aiohttp application for the DCT Agent web UI.

The handler surface is split across mixins:
  - dct.web.state               shared mutable state
  - dct.web.handlers_core       servers / tasks / sessions
  - dct.web.handlers_integrations  board + telegram/discord bridges
  - dct.web.handlers_tools      subagents / git / mcp / skills
  - dct.web.chat_stream         SSE chat endpoint

Static UI assets live in dct/web/static/.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from aiohttp import web

from dct.core.registry import ServerRegistry
from dct.web.auth import auth_middleware
from dct.web.handlers_core import CoreHandlersMixin
from dct.web.handlers_integrations import IntegrationsHandlersMixin
from dct.web.handlers_tools import ToolsHandlersMixin
from dct.web.chat_stream import ChatStreamMixin

STATIC_DIR = Path(__file__).parent / "static"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080


class AgentWebServer(
    CoreHandlersMixin,
    IntegrationsHandlersMixin,
    ToolsHandlersMixin,
    ChatStreamMixin,
):
    """Full web server: state + all handler groups."""


# (method, path, handler-name) — resolved against AgentWebServer at startup.
ROUTES = [
    ("GET", "/api/status", "handle_status"),
    ("GET", "/api/servers", "handle_get_servers"),
    ("POST", "/api/servers/add", "handle_add_server"),
    ("POST", "/api/servers/probe", "handle_probe"),
    ("POST", "/api/select", "handle_select"),
    ("POST", "/api/toggle_agent", "handle_toggle_agent"),
    ("POST", "/api/toggle_plan", "handle_toggle_plan"),
    ("GET", "/api/tasks", "handle_get_tasks"),
    ("POST", "/api/tasks/create", "handle_create_task"),
    ("POST", "/api/tasks/update", "handle_update_task"),
    ("GET", "/api/history", "handle_get_history"),
    ("GET", "/api/sessions", "handle_get_sessions"),
    ("POST", "/api/sessions/switch", "handle_switch_session"),
    ("POST", "/api/clear", "handle_clear"),
    ("POST", "/api/ask_user_response", "handle_ask_user_response"),
    ("GET", "/api/skills", "handle_get_skills"),
    ("POST", "/api/skills/load", "handle_load_skill"),
    ("GET", "/api/board", "handle_get_board_messages"),
    ("POST", "/api/board/post", "handle_post_board_message"),
    ("GET", "/api/board/channels", "handle_get_board_channels"),
    ("POST", "/api/board/clear", "handle_clear_board"),
    ("GET", "/api/telegram", "handle_get_telegram"),
    ("POST", "/api/telegram/start", "handle_start_telegram"),
    ("POST", "/api/telegram/stop", "handle_stop_telegram"),
    ("POST", "/api/telegram/config", "handle_config_telegram"),
    ("GET", "/api/discord", "handle_get_discord"),
    ("POST", "/api/discord/start", "handle_start_discord"),
    ("POST", "/api/discord/stop", "handle_stop_discord"),
    ("POST", "/api/discord/config", "handle_config_discord"),
    ("GET", "/api/subagents", "handle_get_subagents"),
    ("POST", "/api/subagents/spawn", "handle_spawn_subagent"),
    ("GET", "/api/git/status", "handle_git_status"),
    ("GET", "/api/git/diff", "handle_git_diff"),
    ("GET", "/api/mcp/tools", "handle_get_mcp_tools"),
    ("POST", "/api/chat", "handle_chat_stream"),
]


def create_app(registry: Optional[ServerRegistry] = None) -> web.Application:
    server = AgentWebServer(registry)
    app = web.Application(middlewares=[auth_middleware])

    # Static assets & UI entry point
    app.router.add_get("/", server.handle_index)
    if STATIC_DIR.exists():
        app.router.add_static("/static/", path=STATIC_DIR, name="static")

    for method, path, attr in ROUTES:
        app.router.add_route(method, path, getattr(server, attr))

    return app


def run_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    registry: Optional[ServerRegistry] = None,
):
    from dct.core.theme import con, C, BANNER

    app = create_app(registry)
    con.print(BANNER)
    con.print(f"  [{C['ok']}]● DCT-Agent Web Server started[/{C['ok']}]")
    con.print(
        f"  [{C['accent']}]➜ Local UI:[/{C['accent']}] "
        f"[{C['fg']}]http://{host}:{port}[/{C['fg']}]\n"
    )
    web.run_app(app, host=host, port=port, print=None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DCT Agent Web UI Server")
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=(
            f"Bind host (default: {DEFAULT_HOST}). Binding to 0.0.0.0 exposes "
            "this agent (code execution, git, config) to your network; set a "
            "web_auth_token in the config when you do."
        ),
    )
    parser.add_argument(
        "--port",
        default=DEFAULT_PORT,
        type=int,
        help=f"Bind port (default: {DEFAULT_PORT})",
    )
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)
