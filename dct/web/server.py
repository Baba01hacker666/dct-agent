"""
dct.web.server
Modern async web server powered by aiohttp providing REST APIs and Server-Sent Events (SSE)
for the DCT Agent interactive web interface.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional, Any
from aiohttp import web

from dct.core.registry import ServerRegistry, Server
from dct.core.probe import probe_server, probe_all
from dct.core.client import chat_stream
from dct.agent.session import Session
from dct.agent.codeagent import CodeAgent, get_system_prompt
from dct.tools.tasks import get_tracker

AGENT_SERVER_KEY = (
    web.AppKey("agent_server") if hasattr(web, "AppKey") else "agent_server"
)
STATIC_DIR = Path(__file__).parent / "static"


class AgentWebServer:
    def __init__(self, registry: Optional[ServerRegistry] = None):
        self.registry = registry or ServerRegistry()
        self.session = Session()
        self.active_server: Optional[Server] = None
        self.active_model: str = ""
        self.agent_mode: bool = True
        self._ask_user_future: Optional[asyncio.Future] = None
        self._current_agent: Optional[CodeAgent] = None

        # Initialize default server & model
        self._init_server()

    def _init_server(self):
        route = self.registry.route()
        if route:
            self.active_server, self.active_model = route
        elif self.registry.servers:
            self.active_server = self.registry.servers[0]
            self.active_model = self.active_server.models[0] if self.active_server.models else ""

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
            "active_server": {
                "alias": self.active_server.alias if self.active_server else None,
                "host": self.active_server.host if self.active_server else None,
                "port": self.active_server.port if self.active_server else None,
                "status": self.active_server.status if self.active_server else "offline",
                "latency_ms": self.active_server.latency_ms if self.active_server else -1,
                "models": self.active_server.models if self.active_server else [],
            }
            if self.active_server
            else None,
            "active_model": self.active_model,
            "agent_mode": self.agent_mode,
            "session_mode": self.session.mode,
            "user_turns": self.session.user_turns,
            "token_estimate": self.session.token_estimate,
            "servers_count": len(self.registry.servers),
            "online_servers_count": len(self.registry.online()),
            "tasks": tasks,
        }

    # ── Routes ───────────────────────────────────────────────────────────────

    async def handle_index(self, request: web.Request) -> web.Response:
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            return web.Response(text="index.html not found", status=404)
        return web.FileResponse(index_path)

    async def handle_status(self, request: web.Request) -> web.Response:
        return web.json_response(self.get_status_dict())

    async def handle_get_servers(self, request: web.Request) -> web.Response:
        servers = []
        for s in self.registry.servers:
            servers.append({
                "alias": s.alias,
                "host": s.host,
                "port": s.port,
                "status": s.status,
                "latency_ms": s.latency_ms,
                "models": s.models,
                "note": s.note,
                "provider": getattr(s, "provider", "ollama"),
                "is_active": self.active_server and self.active_server.alias == s.alias,
            })
        return web.json_response({"servers": servers})

    async def handle_add_server(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

        host = data.get("host", "").strip()
        port = int(data.get("port", 11434))
        alias = data.get("alias", "").strip()
        note = data.get("note", "").strip()
        api_key = data.get("api_key", "").strip()

        if not host:
            return web.json_response({"ok": False, "error": "Host is required"}, status=400)

        srv = self.registry.add(host, port, alias or f"{host}:{port}", note, api_key=api_key)
        probe_res = await asyncio.to_thread(probe_server, srv)
        self.registry.save()

        if not self.active_server or self.active_server.status != "online":
            self.active_server = srv
            self.active_model = srv.models[0] if srv.models else ""

        return web.json_response({
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
        })

    async def handle_probe(self, request: web.Request) -> web.Response:
        alias = request.query.get("alias")
        if alias:
            srv = self.registry.get(alias)
            if not srv:
                return web.json_response({"ok": False, "error": "Server not found"}, status=404)
            res = await asyncio.to_thread(probe_server, srv)
            self.registry.save()
            return web.json_response({"ok": True, "server": srv.alias, "result": res})

        results = await asyncio.to_thread(probe_all, self.registry)
        self.registry.save()
        return web.json_response({"ok": True, "results": results, "status": self.get_status_dict()})

    async def handle_select(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

        alias = data.get("alias")
        model = data.get("model")

        if alias:
            srv = self.registry.get(alias)
            if not srv:
                return web.json_response({"ok": False, "error": f"Server '{alias}' not found"}, status=404)
            self.active_server = srv
            if model and model in srv.models:
                self.active_model = model
            elif srv.models:
                self.active_model = srv.models[0]

        elif model:
            self.active_model = model

        return web.json_response({"ok": True, "status": self.get_status_dict()})

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
                self.session.mode = "plan" if self.session.mode == "execute" else "execute"
        except Exception:
            self.session.mode = "plan" if self.session.mode == "execute" else "execute"

        return web.json_response({"ok": True, "session_mode": self.session.mode})

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
            return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

        subject = data.get("subject", "").strip()
        desc = data.get("description", "").strip()
        active_form = data.get("active_form")

        if not subject:
            return web.json_response({"ok": False, "error": "Subject is required"}, status=400)

        t = get_tracker().create(subject=subject, description=desc, active_form=active_form)
        return web.json_response({
            "ok": True,
            "task": {
                "id": t.id,
                "subject": t.subject,
                "description": t.description,
                "status": t.status,
                "active_form": t.active_form,
            }
        })

    async def handle_update_task(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

        task_id = str(data.get("task_id", ""))
        status = data.get("status")
        subject = data.get("subject")
        description = data.get("description")

        t = get_tracker().update(task_id, status=status, subject=subject, description=description)
        if not t:
            return web.json_response({"ok": False, "error": f"Task #{task_id} not found"}, status=404)

        return web.json_response({
            "ok": True,
            "task": {
                "id": t.id,
                "subject": t.subject,
                "description": t.description,
                "status": t.status,
                "active_form": t.active_form,
            }
        })

    async def handle_get_history(self, request: web.Request) -> web.Response:
        messages = [
            {"role": m.get("role"), "content": m.get("content", "")}
            for m in self.session.messages
            if m.get("role") != "system"
        ]
        return web.json_response({"history": messages, "turns": self.session.user_turns})

    async def handle_clear(self, request: web.Request) -> web.Response:
        self.session.clear()
        get_tracker().tasks.clear()
        get_tracker()._next_id = 1
        return web.json_response({"ok": True, "message": "Conversation and tasks cleared"})

    async def handle_get_sessions(self, request: web.Request) -> web.Response:
        import os
        import json

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
                    sessions.append({
                        "id": f[:-5],
                        "filename": f,
                        "name": title,
                        "created_at": d.get("created_at", 0),
                        "saved_at": d.get("saved_at", 0),
                        "turns": sum(1 for m in msgs if m.get("role") == "user"),
                        "preview": preview,
                        "is_active": self.session.name == title or f[:-5] == self.session.name,
                    })
            except Exception:
                pass
        return web.json_response({"sessions": sessions})

    async def handle_switch_session(self, request: web.Request) -> web.Response:
        import os

        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

        session_id = data.get("session_id", "").strip()
        if not session_id:
            return web.json_response({"ok": False, "error": "session_id required"}, status=400)

        chats_dir = os.path.expanduser("~/.config/dct/chats")
        filename = f"{session_id}.json" if not session_id.endswith(".json") else session_id
        path = os.path.join(chats_dir, filename)

        if not os.path.exists(path):
            return web.json_response({"ok": False, "error": "Session file not found"}, status=404)

        try:
            self.session = Session.load(path)
            return web.json_response({
                "ok": True,
                "session": {
                    "name": self.session.name,
                    "turns": self.session.user_turns,
                    "mode": self.session.mode,
                },
                "history": [
                    {"role": m.get("role"), "content": m.get("content", "")}
                    for m in self.session.messages
                    if m.get("role") != "system"
                ],
            })
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_ask_user_response(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            answer = data.get("answer", "")
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

        if self._ask_user_future and not self._ask_user_future.done():
            self._ask_user_future.set_result(answer)
            return web.json_response({"ok": True, "message": "Response submitted to agent"})
        return web.json_response({"ok": False, "error": "Agent is not currently waiting for input"})

    # ── SSE Real-Time Streaming Chat ──────────────────────────────────────────

    async def handle_chat_stream(self, request: web.Request) -> web.StreamResponse:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON payload"}, status=400)

        user_text = data.get("message", "").strip()
        if not user_text:
            return web.json_response({"error": "Message is required"}, status=400)

        if not self.active_server:
            return web.json_response({"error": "No active server. Please register or select an active server first."}, status=400)

        # Prepare SSE Stream Response
        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
            },
        )
        await response.prepare(request)

        async def send_event(event_type: str, payload: dict | str):
            payload_str = json.dumps(payload) if isinstance(payload, (dict, list)) else str(payload)
            msg = f"event: {event_type}\ndata: {payload_str}\n\n"
            await response.write(msg.encode("utf-8"))

        # Add user message to session
        self.session.add("user", user_text)
        await send_event("user_message", {"content": user_text, "turns": self.session.user_turns})

        # Queue for thread-to-async communication
        loop = asyncio.get_running_loop()
        event_queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

        if self.agent_mode:
            # Autonomous Agent Loop
            messages = self.session.as_messages()
            if not self.session.system_prompt:
                dyn_prompt = get_system_prompt(self.session)
                sys_msg = {"role": "system", "content": dyn_prompt}
                agent_msgs = [sys_msg] + messages if messages and messages[0]["role"] != "system" else messages
            else:
                agent_msgs = messages

            def on_text(chunk: str):
                loop.call_soon_threadsafe(event_queue.put_nowait, ("text_chunk", {"chunk": chunk}))

            def on_tool(tool_name: str, args_raw: str):
                loop.call_soon_threadsafe(event_queue.put_nowait, ("tool_start", {"tool": tool_name, "args": args_raw}))

            def on_result(tool_name: str, result_text: str):
                tasks_snapshot = [
                    {"id": t.id, "subject": t.subject, "status": t.status, "description": t.description}
                    for t in get_tracker().get_all()
                ]
                loop.call_soon_threadsafe(event_queue.put_nowait, ("tool_result", {
                    "tool": tool_name,
                    "result": result_text[:4000],
                    "tasks": tasks_snapshot,
                }))

            agent = CodeAgent(
                server=self.active_server,
                model=self.active_model,
                session=self.session,
                stream_fn=chat_stream,
                on_text=on_text,
                on_tool=on_tool,
                on_result=on_result,
            )
            self._current_agent = agent

            def run_agent_sync():
                try:
                    final_text = agent.run(agent_msgs)
                    loop.call_soon_threadsafe(event_queue.put_nowait, ("done", {"final": final_text or ""}))
                except Exception as e:
                    loop.call_soon_threadsafe(event_queue.put_nowait, ("error", {"error": str(e)}))
                finally:
                    loop.call_soon_threadsafe(event_queue.put_nowait, ("__EOF__", None))

            runner_task = asyncio.to_thread(run_agent_sync)
            asyncio.create_task(runner_task)

        else:
            # Direct Stream Reply
            messages = self.session.as_messages()

            def run_stream_sync():
                full_reply = []
                try:
                    for chunk in chat_stream(self.active_server, self.active_model, messages):
                        full_reply.append(chunk)
                        loop.call_soon_threadsafe(event_queue.put_nowait, ("text_chunk", {"chunk": chunk}))
                    final_str = "".join(full_reply)
                    self.session.add("assistant", final_str)
                    loop.call_soon_threadsafe(event_queue.put_nowait, ("done", {"final": final_str}))
                except Exception as e:
                    loop.call_soon_threadsafe(event_queue.put_nowait, ("error", {"error": str(e)}))
                finally:
                    loop.call_soon_threadsafe(event_queue.put_nowait, ("__EOF__", None))

            runner_task = asyncio.to_thread(run_stream_sync)
            asyncio.create_task(runner_task)

        # Consume event queue and push SSE to client
        while True:
            ev_type, ev_data = await event_queue.get()
            if ev_type == "__EOF__":
                break
            await send_event(ev_type, ev_data)

        await response.write_eof()
        return response


def create_app(registry: Optional[ServerRegistry] = None) -> web.Application:
    server = AgentWebServer(registry)
    app = web.Application()
    app[AGENT_SERVER_KEY] = server

    # Static assets
    app.router.add_get("/", server.handle_index)
    app.router.add_static("/static/", path=STATIC_DIR, name="static")

    # REST APIs
    app.router.add_get("/api/status", server.handle_status)
    app.router.add_get("/api/servers", server.handle_get_servers)
    app.router.add_post("/api/servers/add", server.handle_add_server)
    app.router.add_post("/api/servers/probe", server.handle_probe)
    app.router.add_post("/api/select", server.handle_select)
    app.router.add_post("/api/toggle_agent", server.handle_toggle_agent)
    app.router.add_post("/api/toggle_plan", server.handle_toggle_plan)
    app.router.add_get("/api/tasks", server.handle_get_tasks)
    app.router.add_post("/api/tasks/create", server.handle_create_task)
    app.router.add_post("/api/tasks/update", server.handle_update_task)
    app.router.add_get("/api/history", server.handle_get_history)
    app.router.add_get("/api/sessions", server.handle_get_sessions)
    app.router.add_post("/api/sessions/switch", server.handle_switch_session)
    app.router.add_post("/api/clear", server.handle_clear)
    app.router.add_post("/api/ask_user_response", server.handle_ask_user_response)

    # SSE Chat Stream
    app.router.add_post("/api/chat", server.handle_chat_stream)

    return app


def run_server(host: str = "127.0.0.1", port: int = 8080, registry: Optional[ServerRegistry] = None):
    from dct.core.theme import con, C, BANNER
    app = create_app(registry)
    con.print(BANNER)
    con.print(f"  [{C['ok']}]● DCT-Agent Web Server started[/{C['ok']}]")
    con.print(f"  [{C['accent']}]➜ Local UI:[/{C['accent']}] [{C['fg']}]http://{host}:{port}[/{C['fg']}]\n")
    web.run_app(app, host=host, port=port, print=None)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="DCT Agent Web UI Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", default=8080, type=int, help="Bind port (default: 8080)")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)
