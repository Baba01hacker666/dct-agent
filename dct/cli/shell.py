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
from dct.cli.clipboard import copy_text


PROMPT_PRESETS: dict[str, str] = {
    "coder": (
        "You are a senior software engineer. Be precise, propose minimal safe changes, "
        "and include short test steps."
    ),
    "security": (
        "You are a security analyst. Focus on threat modeling, abuse paths, detection, "
        "and practical mitigations."
    ),
    "teacher": (
        "You are a patient technical tutor. Explain clearly with examples and a concise summary."
    ),
    "concise": "Answer briefly, with direct actionable output.",
}

# Built-in OpenAI-compatible provider presets — just /add-provider <name> <key>
PROVIDER_PRESETS: dict[str, dict] = {
    "deepseek":     {"base_url": "https://api.deepseek.com",                    "note": "DeepSeek"},
    "qwen":         {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "note": "Alibaba Qwen (DashScope)"},
    "zai":          {"base_url": "https://api.z.ai",                            "note": "Z.ai"},
    "groq":         {"base_url": "https://api.groq.com/openai/v1",              "note": "Groq"},
    "together":     {"base_url": "https://api.together.xyz/v1",                 "note": "Together AI"},
    "openai":       {"base_url": "https://api.openai.com/v1",                   "note": "OpenAI"},
    "mistral":      {"base_url": "https://api.mistral.ai/v1",                   "note": "Mistral AI"},
    "xai":          {"base_url": "https://api.x.ai/v1",                         "note": "xAI Grok"},
    "perplexity":   {"base_url": "https://api.perplexity.ai",                   "note": "Perplexity"},
    "fireworks":    {"base_url": "https://api.fireworks.ai/inference/v1",       "note": "Fireworks AI"},
    "hyperbolic":   {"base_url": "https://api.hyperbolic.xyz/v1",               "note": "Hyperbolic"},
    "cerebras":     {"base_url": "https://api.cerebras.ai/v1",                  "note": "Cerebras"},
    "sambanova":    {"base_url": "https://api.sambanova.ai/v1",                 "note": "SambaNova"},
}

