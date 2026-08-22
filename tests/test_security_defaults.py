"""Security regression tests."""

import inspect

from dct.web.server import run_server, DEFAULT_HOST


def test_web_server_defaults_to_loopback():
    """The web UI executes tools, git commands and mutates config with no
    auth by default — it must default to binding localhost, not 0.0.0.0."""
    assert DEFAULT_HOST == "127.0.0.1"
    sig = inspect.signature(run_server)
    assert sig.parameters["host"].default == "127.0.0.1"


def test_cli_web_subcommand_defaults_to_loopback():
    from dct.cli.main import build_parser

    parser = build_parser()
    # Parse only the web subcommand defaults
    args = parser.parse_args(["web"])
    assert args.host == "127.0.0.1"


def test_auth_middleware_allows_when_no_token(monkeypatch):
    import asyncio
    from dct.core.config import Config
    from aiohttp import web
    from dct.web.auth import auth_middleware

    async def _run():
        monkeypatch.setattr(Config, "get", lambda self, k, d=None: "")

        async def handler(req):
            return web.Response(text="ok")

        req = type("Req", (), {"path": "/api/status", "headers": {}})()
        res = await auth_middleware(req, handler)
        assert res.text == "ok"

    asyncio.run(_run())


def test_auth_middleware_blocks_without_token(monkeypatch):
    import asyncio
    from dct.core.config import Config
    from aiohttp import web
    from dct.web.auth import auth_middleware

    async def _run():
        monkeypatch.setattr(
            Config,
            "get",
            lambda self, k, d=None: "secret" if k == "web_auth_token" else "",
        )

        called = False

        async def handler(req):
            nonlocal called
            called = True
            return web.Response(text="ok")

        req = type("Req", (), {"path": "/api/status", "headers": {}})()
        res = await auth_middleware(req, handler)
        assert res.status == 401
        assert not called

    asyncio.run(_run())


def test_auth_middleware_accepts_bearer_and_non_api_passthrough(monkeypatch):
    import asyncio
    from dct.core.config import Config
    from aiohttp import web
    from dct.web.auth import auth_middleware

    async def _run():
        monkeypatch.setattr(
            Config,
            "get",
            lambda self, k, d=None: "secret" if k == "web_auth_token" else "",
        )

        async def handler(req):
            return web.json_response({"ok": True})

        # Non-API paths bypass auth entirely
        req = type("Req", (), {"path": "/", "headers": {}})()
        res = await auth_middleware(req, handler)
        assert res.status == 200

        req = type(
            "Req",
            (),
            {
                "path": "/api/status",
                "headers": {"Authorization": "Bearer secret"},
            },
        )()
        res = await auth_middleware(req, handler)
        assert res.status == 200

    asyncio.run(_run())
