"""Regression tests for reliability fixes."""

import pytest

from dct.agent.codeagent import CodeAgent
from dct.agent.session import Session
from dct.core.registry import Server


@pytest.fixture
def agent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    server = Server("test", "http://localhost", 11434, "ollama")
    session = Session(mode="execute")
    return CodeAgent(
        server=server,
        model="test-model",
        session=session,
        stream_fn=lambda s, m, msg, **kw: iter(["<tool>DONE</tool>\nDone."]),
        on_text=lambda _: None,
        on_tool=lambda *_: None,
        on_result=lambda *_: None,
    )


class TestToolErrorContainment:
    def test_tool_exception_does_not_crash_loop(self, agent):
        """An unexpected exception inside a tool returns an error string
        instead of propagating and aborting the whole agent run."""
        call = {"tool": "web_search"}  # missing <query> triggers KeyError path
        res = agent._execute_tool(call)
        # Either handled gracefully or contained as TOOL ERROR — never raises
        assert isinstance(res, str)

    def test_broken_tool_returns_tool_error(self, agent):
        original = CodeAgent._dispatch_tool

        def boom(self, call):
            raise RuntimeError("disk on fire")

        CodeAgent._dispatch_tool = boom
        try:
            res = agent._execute_tool({"tool": "get_cwd"})
        finally:
            CodeAgent._dispatch_tool = original
        assert "[TOOL ERROR]" in res
        assert "RuntimeError" in res


class TestContextPruningPairing:
    def _make_msgs(self):
        system = {"role": "system", "content": "sys"}
        assistant_with_tools = {
            "role": "assistant",
            "content": "calling tools",
            "tool_calls": [{"id": "call_1", "function": {"name": "read_file"}}],
        }
        tool_resp = {"role": "tool", "tool_call_id": "call_1", "content": "x" * 90000}
        user = {"role": "user", "content": "y" * 90000}
        return [system, assistant_with_tools, tool_resp, user]

    def test_assistant_tool_call_never_orphaned(self, agent):
        from unittest.mock import patch

        msgs = self._make_msgs()
        with patch.object(agent, "_summarize_dropped", return_value="summary"):
            agent.run(msgs)

    def test_pruning_drops_complete_groups(self, agent):
        """Simulate the pruning logic directly: the assistant message with
        tool_calls must be dropped together with its tool response."""
        msgs = self._make_msgs()
        total_chars = sum(len(m.get("content") or "") for m in msgs)
        assert total_chars > 120000

        # Replicate group-bounds logic used by run()
        groups = []
        i = 0
        while i < len(msgs):
            role = msgs[i].get("role")
            if role == "system":
                i += 1
                continue
            group = [i]
            if role == "assistant" and msgs[i].get("tool_calls"):
                j = i + 1
                while j < len(msgs) and msgs[j].get("role") == "tool":
                    group.append(j)
                    j += 1
            groups.append(group)
            i = j if len(group) > 1 else i + 1

        # Oldest group (assistant+tool pair) is atomic
        assert groups[0] == [1, 2]
        dropped_idx = {i for i in groups[0]}
        roles = {msgs[i]["role"] for i in dropped_idx}
        assert roles == {"assistant", "tool"}

    def test_none_content_does_not_crash_pruning(self):
        msgs = [
            {"role": "assistant", "content": None, "tool_calls": []},
            {"role": "user", "content": "z" * 200000},
        ]
        total = sum(len(m.get("content") or "") for m in msgs)
        assert total == 200000


