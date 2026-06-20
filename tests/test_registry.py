from dct.core.registry import Server, ServerRegistry


def test_server_dict_serialization():
    s = Server("or1", "openrouter.ai", 443, provider="openrouter", api_key="sk-test")
    d = s.to_dict()
    assert d["provider"] == "openrouter"
    assert d["api_key"] == "sk-test"
    assert d["host"] == "openrouter.ai"

    s2 = Server.from_dict(d)
    assert s2.provider == "openrouter"
    assert s2.api_key == "sk-test"
    assert s2.base_url() == "https://openrouter.ai/api/v1"


def test_server_tls_auth_serialization():
    s = Server("secure", "ollama.example.com", 443, api_key="secret123", tls=True, tls_verify=False)
    d = s.to_dict()
    assert d["tls"] is True
    assert d["tls_verify"] is False
    assert d["api_key"] == "secret123"

    s2 = Server.from_dict(d)
    assert s2.tls is True
    assert s2.tls_verify is False
    assert s2.api_key == "secret123"
    assert s2.base_url() == "https://ollama.example.com:443"


def test_server_base_url_tls():
    # api_key implies https
    s = Server("s1", "10.0.0.1", 11434, api_key="key1")
    assert s.base_url() == "https://10.0.0.1:11434"

    # explicit tls
    s2 = Server("s2", "10.0.0.2", 11434, tls=True)
    assert s2.base_url() == "https://10.0.0.2:11434"

    # default: no tls, no api_key → http
    s3 = Server("s3", "localhost", 11434)
    assert s3.base_url() == "http://localhost:11434"


def test_registry_add_openrouter(tmp_path):
    reg_path = tmp_path / "servers.json"
    reg = ServerRegistry(str(reg_path))
    reg.add("openrouter.ai", 443, "or1", provider="openrouter", api_key="sk-test")

    assert len(reg.servers) == 1
    assert reg.servers[0].provider == "openrouter"

    # Reload from disk
    reg2 = ServerRegistry(str(reg_path))
    assert len(reg2.servers) == 1
    assert reg2.servers[0].provider == "openrouter"
    assert reg2.servers[0].api_key == "sk-test"


def test_list_dir_optimization(tmp_path):
    from dct.tools.files import list_dir
    # Create some dummy files
    for i in range(5):
        (tmp_path / f"file_{i}.txt").write_text(f"content {i}")

    # Test listing with limit < total files
    res = list_dir(str(tmp_path), max_entries=3)
    assert res.ok
    lines = res.content.splitlines()
    assert len(lines) == 4  # 3 files + 1 truncation line
    assert "… (+2 more)" in lines[-1]


def test_code_agent_xml_extraction():
    from dct.agent.codeagent import _parse_tool_call, CodeAgent
    from dct.agent.session import Session
    from dct.core.registry import Server

    raw_response = """
    <tool>glob</tool>
    <pattern>*.py</pattern>
    <path>/some/dir</path>
    """
    call = _parse_tool_call(raw_response)
    assert call is not None
    assert call["tool"] == "glob"
    assert call["raw_text"] == raw_response

    # Let's mock the session and server
    session = Session()
    server = Server("local", "localhost", 11434)
    agent = CodeAgent(server, "llama3", session, lambda *args: iter([]))

    # Stub run_glob inside test
    from unittest.mock import patch, MagicMock
    with patch("dct.agent.codeagent.run_glob") as mock_glob:
        mock_glob.return_value = MagicMock(ok=True, content="file1.py")
        result = agent._execute_tool(call)
        assert "file1.py" in result
        mock_glob.assert_called_once_with("*.py", "/some/dir")


