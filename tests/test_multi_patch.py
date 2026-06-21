import os
import json
import tempfile
from unittest.mock import MagicMock, patch
from dct.agent.codeagent import CodeAgent
from dct.agent.session import Session, write_trace_entry


def test_multi_patch_file_success():
    # Setup agent session mock
    session_mock = MagicMock()
    session_mock.mode = "chat"
    agent = CodeAgent(server=None, model="test-model", session=session_mock, stream_fn=lambda *a, **k: iter([]))

    # Create a temporary file to patch
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("line 1: AAA\nline 2: BBB\nline 3: CCC\n")
        temp_path = f.name

    try:
        call = {
            "tool": "multi_patch_file",
            "path": temp_path,
            "patches": [
                {"old": "AAA", "new": "111"},
                {"old": "CCC", "new": "333"}
            ]
        }
        res = agent._execute_tool(call)
        assert "[multi-patched:" in res

        # Read back and assert replacements
        with open(temp_path, "r") as f:
            content = f.read()
        assert "line 1: 111" in content
        assert "line 2: BBB" in content
        assert "line 3: 333" in content
    finally:
        os.unlink(temp_path)


def test_multi_patch_file_failures():
    session_mock = MagicMock()
    session_mock.mode = "chat"
    agent = CodeAgent(server=None, model="test-model", session=session_mock, stream_fn=lambda *a, **k: iter([]))

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("AAA\nBBB\nAAA\n")
        temp_path = f.name

    try:
        # 1. Non-unique target
        call = {
            "tool": "multi_patch_file",
            "path": temp_path,
            "patches": [
                {"old": "AAA", "new": "111"}
            ]
        }
        res = agent._execute_tool(call)
        assert "not unique" in res

        # 2. Target not found
        call_not_found = {
            "tool": "multi_patch_file",
            "path": temp_path,
            "patches": [
                {"old": "DDD", "new": "444"}
            ]
        }
        res_not_found = agent._execute_tool(call_not_found)
        assert "not found" in res_not_found
    finally:
        os.unlink(temp_path)


def test_write_trace_entry_logging():
    import dct.agent.session
    dct.agent.session._cfg = None
    # Mock config to enable tracing
    with patch("dct.core.config.Config") as mock_cfg_class:
        mock_cfg = MagicMock()
        mock_cfg.get.side_effect = lambda key, default=None: True if key == "enable_tracing" else default
        mock_cfg_class.return_value = mock_cfg

        session = Session(name="test_trace_session")
        session.messages = [{"role": "user", "content": "hello trace"}]

        # Call write_trace_entry
        write_trace_entry(session, "test_event", {"extra": "info"})

        # Check that transcript file is created
        log_dir = os.path.expanduser("~/.config/dct/transcripts")
        log_file = os.path.join(log_dir, "test_trace_session.jsonl")

        assert os.path.exists(log_file)

        try:
            with open(log_file, "r") as f:
                lines = f.readlines()
            assert len(lines) >= 1
            data = json.loads(lines[-1])
            assert data["type"] == "test_event"
            assert data["extra"] == "info"
            assert data["session_name"] == "test_trace_session"
        finally:
            # Cleanup transcript file
            if os.path.exists(log_file):
                os.unlink(log_file)
