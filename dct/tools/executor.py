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
        limit = 20000
        if len(out) > limit:
            out = out[:limit] + f"\n...[TRUNCATED {len(out) - limit} chars]..."
        if len(err) > limit:
            err = err[:limit] + f"\n...[TRUNCATED {len(err) - limit} chars]..."
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


def run_python(code: str, timeout: int = 30, cwd: str | None = None) -> ExecResult:
    """Execute Python code in a dedicated virtual environment with auto-pip installation."""
    code = textwrap.dedent(code)
    t0 = time.time()

    # Define dedicated virtual environment path
    venv_dir = os.path.expanduser("~/.config/dct/venv")
    venv_python = os.path.join(venv_dir, "bin", "python")

    # Try setting up virtual environment
    use_venv = True
    try:
        if not os.path.exists(venv_python):
            os.makedirs(os.path.dirname(venv_dir), exist_ok=True)
            subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)
    except Exception:
        use_venv = False

    python_bin = venv_python if (use_venv and os.path.exists(venv_python)) else sys.executable

    # Allow up to 3 auto-install retries for cases where code requires multiple missing packages
    max_retries = 3
    retries = 0
    installed_packages = []

    MODULE_MAPPING = {
        "yaml": "pyyaml",
        "bs4": "beautifulsoup4",
        "PIL": "Pillow",
        "dateutil": "python-dateutil",
        "dotenv": "python-dotenv",
        "mysql": "mysql-connector-python",
        "pg": "psycopg2-binary",
        "psycopg2": "psycopg2-binary",
    }

    while retries <= max_retries:
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, dir=cwd
        ) as f:
            f.write(code)
            tmp = f.name

        try:
            stdout, stderr, rc, timed_out = _run(
                [python_bin, tmp], timeout=timeout, cwd=cwd
            )
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass

        if rc != 0 and not timed_out:
            import re
            m = re.search(r"ModuleNotFoundError:\s*No\s*module\s*named\s*'([^']+)'", stderr)
            if m:
                missing_module = m.group(1)
                package_name = MODULE_MAPPING.get(missing_module, missing_module)

                # Prevent infinite loops installing the same package
                if package_name in installed_packages:
                    break

                try:
                    pip_proc = subprocess.run(
                        [python_bin, "-m", "pip", "install", package_name],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    if pip_proc.returncode == 0:
                        installed_packages.append(package_name)
                        retries += 1
                        continue  # Retry running the python code
                except Exception:
                    pass
        break

    if installed_packages:
        prefix = f"[Auto-installed missing packages in venv: {', '.join(installed_packages)}]\n"
        stdout = prefix + stdout

    return ExecResult(
        language="python",
        code=code,
        stdout=stdout,
        stderr=stderr,
        returncode=rc,
        timed_out=timed_out,
        duration_ms=int((time.time() - t0) * 1000),
    )


def run_bash(code: str, timeout: int = 30, cwd: str | None = None) -> ExecResult:
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


def prepare_background_command(
    language: str, code: str, cwd: str | None = None
) -> tuple[list[str], str | None]:
    """Prepare command argument list and return optional temp file path to clean up later."""
    lang = language.lower().strip()
    if lang in ("python", "python3", "py"):
        code = textwrap.dedent(code)
        # Define dedicated virtual environment path
        venv_dir = os.path.expanduser("~/.config/dct/venv")
        venv_python = os.path.join(venv_dir, "bin", "python")

        # Try setting up virtual environment
        use_venv = True
        try:
            if not os.path.exists(venv_python):
                os.makedirs(os.path.dirname(venv_dir), exist_ok=True)
                subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)
        except Exception:
            use_venv = False

        python_bin = venv_python if (use_venv and os.path.exists(venv_python)) else sys.executable

        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, dir=cwd
        ) as f:
            f.write(code)
            tmp = f.name
        return [python_bin, tmp], tmp

    elif lang in ("bash", "sh", "shell"):
        code = textwrap.dedent(code)
        with tempfile.NamedTemporaryFile(
            suffix=".sh", mode="w", delete=False, dir=cwd
        ) as f:
            f.write("#!/usr/bin/env bash\nset -euo pipefail\n" + code)
            tmp = f.name
        os.chmod(tmp, 0o700)
        return ["/usr/bin/env", "bash", tmp], tmp

    else:
        # Raw shell command
        return ["bash", "-c", code], None