def test_subagent_tool_parsing_and_execution():
    from dct.agent.codeagent import _parse_tool_call, CodeAgent
    from dct.agent.session import Session
    from dct.core.registry import Server

    raw_response = """
    <tool>run_subagent</tool>
    <instruction>Create a helper script</instruction>
    <model>llama3-helper</model>
    <system_prompt>Be extremely fast</system_prompt>
    """
    call = _parse_tool_call(raw_response)
    assert call is not None
    assert call["tool"] == "run_subagent"
    assert call["instruction"] == "Create a helper script"
    assert call["model"] == "llama3-helper"
    assert call["system_prompt"] == "Be extremely fast"

    # Test mock execution of run_subagent
    session = Session()
    server = Server("local", "localhost", 11434)
    
    # Mock stream_fn that returns tool DONE immediately for the sub-agent
    def mock_stream_fn(srv, mdl, msgs):
        yield "<tool>DONE</tool>\nCompleted task."

    agent = CodeAgent(server, "llama3", session, mock_stream_fn)
    
    result = agent._execute_tool(call)
    assert "completed task successfully" in result.lower()


def test_shell_default_agent_mode():
    from dct.cli.shell import Shell
    from dct.core.registry import ServerRegistry
    import tempfile
    
    with tempfile.NamedTemporaryFile(suffix=".json") as tmp:
        registry = ServerRegistry(tmp.name)
        shell = Shell(registry)
        assert shell.agent_mode is True


def test_background_subagent_execution():
    import time
    from dct.agent.codeagent import _parse_tool_call, CodeAgent, BACKGROUND_SUBAGENTS, BACKGROUND_SUBAGENTS_LOCK
    from dct.agent.session import Session
    from dct.core.registry import Server

    raw_response = """
    <tool>run_subagent</tool>
    <instruction>Helper task</instruction>
    <background>true</background>
    """
    call = _parse_tool_call(raw_response)
    assert call is not None
    assert call["background"] == "true"

    session = Session()
    server = Server("local", "localhost", 11434)
    
    def mock_stream_fn(srv, mdl, msgs):
        yield "<tool>DONE</tool>"

    agent = CodeAgent(server, "llama3", session, mock_stream_fn)
    result = agent._execute_tool(call)
    
    assert "started in background" in result
    # We should have a registered background subagent
    assert len(BACKGROUND_SUBAGENTS) > 0
    bg_id = list(BACKGROUND_SUBAGENTS.keys())[-1]
    
    # Wait for background thread to run and complete
    for _ in range(20):
        if BACKGROUND_SUBAGENTS[bg_id]["status"] in ("completed", "failed"):
            break
        time.sleep(0.1)
        
    assert BACKGROUND_SUBAGENTS[bg_id]["status"] == "completed"

    # Cleanup
    with BACKGROUND_SUBAGENTS_LOCK:
        BACKGROUND_SUBAGENTS.pop(bg_id, None)


def test_background_task_execution():
    import time
    from dct.agent.codeagent import _parse_tool_call, CodeAgent, BACKGROUND_TASKS, BACKGROUND_TASKS_LOCK
    from dct.agent.session import Session
    from dct.core.registry import Server

    raw_response = """
    <tool>run_bash</tool>
    <code>echo 'bg task'</code>
    <background>true</background>
    """
    call = _parse_tool_call(raw_response)
    assert call is not None
    assert call["background"] == "true"

    session = Session()
    server = Server("local", "localhost", 11434)
    agent = CodeAgent(server, "llama3", session, lambda *args: iter([]))
    
    result = agent._execute_tool(call)
    assert "started in background" in result
    assert len(BACKGROUND_TASKS) > 0
    task_id = list(BACKGROUND_TASKS.keys())[-1]

    # Wait for task to complete
    for _ in range(30):
        with BACKGROUND_TASKS_LOCK:
            if BACKGROUND_TASKS[task_id]["status"] in ("completed", "failed"):
                break
        time.sleep(0.1)

    # Check status tool
    status_call = {"tool": "bg_status"}
    status_res = agent._execute_tool(status_call)
    assert task_id in status_res

    # Check status details tool
    status_call_detail = {"tool": "bg_status", "id": task_id}
    status_detail_res = agent._execute_tool(status_call_detail)
    assert "echo 'bg task'" in status_detail_res

    # Cleanup
    with BACKGROUND_TASKS_LOCK:
        BACKGROUND_TASKS.pop(task_id, None)


