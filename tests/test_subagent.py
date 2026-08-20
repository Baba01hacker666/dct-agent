"""Tests for subagent spawning and delegation."""

from dct.core.registry import Server
from dct.tools.subagent import list_subagents, get_subagent, spawn_subagent


def test_list_subagents_initial():
    subs = list_subagents()
    assert isinstance(subs, list)


def test_spawn_subagent_empty_task():
    res = spawn_subagent(task="")
    assert not res.ok
    assert "cannot be empty" in res.message


def test_spawn_subagent_background(monkeypatch):
    mock_server = Server(
        "test", "localhost", 11434, models=["mock-model"], status="online"
    )
    monkeypatch.setattr(
        "dct.core.registry.ServerRegistry.first_online",
        lambda self: mock_server,
    )
    monkeypatch.setattr(
        "dct.core.client.chat_stream",
        lambda *args, **kwargs: ["Task completed by mock subagent"],
    )

    res = spawn_subagent(
        task="echo 123",
        role="Test Runner",
        background=True,
    )
    assert res.ok
    assert "launched in background" in res.message
    sub_data = get_subagent(res.subagent_id)
    assert sub_data is not None
    assert sub_data["role"] == "Test Runner"
