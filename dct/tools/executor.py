"""
dct.tools.executor
Safe(ish) local code and shell execution for the coding agent.
Runs Python and Bash in subprocess with timeout + output capture.

WARNING: This executes arbitrary code locally. Use responsibly.
"""

from __future__ import annotations
import os
import sys
import subprocess
import tempfile
import textwrap
import time
from dataclasses import dataclass


@dataclass
class ExecResult:
    language: str
    code: str
    stdout: str
    stderr: str
    returncode: int
    duration_ms: int
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def summary(self) -> str:
        out = self.stdout.strip()
        err = self.stderr.strip()
        parts = []
        if out:
            parts.append(out)
        if err:
            parts.append(f"[stderr]\n{err}")
        if self.timed_out:
            parts.append("[TIMEOUT]")
        return "\n".join(parts) if parts else "(no output)"


def _run(
    cmd: list[str],
    timeout: int,
    cwd: str | None = None,
    env: dict | None = None,
) -> tuple[str, str, int, bool]:
    """Run subprocess, return (stdout, stderr, returncode, timed_out)."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env or os.environ.copy(),
        )
        return proc.stdout, proc.stderr, proc.returncode, False
    except subprocess.TimeoutExpired:
        return "", "Execution timed out.", -1, True
    except Exception as e:
        return "", str(e), -1, False


def run_python(
    code: str, timeout: int = 30, cwd: str | None = None
) -> ExecResult:
    """Execute Python code in a temporary file."""
    code = textwrap.dedent(code)
    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False, dir=cwd
    ) as f:
        f.write(code)
        tmp = f.name
    t0 = time.time()
    try:
        stdout, stderr, rc, timed_out = _run(
            [sys.executable, tmp], timeout=timeout, cwd=cwd
        )
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass
    return ExecResult(
        language="python",
        code=code,
        stdout=stdout,
        stderr=stderr,
        returncode=rc,
        timed_out=timed_out,
        duration_ms=int((time.time() - t0) * 1000),
    )


def run_bash(
    code: str, timeout: int = 30, cwd: str | None = None
) -> ExecResult:
    """Execute bash script."""
    code = textwrap.dedent(code)
    with tempfile.NamedTemporaryFile(
        suffix=".sh", mode="w", delete=False, dir=cwd
    ) as f:
        f.write("#!/usr/bin/env bash\nset -euo pipefail\n" + code)
        tmp = f.name
    os.chmod(tmp, 0o700)
    t0 = time.time()
    try:
        stdout, stderr, rc, timed_out = _run(
            ["/usr/bin/env", "bash", tmp], timeout=timeout, cwd=cwd
        )
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass
    return ExecResult(
        language="bash",
        code=code,
        stdout=stdout,
        stderr=stderr,
        returncode=rc,
        timed_out=timed_out,
        duration_ms=int((time.time() - t0) * 1000),
    )


def run_shell_command(
    command: str, timeout: int = 30, cwd: str | None = None
) -> ExecResult:
    """Run a raw shell command string."""
    t0 = time.time()
    stdout, stderr, rc, timed_out = _run(
        ["bash", "-c", command], timeout=timeout, cwd=cwd
    )
    return ExecResult(
        language="shell",
        code=command,
        stdout=stdout,
        stderr=stderr,
        returncode=rc,
        timed_out=timed_out,
        duration_ms=int((time.time() - t0) * 1000),
    )


def dispatch(
    language: str, code: str, timeout: int = 30, cwd: str | None = None
) -> ExecResult:
    """Dispatch to correct runner based on language string."""
    lang = language.lower().strip()
    if lang in ("python", "python3", "py"):
        return run_python(code, timeout, cwd)
    if lang in ("bash", "sh", "shell"):
        return run_bash(code, timeout, cwd)
    # Fallback: run as shell command
    return run_shell_command(code, timeout, cwd)
