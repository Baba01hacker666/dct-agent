"""Tests for Discord bot bridge."""

import pytest
from dct.discord.bot import DiscordBot


def test_discord_bot_init():
    bot = DiscordBot(token="test_token", allowed_users=["alice", "12345"])
    assert bot.token == "test_token"
    assert bot.allowed_users == ["alice", "12345"]


def test_discord_bot_user_allowed():
    bot = DiscordBot(token="test", allowed_users=["alice", "12345"])
    assert bot.is_user_allowed({"id": 12345, "username": "other"})
    assert bot.is_user_allowed({"id": 99999, "username": "Alice"})
    assert not bot.is_user_allowed({"id": 99999, "username": "bob"})


def test_discord_bot_empty_whitelist_allows_all():
    bot = DiscordBot(token="test", allowed_users=[])
    assert bot.is_user_allowed({"id": 99999, "username": "random"})


@pytest.mark.asyncio
async def test_discord_bot_handle_command_help():
    bot = DiscordBot(token="test")
    res = await bot.handle_command("chan1", {"id": 1}, "!help")
    assert "DCT Agent Discord Bridge" in res
    assert "!status" in res
    assert "!servers" in res


@pytest.mark.asyncio
async def test_discord_bot_handle_command_clear():
    bot = DiscordBot(token="test")
    session = bot.get_channel_session("chan1")
    session.add("user", "hi")
    assert len(session.messages) > 0

    res = await bot.handle_command("chan1", {"id": 1}, "!clear")
    assert "cleared" in res.lower()
    assert len(session.messages) == 0
