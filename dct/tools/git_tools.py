"""
dct.tools.git_tools
Safe Git utilities and worktree management for DCT Agent.
"""

from __future__ import annotations

import os
import subprocess
from typing import NamedTuple, Optional


class GitResult(NamedTuple):
    ok: bool
    message: str
    output: str = ""


def _run_git_cmd(args: list[str], cwd: Optional[str] = None) -> tuple[int, str, str]:
    """Execute git command safely with timeout."""
    try:
        res = subprocess.run(
            ["git"] + args,
            cwd=cwd or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "Git command timed out after 30s"
    except Exception as e:
        return 1, "", f"Git execution failed: {str(e)}"


def git_status(path: Optional[str] = None) -> GitResult:
    """Return status of git repository."""
    code, stdout, stderr = _run_git_cmd(["status", "--short", "--branch"], cwd=path)
    if code != 0:
        return GitResult(ok=False, message=stderr or "Failed to get git status")
    return GitResult(ok=True, message="Git status retrieved", output=stdout)


def git_diff(path: Optional[str] = None, cached: bool = False, file_path: Optional[str] = None) -> GitResult:
    """Return git diff (staged or unstaged)."""
    args = ["diff"]
    if cached:
        args.append("--cached")
    if file_path:
        args.extend(["--", file_path])

    code, stdout, stderr = _run_git_cmd(args, cwd=path)
    if code != 0:
        return GitResult(ok=False, message=stderr or "Failed to get git diff")
    if not stdout:
        return GitResult(ok=True, message="No changes found", output="")
    return GitResult(ok=True, message="Git diff retrieved", output=stdout)


def git_commit(message: str, add_all: bool = True, path: Optional[str] = None) -> GitResult:
    """Stage files and create a git commit."""
    if not message or not message.strip():
        return GitResult(ok=False, message="Commit message cannot be empty")

    if add_all:
        code, _, stderr = _run_git_cmd(["add", "-A"], cwd=path)
        if code != 0:
            return GitResult(ok=False, message=f"git add failed: {stderr}")

    code, stdout, stderr = _run_git_cmd(["commit", "-m", message.strip()], cwd=path)
    if code != 0:
        return GitResult(ok=False, message=f"git commit failed: {stderr or stdout}")
    return GitResult(ok=True, message="Commit successful", output=stdout)


def git_worktree(
    action: str = "list",
    worktree_path: Optional[str] = None,
    branch: Optional[str] = None,
    cwd: Optional[str] = None,
) -> GitResult:
    """Manage Git worktrees (list, add, remove)."""
    act = action.strip().lower()

    if act == "list":
        code, stdout, stderr = _run_git_cmd(["worktree", "list"], cwd=cwd)
        if code != 0:
            return GitResult(ok=False, message=stderr or "Failed to list worktrees")
        return GitResult(ok=True, message="Worktrees listed", output=stdout)

    elif act in ("add", "create"):
        if not worktree_path:
            return GitResult(ok=False, message="worktree_path is required to add worktree")
        args = ["worktree", "add", worktree_path]
        if branch:
            args.extend(["-b", branch])
        code, stdout, stderr = _run_git_cmd(args, cwd=cwd)
        if code != 0:
            return GitResult(ok=False, message=f"Failed to add worktree: {stderr or stdout}")
        return GitResult(ok=True, message="Worktree created", output=stdout or f"Created worktree at {worktree_path}")

    elif act in ("remove", "delete"):
        if not worktree_path:
            return GitResult(ok=False, message="worktree_path is required to remove worktree")
        code, stdout, stderr = _run_git_cmd(["worktree", "remove", worktree_path, "--force"], cwd=cwd)
        if code != 0:
            return GitResult(ok=False, message=f"Failed to remove worktree: {stderr or stdout}")
        return GitResult(ok=True, message="Worktree removed", output=stdout or f"Removed worktree at {worktree_path}")

    else:
        return GitResult(ok=False, message=f"Unknown worktree action '{action}'. Supported: list, add, remove")
