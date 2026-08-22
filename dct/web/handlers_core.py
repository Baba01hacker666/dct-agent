"""
dct.web.handlers_core
REST handlers for servers, sessions, tasks and UI plumbing.
"""

from __future__ import annotations

import asyncio
import json
import os

from aiohttp import web

from dct.core.probe import probe_server, probe_all
from dct.tools.tasks import get_tracker
from dct.web.state import WebState


class CoreHandlersMixin(WebState):
    async def handle_index(self, request: web.Request) -> web.Response:
        from dct.web.server import STATIC_DIR

        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            return web.Response(text="index.html not found", status=404)
        return web.FileResponse(index_path)

    async def handle_status(self, request: web.Request) -> web.Response:
        return web.json_response(self.get_status_dict())

    # ── Servers ──────────────────────────────────────────────────────────────

    async def handle_get_servers(self, request: web.Request) -> web.Response:
        servers = []
        for s in self.registry.servers:
            servers.append(
                {
                    "alias": s.alias,
                    "host": s.host,
                    "port": s.port,
                    "status": s.status,
                    "latency_ms": s.latency_ms,
                    "models": s.models,
                    "note": s.note,
                    "provider": getattr(s, "provider", "ollama"),
                    "is_active": (
                        self.active_server
                        and self.active_server.alias == s.alias
                    ),
                }
            )
        return web.json_response({"servers": servers})

    async def handle_add_server(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return self.invalid_json()

        host = data.get("host", "").strip()
        port = int(data.get("port", 11434))
        alias = data.get("alias", "").strip()
        note = data.get("note", "").strip()
        api_key = data.get("api_key", "").strip()

        if not host:
            return web.json_response(
                {"ok": False, "error": "Host is required"}, status=400
            )

        srv = self.registry.add(
            host, port, alias or f"{host}:{port}", note, api_key=api_key
        )
        probe_res = await asyncio.to_thread(probe_server, srv)
        self.registry.save()

        if not self.active_server or self.active_server.status != "online":
            self.active_server = srv
            self.active_model = srv.models[0] if srv.models else ""

        return web.json_response(
            {
                "ok": True,
                "server": {
                    "alias": srv.alias,
                    "host": srv.host,
                    "port": srv.port,
                    "status": srv.status,
                    "latency_ms": srv.latency_ms,
                    "models": srv.models,
                },
                "probe": probe_res,
            }
        )

    async def handle_probe(self, request: web.Request) -> web.Response:
        alias = request.query.get("alias")
        if alias:
            srv = self.registry.get(alias)
            if not srv:
                return web.json_response(
                    {"ok": False, "error": "Server not found"}, status=404
                )
            res = await asyncio.to_thread(probe_server, srv)
            self.registry.save()
            return web.json_response(
                {"ok": True, "server": srv.alias, "result": res}
            )

        results = await asyncio.to_thread(probe_all, self.registry)
        self.registry.save()
        return web.json_response(
            {
                "ok": True,
                "results": results,
                "status": self.get_status_dict(),
            }
        )

    async def handle_select(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return self.invalid_json()

        alias = data.get("alias")
        model = data.get("model")

        if alias:
            srv = self.registry.get(alias)
            if not srv:
                return web.json_response(
                    {"ok": False, "error": f"Server '{alias}' not found"},
                    status=404,
                )
            self.active_server = srv
            if model and model in srv.models:
                self.active_model = model
            elif srv.models:
                self.active_model = srv.models[0]
        elif model:
            self.active_model = model

        return web.json_response(
            {"ok": True, "status": self.get_status_dict()}
        )

    # ── Modes ────────────────────────────────────────────────────────────────

    async def handle_toggle_agent(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            enabled = bool(data.get("enabled", not self.agent_mode))
        except Exception:
            enabled = not self.agent_mode

        self.agent_mode = enabled
        return web.json_response({"ok": True, "agent_mode": self.agent_mode})

    async def handle_toggle_plan(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            mode = data.get("mode")
            if mode in ("plan", "execute"):
                self.session.mode = mode
            else:
                self.session.mode = (
                    "plan" if self.session.mode == "execute" else "execute"
                )
        except Exception:
            self.session.mode = (
                "plan" if self.session.mode == "execute" else "execute"
            )

        return web.json_response(
            {"ok": True, "session_mode": self.session.mode}
        )

    # ── Tasks ────────────────────────────────────────────────────────────────

    async def handle_get_tasks(self, request: web.Request) -> web.Response:
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
        return web.json_response({"tasks": tasks})

    async def handle_create_task(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return self.invalid_json()

        subject = data.get("subject", "").strip()
        desc = data.get("description", "").strip()
        active_form = data.get("active_form")

        if not subject:
            return web.json_response(
                {"ok": False, "error": "Subject is required"}, status=400
            )

        t = get_tracker().create(
            subject=subject, description=desc, active_form=active_form
        )
        return web.json_response(
            {
                "ok": True,
                "task": {
                    "id": t.id,
                    "subject": t.subject,
                    "description": t.description,
                    "status": t.status,
                    "active_form": t.active_form,
                },
            }
        )

    async def handle_update_task(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return self.invalid_json()

        task_id = str(data.get("task_id", ""))
        status = data.get("status")
        subject = data.get("subject")
        description = data.get("description")

        t = get_tracker().update(
            task_id, status=status, subject=subject, description=description
        )
        if not t:
            return web.json_response(
                {"ok": False, "error": f"Task #{task_id} not found"},
                status=404,
            )

        return web.json_response(
            {
                "ok": True,
                "task": {
                    "id": t.id,
                    "subject": t.subject,
                    "description": t.description,
                    "status": t.status,
                    "active_form": t.active_form,
                },
            }
        )

    # ── History & Sessions ───────────────────────────────────────────────────

    async def handle_get_history(self, request: web.Request) -> web.Response:
        messages = [
            {"role": m.get("role"), "content": m.get("content", "")}
            for m in self.session.messages
            if m.get("role") != "system"
        ]
        return web.json_response(
            {"history": messages, "turns": self.session.user_turns}
        )

    async def handle_clear(self, request: web.Request) -> web.Response:
        self.session.clear()
        get_tracker().tasks.clear()
        get_tracker()._next_id = 1
        return web.json_response(
            {"ok": True, "message": "Conversation and tasks cleared"}
        )

    async def handle_get_sessions(self, request: web.Request) -> web.Response:
        chats_dir = os.path.expanduser("~/.config/dct/chats")
        os.makedirs(chats_dir, exist_ok=True)
        files = sorted(
            [f for f in os.listdir(chats_dir) if f.endswith(".json")],
            reverse=True,
        )
        sessions = []
        for f in files:
            p = os.path.join(chats_dir, f)
            try:
                with open(p) as fh:
                    d = json.load(fh)
                title = d.get("name", f[:-5])
                msgs = d.get("messages", [])
                preview = ""
                for m in msgs:
                    if m.get("role") == "user":
                        preview = m["content"][:80]
                        break
                sessions.append(
                    {
                        "id": f[:-5],
                        "filename": f,
                        "name": title,
                        "created_at": d.get("created_at", 0),
                        "saved_at": d.get("saved_at", 0),
                        "turns": sum(
                            1 for m in msgs if m.get("role") == "user"
                        ),
                        "preview": preview,
                        "is_active": (
                            self.session.name == title
                            or f[:-5] == self.session.name
                        ),
                    }
                )
            except Exception:
                pass
        return web.json_response({"sessions": sessions})

    async def handle_switch_session(
        self, request: web.Request
    ) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return self.invalid_json()

        session_id = data.get("session_id", "").strip()
        if not session_id:
            return web.json_response(
                {"ok": False, "error": "session_id required"}, status=400
            )

        chats_dir = os.path.expanduser("~/.config/dct/chats")
        filename = (
            f"{session_id}.json"
            if not session_id.endswith(".json")
            else session_id
        )
        path = os.path.join(chats_dir, filename)

        if not os.path.exists(path):
            return web.json_response(
                {"ok": False, "error": "Session file not found"}, status=404
            )

        try:
            from dct.agent.session import Session

            self.session = Session.load(path)
            return web.json_response(
                {
                    "ok": True,
                    "session": {
                        "name": self.session.name,
                        "turns": self.session.user_turns,
                        "mode": self.session.mode,
                    },
                    "history": [
                        {
                            "role": m.get("role"),
                            "content": m.get("content", ""),
                        }
                        for m in self.session.messages
                        if m.get("role") != "system"
                    ],
                }
            )
        except Exception as e:
            return web.json_response(
                {"ok": False, "error": str(e)}, status=500
            )

    async def handle_ask_user_response(
        self, request: web.Request
    ) -> web.Response:
        try:
            data = await request.json()
            answer = data.get("answer", "")
        except Exception:
            return self.invalid_json()

        if self._ask_user_future and not self._ask_user_future.done():
            self._ask_user_future.set_result(answer)
            return web.json_response(
                {"ok": True, "message": "Response submitted to agent"}
            )
        return web.json_response(
            {"ok": False, "error": "Agent is not currently waiting for input"}
        )
