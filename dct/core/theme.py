"""
dct.core.theme
Rich color theme, banner, shared output helpers.
"""

from __future__ import annotations
import time
from rich.console import Console
from rich.rule import Rule

con = Console()

C = {
    "accent": "#00e5ff",
    "accent2": "#00bcd4",
    "dim": "#555555",
    "muted": "#333333",
    "ok": "#00e5a0",
    "warn": "#ff6b35",
    "err": "#ff3355",
    "fg": "#c9c9c9",
    "purple": "#bd93f9",
    "yellow": "#f1fa8c",
    "code": "#b5f5ec",
}

VERSION = "3.0.0"

BANNER = f"""\
[{C["accent"]}]\
  ██████╗  ██████╗████████╗
  ██╔══██╗██╔════╝╚══██╔══╝
  ██║  ██║██║        ██║
  ██║  ██║██║        ██║
  ██████╔╝╚██████╗   ██║
  ╚═════╝  ╚═════╝   ╚═╝   \
[/{C["accent"]}][{C["dim"]}]doraemon cyber team · v{VERSION}[/{C["dim"]}]
"""


# ── Output helpers ──────────────────────────────────────────────────────────
def ok(msg: str):
    con.print(f"  [{C['ok']}]✓[/{C['ok']}]  [{C['fg']}]{msg}[/{C['fg']}]")


def err(msg: str):
    con.print(f"  [{C['err']}]✗[/{C['err']}]  [{C['err']}]{msg}[/{C['err']}]")


def info(msg: str):
    con.print(f"  [{C['dim']}]·[/{C['dim']}]  [{C['dim']}]{msg}[/{C['dim']}]")


def warn(msg: str):
    con.print(f"  [{C['warn']}]![/{C['warn']}]  [{C['warn']}]{msg}[/{C['warn']}]")


def hint(msg: str):
    con.print(
        f"  [{C['purple']}]?[/{C['purple']}]  [{C['purple']}]{msg}[/{C['purple']}]"
    )


def section(title: str):
    con.print()
    con.print(Rule(f"[{C['dim']}]{title}[/{C['dim']}]", style=C["muted"]))


def ts() -> str:
    return time.strftime("%H:%M:%S")


def server_tag(s) -> str:
    return (
        f"[{C['accent']}]{s.alias}[/{C['accent']}]"
        f" [{C['dim']}]({s.host}:{s.port})[/{C['dim']}]"
    )


def status_dot(status: str) -> str:
    if status == "online":
        return f"[{C['ok']}]●[/{C['ok']}]"
    if status == "offline":
        return f"[{C['err']}]○[/{C['err']}]"
    return f"[{C['dim']}]·[/{C['dim']}]"
