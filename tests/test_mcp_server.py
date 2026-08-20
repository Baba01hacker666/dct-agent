"""Tests for MCP Server implementation."""

import json
import io
from dct.core.mcp_server import MCPServer, get_tool_definitions


def test_get_tool_definitions():
    tools = get_tool_definitions()
    assert isinstance(tools, list)
    assert len(tools) >= 10
    names = [t["name"] for t in tools]
    assert "read_file" in names
    assert "write_file" in names
    assert "patch_file" in names
    assert "run_bash" in names
    assert "run_python" in names
    assert "fetch_url" in names


def test_mcp_server_initialize():
    in_buf = io.StringIO()
    out_buf = io.StringIO()
    server = MCPServer(in_stream=in_buf, out_stream=out_buf)

    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {}
    }
    server.handle_request(req)

    output = out_buf.getvalue().strip()
    resp = json.loads(output)
    assert resp["id"] == 1
    assert resp["result"]["protocolVersion"] == "2024-11-05"
    assert resp["result"]["serverInfo"]["name"] == "dct-agent"


def test_mcp_server_tools_list():
    in_buf = io.StringIO()
    out_buf = io.StringIO()
    server = MCPServer(in_stream=in_buf, out_stream=out_buf)

    req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
    server.handle_request(req)

    output = out_buf.getvalue().strip()
    resp = json.loads(output)
    assert resp["id"] == 2
    assert "tools" in resp["result"]
    assert len(resp["result"]["tools"]) >= 10


def test_mcp_server_tools_call(tmp_path):
    in_buf = io.StringIO()
    out_buf = io.StringIO()
    server = MCPServer(in_stream=in_buf, out_stream=out_buf)

    test_file = tmp_path / "hello.txt"
    test_file.write_text("Hello MCP World")

    req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "read_file",
            "arguments": {"path": str(test_file)}
        }
    }
    server.handle_request(req)

    output = out_buf.getvalue().strip()
    resp = json.loads(output)
    assert resp["id"] == 3
    assert resp["result"]["isError"] is False
    assert "Hello MCP World" in resp["result"]["content"][0]["text"]


def test_mcp_server_prompts_list():
    in_buf = io.StringIO()
    out_buf = io.StringIO()
    server = MCPServer(in_stream=in_buf, out_stream=out_buf)

    req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "prompts/list",
        "params": {}
    }
    server.handle_request(req)

    output = out_buf.getvalue().strip()
    resp = json.loads(output)
    assert resp["id"] == 4
    assert "prompts" in resp["result"]
    assert len(resp["result"]["prompts"]) > 0
