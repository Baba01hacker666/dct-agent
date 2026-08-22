"""
dct.web.auth
Optional bearer-token authentication middleware for the web API.

The web UI can execute code, run git commands and mutate configuration.
When `web_auth_token` is set in the DCT config, every /api/* request must
present the token via `Authorization: Bearer <token>` or `X-Auth-Token`.
"""

from __future__ import annotations

from aiohttp import web

from dct.core.config import Config


@web.middleware
async def auth_middleware(request: web.Request, handler):
    path = request.path
    if not path.startswith("/api/"):
        return await handler(request)

    expected = str(Config().get("web_auth_token", "") or "").strip()
    if not expected:
        return await handler(request)

    provided = request.headers.get("X-Auth-Token", "")
    if not provided:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            provided = auth[7:].strip()

    import hmac

    if provided and hmac.compare_digest(provided, expected):
        return await handler(request)

    return web.json_response(
        {"ok": False, "error": "Unauthorized: missing or invalid auth token"},
        status=401,
    )
