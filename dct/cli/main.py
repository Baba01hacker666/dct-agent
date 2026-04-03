"""
dct.cli.main
Entry point — handles CLI args, bootstraps registry, launches shell.
"""

from __future__ import annotations
import sys
import argparse

from dct.core.theme import con, C, BANNER, ok, err, info, warn
from dct.core.registry import ServerRegistry
from dct.core.probe import probe_server, probe_all, probe_endpoints_detail
from dct.core.client import list_models, pull_stream, delete_model
from dct.cli.display import (
    show_servers,
    show_models,
    show_all_models,
    show_probe_detail,
    show_probe_summary,
)
from dct.cli.shell import Shell


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dct",
        description="Doraemon Cyber Team — multi-server Ollama agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
One-shot commands (non-interactive):
  dct add <host> <port> [alias] [note]    register a server
  dct add-openrouter <key> [alias]        register OpenRouter
  dct remove <alias|#>                    remove a server
  dct servers                             list all servers
  dct probe [alias|#]                     probe servers
  dct models [alias|#]                    list models
  dct pull <alias|#> <model>             pull a model
  dct delete <alias|#> <model>           delete a model

Interactive mode (default):
  dct                                     launch shell (loads saved servers)
  dct -H 192.168.1.10 -p 11434           start with a specific server active
  dct -H 10.0.0.5 -a vps1 -m mistral    set alias and initial model

Inside the shell type /help for all commands.
        """,
    )
    p.add_argument("-H", "--host", default="", help="initial/primary server host")
    p.add_argument(
        "-p",
        "--port",
        default=11434,
        type=int,
        help="initial server port (default: 11434)",
    )
    p.add_argument("-m", "--model", default="", help="preferred model")
    p.add_argument("-a", "--alias", default="", help="alias for -H server")
    p.add_argument(
        "--no-probe",
        action="store_true",
        help="skip initial parallel probe on startup",
    )
    p.add_argument("--version", action="store_true", help="print version and exit")

    sub = p.add_subparsers(dest="cmd")

    # add
    pa = sub.add_parser("add", help="register a server")
    pa.add_argument("host")
    pa.add_argument("port", type=int)
    pa.add_argument("alias", nargs="?", default="")
    pa.add_argument("note", nargs="?", default="")

    # add-openrouter
    po = sub.add_parser("add-openrouter", help="register OpenRouter")
    po.add_argument("key", help="OpenRouter API Key")
    po.add_argument("alias", nargs="?", default="openrouter")

    # remove
    pr = sub.add_parser("remove", help="unregister a server")
    pr.add_argument("target")

    # servers
    sub.add_parser("servers", help="list all servers")

    # probe
    pp = sub.add_parser("probe", help="probe servers")
    pp.add_argument("target", nargs="?", default="")

    # models
    pm = sub.add_parser("models", help="list models")
    pm.add_argument("target", nargs="?", default="")

    # pull
    ppu = sub.add_parser("pull", help="pull a model")
    ppu.add_argument("target")
    ppu.add_argument("model")

    # delete
    pde = sub.add_parser("delete", help="delete a model")
    pde.add_argument("target")
    pde.add_argument("model")

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    registry = ServerRegistry()

    con.print(BANNER)

    if args.version:
        from dct import __version__

        con.print(f"[{C['accent']}]dct-agent[/{C['accent']}] v{__version__}")
        return

    # ── Non-interactive one-shot commands ────────────────────────────────────
    if args.cmd == "add":
        srv = registry.add(args.host, args.port, args.alias, args.note)
        con.print(f"  [{C['dim']}]probing…[/{C['dim']}]", end=" ")
        res = probe_server(srv)
        registry.save()
        if res["ok"]:
            con.print(f"[{C['ok']}]online[/{C['ok']}]")
            ok(
                f"added: {srv.alias}  ({srv.host}:{srv.port})  {len(srv.models)} model(s)"
            )
        else:
            con.print(f"[{C['err']}]offline[/{C['err']}]")
            warn(f"added as {srv.alias} but currently unreachable")
        return

    if args.cmd == "add-openrouter":
        srv = registry.add(
            "openrouter.ai",
            443,
            args.alias,
            "OpenRouter API",
            provider="openrouter",
            api_key=args.key,
        )
        con.print(f"  [{C['dim']}]probing…[/{C['dim']}]", end=" ")
        res = probe_server(srv)
        registry.save()
        if res["ok"]:
            con.print(f"[{C['ok']}]online[/{C['ok']}]")
            ok(f"added: {srv.alias}  ({len(srv.models)} models available)")
        else:
            con.print(f"[{C['err']}]offline[/{C['err']}]")
            warn(f"added {srv.alias} but API key might be invalid")
        return

    if args.cmd == "remove":
        s = registry.resolve(args.target)
        if not s:
            err(f"server not found: {args.target}")
            sys.exit(1)
        registry.remove(s)
        ok(f"removed {args.target}")
        return

    if args.cmd == "servers":
        show_servers(registry)
        return

    if args.cmd == "probe":
        if args.target:
            s = registry.resolve(args.target)
            if not s:
                err(f"server not found: {args.target}")
                sys.exit(1)
            rows = probe_endpoints_detail(s)
            show_probe_detail(rows)
            probe_server(s)
            registry.save()
            if s.status == "online":
                ok(f"online  ·  {len(s.models)} model(s)")
            else:
                err("offline")
        else:
            con.print(
                f"  [{C['dim']}]probing {len(registry.servers)} server(s)…[/{C['dim']}]"
            )
            results = probe_all(registry)
            show_probe_summary(results, registry)
        return

    if args.cmd == "models":
        target = args.target
        if target:
            s = registry.resolve(target)
            if not s:
                err(f"server not found: {target}")
                sys.exit(1)
            try:
                models = list_models(s)
                s.models = [m["name"] for m in models]
                registry.save()
                show_models(models, s.alias)
            except Exception as e:
                err(str(e))
                sys.exit(1)
        else:
            show_all_models(registry)
        return

    if args.cmd == "pull":
        s = registry.resolve(args.target)
        if not s:
            err(f"server not found: {args.target}")
            sys.exit(1)
        con.print(f"\n  [{C['accent']}]pull[/{C['accent']}] {args.model} → {s.alias}\n")
        try:
            last = ""
            for chunk in pull_stream(s, args.model):
                st = chunk.get("status", "")
                total = chunk.get("total", 0)
                done = chunk.get("completed", 0)
                if total and done:
                    pct = int(done / total * 100)
                    bar = "█" * (pct // 4) + "░" * (25 - pct // 4)
                    con.print(
                        f"  [{C['dim']}]{bar}[/{C['dim']}] [{C['fg']}]{pct}%[/{C['fg']}]",
                        end="\r",
                    )
                elif st and st != last:
                    info(st)
                    last = st
                if chunk.get("status") == "success":
                    con.print()
                    ok(f"{args.model} ready on {s.alias}")
                    probe_server(s)
                    registry.save()
                    break
        except KeyboardInterrupt:
            warn("cancelled")
        except Exception as e:
            err(str(e))
            sys.exit(1)
        return

    if args.cmd == "delete":
        s = registry.resolve(args.target)
        if not s:
            err(f"server not found: {args.target}")
            sys.exit(1)
        if delete_model(s, args.model):
            ok(f"deleted {args.model} from {s.alias}")
            if args.model in s.models:
                s.models.remove(args.model)
                registry.save()
        else:
            err("delete failed")
            sys.exit(1)
        return

    # ── Interactive shell ───────────────────────────────────────────────────
    init_alias = ""
    if args.host:
        srv = registry.add(args.host, args.port, args.alias or f"{
                args.host}:{
                args.port}")
        con.print(f"  [{C['dim']}]probing {srv.alias}…[/{C['dim']}]", end=" ")
        res = probe_server(srv)
        registry.save()
        if res["ok"]:
            con.print(f"[{C['ok']}]online[/{C['ok']}]")
        else:
            con.print(f"[{C['err']}]offline[/{C['err']}]")
        init_alias = srv.alias
    elif registry.servers and not args.no_probe:
        con.print(
            f"  [{C['dim']}]probing {len(registry.servers)} saved server(s)…[/{C['dim']}]"
        )
        results = probe_all(registry)
        online = len(registry.online())
        con.print(f"  [{C['ok']}]{online}[/{C['ok']}] [{C['dim']}]online[/{C['dim']}]")

    shell = Shell(registry)
    shell.init(init_alias=init_alias, init_model=args.model)
    shell.run()
