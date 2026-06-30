import os
import json
from dct.agent.session import Session, write_trace_entry
import dct.agent.session as session_module
from unittest.mock import patch, mock_open


def test_write_trace_entry_disabled(monkeypatch, tmp_path):
    class DummyConfig:
        def get(self, key, default):
            return False

    monkeypatch.setattr(session_module, "_cfg", DummyConfig())

    session = Session(name="test_sess")
    monkeypatch.setattr(os.path, "expanduser", lambda x: x.replace("~", str(tmp_path)))
    write_trace_entry(session, "test", {"msg": "hello"})
    assert not (tmp_path / ".config/dct/transcripts").exists()


def test_write_trace_entry_enabled(monkeypatch, tmp_path):
    class DummyConfig:
        def get(self, key, default):
            if key == "enable_tracing":
                return True
            return default

    monkeypatch.setattr(session_module, "_cfg", DummyConfig())

    # name test/sess-<>_ will test sanitization: c.isalnum() or c in ("-", "_")
    # t e s t s e s s - _
    session = Session(name="test/sess-<>_")
    monkeypatch.setattr(os.path, "expanduser", lambda x: x.replace("~", str(tmp_path)))
    write_trace_entry(session, "test", {"msg": "hello"})

    log_dir = tmp_path / ".config/dct/transcripts"
    assert log_dir.exists()

    log_file = log_dir / "testsess-_.jsonl"
    assert log_file.exists()

    with open(log_file) as f:
        data = json.loads(f.read().strip())

    assert data["type"] == "test"
    assert data["session_name"] == "test/sess-<>_"
    assert data["msg"] == "hello"
    assert "timestamp" in data


def test_write_trace_entry_config_exception(monkeypatch, tmp_path):
    def mock_get_cfg():
        raise Exception("Mock config exception")

    monkeypatch.setattr(session_module, "_get_cfg", mock_get_cfg)

    session = Session(name="test_sess")
    monkeypatch.setattr(os.path, "expanduser", lambda x: x.replace("~", str(tmp_path)))
    # Should not raise exception
    write_trace_entry(session, "test", {"msg": "hello"})
    assert not (tmp_path / ".config/dct/transcripts").exists()


def test_write_trace_entry_write_exception(monkeypatch, tmp_path):
    class DummyConfig:
        def get(self, key, default):
            if key == "enable_tracing":
                return True
            return default

    monkeypatch.setattr(session_module, "_cfg", DummyConfig())

    session = Session(name="test_sess")
    monkeypatch.setattr(os.path, "expanduser", lambda x: x.replace("~", str(tmp_path)))

    # Mock open to raise exception
    with patch("builtins.open", mock_open()) as mocked_file:
        mocked_file.side_effect = IOError("Mock write error")
        # Should not raise exception
        write_trace_entry(session, "test", {"msg": "hello"})
