"""
dct.core.theme
Rich color theme, banner, shared output helpers.
"""

from __future__ import annotations
import time
from rich.console import Console
from rich.rule import Rule

import random

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

VERSION = "3.2.0"

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


# ── Funny status phrases ───────────────────────────────────────────────────
FUNNY_THINKING_PHRASES = [
    "reticulating splines...",
    "consulting the digital oracle...",
    "searching for the missing semicolon...",
    "counting to infinity (twice)...",
    "rewriting this section in Rust...",
    "asking StackOverflow very nicely...",
    "charging the flux capacitor...",
    "translating binary to sarcasm...",
    "calculating the ultimate answer to life...",
    "convincing the CPU to play along...",
    "teaching the AI how to love...",
    "generating believable excuses...",
    "searching for free RAM...",
    "mining bitcoin in the background (jk)...",
    "brewing espresso for the processor...",
    "checking if it works on my machine...",
    "resolving merge conflicts with pure willpower...",
    "bumping node_modules into the fourth dimension...",
    "finding out why the code works when it shouldn't...",
    "blaming git blame...",
    "writing 10 lines of code, deleting 20...",
    "waiting for the coffee to compiler-optimize...",
    "explaining the bug to a rubber duck...",
    "generating 404 errors with premium performance...",
    "hacking the mainframe (actually just typing fast)...",
    "tuning parameters until they match my confirmation bias...",
    "downloading more RAM...",
    "pretending to understand the legacy codebase...",
    "generating bugs at standard speed...",
    "checking if the bug is actually a feature...",
    "remembering to commit, but forgetting to push...",
    "converting caffeine into code...",
    "trying to exit Vim...",
    "centering a div using advanced witchcraft...",
    "rebooting the universe in safe mode...",
]

FUNNY_EXEC_PHRASES = [
    "summoning code monkeys to run {tool_name}...",
    "telling the OS to execute {tool_name} or else...",
    "brute forcing {tool_name} with positive vibes...",
    "unleashing {tool_name} upon the world...",
    "bribing the kernel to allow {tool_name}...",
    "performing magic trick: {tool_name}...",
    "whispering sweet nothings to {tool_name}...",
    "cross-referencing {tool_name} with ancient scrolls...",
    "compiling {tool_name} with hoping and praying...",
    "begging {tool_name} to not return exit code 1...",
    "running {tool_name} and immediately regretting it...",
    "asking the rubber duck to execute {tool_name}...",
    "wrapping {tool_name} in a try-catch and pretending it's fine...",
    "firing up {tool_name} to see what breaks...",
    "explaining to the boss why {tool_name} took 5 minutes...",
    "injecting caffeine directly into {tool_name}...",
    "sending {tool_name} into the void...",
    "running {tool_name} (do not press Ctrl+C, please)...",
    "convincing {tool_name} it's just a test environment...",
    "distracting the garbage collector while running {tool_name}...",
]


def get_funny_thinking_msg() -> str:
    return random.choice(FUNNY_THINKING_PHRASES)


def get_funny_exec_msg(tool_name: str) -> str:
    phrase = random.choice(FUNNY_EXEC_PHRASES)
    return phrase.format(tool_name=tool_name)
