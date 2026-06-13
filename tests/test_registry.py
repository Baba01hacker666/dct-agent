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