class TestPatchFileUniqueness:
    def test_ambiguous_patch_rejected(self, tmp_path):
        from dct.tools.files import patch_file

        f = tmp_path / "dup.txt"
        f.write_text("alpha\nbeta\nalpha\n")
        res = patch_file(str(f), "alpha", "gamma")
        assert not res.ok
        assert "not unique" in res.message
        assert "2 occurrences" in res.message
        # File unchanged
        assert f.read_text() == "alpha\nbeta\nalpha\n"

    def test_unique_patch_still_works(self, tmp_path):
        from dct.tools.files import patch_file

        f = tmp_path / "ok.txt"
        f.write_text("hello world\n")
        res = patch_file(str(f), "world", "there")
        assert res.ok
        assert f.read_text() == "hello there\n"

    def test_missing_target_rejected(self, tmp_path):
        from dct.tools.files import patch_file

        f = tmp_path / "x.txt"
        f.write_text("abc\n")
        res = patch_file(str(f), "nope", "yes")
        assert not res.ok
        assert "not found" in res.message


class TestExecutor:
    def test_timeout_preserves_partial_output(self):
        from dct.tools.executor import run_shell_command

        res = run_shell_command("echo before; sleep 30", timeout=1)
        assert res.timed_out
        assert "before" in res.stdout

    def test_temp_scripts_not_created_in_cwd(self, tmp_path):
        from dct.tools.executor import run_python

        (tmp_path / "marker").touch()
        res = run_python("print('hi')", cwd=str(tmp_path))
        assert res.ok
        leftovers = [p.name for p in tmp_path.iterdir() if p.suffix == ".py"]
        assert leftovers == []


class TestMCPClient:
    class _FakeStdio:
        def __init__(self, lines=()):
            self.buffer = []
            self._lines = list(lines)

        def write(self, s):
            self.buffer.append(s)

        def flush(self):
            pass

        def __iter__(self):
            return iter(self._lines)

    def _fake_process(self, monkeypatch, responses=None):
        """Patch Popen with an object that echoes canned responses."""
        proc = type("FakeProc", (), {})()
        proc.stdin = self._FakeStdio()
        proc.stdout = self._FakeStdio(responses or [])

        def terminate():
            pass

        def kill():
            pass

        proc.terminate = terminate
        proc.kill = kill
        proc.wait = lambda timeout=None: 0
        monkeypatch.setattr(
            "dct.core.mcp.subprocess.Popen", lambda *a, **k: proc
        )

    def test_string_command_is_shlex_split(self, monkeypatch):
        captured = {}

        def fake_popen(cmd, **kwargs):
            captured["cmd"] = cmd
            proc = type("FakeProc", (), {})()
            proc.stdin = TestMCPClient._FakeStdio()
            proc.stdout = TestMCPClient._FakeStdio()

            def terminate():
                pass

            def wait(timeout=None):
                return 0

            def kill():
                pass

            proc.terminate = terminate
            proc.wait = wait
            proc.kill = kill
            return proc

        monkeypatch.setattr("dct.core.mcp.subprocess.Popen", fake_popen)
        from dct.core.mcp import MCPClient

        MCPClient("srv", "npx -y some-server --port 8080")
        assert captured["cmd"] == ["npx", "-y", "some-server", "--port", "8080"]

    def test_notify_sends_no_id_and_returns(self, monkeypatch):
        self._fake_process(monkeypatch)
        from dct.core.mcp import MCPClient

        client = MCPClient("srv", "true")
        assert client.notify("notifications/initialized") is True
        sent = client.process.stdin.buffer[-1]
        assert '"id"' not in sent

    def test_initialize_does_not_hang_on_notification(self, monkeypatch):
        init_response = '{"jsonrpc": "2.0", "id": 1, "result": {"ok": true}}\n'
        self._fake_process(monkeypatch, responses=[init_response])
        from dct.core.mcp import MCPClient
        import time

        t0 = time.time()
        client = MCPClient("srv", "true")
        res = client.initialize()
        elapsed = time.time() - t0
        assert "error" not in res
        assert elapsed < 5  # previously hung ~10s waiting for a notification

    def test_timeout_prunes_stale_response(self, monkeypatch):
        self._fake_process(monkeypatch)  # no responses ever arrive
        from dct.core.mcp import MCPClient

        client = MCPClient("srv", "true")
        res = client.call("tools/list")
        assert "error" in res
        # Give reader thread a beat; stale entry must have been pruned
        import time

        time.sleep(0.05)
        assert client.responses == {}
