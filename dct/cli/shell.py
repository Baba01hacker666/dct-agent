"""
dct.cli.shell
Main interactive REPL. Handles all /commands, chat routing,
agent mode toggling, broadcast, and status display.
"""

from __future__ import annotations

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles import Style
import os
import threading
from typing import Optional

from rich.panel import Panel

from dct.core.theme import (
    con,
    C,
    ok,
    err,
    info,
    warn,
    hint,
    section,
    ts,
    server_tag,
)
from dct.core.registry import ServerRegistry, Server
from dct.core.probe import probe_server, probe_all, probe_endpoints_detail
from dct.core.client import (
    chat_stream,
    list_models,
    pull_stream,
    delete_model,
    show_model,
)
from dct.agent.session import Session
from dct.agent.codeagent import CodeAgent
from dct.tools.executor import dispatch
from dct.tools.files import read_file, write_file
from dct.tools.web import fetch_url, search_ddg
from dct.cli.display import (
    show_servers,
    show_models,
    show_all_models,
    show_probe_detail,
    show_probe_summary,
    show_diff,
    show_exec_result,
)
from dct.cli.help import show_help


class Shell:
    def __init__(self, registry: ServerRegistry):
        self.registry = registry
        self.session = Session()
        self.active: Optional[Server] = None
        self.model: str = ""
        self.agent_mode: bool = False

    # ── Status bar ──────────────────────────────────────────────────────────
    def _status_bar(self) -> str:
        if not self.active:
            return f"  [{C['warn']}]no active server · /add <host> <port> [alias][/{C['warn']}]"
        st = self.active.status
        stc = C["ok"] if st == "online" else C["err"] if st == "offline" else C["dim"]
        ag = f"  [{C['purple']}][AGENT][/{C['purple']}]" if self.agent_mode else ""
        return (
            f"  [{C['accent']}]{self.active.alias}[/{C['accent']}]"
            f"  [{stc}]●[/{stc}]"
            f"  [{C['dim']}]{self.active.host}:{self.active.port}[/{C['dim']}]"
            f"  [{C['fg']}]› {self.model}[/{C['fg']}]"
            f"  [{C['dim']}]{self.session.user_turns}t · ~{
                self.session.token_estimate
            }tok[/{C['dim']}]"
            f"{ag}"
        )

    # ── Init: pick server + model ────────────────────────────────────────────
    def init(self, init_alias: str = "", init_model: str = ""):
        route = self.registry.route(init_model, init_alias)
        if route:
            self.active, self.model = route
        elif self.registry.servers:
            self.active = self.registry.servers[0]
            self.model = self.active.best_model(init_model)
        # No servers at all — will prompt user to /add

        con.print()
        online = len(self.registry.online())
        total = len(self.registry.servers)
        model_count = sum(len(s.models) for s in self.registry.servers)

        con.print(
            Panel(
                f"[{C['accent']}]servers:[/{C['accent']}]  [{C['fg']}]{total} registered · {online} online[/{C['fg']}]\n"
                f"[{C['accent']}]models:[/{C['accent']}]   [{C['fg']}]{model_count} total across all servers[/{C['fg']}]\n"
                f"[{C['accent']}]active:[/{C['accent']}]   [{C['fg']}]{self.active.alias + ' · ' + self.model if self.active else 'none — /add a server first'}[/{C['fg']}]\n"
                f"[{C['dim']}]type /help for all commands · just type to chat[/{C['dim']}]",
                border_style=C["dim"],
                title=f"[{C['accent']}]dct-agent  ·  doraemon cyber team[/{C['accent']}]",
                title_align="left",
            )
        )

        if not self.registry.servers:
            hint("no servers yet. example:")
            hint("  /add localhost 11434 local")
            hint("  /add 192.168.1.10 11434 home")

    # ── Main REPL ────────────────────────────────────────────────────────────

    def run(self):
        history_file = os.path.join(
            os.path.expanduser("~"), ".config", "dct", "history"
        )
        os.makedirs(os.path.dirname(history_file), exist_ok=True)
        session = PromptSession(
            history=FileHistory(history_file),
            auto_suggest=AutoSuggestFromHistory(),
        )

        style = Style.from_dict(
            {
                "bottom-toolbar": "#333333 bg:#ffeb3b",
            }
        )

        while True:
            try:
                con.print()
                con.print(self._status_bar())
                con.print(f"  [{C['dim']}]{'─' * 66}[/{C['dim']}]")
                raw = session.prompt("  › ", multiline=False, style=style)
                raw = raw.strip()

            except (KeyboardInterrupt, EOFError):
                con.print(f"\n  [{C['dim']}]goodbye[/{C['dim']}]")
                self.registry.save()
                break

            if not raw:
                continue

            lo = raw.lower()
            parts = raw.split()

            # ── exit ─────────────────────────────────────────────────────
            if lo in ("/exit", "/quit", "/q"):
                con.print(f"  [{C['dim']}]goodbye[/{C['dim']}]")
                self.registry.save()
                break

            # ── help ─────────────────────────────────────────────────────
            elif lo.startswith("/help"):
                topic = raw[5:].strip()
                show_help(topic)

            # ── servers ──────────────────────────────────────────────────
            elif lo == "/servers":
                show_servers(self.registry)

            # ── probe ────────────────────────────────────────────────────
            elif lo == "/probe":
                con.print(
                    f"  [{C['dim']}]probing {len(self.registry.servers)} server(s)…[/{C['dim']}]"
                )
                results = probe_all(self.registry)
                show_probe_summary(results, self.registry)
                # Refresh active ref
                if self.active:
                    self.active = self.registry.resolve(self.active.alias)

            elif lo.startswith("/probe "):
                target = raw[7:].strip()
                s = self.registry.resolve(target)
                if not s:
                    err(f"server not found: {target}")
                    continue
                con.print(f"\n  [{C['dim']}]probing {server_tag(s)}…[/{C['dim']}]")
                rows = probe_endpoints_detail(s)
                show_probe_detail(rows)
                probe_server(s)
                self.registry.save()
                if s.status == "online":
                    ok(f"online  ·  {len(s.models)} model(s)  ·  {s.latency_ms}ms")
                else:
                    err("offline")

            # ── add ──────────────────────────────────────────────────────
            elif lo.startswith("/add "):
                toks = parts[1:]
                if len(toks) < 2:
                    warn("usage: /add <host> <port> [alias] [note]")
                    continue
                host = toks[0]
                try:
                    port = int(toks[1])
                except ValueError:
                    err("port must be a number")
                    continue
                alias = toks[2] if len(toks) > 2 else ""
                note = " ".join(toks[3:]) if len(toks) > 3 else ""
                srv = self.registry.add(host, port, alias, note)
                con.print(f"  [{C['dim']}]probing {srv.alias}…[/{C['dim']}]", end=" ")
                res = probe_server(srv)
                self.registry.save()
                if res["ok"]:
                    con.print(f"[{C['ok']}]online[/{C['ok']}]")
                    ok(f"added: {server_tag(srv)}  ·  {len(srv.models)} model(s)")
                    if not self.active:
                        self.active = srv
                        self.model = srv.best_model()
                        ok(f"auto-selected as active server  ·  model: {self.model}")
                else:
                    con.print(f"[{C['err']}]offline[/{C['err']}]")
                    warn(f"added as {srv.alias} but unreachable — saved for later")

            # ── remove ───────────────────────────────────────────────────
            elif lo.startswith("/remove "):
                target = raw[8:].strip()
                s = self.registry.resolve(target)
                if not s:
                    err(f"server not found: {target}")
                    continue
                if self.active and s == self.active:
                    warn("removing active server — switching to next online")
                    self.active = None
                self.registry.remove(s)
                ok(f"removed {target}")
                if not self.active:
                    self.active = self.registry.first_online()
                    if self.active:
                        self.model = self.active.best_model(self.model)
                        info(f"auto-switched to {self.active.alias} · {self.model}")

            # ── use ──────────────────────────────────────────────────────
            elif lo.startswith("/use "):
                target = raw[5:].strip()
                s = self.registry.resolve(target)
                if not s:
                    err(f"server not found: {target}")
                    continue
                if s.status == "unknown":
                    con.print(f"  [{C['dim']}]probing…[/{C['dim']}]", end=" ")
                    probe_server(s)
                    self.registry.save()
                    con.print(
                        f"[{C['ok'] if s.status == 'online' else C['err']}]{s.status}[/{C['ok'] if s.status == 'online' else C['err']}]"
                    )
                self.active = s
                if self.model not in s.models and s.models:
                    self.model = s.models[0]
                    info(f"auto-switched model to {self.model}")
                ok(f"active: {server_tag(s)}")

            # ── model ────────────────────────────────────────────────────
            elif lo.startswith("/model "):
                new_model = raw[7:].strip()
                if (
                    self.active
                    and self.active.models
                    and new_model not in self.active.models
                ):
                    warn(
                        f"{new_model} not in {
                            self.active.alias
                        } model list — sending anyway"
                    )
                self.model = new_model
                ok(f"model → {self.model}")

            # ── models ───────────────────────────────────────────────────
            elif lo == "/models":
                if not self.active:
                    err("no active server")
                    continue
                try:
                    models = list_models(self.active)
                    self.active.models = [m["name"] for m in models]
                    self.registry.save()
                    show_models(models, self.active.alias)
                except Exception as e:
                    err(str(e))

            elif lo.startswith("/models "):
                target = raw[8:].strip()
                s = self.registry.resolve(target)
                if not s:
                    err(f"server not found: {target}")
                    continue
                try:
                    models = list_models(s)
                    s.models = [m["name"] for m in models]
                    self.registry.save()
                    show_models(models, s.alias)
                except Exception as e:
                    err(str(e))

            # ── allmodels ────────────────────────────────────────────────
            elif lo == "/allmodels":
                show_all_models(self.registry)

            # ── show ─────────────────────────────────────────────────────
            elif lo.startswith("/show "):
                if not self.active:
                    err("no active server")
                    continue
                model_name = raw[6:].strip()
                try:
                    d = show_model(self.active, model_name)
                    det = d.get("details", {})
                    section(f"model info: {model_name}")
                    for k, v in [
                        ("family", det.get("family")),
                        ("params", det.get("parameter_size")),
                        ("quant", det.get("quantization_level")),
                        ("format", det.get("format")),
                    ]:
                        if v:
                            info(f"{k:12s} {v}")
                    sys_p = d.get("system", "")
                    if sys_p:
                        section("system prompt")
                        con.print(f"  [{C['dim']}]{sys_p[:500]}[/{C['dim']}]")
                except Exception as e:
                    err(str(e))

            # ── pull ─────────────────────────────────────────────────────
            elif lo.startswith("/pull "):
                toks = parts[1:]
                if len(toks) == 1:
                    target_srv = self.active
                    model_name = toks[0]
                elif len(toks) == 2:
                    target_srv = self.registry.resolve(toks[0])
                    model_name = toks[1]
                else:
                    warn("usage: /pull <model>  or  /pull <alias|#> <model>")
                    continue
                if not target_srv:
                    err("server not found")
                    continue
                self._pull(target_srv, model_name)

            # ── delete ───────────────────────────────────────────────────
            elif lo.startswith("/delete "):
                toks = parts[1:]
                if len(toks) == 1:
                    target_srv = self.active
                    model_name = toks[0]
                elif len(toks) == 2:
                    target_srv = self.registry.resolve(toks[0])
                    model_name = toks[1]
                else:
                    warn("usage: /delete <model>  or  /delete <alias|#> <model>")
                    continue
                if not target_srv:
                    err("server not found")
                    continue
                if delete_model(target_srv, model_name):
                    ok(f"deleted {model_name} from {target_srv.alias}")
                    if model_name in target_srv.models:
                        target_srv.models.remove(model_name)
                        self.registry.save()
                else:
                    err(f"failed to delete {model_name}")

            # ── status ───────────────────────────────────────────────────
            elif lo == "/status":
                show_servers(self.registry)

            # ── clear ────────────────────────────────────────────────────
            elif lo == "/clear":
                self.session.clear()
                ok("history cleared")

            # ── history ──────────────────────────────────────────────────
            elif lo == "/history":
                info(
                    f"{self.session.user_turns} user turns · ~{
                        self.session.token_estimate
                    } tokens estimated"
                )

            # ── system ───────────────────────────────────────────────────
            elif lo.startswith("/system "):
                prompt = raw[8:].strip()
                self.session.set_system(prompt)
                ok(f"system prompt set ({len(prompt)} chars) · history cleared")

            # ── save ─────────────────────────────────────────────────────
            elif lo.startswith("/save "):
                fname = raw[6:].strip()
                try:
                    self.session.save(fname)
                    ok(f"saved → {fname}")
                except Exception as e:
                    err(str(e))

            # ── load ─────────────────────────────────────────────────────
            elif lo.startswith("/load "):
                fname = raw[6:].strip()
                try:
                    self.session = Session.load(fname)
                    ok(f"loaded {fname}  ·  {self.session.user_turns} turns")
                except Exception as e:
                    err(str(e))

            # ── agent mode ───────────────────────────────────────────────
            elif lo in ("/agent", "/agent toggle"):
                self.agent_mode = not self.agent_mode
                state = (
                    f"[{C['ok']}]ON[/{C['ok']}]"
                    if self.agent_mode
                    else f"[{C['dim']}]OFF[/{C['dim']}]"
                )
                ok(f"agent mode {state}")
                if self.agent_mode:
                    hint("model can now run code, read/write files, search the web")
                    hint("type /help agent for details")

            elif lo == "/agent status":
                state = "ON" if self.agent_mode else "OFF"
                info(f"agent mode: {state}")

            # ── direct run ───────────────────────────────────────────────
            elif lo.startswith("/run "):
                toks = parts[1:]
                if len(toks) < 2:
                    warn("usage: /run <python|bash|shell> <code>")
                    continue
                lang = toks[0]
                code = raw.split(None, 2)[2] if len(parts) > 2 else ""
                result = dispatch(lang, code)
                show_exec_result(result)

            # ── direct read ──────────────────────────────────────────────
            elif lo.startswith("/read "):
                path = raw[6:].strip()
                r = read_file(path)
                if not r.ok:
                    err(r.message)
                    continue
                section(f"file: {r.path}")
                lines = r.content.splitlines()
                for i, line in enumerate(lines[:200], 1):
                    con.print(
                        f"  [{C['dim']}]{i:4d}[/{C['dim']}]  [{C['fg']}]{line}[/{C['fg']}]"
                    )
                if len(lines) > 200:
                    info(f"… {len(lines) - 200} more lines")

            # ── direct write ─────────────────────────────────────────────
            elif lo.startswith("/write "):
                path = raw[7:].strip()
                con.print(
                    f"  [{C['dim']}]paste content, end with a line containing only ///) [/{C['dim']}]"
                )
                lines = []
                while True:
                    try:
                        line = input()
                    except EOFError:
                        break
                    if line.rstrip() == "///":
                        break
                    lines.append(line)
                content = "\n".join(lines)
                r = write_file(path, content)
                if not r.ok:
                    err(r.message)
                else:
                    ok(f"written: {r.path}")
                    show_diff(r.diff)

            # ── fetch ────────────────────────────────────────────────────
            elif lo.startswith("/fetch "):
                url = raw[7:].strip()
                con.print(f"  [{C['dim']}]fetching {url}…[/{C['dim']}]")
                r = fetch_url(url)
                if not r.ok:
                    err(r.message)
                    continue
                section(f"fetch: {r.title or r.url}")
                con.print(f"[{C['fg']}]{r.content[:4000]}[/{C['fg']}]")

            # ── search ───────────────────────────────────────────────────
            elif lo.startswith("/search "):
                query = raw[8:].strip()
                con.print(f"  [{C['dim']}]searching: {query}…[/{C['dim']}]")
                results = search_ddg(query)
                if not results:
                    warn("no results")
                    continue
                section(f"search: {query}")
                for i, res in enumerate(results, 1):
                    con.print(
                        f"  [{C['accent']}]{i}.[/{C['accent']}] [{C['fg']}]{res['title']}[/{C['fg']}]\n"
                        f"     [{C['dim']}]{res['url']}[/{C['dim']}]\n"
                        f"     [{C['muted']}]{res['snippet']}[/{C['muted']}]"
                        if i <= 5
                        else f"  [{C['dim']}]{i}. {res['title']}[/{C['dim']}]"
                    )

            # ── broadcast ────────────────────────────────────────────────
            elif lo.startswith("/broadcast ") or lo.startswith("/bc "):
                cut = 11 if lo.startswith("/broadcast ") else 4
                msg_txt = raw[cut:].strip()
                if not msg_txt:
                    warn("usage: /broadcast <message>")
                    continue
                self._broadcast(msg_txt)

            # ── unknown command ───────────────────────────────────────────
            elif raw.startswith("/"):
                warn(f"unknown command: {parts[0]}")
                hint("type /help for all commands")

            # ── regular chat message ──────────────────────────────────────
            else:
                self._chat(raw)

    # ── Chat ────────────────────────────────────────────────────────────────
    def _chat(self, user_text: str):
        if not self.active:
            err("no active server. /add <host> <port> [alias]")
            return

        # Auto-failover if offline
        if self.active.status == "offline":
            warn(f"{self.active.alias} offline — reprobing…")
            probe_server(self.active)
            self.registry.save()
            if self.active.status != "online":
                fallback = self.registry.first_online()
                if fallback:
                    warn(f"failover → {fallback.alias}")
                    self.active = fallback
                    self.model = self.active.best_model(self.model)
                else:
                    err("all servers offline")
                    return

        self.session.add("user", user_text)
        messages = self.session.as_messages()

        if self.agent_mode:
            self._run_agent(messages, user_text)
        else:
            self._stream_reply(messages)

    def _stream_reply(self, messages: list[dict]):
        """Stream a normal chat reply, append to session. Auto failover on network error."""
        con.print(
            f"\n  [{C['accent']}]DCT-AI[/{C['accent']}]"
            f"  [{C['dim']}]{self.active.alias} · {self.model} · {ts()}[/{C['dim']}]"
        )
        con.print(f"  [{C['dim']}]{'─' * 66}[/{C['dim']}]")
        con.print("  ", end="")
        full = ""

        while True:
            try:
                for chunk in chat_stream(self.active, self.model, messages):
                    con.print(f"[{C['fg']}]{chunk}[/{C['fg']}]", end="")
                    full += chunk
                break  # Success!
            except Exception as e:
                import requests

                if isinstance(e, requests.exceptions.RequestException):
                    warn(f"\nConnection to {self.active.alias} lost mid-stream.")
                    # Re-probe and find a fallback
                    probe_server(self.active)
                    self.registry.save()
                    fallback = self.registry.first_online()
                    if fallback and fallback != self.active:
                        self.active = fallback
                        self.model = self.active.best_model(self.model)
                        warn(f"Failing over to {self.active.alias} · {self.model}...")
                        con.print(
                            f"\n  [{C['dim']}]{chr(9472) * 66}[/{C['dim']}]\n  ", end=""
                        )
                        continue  # Retry with new server
                    else:
                        err("All servers offline. Cannot complete request.")
                        break
                else:
                    con.print(f"\n  [{C['err']}]{str(e)}[/{C['err']}]")
                    break
            except KeyboardInterrupt:
                con.print(f"\n  [{C['dim']}]cancelled[/{C['dim']}]")
                break

        con.print()
        if full:
            self.session.add("assistant", full)

    def _run_agent(self, messages: list[dict], user_text: str):
        """Run the agentic loop."""
        from dct.agent.codeagent import get_system_prompt

        # Always re-inject dynamic system prompt unless user set a custom one
        if not self.session.system_prompt:
            dynamic_prompt = get_system_prompt(self.session)
            # Find and replace the system prompt in the messages list, or prepend it
            system_msg = {"role": "system", "content": dynamic_prompt}

            # messages list is a copy of session.messages, but let's be careful
            if messages and messages[0]["role"] == "system":
                agent_msgs = [system_msg] + messages[1:]
            else:
                agent_msgs = [system_msg] + messages
        else:
            agent_msgs = messages

        con.print(
            f"\n  [{C['purple']}][AGENT MODE][/{C['purple']}]  [{C['dim']}]{self.active.alias} · {self.model} · {self.session.mode.upper()} MODE[/{C['dim']}]"
        )

        def _on_text(chunk: str):
            con.print(f"[{C['fg']}]{chunk}[/{C['fg']}]", end="")

        def _on_tool(tool_name: str, _: str):
            con.print()
            con.print(
                f"\n  [{C['yellow']}]⚡ tool:[/{C['yellow']}] [{C['fg']}]{tool_name}[/{C['fg']}]"
            )

        def _on_result(tool_name: str, result: str):
            section(f"result: {tool_name}")
            if len(result) > 2000:
                con.print(f"[{C['code']}]{result[:2000]}[/{C['code']}]")
                info(f"… ({len(result)} chars total)")
            else:
                con.print(f"[{C['code']}]{result}[/{C['code']}]")
            con.print()
            con.print(f"  [{C['dim']}]continuing…[/{C['dim']}]")
            con.print("  ", end="")

        agent = CodeAgent(
            server=self.active,
            model=self.model,
            session=self.session,
            stream_fn=chat_stream,
            on_text=_on_text,
            on_tool=_on_tool,
            on_result=_on_result,
        )
        con.print("  ", end="")
        try:
            final = agent.run(agent_msgs)
            con.print()
            if final:
                self.session.add("assistant", final)
        except KeyboardInterrupt:
            con.print(f"\n  [{C['warn']}]agent interrupted[/{C['warn']}]")
        except Exception as e:
            con.print()
            err(str(e))

    # ── Broadcast ────────────────────────────────────────────────────────────
    def _broadcast(self, msg_text: str):
        targets = self.registry.online()
        if not targets:
            err("no online servers to broadcast to")
            return

        section(f"broadcast → {len(targets)} server(s)")
        replies: dict[str, str] = {}
        lock = threading.Lock()

        def _send(s: Server):
            m = s.best_model(self.model)
            msgs = self.session.as_messages() + [{"role": "user", "content": msg_text}]
            full = ""
            con.print(
                f"\n  [{C['accent']}]{s.alias}[/{C['accent']}]"
                f"  [{C['dim']}]{s.host}:{s.port} · {m} · {ts()}[/{C['dim']}]"
            )
            con.print(f"  [{C['dim']}]{'─' * 66}[/{C['dim']}]")
            con.print("  ", end="")
            try:
                for chunk in chat_stream(s, m, msgs):
                    con.print(f"[{C['fg']}]{chunk}[/{C['fg']}]", end="")
                    full += chunk
                con.print()
            except Exception as e:
                con.print()
                err(f"[{s.alias}] {e}")
            with lock:
                replies[s.alias] = full

        threads = [
            threading.Thread(target=_send, args=(s,), daemon=True) for s in targets
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        con.print()
        info(
            f"broadcast complete — {len([r for r in replies.values() if r])} replies received"
        )

    # ── Pull with progress ───────────────────────────────────────────────────
    def _pull(self, srv: Server, model_name: str):
        con.print(
            f"\n  [{C['accent']}]pull[/{C['accent']}] [{C['fg']}]{model_name}[/{
                C['fg']
            }] → {server_tag(srv)}\n"
        )
        try:
            last_status = ""
            for chunk in pull_stream(srv, model_name):
                status = chunk.get("status", "")
                total = chunk.get("total", 0)
                done = chunk.get("completed", 0)
                if total and done:
                    pct = int(done / total * 100)
                    bar = "█" * (pct // 4) + "░" * (25 - pct // 4)
                    con.print(
                        f"  [{C['dim']}]{bar}[/{C['dim']}] [{C['fg']}]{pct}%[/{C['fg']}]",
                        end="\r",
                    )
                elif status and status != last_status:
                    con.print(f"\n  [{C['dim']}]{status}[/{C['dim']}]", end="")
                    last_status = status
                if chunk.get("status") == "success":
                    con.print()
                    ok(f"{model_name} ready on {srv.alias}")
                    probe_server(srv)
                    self.registry.save()
                    break
        except KeyboardInterrupt:
            warn("pull cancelled")
        except Exception as e:
            err(str(e))
        con.print()