# Agent skill presets — /skill <name> to load a specialized persona
SKILL_PRESETS: dict[str, dict] = {
    "web-design": {
        "prompt": (
            "You are an expert frontend developer and UI/UX designer. "
            "Write clean, accessible, responsive HTML/CSS/JS. Use semantic HTML5, "
            "modern CSS (flexbox/grid/custom properties), and vanilla JS or lightweight frameworks. "
            "Prioritize mobile-first design, performance, and accessibility (a11y). "
            "When building a page, create a complete self-contained file with embedded styles and scripts. "
            "Use attractive color schemes, proper typography, and smooth transitions."
        ),
        "desc": "Frontend web design — HTML, CSS, JS, responsive, accessible UIs",
    },
    "react": {
        "prompt": (
            "You are a React expert. Write idiomatic functional components with hooks. "
            "Use TypeScript when possible. Prefer composition over inheritance. "
            "Keep components small and focused. Use proper state management patterns. "
            "Write clean JSX, handle loading/error/empty states, and include basic accessibility."
        ),
        "desc": "React apps — hooks, TypeScript, component architecture",
    },
    "backend": {
        "prompt": (
            "You are a backend systems engineer. Design robust APIs, database schemas, "
            "and service architectures. Write production-grade code with proper error handling, "
            "logging, validation, and security. Think about scalability, rate limiting, "
            "caching strategies, and idempotency. Use async patterns where appropriate."
        ),
        "desc": "Backend APIs, databases, service architecture",
    },
    "python": {
        "prompt": (
            "You are a Python expert. Write idiomatic, type-annotated Python 3.11+ code. "
            "Use dataclasses, pathlib, f-strings, and modern stdlib features. "
            "Follow PEP 8. Structure code with clear modules. Write thorough docstrings. "
            "Prefer standard library over third-party packages when practical. "
            "Include proper error handling and logging."
        ),
        "desc": "Python — idiomatic, typed, modern patterns",
    },
    "pentest": {
        "prompt": (
            "You are a senior penetration tester and red team operator. "
            "Analyze targets methodically: recon → enumeration → exploitation → post-exploitation. "
            "Focus on practical attack paths, not theoretical CVEs. "
            "When you have access, deepen the foothold — check file upload RCE, credential harvesting, "
            "database access, lateral movement, and privilege escalation. "
            "Prefer living-off-the-land techniques. Minimize footprint. "
            "Always inspect actual HTML/source code before guessing parameters. "
            "Exhaustively mine provided recon data (source code, backups, scan output) before brute force."
        ),
        "desc": "Penetration testing — recon, exploitation, post-exploitation",
    },
    "devops": {
        "prompt": (
            "You are a DevOps/SRE engineer. Work with Docker, Kubernetes, CI/CD pipelines, "
            "infrastructure-as-code (Terraform/Pulumi), and cloud platforms (AWS/GCP/Azure). "
            "Write production-ready configs with proper security hardening. "
            "Think about observability, monitoring, alerting, and cost optimization. "
            "Use shell scripts and Makefiles for task automation."
        ),
        "desc": "DevOps — Docker, K8s, CI/CD, IaC, cloud",
    },
    "data": {
        "prompt": (
            "You are a data engineer/scientist. Write efficient data processing pipelines. "
            "Use pandas, numpy, SQL, and relevant ML libraries. "
            "Think about data quality, schema design, and reproducible analysis. "
            "When exploring data, start with summary statistics and visualization. "
            "Document assumptions and caveats clearly."
        ),
        "desc": "Data engineering and analysis — pandas, SQL, pipelines",
    },
    "bug-hunt": {
        "prompt": (
            "You are a code auditor and bug hunter. Review code for security vulnerabilities, "
            "logic errors, race conditions, resource leaks, and edge cases. "
            "Look for: injection flaws, auth bypass, insecure deserialization, "
            "SSRF, path traversal, privilege escalation, and cryptographic weaknesses. "
            "Suggest concrete fixes with code examples. Prioritize by severity."
        ),
        "desc": "Security code review — find vulnerabilities and bugs",
    },
    "cli-tool": {
        "prompt": (
            "You are a CLI tool developer. Build focused, composable command-line utilities. "
            "Use argparse or click. Follow Unix philosophy: do one thing well, "
            "accept stdin, write to stdout. Support --json/--plain output modes. "
            "Include proper --help, man-style docs, exit codes, and signal handling."
        ),
        "desc": "CLI tool development — argparse, Unix philosophy",
    },
    "refactor": {
        "prompt": (
            "You are a code refactoring specialist. Improve code structure without changing behavior. "
            "Extract functions, reduce nesting, eliminate duplication, improve naming. "
            "Apply design patterns where they simplify (not complicate). "
            "Keep changes minimal and safe — each refactor step should be independently testable. "
            "Preserve existing tests and add tests for untested behavior before refactoring."
        ),
        "desc": "Safe refactoring — structure, patterns, test-first",
    },
}


