import re

with open('dct/cli/shell.py', 'r') as f:
    content = f.read()

# Replace ollama import with client
import_old = """from dct.core.ollama import (
    chat_stream,
    list_models,
    pull_stream,
    delete_model,
    show_model,
)"""

import_new = """from dct.core.client import (
    chat_stream,
    list_models,
    pull_stream,
    delete_model,
    show_model,
)"""

content = content.replace(import_old, import_new)

# Add /add-or logic
add_old = """            elif lo.startswith("/add "):
                parts = raw.split(" ", 4)
                if len(parts) < 3:
                    warn("usage: /add <host> <port> [alias] [note]")
                    continue
                h = parts[1]
                p = parts[2]
                if not p.isdigit():
                    err("port must be an integer")
                    continue
                a = parts[3] if len(parts) > 3 else ""
                n = parts[4] if len(parts) > 4 else ""
                srv = self.registry.add(h, int(p), a, n)
                con.print()
                con.print(f"  [{C['dim']}]probing [/{C['dim']}][{C['accent']}]{h}:{p}[/{C['accent']}]...")
                probe_server(srv)
                self.registry.save()
                if srv.status == "online":
                    ok(f"added {srv.alias} ({len(srv.models)} models, {srv.latency_ms}ms)")
                    if not self.active:
                        self.active = srv
                else:
                    err(f"added {srv.alias} but it appears offline")"""

add_new = """            elif lo.startswith("/add "):
                parts = raw.split(" ", 4)
                if len(parts) < 3:
                    warn("usage: /add <host> <port> [alias] [note]")
                    continue
                h = parts[1]
                p = parts[2]
                if not p.isdigit():
                    err("port must be an integer")
                    continue
                a = parts[3] if len(parts) > 3 else ""
                n = parts[4] if len(parts) > 4 else ""
                srv = self.registry.add(h, int(p), a, n)
                con.print()
                con.print(f"  [{C['dim']}]probing [/{C['dim']}][{C['accent']}]{h}:{p}[/{C['accent']}]...")
                probe_server(srv)
                self.registry.save()
                if srv.status == "online":
                    ok(f"added {srv.alias} ({len(srv.models)} models, {srv.latency_ms}ms)")
                    if not self.active:
                        self.active = srv
                else:
                    err(f"added {srv.alias} but it appears offline")

            # ── add-openrouter ──────────────────────────────────────────
            elif lo.startswith("/add-or ") or lo.startswith("/add-openrouter "):
                parts = raw.split(" ", 2)
                if len(parts) < 2:
                    warn("usage: /add-or <api_key> [alias]")
                    continue
                key = parts[1]
                a = parts[2] if len(parts) > 2 else "openrouter"
                srv = self.registry.add("openrouter.ai", 443, a, "OpenRouter API", provider="openrouter", api_key=key)
                con.print()
                con.print(f"  [{C['dim']}]probing [/{C['dim']}][{C['accent']}]openrouter.ai[/{C['accent']}]...")
                probe_server(srv)
                self.registry.save()
                if srv.status == "online":
                    ok(f"added {srv.alias} ({len(srv.models)} models, {srv.latency_ms}ms)")
                    if not self.active:
                        self.active = srv
                else:
                    err(f"added {srv.alias} but it appears offline (invalid key?)")"""

content = content.replace(add_old, add_new)

with open('dct/cli/shell.py', 'w') as f:
    f.write(content)
