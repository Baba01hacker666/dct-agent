"""
dct.tools.files
File system tools: read, write, patch, list, tree.
Used by the coding agent to inspect and modify files.
"""

from __future__ import annotations
import os
import shutil
import subprocess
import difflib
from pathlib import Path
from dataclasses import dataclass


@dataclass
class FileResult:
    ok: bool
    path: str
    content: str = ""
    message: str = ""
    diff: str = ""


def read_file(path: str, max_bytes: int = 512_000) -> FileResult:
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return FileResult(ok=False, path=str(p), message="file not found")
        if p.stat().st_size > max_bytes:
            return FileResult(
                ok=False,
                path=str(p),
                message=f"file too large (>{max_bytes // 1024}KB)",
            )
        content = p.read_text(errors="replace")
        return FileResult(ok=True, path=str(p), content=content)
    except Exception as e:
        return FileResult(ok=False, path=path, message=str(e))


def write_file(path: str, content: str, backup: bool = True) -> FileResult:
    try:
        p = Path(path).expanduser().resolve()
        old_content = ""
        if p.exists():
            old_content = p.read_text(errors="replace")
            if backup:
                shutil.copy2(p, str(p) + ".dct.bak")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        diff = _make_diff(old_content, content, str(p))
        return FileResult(
            ok=True, path=str(p), content=content, message="written", diff=diff
        )
    except Exception as e:
        return FileResult(ok=False, path=path, message=str(e))


def patch_file(path: str, old: str, new: str) -> FileResult:
    """Replace first occurrence of `old` with `new` in file."""
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return FileResult(ok=False, path=str(p), message="file not found")
        content = p.read_text(errors="replace")
        if old not in content:
            return FileResult(
                ok=False, path=str(p), message="patch target not found in file"
            )
        new_content = content.replace(old, new, 1)
        shutil.copy2(p, str(p) + ".dct.bak")
        p.write_text(new_content)
        diff = _make_diff(content, new_content, str(p))
        return FileResult(
            ok=True,
            path=str(p),
            content=new_content,
            message="patched",
            diff=diff,
        )
    except Exception as e:
        return FileResult(ok=False, path=path, message=str(e))


def list_dir(path: str, max_entries: int = 200) -> FileResult:
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return FileResult(ok=False, path=str(p), message="path not found")
        entries = []
        for entry in sorted(p.iterdir()):
            tag = "d" if entry.is_dir() else "f"
            size = ""
            if entry.is_file():
                try:
                    sz = entry.stat().st_size
                    size = f" ({_fmt_size(sz)})"
                except Exception:
                    pass
            entries.append(f"[{tag}] {entry.name}{size}")
            if len(entries) >= max_entries:
                entries.append(
                    f"… (+{len(list(p.iterdir())) - max_entries} more)"
                )
                break
        return FileResult(ok=True, path=str(p), content="\n".join(entries))
    except Exception as e:
        return FileResult(ok=False, path=path, message=str(e))


def tree(path: str, max_depth: int = 3, max_entries: int = 300) -> FileResult:
    """Recursive directory tree."""
    lines: list[str] = []

    def _walk(p: Path, depth: int, prefix: str):
        if depth > max_depth or len(lines) > max_entries:
            return
        try:
            entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name))
        except PermissionError:
            return
        for i, entry in enumerate(entries):
            connector = "└── " if i == len(entries) - 1 else "├── "
            tag = "/" if entry.is_dir() else ""
            lines.append(f"{prefix}{connector}{entry.name}{tag}")
            if entry.is_dir() and depth < max_depth:
                extension = "    " if i == len(entries) - 1 else "│   "
                _walk(entry, depth + 1, prefix + extension)

    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return FileResult(ok=False, path=str(p), message="path not found")
        lines.append(str(p))
        _walk(p, 1, "")
        return FileResult(ok=True, path=str(p), content="\n".join(lines))
    except Exception as e:
        return FileResult(ok=False, path=path, message=str(e))




def run_grep(
    pattern: str,
    path: str = ".",
    glob_pattern: str | None = None,
    output_mode: str = "files_with_matches",
    context: int | None = None,
    head_limit: int = 250
) -> FileResult:
    """Run ripgrep (rg) to search file contents."""
    cmd = ["rg"]
    
    # Map output_mode to rg flags
    if output_mode == "files_with_matches":
        cmd.append("-l")
    elif output_mode == "count":
        cmd.append("-c")
    elif output_mode == "content":
        cmd.append("-n")  # Include line numbers
        if context is not None:
            cmd.extend(["-C", str(context)])
            
    # Apply glob filtering if provided
    if glob_pattern:
        cmd.extend(["--glob", glob_pattern])
        
    cmd.extend(["--", pattern, path])
    
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        
        # rg returns 0 for match, 1 for no match, 2 for error
        if proc.returncode not in (0, 1):
            return FileResult(ok=False, path=path, message=f"grep error: {proc.stderr.strip() or 'unknown error'}")
            
        out = proc.stdout.strip()
        if not out:
            return FileResult(ok=True, path=path, content="(no matches found)")
            
        # Enforce head_limit
        lines = out.splitlines()
        if len(lines) > head_limit:
            lines = lines[:head_limit]
            lines.append(f"... (output truncated to {head_limit} lines)")
            
        return FileResult(ok=True, path=path, content="\n".join(lines))
        
    except FileNotFoundError:
        return FileResult(ok=False, path=path, message="rg (ripgrep) binary not found on the system. Please install it.")
    except Exception as e:
        return FileResult(ok=False, path=path, message=str(e))

def _make_diff(old: str, new: str, fname: str) -> str:
    diff = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{os.path.basename(fname)}",
        tofile=f"b/{os.path.basename(fname)}",
        n=3,
    )
    return "".join(diff)


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    if n < 1024**2:
        return f"{n / 1024:.1f}KB"
    return f"{n / 1024**2:.1f}MB"
