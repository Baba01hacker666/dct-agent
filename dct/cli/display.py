"""
dct.cli.display
Rich display helpers: server tables, model lists, probe results, diffs.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from rich import box
from rich.table import Table
from rich.syntax import Syntax

from dct.core.theme import con, C, section, server_tag, ok, err, info, warn

if TYPE_CHECKING:
    from dct.core.registry import ServerRegistry


def show_servers(registry: "ServerRegistry"):
    section("server registry")
    if not registry.servers:
        warn("no servers registered")
        info("add one: /add <host> <port> [alias] [note]")
        return

    t = Table(
        box=box.SIMPLE, show_header=True, header_style=C["dim"], pad_edge=False
    )
    t.add_column("#", style=C["dim"], justify="right", min_width=3)
    t.add_column("alias", style=C["accent"], min_width=14)
    t.add_column("host", style=C["fg"], min_width=16)
    t.add_column("port", style=C["dim"], justify="right", min_width=6)
    t.add_column("status", justify="center", min_width=10)
    t.add_column("ms", style=C["dim"], justify="right", min_width=5)
    t.add_column("models", style=C["dim"], justify="right", min_width=7)
    t.add_column("version", style=C["muted"], min_width=10)
    t.add_column("note", style=C["muted"], min_width=10)

    for i, s in enumerate(registry.servers, 1):
        st = s.status
        stc = (
            C["ok"]
            if st == "online"
            else C["err"] if st == "offline" else C["dim"]
        )
        ms = str(s.latency_ms) + "ms" if s.latency_ms >= 0 else "—"
        t.add_row(
            str(i),
            s.alias,
            s.host,
            str(s.port),
            f"[{stc}]{st}[/{stc}]",
            ms,
            str(len(s.models)),
            s.version or "—",
            s.note or "",
        )
    con.print(t)


def show_models(models: list[dict], server_alias: str):
    section(f"models on {server_alias}")
    if not models:
        warn("no models found — pull one first")
        return

    t = Table(
        box=box.SIMPLE, show_header=True, header_style=C["dim"], pad_edge=False
    )
    t.add_column("#", style=C["dim"], justify="right", min_width=3)
    t.add_column("name", style=C["accent"], min_width=26)
    t.add_column("size", style=C["fg"], justify="right", min_width=10)
    t.add_column("family", style=C["dim"], min_width=12)
    t.add_column("params", style=C["dim"], min_width=8)
    t.add_column("quant", style=C["muted"], min_width=8)
    t.add_column("modified", style=C["muted"], min_width=12)

    for i, m in enumerate(models, 1):
        sg = m.get("size", 0) / 1e9
        ss = f"{sg:.1f} GB" if sg >= 1 else f"{m.get('size', 0) / 1e6:.0f} MB"
        det = m.get("details", {})
        t.add_row(
            str(i),
            m.get("name", "?"),
            ss,
            det.get("family", "—"),
            det.get("parameter_size", "—"),
            det.get("quantization_level", "—"),
            (m.get("modified_at") or "")[:10] or "—",
        )
    con.print(t)
    info(f"{len(models)} model(s) total")


def show_all_models(registry: "ServerRegistry"):
    section("all models across all servers")
    t = Table(
        box=box.SIMPLE, show_header=True, header_style=C["dim"], pad_edge=False
    )
    t.add_column("server", style=C["accent"], min_width=14)
    t.add_column("status", justify="center", min_width=10)
    t.add_column("model", style=C["fg"], min_width=26)

    for s in registry.servers:
        stc = (
            C["ok"]
            if s.status == "online"
            else C["err"] if s.status == "offline" else C["dim"]
        )
        if not s.models:
            t.add_row(
                s.alias,
                f"[{stc}]{s.status}[/{stc}]",
                f"[{C['dim']}](none)[/{C['dim']}]",
            )
        else:
            for i, m in enumerate(s.models):
                t.add_row(
                    s.alias if i == 0 else "",
                    f"[{stc}]{s.status}[/{stc}]" if i == 0 else "",
                    m,
                )
    con.print(t)


def show_probe_detail(rows: list[dict]):
    t = Table(
        box=box.SIMPLE, show_header=True, header_style=C["dim"], pad_edge=False
    )
    t.add_column("endpoint", style=C["fg"], min_width=16)
    t.add_column("status", justify="center", min_width=8)
    t.add_column("latency", style=C["dim"], justify="right", min_width=8)
    t.add_column("response", style=C["muted"], min_width=30)

    for row in rows:
        color = (
            C["ok"]
            if row["ok"]
            else C["err"] if row["status"] == 0 else C["warn"]
        )
        status_str = f"[{color}]{row['status'] or 'ERR'}[/{color}]"
        lat = f"{row['latency']}ms" if row["latency"] >= 0 else "—"
        t.add_row(row["path"], status_str, lat, row["snippet"])
    con.print(t)


def show_probe_summary(results: dict[str, dict], registry: "ServerRegistry"):
    section("probe results")
    for alias, res in results.items():
        s = registry.resolve(alias)
        if not s:
            continue
        if res.get("ok"):
            ep = res.get("endpoint", "?")
            ms = res.get("latency_ms", -1)
            lat = f" {ms}ms" if ms >= 0 else ""
            mod = len(s.models)
            ok(
                f"{server_tag(s)}  via {ep}{lat}  {mod} model(s)"
                + (f"  ollama {s.version}" if s.version else "")
            )
        else:
            err(f"[{C['err']}]{alias}[/{C['err']}]  offline / unreachable")


def show_diff(diff: str):
    if not diff:
        return
    section("diff")
    syntax = Syntax(diff, "diff", theme="monokai", line_numbers=False)
    con.print(syntax)


def show_exec_result(result, show_code: bool = False):
    from dct.tools.executor import ExecResult

    r: ExecResult = result
    color = C["ok"] if r.ok else C["err"]
    mark = "✓" if r.ok else "✗"
    con.print(
        f"  [{color}]{mark}[/{color}]"
        f"  [{C['dim']}]{r.language}  exit={r.returncode}  {r.duration_ms}ms[/{C['dim']}]"
    )
    if r.stdout.strip():
        section("stdout")
        con.print(f"[{C['code']}]{r.stdout.strip()}[/{C['code']}]")
    if r.stderr.strip():
        section("stderr")
        con.print(f"[{C['warn']}]{r.stderr.strip()}[/{C['warn']}]")
