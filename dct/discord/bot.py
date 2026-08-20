"""
dct.discord.bot
Autonomous Discord Bot bridge for DCT-Agent.
Enables remote agent interactions, code execution, task management,
and multi-server orchestration via Discord Gateway and REST API.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from typing import Any, Dict, List, Optional

import aiohttp

from dct.agent.codeagent import CodeAgent, get_system_prompt
from dct.agent.session import Session
from dct.core.client import chat_stream, list_models
from dct.core.config import Config
from dct.core.probe import probe_all, probe_server
from dct.core.registry import Server, ServerRegistry
from dct.tools.board import get_board
from dct.tools.tasks import get_tracker

logger = logging.getLogger("dct.discord")

GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"
DISCORD_API_BASE = "https://discord.com/api/v10"


class DiscordBot:
    """
    Async Discord Bot bridge using Discord Gateway WebSocket & REST API.
    Zero third-party Discord wrapper libraries required (pure aiohttp).
    """

    def __init__(
        self,
        token: Optional[str] = None,
        allowed_users: Optional[List[str]] = None,
        registry: Optional[ServerRegistry] = None,
    ):
        conf = Config()
        self.token = (
            token
            or os.environ.get("DISCORD_BOT_TOKEN")
            or conf.get("discord_token", "")
        )
        self.allowed_users = (
            allowed_users
            if allowed_users is not None
            else conf.get("discord_allowed_users", [])
        )
        self.registry = registry or ServerRegistry()
        self.session_store: Dict[str, Session] = {}
        self._running = False
        self._stop_event = asyncio.Event()
        self.bot_user_id: Optional[str] = None
        self.bot_username: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None

    def is_user_allowed(self, user_data: dict) -> bool:
        """Check if user ID or username is allowed."""
        if not self.allowed_users:
            return True
        user_id = str(user_data.get("id", ""))
        username = str(user_data.get("username", "")).lower()
        allowed_set = {str(u).lower().lstrip("@") for u in self.allowed_users}
        return user_id in allowed_set or username in allowed_set

    def get_channel_session(self, channel_id: str) -> Session:
        if channel_id not in self.session_store:
            self.session_store[channel_id] = Session(mode="execute")
        return self.session_store[channel_id]

    def get_active_server(self) -> Optional[Server]:
        conf = Config()
        pref = conf.get("default_server", "")
        if pref:
            s = self.registry.resolve(pref)
            if s:
                return s
        return self.registry.first_online() or (
            self.registry.servers[0] if self.registry.servers else None
        )

    def _auth_headers(self) -> dict:
        return {
            "Authorization": f"Bot {self.token}",
            "Content-Type": "application/json",
        }

    async def send_message(
        self,
        channel_id: str,
        content: str,
        reply_to_id: Optional[str] = None,
    ) -> dict:
        """Send message to Discord channel, chunking at 1900 characters."""
        if not content:
            return {"ok": True}

        chunks = []
        text = str(content)
        while len(text) > 1900:
            split_idx = text.rfind("\n", 0, 1900)
            if split_idx == -1 or split_idx < 500:
                split_idx = 1900
            chunks.append(text[:split_idx])
            text = text[split_idx:].lstrip("\n")
        chunks.append(text)

        last_resp = {}
        async with aiohttp.ClientSession() as session:
            for i, chunk in enumerate(chunks):
                payload: Dict[str, Any] = {"content": chunk}
                if i == 0 and reply_to_id:
                    payload["message_reference"] = {"message_id": reply_to_id}

                url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
                try:
                    async with session.post(
                        url,
                        headers=self._auth_headers(),
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        last_resp = await resp.json()
                except Exception as e:
                    logger.error("Failed to send Discord message: %s", e)
        return last_resp

    async def trigger_typing(self, channel_id: str):
        """Trigger typing indicator in Discord channel."""
        url = f"{DISCORD_API_BASE}/channels/{channel_id}/typing"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=self._auth_headers(),
                    timeout=aiohttp.ClientTimeout(total=5),
                ):
                    pass
        except Exception:
            pass

    async def handle_command(
        self, channel_id: str, author: dict, cmd_text: str
    ) -> str:
        """Process Discord bot command."""
        parts = cmd_text.strip().split()
        if not parts:
            return ""
        cmd = parts[0].lower().lstrip("!/").split("@")[0]
        args = parts[1:]
        session = self.get_channel_session(channel_id)

        if cmd in ("start", "help"):
            return (
                "🤖 **DCT Agent Discord Bridge**\n\n"
                "**Available Commands:**\n"
                "• `!status` - Show active server, model, and system status\n"
                "• `!servers` - List all registered Ollama/OpenAI servers\n"
                "• `!models` - List models available on the active server\n"
                "• `!use <alias>` - Switch active server\n"
                "• `!model <name>` - Switch active model\n"
                "• `!agent on|off` - Toggle autonomous agent mode\n"
                "• `!tasks` - View active structured tasks\n"
                "• `!board` - View AI agents discussion board\n"
                "• `!clear` - Clear conversation history for this channel\n\n"
                "To prompt the agent, send any message or mention the bot."
            )

        elif cmd == "status":
            srv = self.get_active_server()
            if not srv:
                return "⚠️ No servers registered. Add a server in CLI or Web UI."
            conf = Config()
            model = conf.get("default_model") or (
                srv.models[0] if srv.models else "default"
            )
            return (
                f"📊 **DCT Agent Status**\n"
                f"• Active Server: `{srv.alias}` ({srv.host}:{srv.port})\n"
                f"• Server Type: `{srv.server_type}`\n"
                f"• Active Model: `{model}`\n"
                f"• Channel Mode: `{session.mode}`\n"
                f"• History Turns: {session.turn_count()} messages"
            )

        elif cmd == "servers":
            probe_all(self.registry)
            lines = ["🌐 **Registered Servers:**"]
            for s in self.registry.servers:
                status_icon = "🟢" if s.online else "🔴"
                lines.append(
                    f"{status_icon} `{s.alias}` ({s.host}:{s.port}) — "
                    f"{len(s.models)} models [{s.server_type}]"
                )
            return "\n".join(lines)

        elif cmd == "models":
            srv = self.get_active_server()
            if not srv:
                return "⚠️ No active server found."
            models = list_models(srv)
            if not models:
                return f"No models found on `{srv.alias}`."
            lines = [f"🧠 **Models on `{srv.alias}`:**"]
            for m in models[:30]:
                lines.append(f"• `{m}`")
            return "\n".join(lines)

        elif cmd == "use":
            if not args:
                return "Usage: `!use <server_alias>`"
            target = args[0]
            s = self.registry.resolve(target)
            if not s:
                return f"❌ Server `{target}` not found."
            probe_server(s)
            Config().set("default_server", s.alias)
            Config().save()
            return f"✅ Switched active server to `{s.alias}`."

        elif cmd == "model":
            if not args:
                return "Usage: `!model <model_name>`"
            model_name = args[0]
            Config().set("default_model", model_name)
            Config().save()
            return f"✅ Set active model to `{model_name}`."

        elif cmd == "clear":
            session.clear()
            return "🧹 Conversation history cleared for this channel."

        elif cmd == "agent":
            if args and args[0].lower() in ("off", "false", "disable"):
                Config().set("agent_mode", False)
                Config().save()
                return "⏸️ Autonomous agent mode disabled."
            else:
                Config().set("agent_mode", True)
                Config().save()
                return "⚡ Autonomous agent mode enabled."

        elif cmd == "tasks":
            tracker = get_tracker()
            tasks = tracker.list_tasks()
            if not tasks:
                return "📋 No tasks currently registered."
            lines = ["📋 **Task Tracker:**"]
            for t in tasks:
                icon = (
                    "✅"
                    if t["status"] == "completed"
                    else "⏳" if t["status"] == "in_progress" else "⚪"
                )
                lines.append(f"{icon} `#{t['id']}` {t['subject']}")
            return "\n".join(lines)

        elif cmd == "board":
            board = get_board()
            msgs = board.read_messages(limit=8)
            if not msgs:
                return "💬 Discussion board is empty."
            lines = ["💬 **Recent Board Messages:**"]
            for m in msgs:
                lines.append(
                    f"• **[{m.sender}]** in `#{m.channel}`: {m.content[:120]}"
                )
            return "\n".join(lines)

        return ""

    async def handle_message(self, msg_data: dict):
        """Handle incoming Discord message event."""
        author = msg_data.get("author", {})
        if author.get("bot", False):
            return

        channel_id = str(msg_data.get("channel_id", ""))
        content = msg_data.get("content", "").strip()
        msg_id = str(msg_data.get("id", ""))

        if not content or not channel_id:
            return

        if not self.is_user_allowed(author):
            logger.info("Unauthorized Discord message from %s", author)
            return

        # Check if bot was mentioned
        if self.bot_user_id and f"<@{self.bot_user_id}>" in content:
            content = content.replace(f"<@{self.bot_user_id}>", "").strip()

        # Handle command
        if content.startswith(("!", "/")):
            reply = await self.handle_command(channel_id, author, content)
            if reply:
                await self.send_message(
                    channel_id, reply, reply_to_id=msg_id
                )
                return

        srv = self.get_active_server()
        if not srv:
            await self.send_message(
                channel_id,
                "⚠️ No registered servers available.",
                reply_to_id=msg_id,
            )
            return

        conf = Config()
        model = conf.get("default_model") or (
            srv.models[0] if srv.models else "default"
        )
        session = self.get_channel_session(channel_id)

        # Trigger typing
        await self.trigger_typing(channel_id)

        # Agent mode
        agent_enabled = conf.get("agent_mode", True)
        if agent_enabled:
            loop = asyncio.get_running_loop()
            collected_tools: List[str] = []

            def on_tool(tool_name: str, call_data: str):
                collected_tools.append(f"⚡ `[{tool_name}]`")

            def run_agent_sync() -> str:
                dyn_prompt = get_system_prompt(session)
                session.set_system(dyn_prompt)
                session.add("user", content)

                agent = CodeAgent(
                    server=srv,
                    model=model,
                    session=session,
                    stream_fn=chat_stream,
                    on_text=lambda _: None,
                    on_tool=on_tool,
                    on_result=lambda _t, _r: None,
                    max_turns=10,
                )
                return agent.run(session.as_messages())

            try:
                res_text = await loop.run_in_executor(None, run_agent_sync)
                tool_summary = (
                    " ".join(collected_tools) + "\n\n"
                    if collected_tools
                    else ""
                )
                await self.send_message(
                    channel_id,
                    f"{tool_summary}{res_text}",
                    reply_to_id=msg_id,
                )
            except Exception as e:
                logger.exception("Discord agent execution error")
                await self.send_message(
                    channel_id,
                    f"❌ Agent Error: {str(e)}",
                    reply_to_id=msg_id,
                )
        else:
            # Simple chat stream
            session.add("user", content)
            loop = asyncio.get_running_loop()

            def run_chat_sync() -> str:
                accum = []
                for chunk in chat_stream(srv, model, session.as_messages()):
                    if isinstance(chunk, str):
                        accum.append(chunk)
                    elif isinstance(chunk, dict) and "content" in chunk:
                        accum.append(chunk["content"])
                full = "".join(accum)
                session.add("assistant", full)
                return full

            try:
                reply_text = await loop.run_in_executor(None, run_chat_sync)
                await self.send_message(
                    channel_id, reply_text, reply_to_id=msg_id
                )
            except Exception as e:
                logger.exception("Discord chat error")
                await self.send_message(
                    channel_id,
                    f"❌ Error: {str(e)}",
                    reply_to_id=msg_id,
                )

    async def _heartbeat_loop(self, interval_sec: float):
        """Send periodic heartbeat to Discord Gateway."""
        while self._running:
            try:
                await asyncio.sleep(interval_sec)
                if self._ws and not self._ws.closed:
                    await self._ws.send_json({"op": 1, "d": None})
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Discord heartbeat error: %s", e)

    async def start_async(self):
        """Main async Gateway connection loop."""
        if not self.token:
            logger.error("No Discord bot token provided.")
            return

        self._running = True
        self._stop_event.clear()

        async with aiohttp.ClientSession() as session:
            self._session = session
            while self._running and not self._stop_event.is_set():
                try:
                    async with session.ws_connect(GATEWAY_URL) as ws:
                        self._ws = ws
                        heartbeat_task: Optional[asyncio.Task] = None

                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = json.loads(msg.data)
                                op = data.get("op")
                                t = data.get("t")
                                d = data.get("d")

                                if op == 10:  # HELLO
                                    interval = d["heartbeat_interval"] / 1000.0
                                    heartbeat_task = asyncio.create_task(
                                        self._heartbeat_loop(interval)
                                    )
                                    # IDENTIFY
                                    identify_payload = {
                                        "op": 2,
                                        "d": {
                                            "token": self.token,
                                            "intents": 33280,  # GUILDS | GUILD_MESSAGES | DIRECT_MESSAGES | MESSAGE_CONTENT
                                            "properties": {
                                                "os": "linux",
                                                "browser": "dct-agent",
                                                "device": "dct-agent",
                                            },
                                        },
                                    }
                                    await ws.send_json(identify_payload)

                                elif op == 0:  # DISPATCH
                                    if t == "READY":
                                        self.bot_user_id = d.get(
                                            "user", {}
                                        ).get("id")
                                        self.bot_username = d.get(
                                            "user", {}
                                        ).get("username")
                                        logger.info(
                                            "Discord Bot Ready: %s (#%s)",
                                            self.bot_username,
                                            self.bot_user_id,
                                        )
                                    elif t == "MESSAGE_CREATE":
                                        asyncio.create_task(
                                            self.handle_message(d)
                                        )

                                elif op == 7:  # RECONNECT
                                    break
                                elif op == 9:  # INVALID_SESSION
                                    await asyncio.sleep(2)
                                    break

                            elif msg.type in (
                                aiohttp.WSMsgType.CLOSED,
                                aiohttp.WSMsgType.ERROR,
                            ):
                                break

                        if heartbeat_task:
                            heartbeat_task.cancel()

                except Exception as e:
                    if self._running:
                        logger.error(
                            "Discord Gateway error: %s (reconnecting in 5s)", e
                        )
                        await asyncio.sleep(5)

    def start(self):
        """Blocking entrypoint."""
        asyncio.run(self.start_async())

    def start_background(self) -> threading.Thread:
        """Start Discord Bot in a background thread."""
        self._running = True
        thread = threading.Thread(target=self.start, daemon=True)
        thread.start()
        return thread

    def stop(self):
        """Signal Discord Bot loop to stop."""
        self._running = False
        self._stop_event.set()


_global_discord_bot: Optional[DiscordBot] = None
_discord_bot_thread: Optional[threading.Thread] = None


def get_discord_bot() -> Optional[DiscordBot]:
    return _global_discord_bot


def start_discord_bridge(
    token: Optional[str] = None,
    allowed_users: Optional[List[str]] = None,
    registry: Optional[ServerRegistry] = None,
) -> DiscordBot:
    global _global_discord_bot, _discord_bot_thread
    if _global_discord_bot is not None and _global_discord_bot._running:
        return _global_discord_bot

    bot = DiscordBot(
        token=token, allowed_users=allowed_users, registry=registry
    )
    _global_discord_bot = bot
    _discord_bot_thread = bot.start_background()
    return bot


def stop_discord_bridge() -> None:
    global _global_discord_bot
    if _global_discord_bot:
        _global_discord_bot.stop()
        _global_discord_bot = None
