"""
dct.web.chat_stream
Server-Sent Events (SSE) chat endpoint bridging the agent loop to the UI.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from aiohttp import web

from dct.core.client import chat_stream
from dct.agent.codeagent import CodeAgent, get_system_prompt
from dct.tools.tasks import get_tracker


class ChatStreamMixin:
    async def handle_chat_stream(
        self, request: web.Request
    ) -> web.StreamResponse:
        try:
            data = await request.json()
        except Exception:
            return web.json_response(
                {"error": "Invalid JSON payload"}, status=400
            )

        user_text = data.get("message", "").strip()
        if not user_text:
            return web.json_response(
                {"error": "Message is required"}, status=400
            )

        if not self.active_server:
            return web.json_response(
                {
                    "error": (
                        "No active server. Please register or select an "
                        "active server first."
                    )
                },
                status=400,
            )

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
            payload_str = (
                json.dumps(payload)
                if isinstance(payload, (dict, list))
                else str(payload)
            )
            msg = f"event: {event_type}\ndata: {payload_str}\n\n"
            await response.write(msg.encode("utf-8"))

        self.session.add("user", user_text)
        await send_event(
            "user_message",
            {"content": user_text, "turns": self.session.user_turns},
        )

        loop = asyncio.get_running_loop()
        event_queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

        if self.agent_mode:
            agent_msgs = self._prepare_agent_messages()

            def on_text(chunk: str):
                loop.call_soon_threadsafe(
                    event_queue.put_nowait, ("text_chunk", {"chunk": chunk})
                )

            def on_tool(tool_name: str, args_raw: str):
                loop.call_soon_threadsafe(
                    event_queue.put_nowait,
                    ("tool_start", {"tool": tool_name, "args": args_raw}),
                )

            def on_result(tool_name: str, result_text: str):
                tasks_snapshot = [
                    {
                        "id": t.id,
                        "subject": t.subject,
                        "status": t.status,
                        "description": t.description,
                    }
                    for t in get_tracker().get_all()
                ]
                loop.call_soon_threadsafe(
                    event_queue.put_nowait,
                    (
                        "tool_result",
                        {
                            "tool": tool_name,
                            "result": result_text[:4000],
                            "tasks": tasks_snapshot,
                        },
                    ),
                )

            from dct.core.config import Config
            from dct.agent.codeagent import MAX_AGENT_TURNS

            agent = CodeAgent(
                server=self.active_server,
                model=self.active_model,
                session=self.session,
                stream_fn=chat_stream,
                on_text=on_text,
                on_tool=on_tool,
                on_result=on_result,
                max_turns=int(
                    Config().get("max_agent_turns", MAX_AGENT_TURNS)
                ),
            )
            self._current_agent = agent

            def run_agent_sync():
                try:
                    final_text = agent.run(agent_msgs)
                    loop.call_soon_threadsafe(
                        event_queue.put_nowait,
                        ("done", {"final": final_text or ""}),
                    )
                except Exception as e:
                    loop.call_soon_threadsafe(
                        event_queue.put_nowait, ("error", {"error": str(e)})
                    )
                finally:
                    loop.call_soon_threadsafe(
                        event_queue.put_nowait, ("__EOF__", None)
                    )

            asyncio.create_task(asyncio.to_thread(run_agent_sync))

        else:

            def run_stream_sync():
                full_reply = []
                try:
                    for chunk in chat_stream(
                        self.active_server,
                        self.active_model,
                        self.session.as_messages(),
                    ):
                        full_reply.append(chunk)
                        loop.call_soon_threadsafe(
                            event_queue.put_nowait,
                            ("text_chunk", {"chunk": chunk}),
                        )
                    final_str = "".join(full_reply)
                    self.session.add("assistant", final_str)
                    loop.call_soon_threadsafe(
                        event_queue.put_nowait, ("done", {"final": final_str})
                    )
                except Exception as e:
                    loop.call_soon_threadsafe(
                        event_queue.put_nowait, ("error", {"error": str(e)})
                    )
                finally:
                    loop.call_soon_threadsafe(
                        event_queue.put_nowait, ("__EOF__", None)
                    )

            asyncio.create_task(asyncio.to_thread(run_stream_sync))

        while True:
            ev_type, ev_data = await event_queue.get()
            if ev_type == "__EOF__":
                break
            await send_event(ev_type, ev_data)

        await response.write_eof()
        return response

    def _prepare_agent_messages(self) -> list[dict]:
        messages = self.session.as_messages()
        if not self.session.system_prompt:
            dyn_prompt = get_system_prompt(self.session)
            sys_msg = {"role": "system", "content": dyn_prompt}
            if messages and messages[0]["role"] != "system":
                return [sys_msg] + messages
        return messages