def test_shell_goal_mode():
    from dct.cli.shell import Shell
    from dct.core.registry import ServerRegistry, Server
    import tempfile
    
    with tempfile.NamedTemporaryFile(suffix=".json") as tmp:
        registry = ServerRegistry(tmp.name)
        # Add a dummy server so active server is resolved
        srv = Server("local", "localhost", 11434, status="online")
        registry.servers.append(srv)
        shell = Shell(registry)
        shell.active = srv
        shell.model = "llama3"
        
        # We can test that goal mode starts and updates session state
        # Let's mock agent run to return DONE immediately
        from unittest.mock import patch
        with patch("dct.cli.shell.chat_stream") as mock_stream:
            mock_stream.return_value = ["<tool>DONE</tool>\nGoal achieved."]
            shell._run_goal_mode("test goal")
            
            assert shell.agent_mode is True
            # Session should contain the user goal and the assistant response
            assert any(m["role"] == "user" and "test goal" in m["content"] for m in shell.session.messages)
            assert any(m["role"] == "assistant" and "Goal achieved" in m["content"] for m in shell.session.messages)


def test_shell_btw_command():
    from dct.cli.shell import Shell
    from dct.core.registry import ServerRegistry, Server
    import tempfile
    
    with tempfile.NamedTemporaryFile(suffix=".json") as tmp:
        registry = ServerRegistry(tmp.name)
        srv = Server("local", "localhost", 11434, status="online")
        registry.servers.append(srv)
        shell = Shell(registry)
        shell.active = srv
        shell.model = "llama3"
        
        # Add a mock message to session history
        shell.session.add("user", "Existing prompt")
        shell.session.add("assistant", "Existing response")
        
        from unittest.mock import patch
        with patch("dct.cli.shell.chat_stream") as mock_stream:
            mock_stream.return_value = ["BTW reply"]
            shell._btw("side question")
            
            # The session history should NOT have the side question or response!
            assert len(shell.session.messages) == 2
            assert not any("side question" in m["content"] for m in shell.session.messages)
            assert not any("BTW reply" in m["content"] for m in shell.session.messages)


def test_cleanup_background_state_removes_stale():
    import time
    from dct.agent.codeagent import (
        _cleanup_background_state,
        BACKGROUND_TASKS,
        BACKGROUND_TASKS_LOCK,
        BACKGROUND_SUBAGENTS,
        BACKGROUND_SUBAGENTS_LOCK,
        BG_CLEANUP_TTL,
    )

    now = time.time()

    with BACKGROUND_TASKS_LOCK:
        BACKGROUND_TASKS.clear()
        BACKGROUND_TASKS["task_stale"] = {
            "command": "echo stale",
            "lang": "bash",
            "status": "completed",
            "result": "ok",
            "log": [],
            "completed_at": now - BG_CLEANUP_TTL - 10,
        }
        BACKGROUND_TASKS["task_fresh"] = {
            "command": "echo fresh",
            "lang": "bash",
            "status": "completed",
            "result": "ok",
            "log": [],
            "completed_at": now - 10,
        }
        BACKGROUND_TASKS["task_running"] = {
            "command": "echo running",
            "lang": "bash",
            "status": "running",
            "result": "",
            "log": [],
            "completed_at": 0,
        }

    with BACKGROUND_SUBAGENTS_LOCK:
        BACKGROUND_SUBAGENTS.clear()
        BACKGROUND_SUBAGENTS["sub_stale"] = {
            "instruction": "do stuff",
            "model": "llama3",
            "status": "failed",
            "result": "error",
            "log": [],
            "completed_at": now - BG_CLEANUP_TTL - 5,
        }

    _cleanup_background_state()

    with BACKGROUND_TASKS_LOCK:
        assert "task_stale" not in BACKGROUND_TASKS
        assert "task_fresh" in BACKGROUND_TASKS
        assert "task_running" in BACKGROUND_TASKS

    with BACKGROUND_SUBAGENTS_LOCK:
        assert "sub_stale" not in BACKGROUND_SUBAGENTS

    # Cleanup
    with BACKGROUND_TASKS_LOCK:
        BACKGROUND_TASKS.clear()
    with BACKGROUND_SUBAGENTS_LOCK:
        BACKGROUND_SUBAGENTS.clear()


