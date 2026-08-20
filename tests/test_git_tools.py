"""Tests for safe git tools."""

from dct.tools.git_tools import git_status, git_diff, git_commit, git_worktree


def test_git_status():
    res = git_status()
    assert res.ok
    assert isinstance(res.output, str)


def test_git_diff():
    res = git_diff()
    assert res.ok
    assert isinstance(res.output, str)


def test_git_commit_empty_message():
    res = git_commit("")
    assert not res.ok
    assert "cannot be empty" in res.message


def test_git_worktree_list():
    res = git_worktree(action="list")
    assert res.ok
    assert isinstance(res.output, str)


def test_git_worktree_unknown_action():
    res = git_worktree(action="invalid_action")
    assert not res.ok
    assert "Unknown worktree action" in res.message
