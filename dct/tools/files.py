"""
dct.tools.files
File system tools: read, write, patch, list, tree.
Used by the coding agent to inspect and modify files.
"""

from __future__ import annotations
import os
import glob as _pyglob
import shutil
import subprocess
import difflib
from pathlib import Path
from dataclasses import dataclass

_HOME = os.path.expanduser("~")


def _safe_path(p: str) -> str:
    """Replace home directory with ~ for privacy in error messages."""
    if p.startswith(_HOME):
        return "~" + p[len(_HOME) :]
    return p


# Default sandbox root — resolved at first call to stay current
_sandbox_root: Path | None = None


def _get_sandbox_root() -> Path | None:
    """Return the project root used for path sandboxing, or None if disabled."""
    global _sandbox_root
    if _sandbox_root is None:
        from dct.core.config import Config

        cfg = Config()
        root = cfg.get("project_root") or ""
        _sandbox_root = Path(root).resolve() if root else None
    return _sandbox_root


def _check_path(path: str | Path) -> Path:
    """Resolve path and raise if sandbox is enabled and path escapes."""
    resolved = Path(path).expanduser().resolve()
    sandbox = _get_sandbox_root()
    if sandbox is not None:
        try:
            resolved.relative_to(sandbox)
        except ValueError:
            raise PermissionError(
                f"Path {str(resolved)!r} is outside the project root "
                f"{str(sandbox)!r}. File operations are sandboxed."
            )
    return resolved


@dataclass
class FileResult:
    ok: bool
    path: str
    content: str = ""
    message: str = ""
    diff: str = ""


@dataclass
class ReadResult(FileResult):
    """Extended result for read_file with metadata."""

    total_lines: int = 0
    file_size: int = 0
    is_binary: bool = False
    warning: str = ""


# Skip diff generation for files larger than this (bytes)
DIFF_MAX_BYTES = 100_000
# Reject writes larger than this (bytes)
WRITE_MAX_BYTES = 50 * 1024 * 1024  # 50 MB


