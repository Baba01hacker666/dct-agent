"""
dct.web.handlers_tools
REST handlers for subagents, git, MCP tools and skills.
"""

from __future__ import annotations

from aiohttp import web

from dct.web.state import WebState


class ToolsHandlersMixin(WebState):
    async def handle_get_subagents(self, request: web.Request) -> web.Response:
        from dct.tools.subagent import list_subagents

        return web.json_response({"subagents": list_subagents()})

    async def handle_spawn_subagent(
        self, request: web.Request
    ) -> web.Response:
        from dct.tools.subagent import spawn_subagent

        try:
            data = await request.json()
        except Exception:
            return self.invalid_json()

        task = data.get("task", "")
        role = data.get("role")
        model = data.get("model")
        skill = data.get("skill")
        bg = data.get("background", True)

        res = spawn_subagent(
            task=task,
            role=role,
            model=model,
            skill=skill,
            background=bg,
        )
        return web.json_response(
            {
                "ok": res.ok,
                "message": res.message,
                "output": res.output,
                "subagent_id": res.subagent_id,
            }
        )

    # ── Git ──────────────────────────────────────────────────────────────────

    async def handle_git_status(self, request: web.Request) -> web.Response:
        from dct.tools.git_tools import git_status

        res = git_status()
        return web.json_response(
            {"ok": res.ok, "output": res.output, "message": res.message}
        )

    async def handle_git_diff(self, request: web.Request) -> web.Response:
        from dct.tools.git_tools import git_diff

        cached = request.query.get("cached", "false").lower() == "true"
        res = git_diff(cached=cached)
        return web.json_response(
            {"ok": res.ok, "output": res.output, "message": res.message}
        )

    # ── MCP ──────────────────────────────────────────────────────────────────

    async def handle_get_mcp_tools(self, request: web.Request) -> web.Response:
        from dct.core.mcp_server import get_tool_definitions

        return web.json_response({"tools": get_tool_definitions()})

    # ── Skills ───────────────────────────────────────────────────────────────

    async def handle_get_skills(self, request: web.Request) -> web.Response:
        from dct.core.config import Config

        try:
            from dct.cli.shell import SKILL_PRESETS
        except ImportError:
            SKILL_PRESETS = {}

        conf = Config()
        custom = conf.get("custom_skills", {})
        skills = []
        for name, data in SKILL_PRESETS.items():
            skills.append(
                {"name": name, "desc": data.get("desc", ""), "type": "builtin"}
            )
        for name, data in custom.items():
            skills.append(
                {"name": name, "desc": data.get("desc", ""), "type": "custom"}
            )

        return web.json_response(
            {"skills": skills, "current_system": self.session.system_prompt}
        )

    async def handle_load_skill(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            name = data.get("name", "").strip()
        except Exception:
            return web.json_response(
                {"ok": False, "error": "Invalid JSON payload"}, status=400
            )

        if not name:
            self.session.set_system("")
            return web.json_response(
                {
                    "ok": True,
                    "message": (
                        "Cleared active skill preset (default system prompt "
                        "restored)"
                    ),
                }
            )

        from dct.core.config import Config

        try:
            from dct.cli.shell import SKILL_PRESETS
        except ImportError:
            SKILL_PRESETS = {}

        conf = Config()
        custom = conf.get("custom_skills", {})
        skill = custom.get(name) or SKILL_PRESETS.get(name)
        if not skill:
            return web.json_response(
                {"ok": False, "error": f"Skill '{name}' not found"}, status=404
            )

        self.session.set_system(skill["prompt"])
        return web.json_response(
            {"ok": True, "message": f"Loaded skill '{name}'", "skill": name}
        )
