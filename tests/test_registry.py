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
    assert s2.base_url() == "https://openrouter.ai"


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


def test_shell_rewind_logic():
    from dct.agent.session import Session
    session = Session()
    session.add("user", "Hello")
    session.add("assistant", "Hi")
    session.add("user", "Help me")
    session.add("assistant", "Sure")

    # Rewind should remove the last user message and subsequent assistant messages
    assert session.rewind()
    assert len(session.messages) == 2
    assert session.messages[0]["content"] == "Hello"
    assert session.messages[1]["content"] == "Hi"


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
    from dct.agent.codeagent import _parse_tool_call, CodeAgent, BACKGROUND_SUBAGENTS
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


def test_background_task_execution():
    import time
    from dct.agent.codeagent import _parse_tool_call, CodeAgent, BACKGROUND_TASKS
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
    
    # Check status tool
    status_call = {"tool": "bg_status"}
    status_res = agent._execute_tool(status_call)
    assert task_id in status_res
    
    # Check status details tool
    status_call_detail = {"tool": "bg_status", "id": task_id}
    status_detail_res = agent._execute_tool(status_call_detail)
    assert "echo 'bg task'" in status_detail_res


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
