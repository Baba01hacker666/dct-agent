"""
dct.core.mcp
Minimal Model Context Protocol (MCP) Client over stdio.
"""

import subprocess
import json
import threading
import time
from typing import Optional, Dict, Any, List
from dct.core.logging import get_logger

logger = get_logger("dct.core.mcp")


class MCPClient:
    def __init__(self, name: str, command: list[str]):
        self.name = name
        self.command = command
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.lock = threading.Lock()
        self.req_id = 0
        self.responses: Dict[int, Any] = {}

        self.reader_thread = threading.Thread(
            target=self._read_stdout, daemon=True
        )
        self.reader_thread.start()

    def _read_stdout(self):
        assert self.process.stdout is not None
        for line in self.process.stdout:
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
                if "id" in msg:
                    with self.lock:
                        self.responses[msg["id"]] = msg
            except json.JSONDecodeError:
                pass

    def call(self, method: str, params: Optional[dict] = None) -> dict:
        with self.lock:
            self.req_id += 1
            curr_id = self.req_id

        req = {
            "jsonrpc": "2.0",
            "id": curr_id,
            "method": method,
            "params": params or {},
        }
        try:
            assert self.process.stdin is not None
            self.process.stdin.write(json.dumps(req) + "\n")
            self.process.stdin.flush()
        except Exception as e:
            return {"error": {"message": f"Write error: {str(e)}"}}

        for _ in range(100):  # 10s timeout
            with self.lock:
                if curr_id in self.responses:
                    return self.responses.pop(curr_id)
            time.sleep(0.1)
        return {"error": {"message": "MCP timeout"}}

    def initialize(self) -> dict:
        res = self.call(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "dct-agent", "version": "1.0.0"},
            },
        )
        self.call("notifications/initialized")
        return res

    def list_tools(self) -> List[dict]:
        res = self.call("tools/list")
        if "error" in res:
            return []
        return res.get("result", {}).get("tools", [])

    def call_tool(self, name: str, args: dict) -> dict:
        res = self.call("tools/call", {"name": name, "arguments": args})
        return res

    def shutdown(self):
        try:
            self.process.terminate()
            self.process.wait(timeout=2)
        except Exception:
            self.process.kill()


class MCPManager:
    """Manages multiple MCP server instances."""

    def __init__(self):
        self.clients: Dict[str, MCPClient] = {}
        self.lock = threading.Lock()

    def add_server(self, name: str, command: list[str]) -> bool:
        with self.lock:
            if name in self.clients:
                return True
            try:
                client = MCPClient(name, command)
                res = client.initialize()
                if "error" in res:
                    client.shutdown()
                    return False
                self.clients[name] = client
                return True
            except Exception:
                logger.exception("Failed to add MCP server '%s'", name)
                return False

    def list_all_tools(self) -> str:
        with self.lock:
            if not self.clients:
                return "No MCP servers configured or running."

            lines = ["[MCP SERVERS & TOOLS]"]
            for name, client in self.clients.items():
                tools = client.list_tools()
                lines.append(f"\nServer: {name}")
                if not tools:
                    lines.append("  (No tools)")
                for t in tools:
                    desc = t.get("description", "No description")
                    lines.append(f"  - {t['name']}: {desc}")
                    # Include schema overview if useful
            return "\n".join(lines)

    def call_tool(self, server_name: str, tool_name: str, args: dict) -> str:
        with self.lock:
            client = self.clients.get(server_name)
            if not client:
                return f"[TOOL ERROR] Unknown MCP server: {server_name}"

        res = client.call_tool(tool_name, args)
        if "error" in res:
            return f"[MCP ERROR] {json.dumps(res['error'])}"

        result_data = res.get("result", {})
        if result_data.get("isError"):
            return f"[MCP TOOL FAILED] {json.dumps(result_data)}"

        content = result_data.get("content", [])
        text_outputs = []
        for c in content:
            if c.get("type") == "text":
                text_outputs.append(c.get("text", ""))
        return (
            "\n".join(text_outputs)
            if text_outputs
            else "[MCP Success - No output]"
        )


_global_mcp = None
_mcp_lock = threading.Lock()


def get_mcp_manager() -> MCPManager:
    global _global_mcp
    if _global_mcp is None:
        with _mcp_lock:
            if _global_mcp is None:
                _global_mcp = MCPManager()
    return _global_mcp
