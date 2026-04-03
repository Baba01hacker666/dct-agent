"""
dct.core.probe
Server probing — cascading health check across all Ollama endpoints.
Supports single and parallel (threaded) probing.
"""

from __future__ import annotations
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

import requests
from requests.exceptions import (
    ConnectionError as RConnErr,
    Timeout,
    RequestException,
)

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
    _t_start = time.time()

    if srv.provider == "openrouter":
        try:
            t0 = time.time()
            r = requests.get(f"{base}/api/v1/models", timeout=PROBE_TIMEOUT)
            ms = int((time.time() - t0) * 1000)
            if r.status_code == 200:
                data = r.json()
                srv.latency_ms = ms
                srv.status = "online"
                # To prevent huge list, maybe just keep top models or empty if we don't want to sync all OpenRouter models.
                # Actually, letting user provide the model name is better, but we will store top 100 or empty.
                models_data = data.get("data", [])
                srv.models = [
                    m.get("id") for m in models_data
                ]  # Store all for auto-complete
                srv.version = "OpenRouter v1"
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

    for path in PROBE_ORDER:
        try:
            t0 = time.time()
            r = requests.get(f"{base}{path}", timeout=PROBE_TIMEOUT)
            ms = int((time.time() - t0) * 1000)
            if r.status_code == 200:
                try:
                    data = r.json()
                except Exception:
                    data = {}

                srv.latency_ms = ms
                srv.status = "online"

                # Harvest models from /api/tags
                if path == "/api/tags" and "models" in data:
                    srv.models = [m["name"] for m in data["models"]]
                else:
                    # Fetch tags separately if we hit a different endpoint
                    # first
                    try:
                        tr = requests.get(f"{base}/api/tags", timeout=PROBE_TIMEOUT)
                        if tr.ok:
                            srv.models = [
                                m["name"] for m in tr.json().get("models", [])
                            ]
                    except Exception:
                        pass

                # Harvest version
                try:
                    vr = requests.get(f"{base}/api/version", timeout=2)
                    if vr.ok:
                        srv.version = vr.json().get("version", "")
                except Exception:
                    pass

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
    rows = []
    for path in PROBE_ORDER:
        try:
            t0 = time.time()
            r = requests.get(f"{base}{path}", timeout=PROBE_TIMEOUT)
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
