"""
dct.web.handlers_integrations
REST handlers for the agent board and Telegram/Discord bridges.
"""

from __future__ import annotations

from aiohttp import web

from dct.web.state import WebState


class IntegrationsHandlersMixin(WebState):
    # ── AI Agents Discussion Board ───────────────────────────────────────────

    async def handle_get_board_messages(
        self, request: web.Request
    ) -> web.Response:
        from dct.tools.board import get_board

        channel = request.query.get("channel", "general")
        limit_str = request.query.get("limit", "50")
        search = request.query.get("search")
        try:
            limit = int(limit_str)
        except ValueError:
            limit = 50
        msgs = get_board().read(channel=channel, limit=limit, search=search)
        return web.json_response({"channel": channel, "messages": msgs})

    async def handle_post_board_message(
        self, request: web.Request
    ) -> web.Response:
        from dct.tools.board import get_board

        try:
            data = await request.json()
        except Exception:
            return self.invalid_json()

        content = data.get("content", "").strip()
        if not content:
            return web.json_response(
                {"ok": False, "error": "Content is required"}, status=400
            )

        sender = data.get("sender", "user").strip() or "user"
        channel = data.get("channel", "general").strip() or "general"
        reply_to = data.get("reply_to")
        tags = data.get("tags", [])

        msg = get_board().post(
            sender=sender,
            content=content,
            channel=channel,
            reply_to=reply_to,
            tags=tags,
        )
        return web.json_response({"ok": True, "message": msg.to_dict()})

    async def handle_get_board_channels(
        self, request: web.Request
    ) -> web.Response:
        from dct.tools.board import get_board

        channels = get_board().list_channels()
        return web.json_response({"channels": channels})

    async def handle_clear_board(self, request: web.Request) -> web.Response:
        from dct.tools.board import get_board

        try:
            data = await request.json()
            channel = data.get("channel")
        except Exception:
            channel = None
        get_board().clear(channel=channel)
        return web.json_response(
            {
                "ok": True,
                "message": f"Cleared board {'#' + channel if channel else 'all channels'}",
            }
        )

    # ── Telegram Bridge ──────────────────────────────────────────────────────

    async def handle_get_telegram(self, request: web.Request) -> web.Response:
        from dct.core.config import Config
        from dct.telegram.bot import get_telegram_bot

        conf = Config()
        bot = get_telegram_bot()
        is_running = bot is not None and bot._running
        token = conf.get("telegram_token", "")
        allowed_users = conf.get("telegram_allowed_users", [])

        return web.json_response(
            {
                "running": is_running,
                "token_configured": bool(token),
                "token_masked": (
                    f"{token[:4]}••••{token[-4:]}"
                    if len(token) > 8
                    else ("configured" if token else "")
                ),
                "allowed_users": allowed_users,
                "bot_info": bot.bot_info if bot and bot._running else {},
            }
        )

    async def handle_start_telegram(
        self, request: web.Request
    ) -> web.Response:
        from dct.core.config import Config
        from dct.telegram.bot import start_telegram_bridge

        try:
            data = await request.json()
        except Exception:
            data = {}

        conf = Config()
        token = data.get("token") or conf.get("telegram_token", "")
        if not token:
            return web.json_response(
                {"ok": False, "error": "Telegram bot token is required"},
                status=400,
            )

        if data.get("token"):
            conf.set("telegram_token", data["token"])
            conf.save()

        allowed = data.get("allowed_users") or conf.get(
            "telegram_allowed_users", []
        )
        start_telegram_bridge(token=token, allowed_users=allowed)
        return web.json_response(
            {"ok": True, "message": "Telegram bridge daemon started"}
        )

    async def handle_stop_telegram(self, request: web.Request) -> web.Response:
        from dct.telegram.bot import stop_telegram_bridge

        stop_telegram_bridge()
        return web.json_response(
            {"ok": True, "message": "Telegram bridge daemon stopped"}
        )

    async def handle_config_telegram(
        self, request: web.Request
    ) -> web.Response:
        from dct.core.config import Config

        try:
            data = await request.json()
        except Exception:
            return self.invalid_json()

        conf = Config()
        if "token" in data:
            conf.set("telegram_token", data["token"].strip())
        if "allowed_users" in data:
            users = data["allowed_users"]
            if isinstance(users, str):
                users = [
                    u.strip().lstrip("@")
                    for u in users.split(",")
                    if u.strip()
                ]
            conf.set("telegram_allowed_users", users)
        conf.save()
        return web.json_response(
            {"ok": True, "message": "Telegram configuration updated"}
        )

    # ── Discord Bot ──────────────────────────────────────────────────────────

    async def handle_get_discord(self, request: web.Request) -> web.Response:
        from dct.core.config import Config
        from dct.discord.bot import get_discord_bot

        conf = Config()
        bot = get_discord_bot()
        is_running = bot is not None and bot._running
        token = conf.get("discord_token", "")
        allowed_users = conf.get("discord_allowed_users", [])

        return web.json_response(
            {
                "running": is_running,
                "token_configured": bool(token),
                "token_masked": (
                    f"{token[:4]}••••{token[-4:]}"
                    if len(token) > 8
                    else ("configured" if token else "")
                ),
                "allowed_users": allowed_users,
                "bot_username": (
                    bot.bot_username if bot and bot._running else None
                ),
            }
        )

    async def handle_start_discord(self, request: web.Request) -> web.Response:
        from dct.core.config import Config
        from dct.discord.bot import start_discord_bridge

        try:
            data = await request.json()
        except Exception:
            data = {}

        conf = Config()
        token = data.get("token") or conf.get("discord_token", "")
        if not token:
            return web.json_response(
                {"ok": False, "error": "Discord bot token is required"},
                status=400,
            )

        if data.get("token"):
            conf.set("discord_token", data["token"])
            conf.save()

        allowed = data.get("allowed_users") or conf.get(
            "discord_allowed_users", []
        )
        start_discord_bridge(
            token=token, allowed_users=allowed, registry=self.registry
        )
        return web.json_response(
            {"ok": True, "message": "Discord bridge daemon started"}
        )

    async def handle_stop_discord(self, request: web.Request) -> web.Response:
        from dct.discord.bot import stop_discord_bridge

        stop_discord_bridge()
        return web.json_response(
            {"ok": True, "message": "Discord bridge daemon stopped"}
        )

    async def handle_config_discord(
        self, request: web.Request
    ) -> web.Response:
        from dct.core.config import Config

        try:
            data = await request.json()
        except Exception:
            return self.invalid_json()

        conf = Config()
        if "token" in data:
            conf.set("discord_token", data["token"].strip())
        if "allowed_users" in data:
            users = data["allowed_users"]
            if isinstance(users, str):
                users = [
                    u.strip().lstrip("@")
                    for u in users.split(",")
                    if u.strip()
                ]
            conf.set("discord_allowed_users", users)
        conf.save()
        return web.json_response(
            {"ok": True, "message": "Discord configuration updated"}
        )
