"""
dct.telegram.bot
Autonomous Telegram Bot bridge for DCT-Agent.
Enables remote agent interactions, code execution, task management,
and multi-server orchestration via Telegram Bot API with long-polling.
"""

from __future__ import annotations

import os
import sys
import time
import json
import asyncio
import logging
import threading
from typing import Optional, List, Dict, Any, Callable

import aiohttp

from dct.core.config import Config
from dct.core.registry import ServerRegistry, Server
from dct.core.client import chat_stream, list_models
from dct.core.probe import probe_all, probe_server
from dct.agent.session import Session
from dct.agent.codeagent import CodeAgent, get_system_prompt
from dct.tools.tasks import get_tracker
from dct.tools.board import get_board

logger = logging.getLogger("dct.telegram")


def escape_markdown(text: str) -> str:
    """Safe plain text representation for Telegram messages."""
    return str(text)


class TelegramBot:
    """
    Async Telegram Bot bridge using long-polling.
    No webhooks or open ports needed; operates behind NAT, firewalls, or on mobile.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        allowed_users: Optional[List[str | int]] = None,
        registry: Optional[ServerRegistry] = None,
    ):
        conf = Config()
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN") or conf.get("telegram_token", "")
        self.allowed_users = (
            allowed_users
            if allowed_users is not None
            else conf.get("telegram_allowed_users", [])
        )
        self.registry = registry or ServerRegistry()
        self.session_store: Dict[int, Session] = {}
        self.active_agent: Optional[CodeAgent] = None
        self._running = False
        self._stop_event = asyncio.Event()
        self._polling_task: Optional[asyncio.Task] = None
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.bot_info: Dict[str, Any] = {}

    def is_user_allowed(self, user_data: dict) -> bool:
        """Check if user ID or username is in allowed whitelist."""
        if not self.allowed_users:
            # If no whitelist specified, allow all or auto-add first user
            return True
        user_id = str(user_data.get("id", ""))
        username = str(user_data.get("username", "")).lower()
        allowed_set = {str(u).lower().lstrip("@") for u in self.allowed_users}
        return user_id in allowed_set or username in allowed_set

    def get_user_session(self, user_id: int) -> Session:
        if user_id not in self.session_store:
            self.session_store[user_id] = Session(mode="execute")
        return self.session_store[user_id]

    def get_active_server(self) -> Optional[Server]:
        conf = Config()
        pref = conf.get("default_server", "")
        if pref:
            s = self.registry.resolve(pref)
            if s:
                return s
        return self.registry.first_online() or (self.registry.servers[0] if self.registry.servers else None)

    async def _api_call(self, http_session: aiohttp.ClientSession, method: str, data: Optional[dict] = None) -> dict:
        url = f"{self.base_url}/{method}"
        try:
            async with http_session.post(url, json=data or {}, timeout=aiohttp.ClientTimeout(total=45)) as resp:
                res_data = await resp.json()
                if not res_data.get("ok"):
                    logger.warning("Telegram API error [%s]: %s", method, res_data.get("description"))
                return res_data
        except Exception as e:
            logger.error("HTTP error calling Telegram API [%s]: %s", method, str(e))
            return {"ok": False, "error": str(e)}

    async def send_message(
        self,
        http_session: aiohttp.ClientSession,
        chat_id: int | str,
        text: str,
        reply_to_message_id: Optional[int] = None,
        reply_markup: Optional[dict] = None,
    ) -> dict:
        """Send message, automatically chunking if exceeds 4000 characters."""
        if not text:
            return {"ok": True}

        # Telegram character limit is 4096. Keep chunks under 4000 for safety.
        chunks = []
        while len(text) > 3900:
            split_idx = text.rfind("\n", 0, 3900)
            if split_idx == -1 or split_idx < 1000:
                split_idx = 3900
            chunks.append(text[:split_idx])
            text = text[split_idx:].lstrip("\n")
        chunks.append(text)

        last_resp = {"ok": True}
        for i, chunk in enumerate(chunks):
            payload = {
                "chat_id": chat_id,
                "text": chunk,
            }
            if i == 0 and reply_to_message_id:
                payload["reply_to_message_id"] = reply_to_message_id
            if i == len(chunks) - 1 and reply_markup:
                payload["reply_markup"] = reply_markup
            last_resp = await self._api_call(http_session, "sendMessage", payload)
        return last_resp

    async def send_chat_action(self, http_session: aiohttp.ClientSession, chat_id: int | str, action: str = "typing") -> None:
        await self._api_call(http_session, "sendChatAction", {"chat_id": chat_id, "action": action})

    async def handle_command(
        self, http_session: aiohttp.ClientSession, chat_id: int, user_id: int, cmd: str, args: str, message_id: int
    ) -> None:
        """Process slash commands received via Telegram."""
        user_sess = self.get_user_session(user_id)
        cmd = cmd.lower()

        if cmd in ("/start", "/help"):
            help_text = (
                "⚡ *DCT-Agent Telegram Bridge*\n\n"
                "Autonomous Multi-Server AI Developer connected to your environment.\n\n"
                "*Commands:*\n"
                "• /status — Check active server, model, turns, and stats\n"
                "• /servers — List registered LLM nodes and latencies\n"
                "• /models — List available models on active server\n"
                "• /skills — List specialized agent skills and personas\n"
                "• /skill `<name>` — Load a specialized skill preset\n"
                "• /tasks — View structured task tracker board\n"
                "• /plan — Toggle safe PLAN mode for exploration\n"
                "• /agent — Toggle autonomous agent execution\n"
                "• /board — View AI agents discussion board\n"
                "• /clear — Reset conversation history\n\n"
                "Send any coding goal or message to begin autonomous agent work!"
            )
            await self.send_message(http_session, chat_id, help_text, reply_to_message_id=message_id)

        elif cmd == "/status":
            online = self.registry.online()
            active_s = self.get_active_server()
            conf = Config()
            status_text = (
                f"📊 *DCT-Agent Status*\n\n"
                f"• *Server:* {active_s.alias if active_s else 'None'} ({active_s.host if active_s else ''})\n"
                f"• *Model:* {conf.get('default_model', active_s.models[0] if active_s and active_s.models else 'None')}\n"
                f"• *Mode:* {'🛡️ PLAN' if user_sess.mode == 'plan' else '⚡ EXECUTE'}\n"
                f"• *Agent Mode:* {'ON' if conf.get('agent_enabled', True) else 'OFF'}\n"
                f"• *Session Turns:* {user_sess.user_turns}\n"
                f"• *Active Tasks:* {len([t for t in get_tracker().get_all() if t.status == 'in_progress'])}\n"
                f"• *Online Nodes:* {len(online)} / {len(self.registry.servers)}"
            )
            await self.send_message(http_session, chat_id, status_text, reply_to_message_id=message_id)

        elif cmd == "/servers":
            if not self.registry.servers:
                await self.send_message(http_session, chat_id, "No servers registered. Register one via CLI or Web UI.", reply_to_message_id=message_id)
                return
            lines = ["🌐 *Registered Servers:*"]
            for s in self.registry.servers:
                st = "🟢" if s.status == "online" else "🔴"
                lines.append(f"{st} *{s.alias}* — `{s.host}:{s.port}` ({s.latency_ms}ms) · {len(s.models)} model(s)")
            await self.send_message(http_session, chat_id, "\n".join(lines), reply_to_message_id=message_id)

        elif cmd == "/models":
            active_s = self.get_active_server()
            if not active_s:
                await self.send_message(http_session, chat_id, "No online server available.", reply_to_message_id=message_id)
                return
            lines = [f"⚡ *Models on {active_s.alias}:*"]
            for m in active_s.models[:30]:
                lines.append(f"• `{m}`")
            if len(active_s.models) > 30:
                lines.append(f"… and {len(active_s.models) - 30} more.")
            await self.send_message(http_session, chat_id, "\n".join(lines), reply_to_message_id=message_id)

        elif cmd == "/skills":
            try:
                from dct.cli.shell import SKILL_PRESETS
            except ImportError:
                SKILL_PRESETS = {}
            conf = Config()
            custom = conf.get("custom_skills", {})
            lines = ["🧠 *Agent Skills:*"]
            lines.append("*Built-in:*")
            for k, v in SKILL_PRESETS.items():
                lines.append(f"• *{k}*: {v.get('desc', '')}")
            if custom:
                lines.append("\n*Custom:*")
                for k, v in custom.items():
                    lines.append(f"• *{k}*: {v.get('desc', '')}")
            lines.append("\nUse `/skill <name>` to activate.")
            await self.send_message(http_session, chat_id, "\n".join(lines), reply_to_message_id=message_id)

        elif cmd == "/skill":
            skill_name = args.strip()
            if not skill_name:
                user_sess.set_system("")
                await self.send_message(http_session, chat_id, "Reset to default system prompt.", reply_to_message_id=message_id)
                return

            try:
                from dct.cli.shell import SKILL_PRESETS
            except ImportError:
                SKILL_PRESETS = {}
            conf = Config()
            custom = conf.get("custom_skills", {})
            skill = custom.get(skill_name) or SKILL_PRESETS.get(skill_name)
            if not skill:
                await self.send_message(http_session, chat_id, f"❌ Skill '{skill_name}' not found. Use /skills to view list.", reply_to_message_id=message_id)
                return

            user_sess.set_system(skill["prompt"])
            await self.send_message(http_session, chat_id, f"✅ Activated skill persona: *{skill_name}*", reply_to_message_id=message_id)

        elif cmd == "/tasks":
            tasks = get_tracker().get_all()
            if not tasks:
                await self.send_message(http_session, chat_id, "🎯 No tasks currently tracked.", reply_to_message_id=message_id)
                return
            lines = ["📋 *Active Task Tracker:*"]
            for t in tasks:
                icon = "✅" if t.status == "completed" else "⚡" if t.status == "in_progress" else "⏳"
                lines.append(f"{icon} [#{t.id}] *{t.subject}* ({t.status})")
            await self.send_message(http_session, chat_id, "\n".join(lines), reply_to_message_id=message_id)

        elif cmd == "/plan":
            if user_sess.mode == "plan":
                user_sess.mode = "execute"
                await self.send_message(http_session, chat_id, "🚀 *Exited Plan Mode.* Switched to EXECUTE mode.", reply_to_message_id=message_id)
            else:
                user_sess.mode = "plan"
                await self.send_message(http_session, chat_id, "🛡️ *Plan Mode Activated.* Destructive code execution is locked.", reply_to_message_id=message_id)

        elif cmd == "/agent":
            conf = Config()
            current = conf.get("agent_enabled", True)
            new_val = not current
            conf.set("agent_enabled", new_val)
            conf.save()
            st_str = "ON 🤖" if new_val else "OFF 💬"
            await self.send_message(http_session, chat_id, f"Autonomous Agent Mode is now *{st_str}*.", reply_to_message_id=message_id)

        elif cmd == "/board":
            conf = Config()
            if not conf.get("enable_agent_board", False):
                await self.send_message(http_session, chat_id, "⚠️ Discussion Board is currently disabled in config.", reply_to_message_id=message_id)
                return
            ch = args.strip() or "general"
            formatted = get_board().format_for_prompt(channel=ch, limit=8)
            await self.send_message(http_session, chat_id, f"💬 *Discussion Board (#{ch}):*\n\n{formatted}", reply_to_message_id=message_id)

        elif cmd == "/clear":
            user_sess.clear()
            get_tracker().clear()
            await self.send_message(http_session, chat_id, "🗑️ Conversation history and tasks cleared.", reply_to_message_id=message_id)

        else:
            await self.send_message(http_session, chat_id, f"Unknown command `{cmd}`. Type /help for available commands.", reply_to_message_id=message_id)

    async def handle_text_message(
        self, http_session: aiohttp.ClientSession, chat_id: int, user_id: int, text: str, message_id: int
    ) -> None:
        """Handle incoming chat messages by invoking the CodeAgent."""
        online = self.registry.online()
        active_s = self.get_active_server()
        if not active_s:
            await self.send_message(
                http_session, chat_id, "❌ Error: No online servers available to process this request.", reply_to_message_id=message_id
            )
            return

        conf = Config()
        model_name = conf.get("default_model") or (active_s.models[0] if active_s.models else "qwen2.5-coder:7b")
        user_sess = self.get_user_session(user_id)
        user_sess.add("user", text)

        # Notify user agent has begun
        await self.send_chat_action(http_session, chat_id, "typing")

        loop = asyncio.get_running_loop()
        tool_updates = []

        def on_tool(t_name: str, t_args: str):
            tool_msg = f"⚡ `Running: {t_name}`"
            tool_updates.append(tool_msg)
            # Trigger typing action in telegram
            asyncio.run_coroutine_threadsafe(self.send_chat_action(http_session, chat_id, "typing"), loop)

        def on_result(t_name: str, t_res: str):
            pass

        agent_mode = conf.get("agent_enabled", True)
        if agent_mode:
            messages = user_sess.as_messages()
            if not user_sess.system_prompt:
                dyn_prompt = get_system_prompt(user_sess)
                sys_msg = {"role": "system", "content": dyn_prompt}
                agent_msgs = [sys_msg] + messages if messages and messages[0]["role"] != "system" else messages
            else:
                agent_msgs = messages

            agent = CodeAgent(
                server=active_s,
                model=model_name,
                session=user_sess,
                stream_fn=chat_stream,
                on_text=lambda _: None,
                on_tool=on_tool,
                on_result=on_result,
            )
            self.active_agent = agent

            # Periodic typing action while agent processes turns
            stop_typing = False

            async def typing_pinger():
                while not stop_typing:
                    await self.send_chat_action(http_session, chat_id, "typing")
                    await asyncio.sleep(4.5)

            typing_task = asyncio.create_task(typing_pinger())

            try:
                final_res = await asyncio.to_thread(agent.run, agent_msgs)
            except Exception as e:
                final_res = f"❌ Agent Error: {str(e)}"
            finally:
                stop_typing = True
                typing_task.cancel()

            reply_text = final_res or "✓ Task completed."
            await self.send_message(http_session, chat_id, reply_text, reply_to_message_id=message_id)

        else:
            # Direct chat mode
            messages = user_sess.as_messages()
            full_reply = []

            def run_direct():
                for chunk in chat_stream(active_s, model_name, messages):
                    full_reply.append(chunk)

            await asyncio.to_thread(run_direct)
            final_str = "".join(full_reply)
            user_sess.add("assistant", final_str)
            await self.send_message(http_session, chat_id, final_str, reply_to_message_id=message_id)

    async def _poll_loop(self) -> None:
        """Long-polling update loop for Telegram Bot API."""
        async with aiohttp.ClientSession() as http_session:
            # Test bot token and get identity
            me_res = await self._api_call(http_session, "getMe")
            if not me_res.get("ok"):
                logger.error("Invalid Telegram token or unreachable API: %s", me_res.get("description"))
                print(f"[Telegram Error] Invalid token or connection failed: {me_res.get('description')}")
                return

            self.bot_info = me_res.get("result", {})
            bot_username = self.bot_info.get("username", "DCT_Bot")
            print(f"[Telegram] Connected as @{bot_username} (ID: {self.bot_info.get('id')})")

            offset = 0
            while self._running:
                try:
                    payload = {"offset": offset, "timeout": 25, "allowed_updates": ["message"]}
                    data = await self._api_call(http_session, "getUpdates", payload)
                    if not data.get("ok"):
                        await asyncio.sleep(3)
                        continue

                    updates = data.get("result", [])
                    for update in updates:
                        update_id = update["update_id"]
                        offset = max(offset, update_id + 1)

                        msg = update.get("message")
                        if not msg:
                            continue

                        chat_id = msg["chat"]["id"]
                        user = msg.get("from", {})
                        user_id = user.get("id", chat_id)
                        message_id = msg["message_id"]

                        # Auth check
                        if not self.is_user_allowed(user):
                            await self.send_message(
                                http_session,
                                chat_id,
                                "⛔ Access Denied. Your Telegram account is not authorized to interact with this DCT-Agent node.",
                                reply_to_message_id=message_id,
                            )
                            continue

                        text = msg.get("text", "").strip()

                        # Photo / Document attachment handling
                        if msg.get("photo") or msg.get("document"):
                            file_id = ""
                            file_name = "attachment"
                            if msg.get("photo"):
                                file_id = msg["photo"][-1]["file_id"]
                                file_name = f"photo_{int(time.time())}.jpg"
                            elif msg.get("document"):
                                file_id = msg["document"]["file_id"]
                                file_name = msg["document"].get("file_name", f"doc_{int(time.time())}")

                            # Download file
                            f_info = await self._api_call(http_session, "getFile", {"file_id": file_id})
                            if f_info.get("ok"):
                                file_path = f_info["result"]["file_path"]
                                download_url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
                                os.makedirs("downloads", exist_ok=True)
                                local_path = os.path.join(os.getcwd(), "downloads", file_name)
                                async with http_session.get(download_url) as dl_resp:
                                    with open(local_path, "wb") as f:
                                        f.write(await dl_resp.read())
                                caption = msg.get("caption", "").strip()
                                prompt = f"Received file saved at '{local_path}'. {caption}"
                                await self.handle_text_message(http_session, chat_id, user_id, prompt, message_id)
                            continue

                        if not text:
                            continue

                        # Command routing
                        if text.startswith("/"):
                            parts = text.split(" ", 1)
                            cmd = parts[0].split("@")[0]  # strip @botname
                            args = parts[1] if len(parts) > 1 else ""
                            await self.handle_command(http_session, chat_id, user_id, cmd, args, message_id)
                        else:
                            await self.handle_text_message(http_session, chat_id, user_id, text, message_id)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.exception("Error in Telegram polling loop: %s", e)
                    await asyncio.sleep(2)

    def start(self) -> None:
        """Start polling loop synchronously (blocks current thread)."""
        if not self.token:
            print("[Telegram Error] No bot token provided. Set TELEGRAM_BOT_TOKEN or configure telegram_token.")
            return
        self._running = True
        try:
            asyncio.run(self._poll_loop())
        except KeyboardInterrupt:
            self.stop()

    def start_background(self) -> threading.Thread:
        """Start polling in a background daemon thread."""
        self._running = True
        thread = threading.Thread(target=self.start, daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        """Signal polling loop to terminate."""
        self._running = False


_global_bot: Optional[TelegramBot] = None
_bot_thread: Optional[threading.Thread] = None


def get_telegram_bot() -> Optional[TelegramBot]:
    global _global_bot
    return _global_bot


def start_telegram_bridge(token: Optional[str] = None, allowed_users: Optional[List[str]] = None) -> TelegramBot:
    global _global_bot, _bot_thread
    if _global_bot is not None and _global_bot._running:
        return _global_bot

    bot = TelegramBot(token=token, allowed_users=allowed_users)
    _global_bot = bot
    _bot_thread = bot.start_background()
    return bot


def stop_telegram_bridge() -> None:
    global _global_bot
    if _global_bot:
        _global_bot.stop()
        _global_bot = None
