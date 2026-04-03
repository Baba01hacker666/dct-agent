from unittest.mock import patch, MagicMock
from dct.core.registry import Server
from dct.core import client
from dct.core.openrouter import _extract_stream_text


def test_chat_once_openrouter():
    s = Server("or1", "openrouter.ai", 443, provider="openrouter", api_key="test_key")

    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Hello from OpenRouter"}}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        reply = client.chat_once(
            s, "openai/gpt-4o", [{"role": "user", "content": "Hi"}]
        )
        assert reply == "Hello from OpenRouter"

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://openrouter.ai/api/v1/chat/completions"
        assert kwargs["headers"]["Authorization"] == "Bearer test_key"
        assert kwargs["json"]["model"] == "openai/gpt-4o"


def test_extract_stream_text_openrouter_parts():
    delta = {
        "content": [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": " world"},
        ]
    }
    assert _extract_stream_text(delta) == "Hello world"
