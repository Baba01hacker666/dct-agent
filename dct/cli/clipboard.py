"""
Clipboard helpers for shell commands like /copy.
"""

from __future__ import annotations

import os
import subprocess


def _copy_with(cmd: list[str], text: str) -> bool:
    try:
        subprocess.run(cmd, input=text, text=True, check=True, capture_output=True)
        return True
    except Exception:
        return False


def copy_text(text: str) -> bool:
    """
    Best-effort clipboard copy across platforms.
    Returns True if clipboard integration succeeded.
    """
    # macOS
    if _copy_with(["pbcopy"], text):
        return True

    # Linux
    if _copy_with(["xclip", "-selection", "clipboard"], text):
        return True
    if _copy_with(["xsel", "--clipboard", "--input"], text):
        return True
    if _copy_with(["wl-copy"], text):
        return True

    # Windows
    if os.name == "nt" and _copy_with(["clip"], text):
        return True

    # OSC52 fallback (some terminals support this)
    try:
        import base64

        encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
        print(f"\033]52;c;{encoded}\a", end="", flush=True)
        return True
    except Exception:
        return False
