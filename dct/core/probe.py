"""
dct.core.probe
Server probing — cascading health check across all Ollama endpoints.
Supports single and parallel (threaded) probing.
"""

from __future__ import annotations
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Any
from dct.core.logging import get_logger

import httpx
from httpx import (
    ConnectError as RConnErr,
    TimeoutException as Timeout,
    RequestError as RequestException,
)

logger = get_logger("dct.core.probe")

if TYPE_CHECKING:
    from dct.core.registry import Server, ServerRegistry

PROBE_TIMEOUT = 4
PROBE_ORDER = ["/api/tags", "/api/version", "/api/ps", "/health"]


def probe_server(srv: "Server") -> dict:
    """
    Try endpoints in order. First 200 wins.
    Updates srv.status, srv.models, srv.version, srv.latency_ms in place.
    Returns: {"ok": bool, "endpoint": str, "data": dict}
    """
    base = srv.base_url()
    headers = {}
    if srv.api_key:
        headers["Authorization"] = f"Bearer {srv.api_key}"
    req_kwargs: dict[str, Any] = {"headers": headers}
    if not srv.tls_verify:
        req_kwargs["verify"] = False

    if srv.provider in ("openrouter", "openai"):
        try:
            t0 = time.time()
            r = httpx.get(f"{base}/api/v1/models", timeout=PROBE_TIMEOUT, **req_kwargs)
            ms = int((time.time() - t0) * 1000)
            if r.status_code == 200:
                data = r.json()
                srv.latency_ms = ms
                srv.status = "online"
                models_data = data.get("data", [])
                srv.models = [m.get("id") for m in models_data]
                srv.version = (
                    "OpenRouter v1" if srv.provider == "openrouter" else "OpenAI API"
                )
                return {
                    "ok": True,
                    "endpoint": "/api/v1/models",
                    "data": {"count": len(srv.models)},
                    "latency_ms": ms,
                }
        except (RConnErr, Timeout, RequestException):
            pass
        srv.status = "offline"
        srv.latency_ms = -1
        return {"ok": False, "endpoint": None, "data": {}, "latency_ms": -1}

    tried_tags = False
    for path in PROBE_ORDER:
        if path == "/api/tags":
            tried_tags = True
        try:
            t0 = time.time()
            r = httpx.get(f"{base}{path}", timeout=PROBE_TIMEOUT, **req_kwargs)
            ms = int((time.time() - t0) * 1000)
            if r.status_code == 200:
                try:
                    data = r.json()
                except Exception:
                    data = {}

                srv.latency_ms = ms
                srv.status = "online"

                if path == "/api/tags" and "models" in data:
                    srv.models = [m["name"] for m in data["models"]]
                else:
                    if not tried_tags:
                        try:
                            tr = httpx.get(
                                f"{base}/api/tags", timeout=PROBE_TIMEOUT, **req_kwargs
                            )
                            if tr.is_success:
                                srv.models = [
                                    m["name"] for m in tr.json().get("models", [])
                                ]
                        except Exception:
                            logger.debug(
                                "Failed to fetch tags from %s", base, exc_info=True
                            )

                try:
                    vr = httpx.get(
                        f"{base}/api/version", timeout=PROBE_TIMEOUT, **req_kwargs
                    )
                    if vr.is_success:
                        srv.version = vr.json().get("version", "")
                except Exception:
                    logger.debug("Failed to fetch version from %s", base, exc_info=True)

                return {
                    "ok": True,
                    "endpoint": path,
                    "data": data,
                    "latency_ms": ms,
                }

        except (RConnErr, Timeout, RequestException):
            continue

    srv.status = "offline"
    srv.latency_ms = -1
    return {"ok": False, "endpoint": None, "data": {}, "latency_ms": -1}


def probe_all(registry: "ServerRegistry") -> dict[str, dict]:
    """
    Probe all servers in parallel.
    Returns {alias: probe_result}.
    """
    if not registry.servers:
        return {}

    results: dict[str, dict] = {}
    workers = min(32, len(registry.servers))

    with ThreadPoolExecutor(max_workers=workers) as ex:
        fut_map = {ex.submit(probe_server, s): s for s in registry.servers}
        for fut in as_completed(fut_map):
            s = fut_map[fut]
            try:
                results[s.alias] = fut.result()
            except Exception as e:
                s.status = "offline"
                results[s.alias] = {"ok": False, "error": str(e)}

    registry.save()
    return results


def probe_endpoints_detail(srv: "Server") -> list[dict]:
    """
    Hit every probe endpoint individually and return timing + status for each.
    Used for the detailed /probe <alias> display.
    """
    base = srv.base_url()
    headers = {}
    if srv.api_key:
        headers["Authorization"] = f"Bearer {srv.api_key}"
    req_kwargs: dict[str, Any] = {"headers": headers}
    if not srv.tls_verify:
        req_kwargs["verify"] = False
    rows = []
    for path in PROBE_ORDER:
        try:
            t0 = time.time()
            r = httpx.get(f"{base}{path}", timeout=PROBE_TIMEOUT, **req_kwargs)
            ms = int((time.time() - t0) * 1000)
            try:
                snippet = str(r.json())[:72] + "…"
            except Exception:
                snippet = (r.text or "")[:72]
            rows.append(
                {
                    "path": path,
                    "status": r.status_code,
                    "ok": r.status_code == 200,
                    "latency": ms,
                    "snippet": snippet,
                }
            )
        except (RConnErr, Timeout):
            rows.append(
                {
                    "path": path,
                    "status": 0,
                    "ok": False,
                    "latency": -1,
                    "snippet": "TIMEOUT",
                }
            )
        except RequestException as e:
            rows.append(
                {
                    "path": path,
                    "status": 0,
                    "ok": False,
                    "latency": -1,
                    "snippet": str(e)[:60],
                }
            )
    return rows
