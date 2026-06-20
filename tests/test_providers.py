from unittest.mock import patch, MagicMock
from dct.core.registry import Server
from dct.core import client
from dct.core.openrouter import _extract_stream_text


def test_ollama_auth_headers():
    from dct.core.ollama import _auth_headers, _request_kwargs

    # No auth
    s = Server("s1", "localhost", 11434)
    assert _auth_headers(s) == {}

    # With API key
    s2 = Server("s2", "host", 443, api_key="mykey123")
    assert _auth_headers(s2) == {"Authorization": "Bearer mykey123"}

    # TLS verify
    s3 = Server("s3", "host", 443, tls_verify=False)
    kwargs = _request_kwargs(s3, {"timeout": 5})
    assert kwargs["verify"] is False
    assert kwargs["timeout"] == 5


def test_read_image():
    import tempfile
    import os
    from dct.tools.image import read_image

    # Non-existent file
    r = read_image("/nonexistent/path.png")
    assert not r.ok
    assert "not found" in r.message

    # Unsupported extension
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"hello")
        f.flush()
        tmp_path = f.name
    try:
        r = read_image(tmp_path)
        assert not r.ok
        assert "unsupported" in r.message
    finally:
        os.unlink(tmp_path)

    # Valid PNG (1x1 pixel)
    import struct
    import zlib

    def make_png():
        # Minimal valid PNG: 1x1 red pixel
        raw_data = b"\x00" + b"\xff\x00\x00"  # filter=0, R=255, G=0, B=0
        compressed = zlib.compress(raw_data)

        def chunk(ctype, data):
            c = ctype + data
            crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
            return struct.pack(">I", len(data)) + c + crc
        ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        return (b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", ihdr)
                + chunk(b"IDAT", compressed)
                + chunk(b"IEND", b""))

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(make_png())
        f.flush()
        png_path = f.name
    try:
        r = read_image(png_path)
        assert r.ok
        assert r.data_url.startswith("data:image/png;base64,")
        assert r.mime_type == "image/png"
    finally:
        os.unlink(png_path)


def test_ollama_chat_with_images():
    from dct.core import ollama
    s = Server("s1", "localhost", 11434)
    msgs = [{"role": "user", "content": "What is this?"}]

    with patch("dct.core.ollama._post_stream") as mock_stream:
        mock_stream.return_value = iter([{
            "message": {"content": "a red pixel"},
            "done": True,
        }])
        chunks = list(ollama.chat_stream(s, "llava", msgs, images=["data:image/png;base64,AAAA"]))
        assert "a red pixel" in "".join(chunks)
        # Verify images were attached to the last user message
        call_args = mock_stream.call_args
        payload = call_args[0][1]  # second positional arg is payload
        assert payload["messages"][-1].get("images") == ["data:image/png;base64,AAAA"]


def test_chat_once_openrouter():
    s = Server("or1", "openrouter.ai", 443, provider="openrouter", api_key="test_key")

    with patch("dct.core.http.client.post") as mock_post:
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


def test_shell_rewind_logic():
    from dct.agent.session import Session
    session = Session()
    session.add("user", "Hello")
    session.add("assistant", "Hi")
    session.add("user", "Help me")
    session.add("assistant", "Sure")

    # Rewind should remove the last user message and subsequent assistant messages
    assert session.rewind()
    assert len(session.messages) == 2
    assert session.messages[0]["content"] == "Hello"
    assert session.messages[1]["content"] == "Hi"