class Shell:
    def __init__(self, registry: ServerRegistry):
        self.registry = registry
        self.session = Session()
        self.active: Optional[Server] = None
        self.model: str = ""
        from dct.core.config import Config
        self.config = Config()
        self.agent_mode: bool = self.config.get("agent_enabled", True)
        self._probe_stop = threading.Event()
        self._probe_thread: Optional[threading.Thread] = None

    # ── Status bar ──────────────────────────────────────────────────────────
    def _status_bar(self) -> str:
        if not self.active:
            return f"  [{C['warn']}]no active server · /add <host> <port> [alias][/{C['warn']}]"
        st = self.active.status
        stc = C["ok"] if st == "online" else C["err"] if st == "offline" else C["dim"]
        ag = f"  [{C['purple']}][AGENT][/{C['purple']}]" if self.agent_mode else ""
        tok_est = self.session.token_estimate
        turns = self.session.user_turns
        return (
            f"  [{C['accent']}]{self.active.alias}[/{C['accent']}]"
            f"  [{stc}]●[/{stc}]"
            f"  [{C['dim']}]{self.active.host}:{self.active.port}[/{C['dim']}]"
            f"  [{C['fg']}]› {self.model}[/{C['fg']}]"
            f"  [{C['dim']}]{turns}t · ~{tok_est}tok[/{C['dim']}]"
            f"{ag}"
        )

    # ── Init: pick server + model ────────────────────────────────────────────
    def init(self, init_alias: str = "", init_model: str = ""):
        # CLI args override config defaults
        init_alias = init_alias or self.config.get("default_server", "")
        init_model = init_model or self.config.get("default_model", "")
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

        self._start_auto_probe()

    # ── Auto-probe ───────────────────────────────────────────────────────────

    def _start_auto_probe(self):
        interval = self.config.get("auto_probe_interval", 60)
        if interval <= 0:
            return
        self._probe_stop.clear()
        self._probe_thread = threading.Thread(
            target=self._auto_probe_loop, args=(interval,), daemon=True
        )
        self._probe_thread.start()

    def _auto_probe_loop(self, interval: int):
        from dct.core.probe import probe_all
        while not self._probe_stop.wait(interval):
            try:
                results = probe_all(self.registry)
                changed = sum(
                    1 for r in results.values()
                    if r.get("ok") and r.get("endpoint")
                )
                if changed > 0:
                    pass  # silent background refresh
            except Exception:
                pass

    def _stop_auto_probe(self):
        self._probe_stop.set()

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
                "bottom-toolbar": "bg:#1f2937 #f9fafb",
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
                self._stop_auto_probe()
                self.registry.save()
                break

            if not raw:
                continue

            lo = raw.lower()
            parts = raw.split()

            # ── exit ─────────────────────────────────────────────────────
            if lo in ("/exit", "/quit", "/q"):
                con.print(f"  [{C['dim']}]goodbye[/{C['dim']}]")
                self._stop_auto_probe()
                self.registry.save()
                break

            # ── help ─────────────────────────────────────────────────────
            elif lo.startswith("/help"):
                topic = raw[5:].strip()
                show_help(topic)

            # ── rewind ───────────────────────────────────────────────────
            elif lo in ("/rewind", "/back", "/undo"):
                if self.session.rewind():
                    ok("rewound conversation by 1 turn")
                else:
                    warn("nothing to rewind")
                continue

            # ── editai ───────────────────────────────────────────────────
            elif lo == "/editai":
                last_ai_idx = -1
                for i in range(len(self.session.messages) - 1, -1, -1):
                    if self.session.messages[i].get("role") == "assistant":
                        last_ai_idx = i
                        break

                if last_ai_idx == -1:
                    warn("no AI response found to edit")
                    continue

                con.print(f"  [{C['dim']}]editing last AI response (press Esc then Enter to save)[/{C['dim']}]")
                try:
                    edited = session.prompt(
                        "edit> ",
                        default=self.session.messages[last_ai_idx].get("content", ""),
                        multiline=True,
                    )
                    self.session.messages[last_ai_idx]["content"] = edited.strip()
                    ok("AI response updated in session memory")
                except (KeyboardInterrupt, EOFError):
                    warn("edit cancelled")
                continue

            # ── retry ────────────────────────────────────────────────────
            elif lo == "/retry":
                last_user = ""
                for i in range(len(self.session.messages) - 1, -1, -1):
                    if self.session.messages[i].get("role") == "user":
                        last_user = self.session.messages[i].get("content", "")
                        break
                if not last_user:
                    warn("no user prompt found to retry")
                    continue

                self.session.rewind()
                raw = last_user
                con.print(f"  [{C['dim']}]retrying: {raw[:50]}...[/{C['dim']}]")
                # Break out of command if/elif block to process `raw` below
                pass

            # ── commit ───────────────────────────────────────────────────
            elif lo == "/commit":
                import subprocess
                if not os.path.exists(".git"):
                    warn("not a git repository")
                    continue
                diff = subprocess.run(["git", "diff", "--cached"], capture_output=True, text=True).stdout
                if not diff:
                    warn("no staged changes. staging all modified tracked files...")
                    subprocess.run(["git", "add", "-u"])
                    diff = subprocess.run(["git", "diff", "--cached"], capture_output=True, text=True).stdout
                if not diff:
                    warn("no changes to commit")
                    continue
                if len(diff) > 40000:
                    diff = diff[:40000] + "\n...[DIFF TRUNCATED]"

                prompt = (
                    "Generate a concise, conventional git commit message for the following diff.\n"
                    "Do not include any explanations or markdown blocks. Just the message itself.\n"
                    f"DIFF:\n{diff}"
                )
                con.print(f"  [{C['dim']}]generating commit message...[/{C['dim']}]")
                try:
                    from dct.core.client import chat_once
                    msg = chat_once(self.active, self.model, [{"role": "user", "content": prompt}]).strip()
                    if msg.startswith("```"):
                        msg = "\n".join(msg.split("\n")[1:-1]).strip()
                    con.print(f"\n[{C['accent']}]Generated Message:[/{C['accent']}]\n{msg}\n")
                    confirm = session.prompt("Commit with this message? [Y/n/e(dit)]> ").strip().lower()
                    if confirm == 'e':
                        msg = session.prompt("edit> ", default=msg, multiline=True).strip()
                        confirm = 'y'
                    if confirm in ('y', '', 'yes'):
                        subprocess.run(["git", "commit", "-m", msg])
                        ok("committed successfully")
                    else:
                        warn("commit aborted")
                except Exception as e:
                    err(f"failed: {e}")
                continue

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
                # Parse flags
                api_key = ""
                use_tls = False
                no_tls_verify = False
                positional = []
                i = 0
                while i < len(toks):
                    if toks[i] == "--api-key" and i + 1 < len(toks):
                        api_key = toks[i + 1]
                        i += 2
                    elif toks[i] == "--tls":
                        use_tls = True
                        i += 1
                    elif toks[i] == "--no-tls-verify":
                        no_tls_verify = True
                        i += 1
                    else:
                        positional.append(toks[i])
                        i += 1
                toks = positional

                if len(toks) < 2:
                    warn("usage: /add <host> <port> [alias] [note] [--api-key KEY] [--tls] [--no-tls-verify]")
                    continue
                host = toks[0]
                try:
                    port = int(toks[1])
                except ValueError:
                    err("port must be a number")
                    continue
                alias = toks[2] if len(toks) > 2 else ""
                note = " ".join(toks[3:]) if len(toks) > 3 else ""
                srv = self.registry.add(
                    host, port, alias, note,
                    api_key=api_key,
                    tls=use_tls,
                    tls_verify=not no_tls_verify,
                )
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

            # ── add-openai ──────────────────────────────────────────────
            elif lo.startswith("/add-openai "):
                toks = raw[12:].strip().split()
                if len(toks) < 2:
                    warn("usage: /add-openai <base_url> <api_key> [alias] [note]")
                    continue
                base_url = toks[0]
                api_key = toks[1]
                alias = toks[2] if len(toks) > 2 else base_url.split("://")[-1].split("/")[0].split(".")[0]
                note = " ".join(toks[3:]) if len(toks) > 3 else base_url
                srv = self.registry.add(
                    "api", 443, alias, note,
                    provider="openai", api_key=api_key, base_url=base_url,
                )
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
                    warn(f"added {srv.alias} but might be unreachable — saved for later")

            # ── add-provider (convenience) ──────────────────────────────
            elif lo.startswith("/add-provider "):
                toks = raw[14:].strip().split()
                if not toks:
                    warn("usage: /add-provider <name> <api_key> [alias]  —  /add-provider --list")
                    continue
                if toks[0] == "--list":
                    info("built-in provider presets:")
                    for name, p in PROVIDER_PRESETS.items():
                        con.print(f"  [{C['accent']}]{name:12}[/{C['accent']}] [{C['dim']}]{p['base_url']}[/{C['dim']}]  ({p['note']})")
                    continue
                name = toks[0].lower()
                if name not in PROVIDER_PRESETS:
                    err(f"unknown provider: {name}")
                    hint("use /add-provider --list to see built-in presets")
                    hint(f"or /add-openai <base_url> <api_key> for custom endpoints")
                    continue
                if len(toks) < 2:
                    warn(f"usage: /add-provider {name} <api_key> [alias]")
                    continue
                preset = PROVIDER_PRESETS[name]
                api_key = toks[1]
                alias = toks[2] if len(toks) > 2 else name
                srv = self.registry.add(
                    "api", 443, alias, preset["note"],
                    provider="openai", api_key=api_key, base_url=preset["base_url"],
                )
                con.print(f"  [{C['dim']}]probing {srv.alias} ({preset['note']})…[/{C['dim']}]", end=" ")
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
                    warn(f"added {srv.alias} but might be unreachable — saved for later")

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
                    active_alias = self.active.alias
                    warn(
                        f"{new_model} not in {active_alias} model list — sending anyway"
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
                hist_turns = self.session.user_turns
                hist_tok = self.session.token_estimate
                info(f"{hist_turns} user turns · ~{hist_tok} tokens estimated")

            # ── copy ─────────────────────────────────────────────────────
            elif lo == "/copy":
                content = self.session.transcript(include_system=False)
                if not content:
                    warn("nothing to copy yet")
                    continue
                if copy_text(content):
                    ok(
                        f"copied {len(content)} chars to clipboard (session transcript)"
                    )
                else:
                    warn("clipboard unavailable — printing transcript instead")
                    con.print(content)

            # ── system ───────────────────────────────────────────────────
            elif lo.startswith("/system "):
                prompt = raw[8:].strip()
                self.session.set_system(prompt)
                ok(f"system prompt set ({len(prompt)} chars) · history cleared")

            # ── prompt presets ───────────────────────────────────────────
            elif lo == "/prompts":
                section("prompt presets")
                for key, value in PROMPT_PRESETS.items():
                    con.print(
                        f"  [{C['accent']}]{key}[/{C['accent']}]  [{C['dim']}]{value}[/{C['dim']}]"
                    )
                hint("use: /prompt <name>")

            elif lo.startswith("/prompt "):
                preset = raw[8:].strip().lower()
                prompt = PROMPT_PRESETS.get(preset)
                if not prompt:
                    warn(f"unknown preset: {preset}")
                    hint(f"available: {', '.join(PROMPT_PRESETS.keys())}")
                    continue
                self.session.set_system(prompt)
                ok(f"applied system prompt preset: {preset}")

            # ── skill presets ────────────────────────────────────────────
            elif lo == "/skills":
                custom = self.config.get("custom_skills", {})
                section("agent skill presets")
                all_names = sorted(set(list(SKILL_PRESETS.keys()) + list(custom.keys())))
                for key in all_names:
                    if key in custom:
                        s = custom[key]
                        tag = "[*]"
                    else:
                        s = SKILL_PRESETS[key]
                        tag = "   "
                    con.print(
                        f"  [{C['accent']}]{tag} {key:12}[/{C['accent']}] [{C['dim']}]{s['desc']}[/{C['dim']}]"
                    )
                hint("use: /skill <name>  |  /skill add <name> <desc>  |  /skill remove <name>")
                if custom:
                    hint("[*] = custom skill")

            elif lo.startswith("/skill add "):
                rest = raw[11:].strip()
                parts_sk = rest.split(None, 1)
                if len(parts_sk) < 2:
                    warn("usage: /skill add <name> <description>")
                    continue
                name, desc = parts_sk[0].lower(), parts_sk[1]
                if name in SKILL_PRESETS:
                    warn(f"'{name}' is a built-in skill name — choose a different name")
                    continue
                con.print(f"  [{C['dim']}]enter system prompt (end with a line containing only ///)[/{C['dim']}]")
                lines = []
                while True:
                    try:
                        line = input("  ... ")
                    except (KeyboardInterrupt, EOFError):
                        con.print()
                        break
                    if line.strip() == "///":
                        break
                    lines.append(line)
                prompt = "\n".join(lines)
                if not prompt.strip():
                    warn("empty prompt — skill not saved")
                    continue
                custom = dict(self.config.get("custom_skills", {}))
                custom[name] = {"prompt": prompt, "desc": desc}
                self.config.set("custom_skills", custom)
                self.config.save()
                ok(f"custom skill saved: {name}")

            elif lo.startswith("/skill remove "):
                name = raw[15:].strip().lower()
                custom = dict(self.config.get("custom_skills", {}))
                if name not in custom:
                    warn(f"custom skill not found: {name}")
                    continue
                del custom[name]
                self.config.set("custom_skills", custom)
                self.config.save()
                ok(f"removed custom skill: {name}")

            elif lo.startswith("/skill "):
                name = raw[7:].strip().lower()
                custom = self.config.get("custom_skills", {})
                skill = custom.get(name) or SKILL_PRESETS.get(name)
                if not skill:
                    warn(f"unknown skill: {name}")
                    hint(f"built-in: {', '.join(SKILL_PRESETS.keys())}")
                    hint(f"custom: {', '.join(custom.keys())}" if custom else "no custom skills yet — use /skill add")
                    hint("use /skills to see all")
                    continue
                self.session.set_system(skill["prompt"])
                if not self.agent_mode:
                    self.agent_mode = True
                    con.print(f"  [{C['purple']}][AGENT ON][/{C['purple']}]", end=" ")
                tag = "[custom] " if name in custom else ""
                ok(f"loaded skill: {tag}{name} — {skill['desc']}")

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

            # ── config ──────────────────────────────────────────────────
            elif lo == "/config":
                info("config (~/.config/dct/config.json):")
                for k in ["default_server", "default_model", "agent_enabled",
                          "max_agent_turns", "history_limit", "no_probe_on_start",
                          "auto_probe_interval", "custom_skills"]:
                    v = self.config.get(k)
                    con.print(f"  [{C['dim']}]{k}[/{C['dim']}] = [{C['fg']}]{v!r}[/{C['fg']}]")

            elif lo.startswith("/config set "):
                rest = raw[12:].strip()
                parts_cfg = rest.split(None, 1)
                if len(parts_cfg) < 2:
                    warn("usage: /config set <key> <value>")
                    continue
                key, raw_val = parts_cfg[0], parts_cfg[1]
                # Coerce bool/int
                if raw_val.lower() in ("true", "yes", "on"):
                    val = True
                elif raw_val.lower() in ("false", "no", "off"):
                    val = False
                elif raw_val.isdigit():
                    val = int(raw_val)
                else:
                    val = raw_val
                try:
                    self.config.set(key, val)
                    self.config.save()
                    ok(f"config {key} = {val!r}")
                except Exception as e:
                    err(f"failed to set config: {e}")

            # ── goal mode ────────────────────────────────────────────────
            elif lo.startswith("/goal ") or lo == "/goal":
                goal_text = raw[5:].strip()
                if not goal_text:
                    warn("usage: /goal <goal description>")
                    continue
                self._run_goal_mode(goal_text)

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

            elif lo.startswith("/vision ") or lo.startswith("/image "):
                rest = raw.split(None, 1)
                if len(rest) < 2:
                    warn("usage: /vision <image_path> <prompt>")
                    continue
                img_path = rest[1].split(None, 1)[0]
                prompt = rest[1][len(img_path):].strip()
                if not prompt:
                    warn("usage: /vision <image_path> <prompt>")
                    continue
                from dct.tools.image import read_image
                img = read_image(img_path)
                if not img.ok:
                    err(img.message)
                    continue
                if not self.active:
                    err("no active server — /use <alias> first")
                    continue
                con.print(f"  [{C['dim']}]image: {img.path} ({img.mime_type})[/{C['dim']}]")
                con.print(f"  [{C['dim']}]asking {self.model}…[/{C['dim']}]")
                msgs = [{"role": "user", "content": prompt}]
                try:
                    for chunk in chat_stream(self.active, self.model, msgs, images=[img.data_url]):
                        con.print(f"[{C['fg']}]{chunk}[/{C['fg']}]", end="")
                    con.print()
                except Exception as e:
                    err(str(e))

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

            # ── btw ──────────────────────────────────────────────────────
            elif lo.startswith("/btw "):
                msg_txt = raw[5:].strip()
                if not msg_txt:
                    warn("usage: /btw <question>")
                    continue
                self._btw(msg_txt)

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
        if not self.active:
            err("No active server.")
            return
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
        from dct.agent.codeagent import CodeAgent, get_system_prompt

        if not self.active:
            err("No active server.")
            return

        # Always inject the dynamic tool prompt; merge user system prompt as
        # additional preferences so models always receive tool instructions.
        dynamic_prompt = get_system_prompt(
            self.session, user_system_prompt=self.session.system_prompt or ""
        )
        system_msg = {"role": "system", "content": dynamic_prompt}
        non_system_msgs = [m for m in messages if m.get("role") != "system"]
        agent_msgs = [system_msg] + non_system_msgs

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

    def _run_goal_mode(self, goal_text: str):
        """Run agent continuously until it is finished."""
        if not self.active:
            err("No active server.")
            return

        from dct.agent.codeagent import CodeAgent, get_system_prompt
        from dct.core.theme import con, C, ok, warn

        con.print(
            Panel(
                f"[{C['purple']}]Goal:[/{C['purple']}] [{C['fg']}]{goal_text}[/{C['fg']}]\n"
                f"[{C['dim']}]Running autonomously until <tool>DONE</tool> is emitted. Press Ctrl+C to cancel.[/{C['dim']}]",
                border_style=C["purple"],
                title=f"[{C['purple']}]GOAL MODE ACTIVE[/{C['purple']}]",
                title_align="left",
            )
        )

        self.agent_mode = True
        self.session.add("user", goal_text)

        iteration = 1
        max_iterations = 10

        while iteration <= max_iterations:
            messages = self.session.as_messages()
            dynamic_prompt = get_system_prompt(
                self.session, user_system_prompt=self.session.system_prompt or ""
            )
            system_msg = {"role": "system", "content": dynamic_prompt}
            non_system_msgs = [m for m in messages if m.get("role") != "system"]
            agent_msgs = [system_msg] + non_system_msgs

            con.print(
                f"\n  [{C['purple']}][GOAL MODE ITERATION {iteration}][/{C['purple']}]  [{C['dim']}]{self.active.alias} · {self.model} · {self.session.mode.upper()} MODE[/{C['dim']}]"
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

                # Check if the agent called DONE
                if "<tool>DONE</tool>" in final:
                    ok("Goal achieved successfully!")
                    break

                # If not done, auto-inject continue prompt and increment iteration
                iteration += 1
                if iteration <= max_iterations:
                    self.session.add(
                        "user",
                        "[GOAL MODE CONTINUE] You have not yet called <tool>DONE</tool>. "
                        "Please continue working on the goal until it is fully finished."
                    )
                else:
                    warn("Reached maximum goal iterations safety limit. Stopping.")
            except KeyboardInterrupt:
                con.print(f"\n  [{C['dim']}]Goal cancelled by user.[/{C['dim']}]")
                break
            except Exception as e:
                con.print(f"\n  [{C['err']}][GOAL ERROR]: {str(e)}[/{C['err']}]")
                break

    def _btw(self, msg_txt: str):
        """Ask a side question using current context without modifying session history."""
        if not self.active:
            err("No active server.")
            return

        # Build message history with the side question appended
        messages = self.session.as_messages() + [{"role": "user", "content": msg_txt}]

        con.print(
            f"\n  [{C['purple']}][BTW MODE][/{C['purple']}]  [{C['dim']}]{self.active.alias} · {self.model} · {ts()}[/{C['dim']}]"
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
        fg = C['fg']
        con.print(
            f"\n  [{C['accent']}]pull[/{C['accent']}] [{fg}]{model_name}[/{fg}] → {server_tag(srv)}\n"
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
