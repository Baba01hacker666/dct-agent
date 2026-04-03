import re

with open('dct/core/probe.py', 'r') as f:
    content = f.read()

# Add openrouter logic to probe_server
probe_old = """def probe_server(srv: "Server") -> dict:
    \"\"\"
    Try Ollama endpoints in order. First 200 wins.
    Updates srv.status, srv.models, srv.version, srv.latency_ms in place.
    Returns: {"ok": bool, "endpoint": str, "data": dict}
    \"\"\"
    base = srv.base_url()
    _t_start = time.time()"""

probe_new = """def probe_server(srv: "Server") -> dict:
    \"\"\"
    Try endpoints in order. First 200 wins.
    Updates srv.status, srv.models, srv.version, srv.latency_ms in place.
    Returns: {"ok": bool, "endpoint": str, "data": dict}
    \"\"\"
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
                srv.models = [m.get("id") for m in models_data] # Store all for auto-complete
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
"""

content = content.replace(probe_old, probe_new)

with open('dct/core/probe.py', 'w') as f:
    f.write(content)