def _is_binary(path: Path, probe_bytes: int = 8192) -> bool:
    """Detect binary files by checking for null bytes in the first chunk."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(probe_bytes)
        return b"\x00" in chunk
    except Exception:
        return False


def read_file(
    path: str,
    max_bytes: int = 512_000,
    start_line: int | None = None,
    end_line: int | None = None,
    tail: int | None = None,
    line_limit: int = 2000,
) -> ReadResult:
    """Read a file with optional line slicing and metadata.

    Args:
        path: File path to read.
        max_bytes: Maximum file size in bytes (default 512KB).
        start_line: 1-based start line (inclusive). None = start of file.
        end_line: 1-based end line (inclusive). None = end of file.
        tail: Show only the last N lines. Takes precedence over start_line/end_line.
        line_limit: Maximum number of output lines (default 2000).

    Returns:
        ReadResult with content (line-numbered), metadata, and any warnings.
    """
    try:
        p = _check_path(path)
        if not p.exists():
            return ReadResult(ok=False, path=str(p), message="file not found")

        file_size = p.stat().st_size
        if file_size > max_bytes:
            return ReadResult(
                ok=False,
                path=str(p),
                file_size=file_size,
                message=f"file too large ({fmt_size(file_size)}, max {fmt_size(max_bytes)})",
            )

        # Binary detection
        if _is_binary(p):
            return ReadResult(
                ok=False,
                path=_safe_path(str(p)),
                file_size=file_size,
                is_binary=True,
                message="binary file detected — use read_image for images or a hex tool for raw bytes",
            )

        content = p.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        total_lines = len(lines)
        warning = ""

        # Conflict: tail takes precedence over start_line/end_line
        if tail is not None and (start_line is not None or end_line is not None):
            warning = "tail takes precedence — start_line/end_line were ignored"

        # Apply slicing
        if tail is not None:
            start_idx = max(0, total_lines - tail)
            lines_to_show = lines[start_idx:]
        else:
            start_idx = max(0, (start_line or 1) - 1)
            end_idx = min(total_lines, end_line) if end_line else total_lines
            if start_idx >= end_idx:
                start_idx = min(start_idx, total_lines)
                end_idx = start_idx
            lines_to_show = lines[start_idx:end_idx]

        # Apply output line limit
        truncated = False
        if len(lines_to_show) > line_limit:
            lines_to_show = lines_to_show[:line_limit]
            truncated = True

        # Build numbered output
        numbered = "\n".join(
            f"{i + start_idx + 1:4d}  {line_text}"
            for i, line_text in enumerate(lines_to_show)
        )
        if truncated:
            numbered += "\n...[TRUNCATED]..."

        # Header with metadata
        show_range = f"{start_idx + 1}-{start_idx + len(lines_to_show)}"
        header = f"[file: {_safe_path(str(p))}  lines {show_range} of {total_lines}  size: {fmt_size(file_size)}]"
        result_content = f"{header}\n{numbered}"

        return ReadResult(
            ok=True,
            path=_safe_path(str(p)),
            content=result_content,
            total_lines=total_lines,
            file_size=file_size,
            warning=warning,
        )
    except Exception as e:
        return ReadResult(ok=False, path=_safe_path(path), message=str(e))


def write_file(path: str, content: str, backup: bool = True) -> FileResult:
    try:
        p = _check_path(path)

        content_bytes = len(content.encode("utf-8", errors="replace"))
        if content_bytes > WRITE_MAX_BYTES:
            return FileResult(
                ok=False,
                path=str(p),
                message=f"content too large ({content_bytes / 1024 / 1024:.1f} MB, max {WRITE_MAX_BYTES / 1024 / 1024:.0f} MB)",
            )

        # Auto-Linter: prevent writing broken python syntax
        if p.suffix == ".py":
            import ast

            try:
                ast.parse(content)
            except SyntaxError as e:
                return FileResult(
                    ok=False,
                    path=str(p),
                    message=f"SyntaxError: {e.msg} at line {e.lineno}",
                )

        old_content = ""
        was_new = not p.exists()
        if not was_new:
            if content_bytes <= DIFF_MAX_BYTES:
                old_content = p.read_text(encoding="utf-8", errors="replace")
            if backup:
                shutil.copy2(p, str(p) + ".dct.bak")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

        if content_bytes > DIFF_MAX_BYTES:
            diff = f"(file too large for diff: {content_bytes / 1024:.1f} KB)"
        elif was_new:
            diff = "(new file)"
        else:
            diff = _make_diff(old_content, content, str(p))

        return FileResult(
            ok=True, path=str(p), content=content, message="written", diff=diff
        )
    except Exception as e:
        return FileResult(ok=False, path=_safe_path(path), message=str(e))


def patch_file(path: str, old: str, new: str) -> FileResult:
    """Replace first occurrence of `old` with `new` in file."""
    try:
        p = _check_path(path)
        if not p.exists():
            return FileResult(ok=False, path=str(p), message="file not found")
        content = p.read_text(encoding="utf-8", errors="replace")
        if old not in content:
            return FileResult(
                ok=False, path=str(p), message="patch target not found in file"
            )
        new_content = content.replace(old, new, 1)

        # Auto-Linter: prevent writing broken python syntax
        if p.suffix == ".py":
            import ast

            try:
                ast.parse(new_content)
            except SyntaxError as e:
                return FileResult(
                    ok=False,
                    path=str(p),
                    message=f"SyntaxError after patch: {e.msg} at line {e.lineno}",
                )

        shutil.copy2(p, str(p) + ".dct.bak")
        p.write_text(new_content, encoding="utf-8")

        new_bytes = len(new_content.encode("utf-8", errors="replace"))
        if new_bytes > DIFF_MAX_BYTES:
            diff = f"(file too large for diff: {new_bytes / 1024:.1f} KB)"
        else:
            diff = _make_diff(content, new_content, str(p))

        return FileResult(
            ok=True,
            path=str(p),
            content=new_content,
            message="patched",
            diff=diff,
        )
    except Exception as e:
        return FileResult(ok=False, path=_safe_path(path), message=str(e))


def list_dir(path: str, max_entries: int = 200) -> FileResult:
    try:
        p = _check_path(path)
        if not p.exists():
            return FileResult(ok=False, path=str(p), message="path not found")
        all_entries = sorted(p.iterdir())
        entries = []
        for entry in all_entries[:max_entries]:
            tag = "d" if entry.is_dir() else "f"
            size = ""
            if entry.is_file():
                try:
                    sz = entry.stat().st_size
                    size = f" ({fmt_size(sz)})"
                except Exception:
                    pass
            entries.append(f"[{tag}] {entry.name}{size}")
        if len(all_entries) > max_entries:
            entries.append(f"… (+{len(all_entries) - max_entries} more)")
        return FileResult(ok=True, path=str(p), content="\n".join(entries))
    except Exception as e:
        return FileResult(ok=False, path=_safe_path(path), message=str(e))


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
        p = _check_path(path)
        if not p.exists():
            return FileResult(ok=False, path=str(p), message="path not found")
        lines.append(str(p))
        _walk(p, 1, "")
        return FileResult(ok=True, path=str(p), content="\n".join(lines))
    except Exception as e:
        return FileResult(ok=False, path=_safe_path(path), message=str(e))


def run_grep(
    pattern: str,
    path: str = ".",
    glob_pattern: str | None = None,
    output_mode: str = "files_with_matches",
    context: int | None = None,
    head_limit: int = 250,
) -> FileResult:
    """Run ripgrep (rg) to search file contents. Falls back to system grep."""
    try:
        subprocess.run(["rg", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return _run_grep_fallback(
            pattern, path, glob_pattern, output_mode, context, head_limit
        )
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
            return FileResult(
                ok=False,
                path=path,
                message=f"grep error: {proc.stderr.strip() or 'unknown error'}",
            )

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
        return FileResult(
            ok=False,
            path=path,
            message="rg (ripgrep) binary not found on the system. Please install it.",
        )
    except Exception as e:
        return FileResult(ok=False, path=_safe_path(path), message=str(e))


def _run_grep_fallback(
    pattern: str,
    path: str = ".",
    glob_pattern: str | None = None,
    output_mode: str = "files_with_matches",
    context: int | None = None,
    head_limit: int = 250,
) -> FileResult:
    """Fallback using system grep when rg is unavailable."""
    cmd = ["grep", "-r"]
    if output_mode == "files_with_matches":
        cmd.append("-l")
    elif output_mode == "content":
        cmd.append("-n")
        if context is not None:
            cmd.extend(["-C", str(context)])
    if glob_pattern:
        cmd.extend(["--include", glob_pattern])
    cmd.extend(["--", pattern, path])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode not in (0, 1):
            return FileResult(
                ok=False,
                path=path,
                message=f"grep error: {proc.stderr.strip() or 'unknown error'}",
            )
        out = proc.stdout.strip()
        if not out:
            return FileResult(ok=True, path=path, content="(no matches found)")
        lines = out.splitlines()
        if len(lines) > head_limit:
            lines = lines[:head_limit]
            lines.append(f"... (output truncated to {head_limit} lines)")
        return FileResult(ok=True, path=path, content="\n".join(lines))
    except FileNotFoundError:
        return FileResult(
            ok=False, path=path, message="Neither rg nor grep found on PATH."
        )
    except Exception as e:
        return FileResult(ok=False, path=_safe_path(path), message=str(e))


def _make_diff(old: str, new: str, fname: str) -> str:
    diff = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{os.path.basename(fname)}",
        tofile=f"b/{os.path.basename(fname)}",
        n=3,
    )
    return "".join(diff)


def fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    if n < 1024**2:
        return f"{n / 1024:.1f}KB"
    return f"{n / 1024**2:.1f}MB"


# Backward-compatible alias
_fmt_size = fmt_size


def run_glob(
    pattern: str,
    path: str = ".",
) -> FileResult:
    """Fast file pattern matching using ripgrep --files. Falls back to Python glob."""
    try:
        subprocess.run(["rg", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return _run_glob_fallback(pattern, path)
    cmd = ["rg", "--files", "--glob", pattern, path]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)

        # rg returns 0 for match, 1 for no match, 2 for error
        if proc.returncode not in (0, 1):
            return FileResult(
                ok=False,
                path=path,
                message=f"glob error: {proc.stderr.strip() or 'unknown error'}",
            )

        out = proc.stdout.strip()
        if not out:
            return FileResult(ok=True, path=path, content="(no matching files found)")

        return FileResult(ok=True, path=path, content=out)
    except Exception as e:
        return FileResult(ok=False, path=_safe_path(path), message=str(e))


def _run_glob_fallback(pattern: str, path: str = ".") -> FileResult:
    """Fallback using Python's glob module when rg is unavailable."""
    try:
        matches = _pyglob.glob(pattern, root_dir=path, recursive=True)
    except TypeError:
        # Python < 3.10 doesn't support root_dir
        import os as _os

        cwd = _os.getcwd()
        try:
            _os.chdir(path)
            matches = _pyglob.glob(pattern, recursive=True)
        finally:
            _os.chdir(cwd)
    except Exception as e:
        return FileResult(ok=False, path=_safe_path(path), message=str(e))

    matches.sort()
    if not matches:
        return FileResult(ok=True, path=path, content="(no matches found)")
    return FileResult(ok=True, path=path, content="\n".join(matches))
