"""
dct.core.mcp_server
Model Context Protocol (MCP) Server over stdio for DCT Agent.
Exposes DCT's file, execution, code navigation, and search tools to
external MCP clients such as Claude Desktop, Cursor, and Zed.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional

from dct.core.logging import get_logger
from dct.tools.executor import dispatch
from dct.tools.files import (
    list_dir,
    patch_file,
    read_file,
    run_glob,
    run_grep,
    tree,
    write_file,
)
from dct.tools.lsp import find_references, goto_definition, repo_map
from dct.tools.web import fetch_url, search_ddg

logger = get_logger("dct.core.mcp_server")

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "dct-agent"
SERVER_VERSION = "3.2.1"


def get_tool_definitions() -> List[Dict[str, Any]]:
    """Return JSON Schema tool definitions for MCP clients."""
    return [
        {
            "name": "read_file",
            "description": "Read file contents with line numbers and optional line slicing.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative file path."},
                    "start_line": {"type": "integer", "description": "Optional starting line number (1-based)."},
                    "end_line": {"type": "integer", "description": "Optional ending line number (inclusive)."},
                },
                "required": ["path"],
            },
        },
        {
            "name": "write_file",
            "description": "Create or overwrite a file with given content.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Target file path."},
                    "content": {"type": "string", "description": "Full file content to write."},
                },
                "required": ["path", "content"],
            },
        },
        {
            "name": "patch_file",
            "description": "Replace an exact chunk of old text with new text in a file.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to file to patch."},
                    "old": {"type": "string", "description": "Exact text sequence to be replaced."},
                    "new": {"type": "string", "description": "New replacement content."},
                },
                "required": ["path", "old", "new"],
            },
        },
        {
            "name": "list_dir",
            "description": "List entries in a directory with file types and sizes.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (defaults to current directory)."},
                },
            },
        },
        {
            "name": "tree",
            "description": "Return visual directory tree structure.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Root directory for tree (defaults to .)."},
                },
            },
        },
        {
            "name": "run_grep",
            "description": "Search file contents using ripgrep or regex fallback.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Search pattern or regular expression."},
                    "path": {"type": "string", "description": "Directory or file to search within."},
                    "glob": {"type": "string", "description": "Optional glob filter (e.g. *.py)."},
                },
                "required": ["pattern"],
            },
        },
        {
            "name": "run_glob",
            "description": "Find files matching a glob pattern.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern (e.g. **/*.ts)."},
                    "path": {"type": "string", "description": "Root search directory."},
                },
                "required": ["pattern"],
            },
        },
        {
            "name": "run_bash",
            "description": "Execute a shell command locally and capture stdout/stderr.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Bash command line to execute."},
                },
                "required": ["command"],
            },
        },
        {
            "name": "run_python",
            "description": "Execute Python code snippet locally and capture output.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute."},
                },
                "required": ["code"],
            },
        },
        {
            "name": "fetch_url",
            "description": "Fetch a public webpage or API endpoint safely (with SSRF protection).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "HTTP/HTTPS URL to fetch."},
                },
                "required": ["url"],
            },
        },
        {
            "name": "web_search",
            "description": "Search the web using DuckDuckGo.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                },
                "required": ["query"],
            },
        },
        {
            "name": "lsp_goto_definition",
            "description": "Find code definition using LSP/Jedi.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Source file path."},
                    "line": {"type": "integer", "description": "Line number (1-based)."},
                    "column": {"type": "integer", "description": "Column number (0-based)."},
                },
                "required": ["path", "line", "column"],
            },
        },
        {
            "name": "lsp_find_references",
            "description": "Find references to a symbol using LSP/Jedi.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Source file path."},
                    "line": {"type": "integer", "description": "Line number (1-based)."},
                    "column": {"type": "integer", "description": "Column number (0-based)."},
                },
                "required": ["path", "line", "column"],
            },
        },
        {
            "name": "lsp_repo_map",
            "description": "Generate an outline/symbol map of the repository.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Root directory path."},
                },
            },
        },
    ]


class MCPServer:
    """Standard Model Context Protocol Server over stdio."""

    def __init__(self, in_stream=None, out_stream=None):
        self.in_stream = in_stream or sys.stdin
        self.out_stream = out_stream or sys.stdout
        self._running = True

    def send_response(
        self,
        req_id: Any,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[Dict[str, Any]] = None,
    ):
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": req_id}
        if error is not None:
            payload["error"] = error
        else:
            payload["result"] = result or {}
        line = json.dumps(payload) + "\n"
        self.out_stream.write(line)
        self.out_stream.flush()

    def handle_request(self, req: Dict[str, Any]):
        method = req.get("method", "")
        req_id = req.get("id")
        params = req.get("params", {})

        if method == "initialize":
            self.send_response(
                req_id,
                result={
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {"listChanged": True},
                        "resources": {},
                        "prompts": {},
                    },
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "version": SERVER_VERSION,
                    },
                },
            )
        elif method in ("notifications/initialized", "initialized"):
            pass
        elif method == "ping":
            self.send_response(req_id, result={})
        elif method == "tools/list":
            self.send_response(req_id, result={"tools": get_tool_definitions()})
        elif method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments", {})
            res_str, is_err = self.execute_tool(name, args)
            self.send_response(
                req_id,
                result={
                    "content": [{"type": "text", "text": res_str}],
                    "isError": is_err,
                },
            )
        elif method == "prompts/list":
            from dct.cli.shell import PROMPT_PRESETS, SKILL_PRESETS

            prompts = []
            for k, v in PROMPT_PRESETS.items():
                prompts.append({"name": f"prompt_{k}", "description": v[:80]})
            for k, v in SKILL_PRESETS.items():
                prompts.append(
                    {"name": f"skill_{k}", "description": v.get("desc", "")}
                )
            self.send_response(req_id, result={"prompts": prompts})
        elif method == "resources/list":
            self.send_response(req_id, result={"resources": []})
        else:
            if req_id is not None:
                self.send_response(
                    req_id,
                    error={
                        "code": -32601,
                        "message": f"Method '{method}' not found",
                    },
                )

    def execute_tool(self, name: str, args: Dict[str, Any]) -> tuple[str, bool]:
        """Dispatch tool by name and return (output_string, is_error)."""
        try:
            if name == "read_file":
                path = args.get("path", "")
                sl = args.get("start_line")
                el = args.get("end_line")
                res = read_file(path, start_line=sl, end_line=el)
                return (
                    res.content if res.ok else f"Error: {res.message}",
                    not res.ok,
                )

            elif name == "write_file":
                path = args.get("path", "")
                content = args.get("content", "")
                res = write_file(path, content)
                return (res.message, not res.ok)

            elif name == "patch_file":
                path = args.get("path", "")
                old = args.get("old", "")
                new = args.get("new", "")
                res = patch_file(path, old, new)
                return (res.message, not res.ok)

            elif name == "list_dir":
                path = args.get("path", ".")
                res = list_dir(path)
                return (res.message, not res.ok)

            elif name == "tree":
                path = args.get("path", ".")
                res = tree(path)
                return (res.message, not res.ok)

            elif name == "run_grep":
                pattern = args.get("pattern", "")
                path = args.get("path", ".")
                glob_pat = args.get("glob")
                res = run_grep(pattern, path=path, glob_pat=glob_pat)
                return (res.message, not res.ok)

            elif name == "run_glob":
                pattern = args.get("pattern", "")
                path = args.get("path", ".")
                res = run_glob(pattern, path=path)
                return (res.message, not res.ok)

            elif name == "run_bash":
                cmd = args.get("command", "")
                res = dispatch("bash", cmd)
                out = res.stdout
                if res.stderr:
                    out += f"\n[stderr]\n{res.stderr}"
                return (
                    out or f"Process exited with code {res.code}",
                    res.code != 0,
                )

            elif name == "run_python":
                code = args.get("code", "")
                res = dispatch("python", code)
                out = res.stdout
                if res.stderr:
                    out += f"\n[stderr]\n{res.stderr}"
                return (
                    out or f"Process exited with code {res.code}",
                    res.code != 0,
                )

            elif name == "fetch_url":
                url = args.get("url", "")
                res = fetch_url(url)
                return (
                    res.content if res.ok else f"Error: {res.message}",
                    not res.ok,
                )

            elif name == "web_search":
                query = args.get("query", "")
                res = search_ddg(query)
                return (
                    res.content if res.ok else f"Error: {res.message}",
                    not res.ok,
                )

            elif name == "lsp_goto_definition":
                path = args.get("path", "")
                line = int(args.get("line", 1))
                col = int(args.get("column", 0))
                res = goto_definition(path, line, col)
                return (res.message, not res.ok)

            elif name == "lsp_find_references":
                path = args.get("path", "")
                line = int(args.get("line", 1))
                col = int(args.get("column", 0))
                res = find_references(path, line, col)
                return (res.message, not res.ok)

            elif name == "lsp_repo_map":
                path = args.get("path", ".")
                res = repo_map(path)
                return (res.message, not res.ok)

            else:
                return (f"Unknown tool '{name}'", True)

        except Exception as e:
            return (f"Tool execution exception: {str(e)}", True)

    def run_stdio(self):
        """Run MCP Server on stdio until EOF."""
        for raw_line in self.in_stream:
            line = raw_line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                self.handle_request(msg)
            except json.JSONDecodeError as e:
                self.send_response(
                    None,
                    error={"code": -32700, "message": f"Parse error: {str(e)}"},
                )
            except Exception as e:
                logger.exception("Error handling MCP request")
                self.send_response(
                    None,
                    error={
                        "code": -32603,
                        "message": f"Internal error: {str(e)}",
                    },
                )


def run_mcp_server():
    """CLI entrypoint for running MCP server."""
    server = MCPServer()
    server.run_stdio()
