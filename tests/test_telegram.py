import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from dct.core.config import Config
from dct.core.registry import ServerRegistry
from dct.telegram.bot import TelegramBot, start_telegram_bridge, stop_telegram_bridge, get_telegram_bot


def test_telegram_bot_init_and_whitelist():
    # Test allowed_users whitelist
    bot = TelegramBot(token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11", allowed_users=["12345", "testuser", "@admin"])
    
    # 1. Allowed user ID
    assert bot.is_user_allowed({"id": 12345, "username": "other"}) is True
    assert bot.is_user_allowed({"id": "12345"}) is True

    # 2. Allowed username (with and without @)
    assert bot.is_user_allowed({"id": 99999, "username": "testuser"}) is True
    assert bot.is_user_allowed({"id": 88888, "username": "admin"}) is True

    # 3. Disallowed user
    assert bot.is_user_allowed({"id": 77777, "username": "stranger"}) is False

    # 4. Open mode (no allowed_users)
    bot_open = TelegramBot(token="test_token", allowed_users=[])
    assert bot_open.is_user_allowed({"id": 77777, "username": "stranger"}) is True


@pytest.mark.asyncio
async def test_telegram_slash_commands(tmp_path):
    conf_file = str(tmp_path / "config.json")
    c = Config(conf_file)
    c.set("default_server", "local")
    c.save()

    registry = ServerRegistry(str(tmp_path / "servers.json"))
    registry.add("127.0.0.1", 11434, "local")
    registry.save()

    bot = TelegramBot(token="test_token", registry=registry)

    # Mock HTTP session
    mock_http = AsyncMock()
    mock_http.post = MagicMock()

    async def mock_api_call(http_sess, method, data=None):
        return {"ok": True, "result": {"message_id": 101}}

    bot._api_call = AsyncMock(side_effect=mock_api_call)
    bot.send_message = AsyncMock(return_value={"ok": True})

    # Test /start command
    await bot.handle_command(mock_http, chat_id=123, user_id=123, cmd="/start", args="", message_id=1)
    bot.send_message.assert_called_once()
    assert "DCT-Agent Telegram Bridge" in bot.send_message.call_args[0][2]

    # Test /status command
    bot.send_message.reset_mock()
    await bot.handle_command(mock_http, chat_id=123, user_id=123, cmd="/status", args="", message_id=1)
    bot.send_message.assert_called_once()
    assert "DCT-Agent Status" in bot.send_message.call_args[0][2]

    # Test /plan command (toggle)
    bot.send_message.reset_mock()
    await bot.handle_command(mock_http, chat_id=123, user_id=123, cmd="/plan", args="", message_id=1)
    bot.send_message.assert_called_once()
    assert "Plan Mode Activated" in bot.send_message.call_args[0][2]

    # Test /clear command
    bot.send_message.reset_mock()
    await bot.handle_command(mock_http, chat_id=123, user_id=123, cmd="/clear", args="", message_id=1)
    bot.send_message.assert_called_once()
    assert "cleared" in bot.send_message.call_args[0][2]


@pytest.mark.asyncio
async def test_telegram_message_chunking():
    bot = TelegramBot(token="test_token")
    mock_http = AsyncMock()

    sent_payloads = []

    async def mock_api_call(http_sess, method, data=None):
        sent_payloads.append((method, data))
        return {"ok": True, "result": {"message_id": 101}}

    bot._api_call = AsyncMock(side_effect=mock_api_call)

    # 1. Short message
    await bot.send_message(mock_http, chat_id=123, text="Hello world")
    assert len(sent_payloads) == 1
    assert sent_payloads[0][1]["text"] == "Hello world"

    # 2. Long message (> 4000 characters)
    sent_payloads.clear()
    long_text = "A" * 9000
    await bot.send_message(mock_http, chat_id=123, text=long_text)
    assert len(sent_payloads) >= 3
    reconstructed = "".join(p[1]["text"] for p in sent_payloads)
    assert reconstructed == long_text


def test_telegram_bridge_lifecycle():
    stop_telegram_bridge()
    assert get_telegram_bot() is None

    # Test lifecycle functions with mock start
    with patch.object(TelegramBot, "start_background", return_value=MagicMock()):
        bot = start_telegram_bridge(token="mock_token_123")
        assert bot is not None
        assert get_telegram_bot() == bot
        stop_telegram_bridge()
        assert get_telegram_bot() is None