def test_append_log_safe_truncates():
    from dct.agent.codeagent import _append_log_safe, BG_LOG_MAX_CHARS

    entry = {"log": []}
    chunk = "x" * (BG_LOG_MAX_CHARS // 2 + 1)
    _append_log_safe(entry, chunk)
    assert len(entry["log"]) == 1

    _append_log_safe(entry, chunk)
    assert len(entry["log"]) == 1  # first chunk evicted

    total = sum(len(c) for c in entry["log"])
    assert total <= BG_LOG_MAX_CHARS


def test_config_defaults(tmp_path):
    from dct.core.config import Config
    cfg_path = tmp_path / "config.json"
    cfg = Config(str(cfg_path))
    assert cfg.get("agent_enabled") is True
    assert cfg.get("max_agent_turns") == 12
    assert cfg.get("default_server") == ""

    cfg.set("default_model", "llama3")
    cfg.set("agent_enabled", False)
    cfg.save()

    cfg2 = Config(str(cfg_path))
    assert cfg2.get("default_model") == "llama3"
    assert cfg2.get("agent_enabled") is False
    # Unset keys fall back to defaults
    assert cfg2.get("max_agent_turns") == 12


def test_auto_probe_thread_lifecycle():
    from dct.cli.shell import Shell
    from dct.core.registry import ServerRegistry
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".json") as tmp:
        registry = ServerRegistry(tmp.name)
        shell = Shell(registry)
        # Disable auto-probe for this test
        shell.config.set("auto_probe_interval", 0)
        shell.config.save()
        shell._start_auto_probe()
        assert shell._probe_thread is None  # interval <= 0

        # Enable and start
        shell.config.set("auto_probe_interval", 60)
        shell.config.save()
        shell._start_auto_probe()
        assert shell._probe_thread is not None
        assert shell._probe_thread.is_alive()

        shell._stop_auto_probe()
        shell._probe_thread.join(timeout=2)
        assert not shell._probe_thread.is_alive()


def test_run_python_auto_install():
    from unittest.mock import patch, MagicMock
    from dct.tools.executor import run_python

    # Mock the internal _run function
    # On first call, return ModuleNotFoundError in stderr and returncode 1
    # On second call, return successful execution
    with patch("dct.tools.executor._run") as mock_run, \
         patch("dct.tools.executor.subprocess.run") as mock_sub_run, \
         patch("dct.tools.executor.os.path.exists") as mock_exists:

        called_venv = []

        def side_effect_fn(path):
            if "venv" in str(path) and (str(path).endswith("python") or str(path).endswith("python.exe")):
                called_venv.append(path)
                return len(called_venv) > 1
            return True
        mock_exists.side_effect = side_effect_fn

        mock_run.side_effect = [
            ("", "ModuleNotFoundError: No module named 'fake_module_for_test'", 1, False),
            ("success_output", "", 0, False)
        ]

        # Mock subprocess.run for the pip install call to succeed
        mock_pip_res = MagicMock()
        mock_pip_res.returncode = 0
        mock_sub_run.return_value = mock_pip_res

        res = run_python("import fake_module_for_test")

        assert res.ok
        assert "Auto-installed missing packages in venv: fake_module_for_test" in res.stdout
        assert "success_output" in res.stdout
        assert mock_run.call_count == 2

        # Verify venv setup and pip install were called
        assert mock_sub_run.call_count == 2

        # First call: venv creation
        venv_args = mock_sub_run.call_args_list[0][0][0]
        assert "venv" in venv_args

        # Second call: pip install
        pip_args = mock_sub_run.call_args_list[1][0][0]
        assert "pip" in pip_args
        assert "install" in pip_args
        assert "fake_module_for_test" in pip_args

