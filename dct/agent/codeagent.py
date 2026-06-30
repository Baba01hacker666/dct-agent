"""
dct.agent.codeagent
Agentic loop: the model produces structured tool calls, we execute them,
feed results back, and continue until the model signals DONE.

Tool call format the model is instructed to use:

  <tool>run_python</tool>
  <code>
  print("hello")
  </code>

  <tool>run_bash</tool>
  <code>ls -la</code>

  <tool>run_shell</tool>
  <code>nmap -sV 10.0.0.1</code>

  <tool>read_file</tool>
  <path>/etc/passwd</path>

  <tool>write_file</tool>
  <path>/tmp/out.py</path>
  <code>print("written")</code>

  <tool>patch_file</tool>
  <path>/tmp/out.py</path>
  <old>print("written")</old>
  <new>print("patched")</new>

  <tool>list_dir</tool>
  <path>/tmp</path>

  <tool>tree</tool>
  <path>.</path>

  <tool>fetch_url</tool>
  <url>https://example.com</url>

  <tool>web_search</tool>
  <query>python requests library</query>

  <tool>DONE</tool>   ← signals agent should stop the loop
"""

from __future__ import annotations
import threading
import time
from itertools import count
from typing import Callable, TYPE_CHECKING

from dct.tools.executor import dispatch, ExecResult
from dct.tools.files import (
    read_file,
    write_file,
    patch_file,
    list_dir,
    tree,
    run_grep,
    run_glob,
)
from dct.tools.image import read_image
from dct.tools.web import fetch_url, search_ddg
from dct.skills.notebook import edit_notebook_cell
from dct.skills.web import fetch_and_extract
from dct.agent.parser import (
    _extract_tag,
    _has_tool_call,
    _parse_tool_call,
    _sanitize_tool_result,
)
from dct.agent.session import write_trace_entry
from dct.core.logging import get_logger

logger = get_logger("dct.agent.codeagent")

if TYPE_CHECKING:
    from dct.core.registry import Server
    from dct.agent.session import Session

MAX_AGENT_TURNS = 12  # safety cap on autonomous iterations

BACKGROUND_TASKS: dict[str, dict] = {}
BACKGROUND_TASKS_LOCK = threading.Lock()
_task_id_counter = count(1)

BACKGROUND_SUBAGENTS: dict[str, dict] = {}
BACKGROUND_SUBAGENTS_LOCK = threading.Lock()
_bg_id_counter = count(1)

# Cleanup: remove completed/failed entries older than this (seconds)
BG_CLEANUP_TTL = 300
# Max chars per background log
BG_LOG_MAX_CHARS = 10000


def _run_auto_linter(path: str) -> str:
    import subprocess
    import os

    if not os.path.exists(path):
        return ""
    ext = os.path.splitext(path)[1].lower()
    errors = []
    if ext == ".py":
        try:
            subprocess.run(
                ["python3", "-m", "py_compile", path],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            errors.append(f"SyntaxError:\n{e.stderr.strip()}")
            return "\n".join(errors)
        try:
            res = subprocess.run(
                ["ruff", "check", path], capture_output=True, text=True
            )
            if res.returncode != 0:
                errors.append(
                    f"Ruff Lint Errors:\n{res.stdout.strip() or res.stderr.strip()}"
                )
        except FileNotFoundError:
            pass
        try:
            res = subprocess.run(
                ["flake8", path], capture_output=True, text=True
            )
            if res.returncode != 0:
                errors.append(
                    f"Flake8 Lint Errors:\n{res.stdout.strip() or res.stderr.strip()}"
                )
        except FileNotFoundError:
            pass
    return "\n".join(errors) if errors else ""


def find_agents_md(cwd: str) -> str:
    import os

    agents_content = []
    current_dir = os.path.abspath(cwd)
    paths_to_check = []
    while True:
        paths_to_check.append(os.path.join(current_dir, "AGENTS.md"))
        parent = os.path.dirname(current_dir)
        if parent == current_dir:
            break
        current_dir = parent

    paths_to_check.reverse()

    for path in paths_to_check:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    agents_content.append(f"--- {path} ---\n{f.read()}")
            except OSError:
                logger.exception(
                    "Failed to read AGENTS.md directives from %s", path
                )

    if agents_content:
        return (
            "[AGENTS.md DIRECTIVES]\n" + "\n\n".join(agents_content) + "\n\n"
        )
    return ""


def load_persona_file(filename: str, default_content: str) -> str:
    import os

    path = os.path.join(os.path.expanduser("~"), ".config", "dct", filename)
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(default_content)
        return default_content
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def _cleanup_background_state() -> None:
    """Remove stale completed/failed background tasks and sub-agents."""
    now = time.time()
    with BACKGROUND_TASKS_LOCK:
        stale = [
            tid
            for tid, t in BACKGROUND_TASKS.items()
            if t["status"] in ("completed", "failed", "killed")
            and now - t.get("completed_at", 0) > BG_CLEANUP_TTL
        ]
        for tid in stale:
            del BACKGROUND_TASKS[tid]
    with BACKGROUND_SUBAGENTS_LOCK:
        stale = [
            sid
            for sid, s in BACKGROUND_SUBAGENTS.items()
            if s["status"] in ("completed", "failed")
            and now - s.get("completed_at", 0) > BG_CLEANUP_TTL
        ]
        for sid in stale:
            del BACKGROUND_SUBAGENTS[sid]


def _append_log_safe(entry: dict, text: str) -> None:
    """Append to a background entry log, capping total length."""
    entry["log"].append(text)
    total = sum(len(c) for c in entry["log"])
    while total > BG_LOG_MAX_CHARS and len(entry["log"]) > 1:
        removed = entry["log"].pop(0)
        total -= len(removed)


def get_system_prompt(session, user_system_prompt: str = "") -> str:
    import os
    import time

    os_info = os.uname().sysname if hasattr(os, "uname") else os.name
    cwd = os.getcwd()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    mode = session.mode.upper()
    plan_file = session.agent_plan_file

    prompt = f"""You are DCT-Agent, an elite autonomous AI developer built by Doraemon Cyber Team.

[ENVIRONMENT]
OS: {os_info}
Current Working Directory: {cwd}
Current Time: {now}
Current Mode: {mode}
"""

    from dct.core.config import Config

    conf = Config()
    use_native = conf.get("use_native_tools", True)

    if use_native:
        prompt += """
[AVAILABLE TOOLS]
You have access to the following tools via Native Tool Calling (e.g. `dct_tool`).
Pass the `tool_name` parameter and provide arguments in `kwargs`:
- run_python(code: str, background: bool) — execute Python 3 code
- run_bash(code: str, background: bool) — execute bash script
- run_shell(command: str, background: bool) — run a shell command
- read_file(path: str, start_line: int, end_line: int, tail: int) — read a file
- read_image(path: str) — read an image file for vision models
- write_file(path: str, code: str) — write/create a file
- patch_file(path: str, old: str, new: str) — find+replace in file
- multi_patch_file(path: str, patches: list) — multiple non-contiguous find+replaces
- list_dir(path: str) — list directory
- tree(path: str) — directory tree
- glob(pattern: str, path: str) — fast file discovery using ripgrep
- repo_map(path: str) — Generate a semantic map of all classes and functions
- goto_definition(path: str, line: int, column: int) — Find definition of a symbol
- find_references(path: str, line: int, column: int) — Find all references to a symbol
- update_plan(plan: str, explanation: str) — Track steps and progress in a markdown plan
- notebook_edit(path: str, index: int, mode: str, source: str) — Edit jupyter notebooks
- web_extract(url: str, selector: str) — Fetch webpage and optionally extract via CSS selector
- grep(pattern: str, path: str, glob: str, output_mode: str, context: int) — fast regex search
- fetch_url(url: str) — fetch a URL
- ask_user(question: str, choices: str) — Ask the user a question
- get_cwd() — Get current working directory
- run_subagent(instruction: str, model: str, skill: str, system_prompt: str, background: bool) — spawn a sub-agent
- run_swarm(instruction: str, members: str) — spawn a parallel swarm of agents
- mcp_list() — List all connected MCP servers and their tools
- mcp_call(server: str, name: str, args: dict) — Call an MCP server tool
- memory_store(text: str) — Store important facts in vector memory
- memory_search(query: str) — Semantically search long-term memory
- bg_status(id: str) — check status/logs of background tasks/sub-agents
- bg_kill(id: str) — kill a running background task
- bg_send_input(id: str, input: str) — send input to a running background task
- enter_plan_mode() — Enter PLAN mode to explore and write a plan before coding
- exit_plan_mode() — Exit PLAN mode once a plan is approved
- skill_list() — List available built-in and custom skills
- skill_load(name: str) — Apply a skill to current session
- skill_create(name: str, description: str, prompt: str) — Create or update a custom skill autonomously
- DONE() — Finish your work
"""
        if conf.get("enable_persona", True):
            prompt += "- core_memory_manage(action: str, section: str, old_text: str, new_text: str) — Autonomously update your core identity/memory\n"

        prompt += """
[TOOL CALL FORMAT]
- You MUST use the provided Native Function/Tool Call API (`dct_tool`).
- Do NOT output raw XML tags like <tool>...</tool> in your text! Provide structured arguments.
- Pass the `tool_name` parameter and place the tool's required parameters into the `kwargs` dict.
- Always output exactly ONE tool call at a time.
- Finish only when truly done by calling `dct_tool` with `tool_name='DONE'`.
"""
    else:
        prompt += """
[AVAILABLE TOOLS]
You can use tools by emitting structured XML tags in your response.
  <tool>run_python</tool><code>...</code><background>true|false</background>  — execute Python 3 code
  <tool>run_bash</tool><code>...</code><background>true|false</background>    — execute bash script
  <tool>run_shell</tool><code>...</code><background>true|false</background>   — run a shell command
  <tool>read_file</tool><path>...</path><start_line>...</start_line><end_line>...</end_line><tail>...</tail> — read a file
  <tool>read_image</tool><path>...</path>        — read an image file
  <tool>write_file</tool><path>...</path><code>...</code>  — write/create a file
  <tool>patch_file</tool><path>...</path><old>...</old><new>...</new>  — find+replace in file
  <tool>multi_patch_file</tool><path>...</path><patch><old>...</old><new>...</new></patch> — multiple non-contiguous find+replaces
  <tool>list_dir</tool><path>...</path>          — list directory
  <tool>tree</tool><path>...</path>              — directory tree
  <tool>glob</tool><pattern>...</pattern><path>...</path>      — fast file discovery
  <tool>repo_map</tool><path>...</path>          — Generate a semantic map
  <tool>goto_definition</tool><path>...</path><line>...</line><column>0</column> — Find definition
  <tool>find_references</tool><path>...</path><line>...</line><column>0</column> — Find references
  <tool>task_create</tool><subject>...</subject><description>...</description> — Create tasks
  <tool>task_update</tool><id>...</id><status>...</status>       — Update task
  <tool>task_list</tool>                                         — List tasks
  <tool>notebook_edit</tool><path>...</path><index>...</index><mode>replace|insert|delete</mode><source>...</source> — Edit notebooks
  <tool>web_extract</tool><url>...</url><selector>...</selector> — Fetch webpage
  <tool>grep</tool><pattern>...</pattern><path>...</path><glob>...</glob><output_mode>content</output_mode><context>2</context>  — regex search
  <tool>fetch_url</tool><url>...</url>           — fetch a URL
  <tool>ask_user</tool><question>...</question><choices>a,b,c</choices>  — Ask the user
  <tool>get_cwd</tool>                           — Get current working directory
  <tool>run_subagent</tool><instruction>...</instruction> — spawn sub-agent
  <tool>run_swarm</tool><instruction>...</instruction><members>...</members> — spawn parallel swarm
  <tool>mcp_list</tool>                          — List connected MCP tools
  <tool>mcp_call</tool><server>...</server><name>...</name><args>{{...json...}}</args> — Call MCP tool
  <tool>memory_store</tool><text>...</text>      — Store memory
  <tool>memory_search</tool><query>...</query>   — Search memory
  <tool>bg_status</tool><id>...</id>             — Check background tasks
  <tool>bg_kill</tool><id>...</id>               — Kill background task
  <tool>bg_send_input</tool><id>...</id><input>...</input> — Send input to background task
  <tool>enter_plan_mode</tool>                   — Enter PLAN mode
  <tool>exit_plan_mode</tool>                    — Exit PLAN mode
  <tool>skill_list</tool>                        — List skills
  <tool>skill_load</tool><name>...</name>        — Apply skill
  <tool>skill_create</tool><name>...</name><prompt>...</prompt> — Create custom skill
  <tool>DONE</tool>                              — Finish execution
"""
        if conf.get("enable_persona", True):
            prompt += "  <tool>core_memory_manage</tool><action>append|replace|rewrite</action><section>...</section><new_text>...</new_text> — Update memory\n"

        prompt += """
[TOOL CALL FORMAT]
- Always output exactly ONE tool call at a time.
- Use this shape:
  <tool>run_shell</tool>
  <code>pwd</code>
- For file reads:
  <tool>read_file</tool>
  <path>README.md</path>
- For multi-patch edits:
  <tool>multi_patch_file</tool>
  <path>file.py</path>
  <patch>
  <old>old_text_1</old>
  <new>new_text_1</new>
  </patch>
"""

    prompt += """
[WORKFLOW & GUIDELINES]
1) Understand the user goal and constraints.
2) If information is missing, use read/search tools first.
3) Make small, verifiable steps and inspect results.
4) Prefer minimal safe edits; do not overwrite unrelated content.
5) Summarize what changed and what remains, then emit the DONE tool.

[IMPORTANT BEHAVIOR]
- If the user is just chatting or greeting (e.g., 'hi', 'hello'), respond conversationally without invoking any tools. Use tools ONLY when necessary to fulfill a specific actionable request.
- Never invent or hallucinate tool output. If unsure, run a tool.
- If a tool fails, explain briefly and try an alternative.
- Keep responses compact between tool calls.
- When modifying files, prefer `patch_file` or `multi_patch_file` for targeted edits.
- Do not repeatedly list directories (`ls`, `list_dir`, `tree`) if you already know they are empty or if you have already seen their contents.
- Manage your core persona using `core_memory_manage`. Update 'user.md' with user preferences, 'memory.md' with crucial global context, 'project.md' with repo-specific knowledge (build commands, architecture), and 'soul.md' to evolve your own core directives.
"""

    if session.mode == "plan":
        prompt += f"""
[PLAN MODE ACTIVE]
You are currently in PLAN mode.
- You CANNOT execute code (run_python, run_bash, run_shell are BLOCKED).
- You CANNOT modify files, EXCEPT for the designated plan file: {plan_file}
- Your goal is to use read_file, grep, list_dir, and tree to explore the codebase, understand patterns, and write a concrete implementation strategy into the plan file using write_file.
- Once the user approves the plan, use `exit_plan_mode` to return to execution mode.
"""

    if conf.get("enable_persona", True):
        soul_content = load_persona_file(
            "soul.md",
            "You are DCT Agent, an autonomous and elite developer AI.\nYou prioritize clean code, user autonomy, and security.",
        )
        user_content = load_persona_file(
            "user.md",
            "The user is a developer using DCT Agent. They prefer concise and direct answers.",
        )
        memory_content = load_persona_file(
            "memory.md",
            "- Initialized memory.\n- Use core_memory_manage to add important facts here.",
        )

        # OpenHands-style Project Memory
        import os

        project_dir = os.path.join(os.getcwd(), ".dct")
        project_path = os.path.join(project_dir, "project.md")
        if not os.path.exists(project_path):
            os.makedirs(project_dir, exist_ok=True)
            with open(project_path, "w", encoding="utf-8") as f:
                f.write(
                    "- Initialized project memory. Store repository-specific knowledge here."
                )
        with open(project_path, "r", encoding="utf-8") as f:
            project_content = f.read().strip()

        prompt += f"""
[CORE MEMORY]
<soul>
{soul_content}
</soul>

<user_profile>
{user_content}
</user_profile>

<global_memory>
{memory_content}
</global_memory>

<project_memory>
{project_content}
</project_memory>

{find_agents_md(os.getcwd())}
"""

    if user_system_prompt.strip():
        prompt += f"""
[USER SYSTEM PREFERENCES]
Apply the following additional instructions while still obeying all tool and safety rules above:
{user_system_prompt.strip()}
"""

    return prompt


class CodeAgent:
    """
    Agentic loop around a streaming Ollama model.
    Parses tool calls from model output, executes them, feeds results back.
    """

    def __init__(
        self,
        server: "Server",
        model: str,
        session: "Session",
        stream_fn: Callable,
        on_text: Callable[[str], None] = print,
        on_tool: Callable[[str, str], None] | None = None,
        on_result: Callable[[str, str], None] | None = None,
        max_turns: int = MAX_AGENT_TURNS,
    ):
        self.server = server
        self.model = model
        self.session = session
        self.stream_fn = stream_fn
        self.on_text = on_text
        self.on_tool = on_tool
        self.on_result = on_result
        self.max_turns = max_turns

    def _execute_tool(self, call: dict) -> str:
        """Dispatch tool call, return result string for model."""
        tool = call["tool"]
        mode = self.session.mode
        plan_file = self.session.agent_plan_file

        if tool == "enter_plan_mode":
            self.session.mode = "plan"
            return f"[PLAN MODE ENTERED]\nYou are now in PLAN mode.\n- Exploration tools (read_file, grep, etc.) are UNLOCKED.\n- Execution and modification tools are BLOCKED.\n- You may ONLY write to the plan file: {plan_file}\n\nBegin exploring the codebase and write your strategy to the plan file. Once the user approves, use <tool>exit_plan_mode</tool>."

        elif tool == "exit_plan_mode":
            self.session.mode = "execute"
            return "[PLAN MODE EXITED]\nYou are now in EXECUTE mode. All tools (including execution and file modification) are unlocked. Proceed with implementing your plan."

        elif tool == "skill_list":
            from dct.core.config import Config

            try:
                from dct.cli.shell import SKILL_PRESETS
            except ImportError:
                SKILL_PRESETS = {}
            conf = Config()
            custom = conf.get("custom_skills", {})
            lines = ["[AVAILABLE SKILLS]"]
            lines.append("Built-in:")
            for k, v in SKILL_PRESETS.items():
                lines.append(f"  - {k}: {v.get('desc', '')}")
            lines.append("Custom:")
            for k, v in custom.items():
                lines.append(f"  - {k}: {v.get('desc', '')}")
            return "\n".join(lines)

        elif tool == "skill_load":
            name = call.get("name")
            if not name:
                return "[TOOL ERROR] <name> is required."
            from dct.core.config import Config

            try:
                from dct.cli.shell import SKILL_PRESETS
            except ImportError:
                SKILL_PRESETS = {}
            conf = Config()
            custom = conf.get("custom_skills", {})
            skill = custom.get(name) or SKILL_PRESETS.get(name)
            if not skill:
                return f"[TOOL ERROR] Skill '{name}' not found. Use <tool>skill_list</tool> to see available skills."
            self.session.set_system(skill["prompt"])
            return f"[Success] Loaded skill '{name}'. System prompt updated for subsequent turns."

        elif tool == "skill_create":
            name = call.get("name")
            desc = call.get("description")
            prompt_text = call.get("prompt")
            if not name or not desc or not prompt_text:
                return "[TOOL ERROR] <name>, <description>, and <prompt> are required."

            from dct.core.config import Config

            try:
                from dct.cli.shell import SKILL_PRESETS
            except ImportError:
                SKILL_PRESETS = {}
            if name in SKILL_PRESETS:
                return f"[TOOL ERROR] '{name}' is a built-in skill. Choose a different name."

            conf = Config()
            custom = dict(conf.get("custom_skills", {}))
            custom[name] = {"desc": desc, "prompt": prompt_text.strip()}
            conf.set("custom_skills", custom)
            conf.save()
            return f"[Success] Created custom skill '{name}'. You can now load it using <tool>skill_load</tool>."

        elif tool == "run_swarm":
            instruction = call.get("instruction") or ""
            members_text = call.get("members") or ""
            if not instruction or not members_text:
                return "[TOOL ERROR] <instruction> and <members> are required."

            lines = [L.strip() for L in members_text.splitlines() if L.strip()]
            if not lines:
                return "[TOOL ERROR] No members defined."

            from dct.core.registry import ServerRegistry

            registry = ServerRegistry()

            from dct.core.config import Config

            try:
                from dct.cli.shell import SKILL_PRESETS
            except ImportError:
                SKILL_PRESETS = {}
            conf = Config()
            custom_skills = conf.get("custom_skills", {})

            spawned = []
            for line in lines:
                parts = [p.strip() for p in line.split("|")]
                role = parts[0] if len(parts) > 0 else "member"
                s_model = (
                    parts[1] if len(parts) > 1 and parts[1] else self.model
                )
                s_server_alias = (
                    parts[2] if len(parts) > 2 and parts[2] else ""
                )
                s_skill = parts[3] if len(parts) > 3 and parts[3] else ""

                target_server = self.server
                if s_server_alias:
                    resolved = registry.resolve(s_server_alias)
                    if resolved and resolved.status == "online":
                        target_server = resolved
                    else:
                        rt = registry.route(s_model, s_server_alias)
                        if rt:
                            target_server, s_model = rt
                else:
                    rt = registry.route(s_model)
                    if rt:
                        target_server, s_model = rt

                sub_system = f"Your role in this swarm: {role}\n"
                if s_skill:
                    skill_data = custom_skills.get(
                        s_skill
                    ) or SKILL_PRESETS.get(s_skill)
                    if skill_data:
                        sub_system += skill_data["prompt"] + "\n\n"

                from dct.agent.session import Session as SubSession

                sub_session = SubSession(mode=self.session.mode)
                sub_dynamic = get_system_prompt(
                    sub_session, user_system_prompt=sub_system
                )
                sub_session.set_system(sub_dynamic)
                sub_session.add("user", instruction)

                _cleanup_background_state()
                with BACKGROUND_SUBAGENTS_LOCK:
                    bg_id = f"swarm_{role}_{next(_bg_id_counter)}"
                    BACKGROUND_SUBAGENTS[bg_id] = {
                        "instruction": f"[SWARM: {role}] {instruction}",
                        "model": s_model,
                        "status": "running",
                        "result": "",
                        "log": [],
                        "completed_at": 0,
                    }

                bg_sub_data = BACKGROUND_SUBAGENTS[bg_id]

                def _make_callbacks(data):
                    def on_text(chunk):
                        _append_log_safe(data, chunk)

                    def on_tool(t_name, t_call):
                        _append_log_safe(
                            data, f"\n⚡ tool: {t_name}\nCall: {t_call}\n"
                        )

                    def on_result(t_name, t_res):
                        _append_log_safe(
                            data, f"\nresult: {t_name}\n{t_res}\n"
                        )

                    return on_text, on_tool, on_result

                bg_on_text, bg_on_tool, bg_on_result = _make_callbacks(
                    bg_sub_data
                )

                sub_agent = CodeAgent(
                    server=target_server,
                    model=s_model,
                    session=sub_session,
                    stream_fn=self.stream_fn,
                    on_text=bg_on_text,
                    on_tool=bg_on_tool,
                    on_result=bg_on_result,
                    max_turns=self.max_turns,
                )

                def run_subagent_bg(b_id, agent_instance, msgs):
                    try:
                        res = agent_instance.run(msgs)
                        with BACKGROUND_SUBAGENTS_LOCK:
                            BACKGROUND_SUBAGENTS[b_id]["status"] = "completed"
                            BACKGROUND_SUBAGENTS[b_id]["result"] = res
                            BACKGROUND_SUBAGENTS[b_id][
                                "completed_at"
                            ] = time.time()
                    except Exception as e:
                        with BACKGROUND_SUBAGENTS_LOCK:
                            BACKGROUND_SUBAGENTS[b_id]["status"] = "failed"
                            BACKGROUND_SUBAGENTS[b_id]["result"] = str(e)
                            BACKGROUND_SUBAGENTS[b_id][
                                "completed_at"
                            ] = time.time()

                sub_thread = threading.Thread(
                    target=run_subagent_bg,
                    args=(bg_id, sub_agent, sub_session.as_messages()),
                    daemon=True,
                )
                sub_thread.start()
                spawned.append(
                    f"Role: {role} | Task ID: {bg_id} | Model: {s_model} | Server: {target_server.alias}"
                )

            return "[Swarm started in background]\n" + "\n".join(spawned)

        elif tool == "mcp_list":
            from dct.core.mcp import get_mcp_manager
            from dct.core.config import Config

            conf = Config()
            mcp_servers = conf.get("mcp_servers", {})
            mgr = get_mcp_manager()
            for sname, scmd in mcp_servers.items():
                mgr.add_server(sname, scmd)
            return mgr.list_all_tools()

        elif tool == "mcp_call":
            s_server = call.get("server")
            t_name = call.get("name")
            t_args_str = call.get("args") or "{}"
            if not s_server or not t_name:
                return "[TOOL ERROR] <server> and <name> are required."
            try:
                import json

                t_args = json.loads(t_args_str)
            except json.JSONDecodeError:
                return "[TOOL ERROR] <args> must be valid JSON."

            from dct.core.mcp import get_mcp_manager
            from dct.core.config import Config

            mgr = get_mcp_manager()
            conf = Config()
            if s_server not in mgr.clients:
                mcp_servers = conf.get("mcp_servers", {})
                if s_server in mcp_servers:
                    mgr.add_server(s_server, mcp_servers[s_server])

            return mgr.call_tool(s_server, t_name, t_args)

        elif tool == "memory_store":
            m_text = call.get("text")
            if not m_text:
                return "[TOOL ERROR] <text> is required."
            from dct.core.client import get_embeddings
            from dct.core.memory import get_store

            try:
                vec = get_embeddings(self.server, m_text)
            except Exception as e:
                return f"[TOOL ERROR] Embedding API failed: {e}"
            if not vec:
                return "[TOOL ERROR] Embedding API returned empty vector."
            return get_store().store(m_text, vec)

        elif tool == "memory_search":
            m_query = call.get("query")
            if not m_query:
                return "[TOOL ERROR] <query> is required."
            from dct.core.client import get_embeddings
            from dct.core.memory import get_store

            try:
                vec = get_embeddings(self.server, m_query)
            except Exception as e:
                return f"[TOOL ERROR] Embedding API failed: {e}"
            if not vec:
                return "[TOOL ERROR] Embedding API returned empty vector."
            results = get_store().search(vec, top_k=3)
            if not results:
                return "No matching memories found."
            lines = ["[MEMORY RESULTS]"]
            for mem_res in results:
                lines.append(f"- {mem_res['text']}")
            return "\n".join(lines)

        elif tool == "core_memory_manage":
            from dct.core.config import Config

            if not Config().get("enable_persona", True):
                return "[TOOL ERROR] Persona feature is disabled in config."

            m_action = call.get("action")
            m_section = call.get("section")
            m_old = call.get("old_text") or ""
            m_new = call.get("new_text") or ""

            if m_section not in ("soul", "user", "memory", "project"):
                return "[TOOL ERROR] <section> must be one of: soul, user, memory, project."

            import os

            if m_section == "project":
                path = os.path.join(os.getcwd(), ".dct", "project.md")
            else:
                path = os.path.join(
                    os.path.expanduser("~"),
                    ".config",
                    "dct",
                    f"{m_section}.md",
                )

            if m_action == "append":
                if not m_new:
                    return "[TOOL ERROR] <new_text> is required for append."
                with open(path, "a", encoding="utf-8") as f:
                    f.write(f"\n{m_new}")
                return f"[Success] Appended to {m_section}.md. It will be visible next turn."

            elif m_action == "replace":
                if not m_old or not m_new:
                    return "[TOOL ERROR] <old_text> and <new_text> required."
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                if m_old not in content:
                    return f"[TOOL ERROR] Exact <old_text> not found in {m_section}.md."
                content = content.replace(m_old, m_new)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                return f"[Success] Replaced text in {m_section}.md."

            elif m_action == "rewrite":
                if not m_new:
                    return "[TOOL ERROR] <new_text> required for rewrite."
                with open(path, "w", encoding="utf-8") as f:
                    f.write(m_new)
                return f"[Success] Rewrote entire {m_section}.md."

            else:
                return "[TOOL ERROR] <action> must be append, replace, or rewrite."

        elif tool == "run_subagent":
            instruction = (
                call.get("instruction")
                or call.get("prompt")
                or call.get("code")
                or ""
            )
            if not instruction:
                return "[TOOL ERROR] <instruction> is required."

            sub_model = call.get("model") or self.model
            sub_system = call.get("system_prompt") or ""
            sub_skill = call.get("skill") or ""
            is_bg = (call.get("background") or "").strip().lower() == "true"

            if sub_skill:
                from dct.core.config import Config

                try:
                    from dct.cli.shell import SKILL_PRESETS
                except ImportError:
                    SKILL_PRESETS = {}
                conf = Config()
                custom = conf.get("custom_skills", {})
                skill_data = custom.get(sub_skill) or SKILL_PRESETS.get(
                    sub_skill
                )
                if skill_data:
                    sub_system = skill_data["prompt"] + "\n\n" + sub_system
                else:
                    return f"[TOOL ERROR] Skill '{sub_skill}' not found."

            from dct.agent.session import Session as AgentSession

            sub_session = AgentSession(mode=self.session.mode)

            sub_dynamic_prompt = get_system_prompt(
                sub_session, user_system_prompt=sub_system
            )
            sub_session.set_system(sub_dynamic_prompt)
            sub_session.add("user", instruction)

            if is_bg:
                _cleanup_background_state()
                with BACKGROUND_SUBAGENTS_LOCK:
                    bg_id = f"subagent_{next(_bg_id_counter)}"
                    BACKGROUND_SUBAGENTS[bg_id] = {
                        "instruction": instruction,
                        "model": sub_model,
                        "status": "running",
                        "result": "",
                        "log": [],
                        "completed_at": 0,
                    }

                bg_sub_data = BACKGROUND_SUBAGENTS[bg_id]

                def bg_on_text(chunk: str):
                    _append_log_safe(bg_sub_data, chunk)

                def bg_on_tool(sub_tool_name: str, sub_call_str: str):
                    _append_log_safe(
                        bg_sub_data,
                        f"\n⚡ tool: {sub_tool_name}\nCall: {sub_call_str}\n",
                    )

                def bg_on_result(sub_tool_name: str, sub_result: str):
                    _append_log_safe(
                        bg_sub_data,
                        f"\nresult: {sub_tool_name}\n{sub_result}\n",
                    )

                sub_agent = CodeAgent(
                    server=self.server,
                    model=sub_model,
                    session=sub_session,
                    stream_fn=self.stream_fn,
                    on_text=bg_on_text,
                    on_tool=bg_on_tool,
                    on_result=bg_on_result,
                    max_turns=self.max_turns,
                )

                def run_subagent_bg(b_id, agent_instance, msgs):
                    try:
                        res = agent_instance.run(msgs)
                        with BACKGROUND_SUBAGENTS_LOCK:
                            BACKGROUND_SUBAGENTS[b_id]["status"] = "completed"
                            BACKGROUND_SUBAGENTS[b_id]["result"] = res
                            BACKGROUND_SUBAGENTS[b_id][
                                "completed_at"
                            ] = time.time()
                    except Exception as e:
                        with BACKGROUND_SUBAGENTS_LOCK:
                            BACKGROUND_SUBAGENTS[b_id]["status"] = "failed"
                            BACKGROUND_SUBAGENTS[b_id]["result"] = str(e)
                            BACKGROUND_SUBAGENTS[b_id][
                                "completed_at"
                            ] = time.time()

                sub_thread = threading.Thread(
                    target=run_subagent_bg,
                    args=(bg_id, sub_agent, sub_session.as_messages()),
                    daemon=True,
                )
                sub_thread.start()

                from dct.core.theme import con, C

                con.print(
                    f"\n  [{C['purple']}][SUB-AGENT STARTED IN BACKGROUND][/{C['purple']}] Task ID: {bg_id} | Model: {sub_model}"
                )
                return f"[Sub-agent started in background. Task ID: {bg_id}]"

            else:
                from dct.core.theme import con, C, info, section

                con.print(
                    f"\n  [{C['purple']}][SUB-AGENT STARTING][/{C['purple']}] Model: {sub_model} | Mode: {sub_session.mode.upper()}"
                )
                con.print(
                    f"  [{C['dim']}]Instruction: {instruction}[/{C['dim']}]"
                )
                con.print(f"  [{C['dim']}]{'─' * 66}[/{C['dim']}]")

                def sub_on_text(chunk: str):
                    con.print(
                        f"[{C['purple']}]{chunk}[/{C['purple']}]", end=""
                    )

                def sub_on_tool(sub_tool_name: str, sub_call_str: str):
                    con.print()
                    con.print(
                        f"\n  [{C['purple']}]⚡ sub-agent tool:[/{C['purple']}] [{C['fg']}]{sub_tool_name}[/{C['fg']}]"
                    )

                def sub_on_result(sub_tool_name: str, sub_result: str):
                    section(f"sub-agent result: {sub_tool_name}")
                    if len(sub_result) > 2000:
                        con.print(
                            f"[{C['code']}]{sub_result[:2000]}[/{C['code']}]"
                        )
                        info(f"… ({len(sub_result)} chars total)")
                    else:
                        con.print(f"[{C['code']}]{sub_result}[/{C['code']}]")
                    con.print()
                    con.print(
                        f"  [{C['dim']}]continuing sub-agent…[/{C['dim']}]"
                    )
                    con.print("  ", end="")

                sub_agent = CodeAgent(
                    server=self.server,
                    model=sub_model,
                    session=sub_session,
                    stream_fn=self.stream_fn,
                    on_text=sub_on_text,
                    on_tool=sub_on_tool,
                    on_result=sub_on_result,
                    max_turns=self.max_turns,
                )

                try:
                    sub_response = sub_agent.run(sub_session.as_messages())
                    con.print(
                        f"\n  [{C['purple']}][SUB-AGENT COMPLETED][/{C['purple']}]"
                    )
                    con.print(f"  [{C['dim']}]{'─' * 66}[/{C['dim']}]")
                    return f"[Sub-agent completed task successfully]\nResponse: {sub_response}"
                except Exception as e:
                    con.print(
                        f"\n  [{C['err']}][SUB-AGENT FAILED]: {str(e)}[/{C['err']}]"
                    )
                    con.print(f"  [{C['dim']}]{'─' * 66}[/{C['dim']}]")
                    return f"[TOOL ERROR] Sub-agent execution failed: {str(e)}"

        elif tool == "bg_status":
            _cleanup_background_state()
            tid = call.get("id")
            if tid:
                with BACKGROUND_TASKS_LOCK:
                    if tid in BACKGROUND_TASKS:
                        bg_task = BACKGROUND_TASKS[tid]
                        log_str = "".join(bg_task["log"])
                        return f"[Background Task Details]\nTask ID: {tid}\nCommand: {bg_task['command']}\nStatus: {bg_task['status']}\nResult: {bg_task['result']}\nLogs:\n{log_str}"

                with BACKGROUND_SUBAGENTS_LOCK:
                    if tid in BACKGROUND_SUBAGENTS:
                        sub = BACKGROUND_SUBAGENTS[tid]
                        log_str = "".join(sub["log"])
                        return f"[Background Sub-Agent Details]\nTask ID: {tid}\nInstruction: {sub['instruction']}\nStatus: {sub['status']}\nResult: {sub['result']}\nLogs:\n{log_str}"

                return f"[TOOL ERROR] Background task or sub-agent with ID {tid} not found."

            lines = ["[BACKGROUND TASKS & SUB-AGENTS]"]
            with BACKGROUND_TASKS_LOCK:
                for t_id, task in BACKGROUND_TASKS.items():
                    lines.append(
                        f"- {t_id} (Task): {task['status']} | Command: {task['command'][:60]}"
                    )
            with BACKGROUND_SUBAGENTS_LOCK:
                for s_id, sub in BACKGROUND_SUBAGENTS.items():
                    lines.append(
                        f"- {s_id} (Sub-agent): {sub['status']} | Instruction: {sub['instruction'][:60]}"
                    )

            if len(lines) == 1:
                return "No active or completed background tasks or sub-agents."
            return "\n".join(lines)

        elif tool == "bg_kill":
            tid = call.get("id")
            if not tid:
                return "[TOOL ERROR] <id> is required for bg_kill."

            with BACKGROUND_TASKS_LOCK:
                if tid in BACKGROUND_TASKS:
                    bg_task = BACKGROUND_TASKS[tid]
                    if bg_task["status"] != "running":
                        return f"[TOOL ERROR] Task {tid} is not running (status: {bg_task['status']})."

                    proc = bg_task.get("proc")
                    if proc:
                        try:
                            import subprocess

                            proc.terminate()
                            try:
                                proc.wait(timeout=1)
                            except subprocess.TimeoutExpired:
                                proc.kill()
                        except Exception:
                            pass

                    bg_task["status"] = "killed"
                    bg_task["result"] = "[Killed by user/agent]"
                    bg_task["completed_at"] = time.time()
                    bg_task["log"].append("[Process terminated by bg_kill]\n")
                    return f"[Success] Terminated background task {tid}."

            return f"[TOOL ERROR] Background task with ID {tid} not found."

        elif tool == "bg_send_input":
            tid = call.get("id")
            input_text = call.get("input")
            if not tid:
                return "[TOOL ERROR] <id> is required for bg_send_input."
            if input_text is None:
                return "[TOOL ERROR] <input> is required for bg_send_input."

            if not input_text.endswith("\n"):
                input_text += "\n"

            with BACKGROUND_TASKS_LOCK:
                if tid in BACKGROUND_TASKS:
                    bg_task = BACKGROUND_TASKS[tid]
                    if bg_task["status"] != "running":
                        return f"[TOOL ERROR] Task {tid} is not running (status: {bg_task['status']})."

                    proc = bg_task.get("proc")
                    if not proc or not proc.stdin:
                        return f"[TOOL ERROR] Task {tid} has no active input stream."

                    try:
                        proc.stdin.write(input_text)
                        proc.stdin.flush()
                        bg_task["log"].append(f"[Input sent: {input_text}]")
                        return (
                            f"[Success] Sent input to background task {tid}."
                        )
                    except Exception as e:
                        return f"[TOOL ERROR] Failed to write to task stdin: {str(e)}"

            return f"[TOOL ERROR] Background task with ID {tid} not found."

        if tool in (
            "run_python",
            "run_bash",
            "run_shell",
            "python",
            "bash",
            "shell",
        ):
            if mode == "plan":
                return "[TOOL ERROR] Execution is blocked in PLAN mode. You must use <tool>exit_plan_mode</tool> first."

            lang = (
                "python"
                if "python" in tool
                else "bash" if "bash" in tool else "shell"
            )
            code = call.get("code") or ""
            if not code:
                return "[TOOL ERROR] No code provided. You must wrap your code/script inside <code>...</code> tags."

            is_bg = (call.get("background") or "").strip().lower() == "true"
            if is_bg:
                _cleanup_background_state()
                import subprocess
                import os
                from dct.tools.executor import prepare_background_command

                with BACKGROUND_TASKS_LOCK:
                    task_id = f"task_{next(_task_id_counter)}"
                    BACKGROUND_TASKS[task_id] = {
                        "command": code,
                        "lang": lang,
                        "status": "running",
                        "result": "",
                        "log": [],
                        "completed_at": 0,
                        "proc": None,
                        "temp_file": None,
                    }

                cmd_args, temp_file = prepare_background_command(lang, code)
                try:
                    proc = subprocess.Popen(
                        cmd_args,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        stdin=subprocess.PIPE,
                        text=True,
                        bufsize=1,
                        universal_newlines=True,
                    )
                    with BACKGROUND_TASKS_LOCK:
                        BACKGROUND_TASKS[task_id]["proc"] = proc
                        BACKGROUND_TASKS[task_id]["temp_file"] = temp_file
                except Exception as e:
                    with BACKGROUND_TASKS_LOCK:
                        BACKGROUND_TASKS[task_id]["status"] = "failed"
                        BACKGROUND_TASKS[task_id][
                            "result"
                        ] = f"Failed to start process: {str(e)}"
                        BACKGROUND_TASKS[task_id]["completed_at"] = time.time()
                    if temp_file:
                        try:
                            os.unlink(temp_file)
                        except Exception:
                            pass
                    return f"[TOOL ERROR] Failed to start background process: {str(e)}"

                def read_output(t_id, p_obj):
                    try:
                        # Read line-by-line
                        for line in iter(p_obj.stdout.readline, ""):
                            if not line:
                                break
                            with BACKGROUND_TASKS_LOCK:
                                if t_id in BACKGROUND_TASKS:
                                    _append_log_safe(
                                        BACKGROUND_TASKS[t_id], line
                                    )
                    except Exception as e:
                        with BACKGROUND_TASKS_LOCK:
                            if t_id in BACKGROUND_TASKS:
                                BACKGROUND_TASKS[t_id]["log"].append(
                                    f"[Error reading output: {str(e)}]\n"
                                )
                    finally:
                        rc = p_obj.wait()

                        # Clean up temp file and set exit status
                        temp_file_to_del = None
                        with BACKGROUND_TASKS_LOCK:
                            if t_id in BACKGROUND_TASKS:
                                task_entry = BACKGROUND_TASKS[t_id]
                                temp_file_to_del = task_entry.get("temp_file")
                                if task_entry["status"] == "running":
                                    task_entry["status"] = (
                                        "completed" if rc == 0 else "failed"
                                    )
                                    task_entry["result"] = (
                                        f"[Completed with exit code {rc}]"
                                    )
                                task_entry["completed_at"] = time.time()
                                task_entry["log"].append(
                                    f"[Process exited with code {rc}]\n"
                                )

                        if temp_file_to_del:
                            try:
                                os.unlink(temp_file_to_del)
                            except Exception:
                                pass

                cmd_thread = threading.Thread(
                    target=read_output, args=(task_id, proc), daemon=True
                )
                cmd_thread.start()
                return f"[Task started in background. Task ID: {task_id}]"

            result: ExecResult = dispatch(lang, code, timeout=30)
            out = result.summary()
            status = "✓" if result.ok else "✗"
            return f"[{status} {lang} exit={result.returncode} {result.duration_ms}ms]\n{out}"
        elif tool == "repo_map":
            path = call.get("path") or "."
            from dct.tools.lsp import generate_repo_map

            res = generate_repo_map(path)
            if not res.ok:
                return f"[TOOL ERROR] {res.message}"
            return f"Semantic Repo Map:\n{res.data}"

        elif tool in ("goto_definition", "find_references"):
            path = call.get("path") or ""
            line_str = call.get("line") or ""
            col_str = call.get("column") or "0"
            if not path or not line_str:
                return (
                    f"[TOOL ERROR] <path> and <line> are required for {tool}."
                )
            try:
                lint = int(line_str)
                cint = int(col_str)
            except ValueError:
                return "[TOOL ERROR] <line> and <column> must be integers."

            from dct.tools.lsp import goto_definition, find_references
            import json

            if tool == "goto_definition":
                res = goto_definition(path, lint, cint)
            else:
                res = find_references(path, lint, cint)

            if not res.ok:
                return f"[TOOL ERROR] {res.message}"
            return json.dumps(res.data, indent=2)

        elif tool == "read_image":
            path = call.get("path") or ""
            if not path:
                return "[TOOL ERROR] <path> is required for read_image tool."
            img_res = read_image(path)
            if not img_res.ok:
                return f"[TOOL ERROR] {img_res.message}"
            return f"[image: {img_res.path}  {img_res.mime_type}  data_url length: {len(img_res.data_url)} chars]\n{img_res.data_url}"

        elif tool == "read_file":
            path = call.get("path") or ""
            start_str = call.get("start_line")
            end_str = call.get("end_line")
            tail_str = call.get("tail")

            try:
                start_line = int(start_str) if start_str else None
                end_line = int(end_str) if end_str else None
                tail = int(tail_str) if tail_str else None
            except ValueError:
                return "[TOOL ERROR] start_line, end_line, and tail must be integers."

            file_res = read_file(
                path,
                start_line=start_line,
                end_line=end_line,
                tail=tail,
            )
            if not file_res.ok:
                return f"[TOOL ERROR] {file_res.message}"
            if getattr(file_res, "warning", ""):
                return f"[WARNING] {file_res.warning}\n{file_res.content}"
            return file_res.content

        elif tool == "write_file":
            path = call.get("path") or call.get("file") or ""
            if not path:
                return "[TOOL ERROR] You must provide a <path> tag specifying the file location."

            if mode == "plan":
                import os

                if os.path.abspath(path) != plan_file:
                    return f"[TOOL ERROR] In PLAN mode, you may only modify the designated plan file: {plan_file}"

            content = call.get("code") or ""
            write_res = write_file(path, content)
            if not write_res.ok:
                return f"[TOOL ERROR] {write_res.message}"
            size_info = f"  {len(content.encode('utf-8', errors='replace')) / 1024:.1f} KB"
            res_str = f"[written: {write_res.path}{size_info}]\n{write_res.diff[:1200] if write_res.diff else '(new file)'}"
            linter_err = _run_auto_linter(write_res.path)
            if linter_err:
                res_str += f"\n\n[AUTO-REFLECTION ERROR] Linter detected issues after your edit:\n{linter_err}"
            return res_str

        elif tool == "patch_file":
            path = call.get("path") or call.get("file") or ""
            if not path:
                return "[TOOL ERROR] You must provide a <path> tag specifying the file location."

            if mode == "plan":
                import os

                if os.path.abspath(path) != plan_file:
                    return f"[TOOL ERROR] In PLAN mode, you may only modify the designated plan file: {plan_file}"

            old = call.get("old") or ""
            new = call.get("new") or ""
            patch_res = patch_file(path, old, new)
            if not patch_res.ok:
                return f"[TOOL ERROR] {patch_res.message}"
            size_info = (
                f"  {len(patch_res.content.encode('utf-8', errors='replace')) / 1024:.1f} KB"
                if patch_res.content
                else ""
            )
            res_str = f"[patched: {patch_res.path}{size_info}]\n{patch_res.diff[:1200]}"
            linter_err = _run_auto_linter(patch_res.path)
            if linter_err:
                res_str += f"\n\n[AUTO-REFLECTION ERROR] Linter detected issues after your edit:\n{linter_err}"
            return res_str

        elif tool == "multi_patch_file":
            path = call.get("path") or call.get("file") or ""
            if not path:
                return "[TOOL ERROR] You must provide a <path> tag specifying the file location."

            from pathlib import Path

            if path:
                path = str(Path(path).expanduser().resolve())

            if mode == "plan":
                import os

                if os.path.abspath(path) != plan_file:
                    return f"[TOOL ERROR] In PLAN mode, you may only modify the designated plan file: {plan_file}"

            patches = call.get("patches") or []
            if not path:
                return "[TOOL ERROR] <path> is required for multi_patch_file."
            if not patches:
                return "[TOOL ERROR] At least one <patch> block containing <old> and <new> is required."

            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                return f"[TOOL ERROR] Failed to read file: {str(e)}"

            import difflib

            old_content = content
            for i, p in enumerate(patches):
                old_text = p["old"]
                new_text = p["new"]
                if old_text not in content:
                    return f"[TOOL ERROR] Patch #{i + 1} failed: Target content not found in the file."

                occurrences = content.count(old_text)
                if occurrences > 1:
                    return f"[TOOL ERROR] Patch #{i + 1} failed: Target content is not unique (found {occurrences} occurrences)."

                content = content.replace(old_text, new_text)

            if path.endswith(".py"):
                import ast

                try:
                    ast.parse(content)
                except SyntaxError as e:
                    return f"[TOOL ERROR] SyntaxError after multi-patch: {e.msg} at line {e.lineno}"

            try:
                import shutil
                import os

                if os.path.exists(path):
                    shutil.copy2(path, path + ".dct.bak")

                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                diff_lines = list(
                    difflib.unified_diff(
                        old_content.splitlines(keepends=True),
                        content.splitlines(keepends=True),
                        fromfile="a/" + path,
                        tofile="b/" + path,
                        n=3,
                    )
                )
                diff_str = "".join(diff_lines)
                size_info = f"  {len(content.encode('utf-8', errors='replace')) / 1024:.1f} KB"
                res_str = (
                    f"[multi-patched: {path}{size_info}]\n{diff_str[:1200]}"
                )
                linter_err = _run_auto_linter(path)
                if linter_err:
                    res_str += f"\n\n[AUTO-REFLECTION ERROR] Linter detected issues after your edit:\n{linter_err}"
                return res_str
            except Exception as e:
                return f"[TOOL ERROR] Failed to write file: {str(e)}"

        elif tool == "grep":
            pattern = call.get("pattern")
            if not pattern:
                return "[TOOL ERROR] <pattern> is required for grep tool."

            path = call.get("path") or "."
            glob_pattern = call.get("glob")
            output_mode = call.get("output_mode") or "files_with_matches"

            context_str = call.get("context")
            context = (
                int(context_str)
                if context_str and context_str.isdigit()
                else None
            )

            head_limit_str = call.get("head_limit")
            head_limit = (
                int(head_limit_str)
                if head_limit_str and head_limit_str.isdigit()
                else 250
            )

            r = run_grep(
                pattern, path, glob_pattern, output_mode, context, head_limit
            )
            if not r.ok:
                return f"[TOOL ERROR] {r.message}"
            return f"[grep: {pattern!r} in {r.path}]\n{r.content}"

        elif tool == "glob":
            pattern = call.get("pattern")
            path = call.get("path") or "."
            if not pattern:
                return "[TOOL ERROR] <pattern> is required for glob tool."
            r = run_glob(pattern, path)
            if not r.ok:
                return f"[TOOL ERROR] {r.message}"
            return r.content
        elif tool == "list_dir":
            path = call.get("path") or "."
            r = list_dir(path)
            if not r.ok:
                return f"[TOOL ERROR] {r.message}"
            return f"[ls: {r.path}]\n{r.content}"

        elif tool == "tree":
            path = call.get("path") or "."
            r = tree(path)
            if not r.ok:
                return f"[TOOL ERROR] {r.message}"
            return f"[tree: {r.path}]\n{r.content}"

        elif tool == "fetch_url":
            url = call.get("url") or ""
            r_web = fetch_url(url)
            if not r_web.ok:
                return f"[TOOL ERROR] {r_web.message}"
            return f"[fetched: {r_web.url}  title={r_web.title!r}]\n{r_web.content[:6000]}"

        elif tool == "web_extract":
            url = _extract_tag(call["raw_text"], "url")
            selector = _extract_tag(call["raw_text"], "selector")
            if not url:
                return "[TOOL ERROR] <url> is required."

            r_ext = fetch_and_extract(url, selector)
            if not r_ext.ok:
                return f"[TOOL ERROR] {r_ext.message}"
            return r_ext.content
        elif tool == "web_search":
            query = call.get("query") or ""
            results = search_ddg(query)
            if not results:
                return "[web_search] no results"
            lines = [f"[web_search: {query!r}]"]
            for i, item in enumerate(results, 1):
                lines.append(
                    f"{i}. {item['title']}\n   {item['url']}\n   {item['snippet']}"
                )
            return "\n".join(lines)

        elif tool == "get_cwd":
            import os

            return f"[cwd]\n{os.getcwd()}"

        elif tool == "ask_user":
            question = (
                _extract_tag(call["raw_text"], "question")
                or call.get("question")
                or call.get("code")
                or ""
            )
            choices_raw = _extract_tag(
                call["raw_text"], "choices"
            ) or call.get("choices", "")

            from dct.core.theme import con, C

            con.print(
                f"\n  [{C['purple']}]? Agent Question:[/{C['purple']}] [{C['fg']}]{question}[/{C['fg']}]"
            )

            choices = []
            if isinstance(choices_raw, list):
                choices = choices_raw
            elif isinstance(choices_raw, str) and choices_raw.strip():
                choices = [
                    c.strip() for c in choices_raw.split(",") if c.strip()
                ]

            if choices:
                for idx, c in enumerate(choices, 1):
                    con.print(f"    [{C['accent']}]{idx})[/{C['accent']}] {c}")
                con.print(
                    f"    [{C['dim']}](Select 1-{len(choices)} or type your own answer)[/{C['dim']}]"
                )

            from prompt_toolkit import PromptSession

            prompt_sess = PromptSession()

            try:
                answer = prompt_sess.prompt("  › ")
            except (KeyboardInterrupt, EOFError):
                answer = "User cancelled."

            # If user typed a number matching a choice, expand it
            if choices and answer.strip().isdigit():
                idx = int(answer.strip())
                if 1 <= idx <= len(choices):
                    answer = choices[idx - 1]

            return f"[User responded]\n{answer}"

        elif tool == "notebook_edit":
            path = _extract_tag(call["raw_text"], "path") or ""
            index = _extract_tag(call["raw_text"], "index")
            edit_mode = _extract_tag(call["raw_text"], "mode") or "replace"
            source = _extract_tag(call["raw_text"], "source") or ""

            if not path or not index:
                return "[TOOL ERROR] <path> and <index> are required."
            try:
                idx = int(index)
            except ValueError:
                return "[TOOL ERROR] <index> must be an integer."

            r_nb = edit_notebook_cell(path, idx, source, edit_mode)
            if not r_nb.ok:
                return f"[TOOL ERROR] {r_nb.message}"
            return "[SUCCESS] Notebook updated."
        elif tool == "update_plan":
            plan = (
                call.get("plan")
                or _extract_tag(call.get("raw_text", ""), "plan")
                or ""
            )
            explanation = (
                call.get("explanation")
                or _extract_tag(call.get("raw_text", ""), "explanation")
                or ""
            )
            if not plan:
                return "[TOOL ERROR] <plan> is required."
            import os

            plan_file = os.path.join(
                os.path.expanduser("~/.config/dct"), "current_plan.md"
            )
            with open(plan_file, "w", encoding="utf-8") as f:
                f.write(plan)
            return f"[SUCCESS] Plan updated. Explanation: {explanation}"
        elif tool == "DONE":
            return "__DONE__"

        else:
            return f"[TOOL ERROR] Unknown tool: {tool!r}"

    def _summarize_dropped(self, dropped: list[dict]) -> str:
        from dct.core.client import chat_once

        text_parts = []
        for m in dropped:
            text_parts.append(f"{m.get('role', 'unknown').upper()}:\n{m.get('content', '')}\n\n")
        text = "".join(text_parts)

        if len(text) > 60000:
            text = text[-60000:]

        prompt = (
            "Summarize the following interaction history concisely. "
            "Focus on high-level actions taken, important file paths, "
            "and current state. Omit verbose tool outputs. This summary will serve as "
            "memory for an agent continuing the task.\n\n"
            f"{text}"
        )
        try:
            return chat_once(
                self.server, self.model, [{"role": "user", "content": prompt}]
            )
        except Exception as e:
            return f"(Summary failed: {e})"

    def _get_native_tools(self) -> list[dict] | None:
        from dct.core.config import Config

        if not Config().get("use_native_tools", True):
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": "dct_tool",
                    "description": "Execute a DCT Agent tool. Check the AVAILABLE TOOLS list in system prompt for valid names and parameters.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tool_name": {
                                "type": "string",
                                "description": "Name of the tool (e.g. run_shell, read_file, DONE)",
                            },
                            "kwargs": {
                                "type": "object",
                                "description": "Key-value arguments mapping directly to the XML tags described in the prompt. Do not use XML in strings.",
                            },
                        },
                        "required": ["tool_name", "kwargs"],
                    },
                },
            }
        ]

    def run(self, messages: list[dict]) -> str:
        """
        Run agentic loop. `messages` should already include system prompt + user message.
        Returns final accumulated text.
        """
        write_trace_entry(
            self.session, "agent_run_start", {"messages_count": len(messages)}
        )
        msgs = list(messages)
        final_text = ""

        for turn in range(self.max_turns):
            # ── CONTEXT PRUNING (Sliding Window) ──
            # Prevent context window exhaustion during long agentic loops
            total_chars = sum(len(m.get("content") or "") for m in msgs)
            if total_chars > 120000:  # Roughly 30k tokens
                # Collect non-system message indices oldest-first
                non_sys = [
                    i for i, m in enumerate(msgs) if m.get("role") != "system"
                ]
                dropped: list[dict] = []
                for i in sorted(non_sys):
                    if total_chars <= 80000 or len(msgs) - len(dropped) <= 3:
                        break
                    dropped.append(msgs[i])
                    total_chars -= len(msgs[i].get("content", ""))

                # Remove dropped messages (iterate in reverse to preserve indices)
                drop_set = set(id(m) for m in dropped)
                msgs = [m for m in msgs if id(m) not in drop_set]

                if dropped:
                    self.on_text(
                        "\n\n[System] Context limit reached. Summarizing older interactions...\n"
                    )
                    summary = self._summarize_dropped(dropped)
                    insert_idx = (
                        1 if msgs and msgs[0].get("role") == "system" else 0
                    )
                    msgs.insert(
                        insert_idx,
                        {
                            "role": "system",
                            "content": f"[PREVIOUS CONTEXT SUMMARY]\n{summary}",
                        },
                    )

            from dct.core.theme import (
                con,
                C,
                get_funny_thinking_msg,
                get_funny_exec_msg,
            )

            class FunctionCallsFilter:
                def __init__(self, callback):
                    self.callback = callback
                    self.buffer = ""
                    self.in_block = False
                    self.start_tag = "<function_calls>"
                    self.end_tag = "</function_calls>"

                def push(self, text: str):
                    self.buffer += text
                    while self.buffer:
                        if not self.in_block:
                            idx = self.buffer.find(self.start_tag)
                            if idx == -1:
                                for i in range(1, len(self.start_tag)):
                                    if self.buffer.endswith(self.start_tag[:i]) and self.start_tag.startswith(self.buffer[-i:]):
                                        safe_len = len(self.buffer) - i
                                        if safe_len > 0:
                                            self.callback(self.buffer[:safe_len])
                                            self.buffer = self.buffer[safe_len:]
                                        return
                                self.callback(self.buffer)
                                self.buffer = ""
                            else:
                                self.callback(self.buffer[:idx])
                                self.buffer = self.buffer[idx + len(self.start_tag):]
                                self.in_block = True
                        else:
                            idx = self.buffer.find(self.end_tag)
                            if idx == -1:
                                for i in range(1, len(self.end_tag)):
                                    if self.buffer.endswith(self.end_tag[:i]) and self.end_tag.startswith(self.buffer[-i:]):
                                        self.buffer = self.buffer[-i:]
                                        return
                                self.buffer = ""
                            else:
                                self.buffer = self.buffer[idx + len(self.end_tag):]
                                self.in_block = False

                def flush(self):
                    if self.buffer and not self.in_block:
                        self.callback(self.buffer)
                        self.buffer = ""

            ui_filter = FunctionCallsFilter(self.on_text)

            response_text_parts = []
            native_tool_calls = []
            status = con.status(
                f"[{C['dim']}]{get_funny_thinking_msg()}[/{C['dim']}]",
                spinner="dots",
            )
            status.start()
            first_chunk = True
            try:
                for chunk in self.stream_fn(
                    self.server,
                    self.model,
                    msgs,
                    tools=self._get_native_tools(),
                ):
                    if isinstance(chunk, dict) and "tool_calls" in chunk:
                        native_tool_calls = chunk["tool_calls"]
                        if "content" in chunk and chunk["content"]:
                            if first_chunk:
                                status.stop()
                                first_chunk = False
                            ui_filter.push(chunk["content"])
                            response_text_parts.append(chunk["content"])
                        continue
                    if first_chunk:
                        status.stop()
                        first_chunk = False
                    ui_filter.push(chunk)
                    response_text_parts.append(chunk)
            finally:
                status.stop()
                ui_filter.flush()

            response_text = "".join(response_text_parts)
            final_text = response_text
            assistant_msg = {"role": "assistant", "content": response_text}
            if native_tool_calls:
                assistant_msg["tool_calls"] = native_tool_calls
            msgs.append(assistant_msg)
            write_trace_entry(
                self.session,
                "model_response",
                {"content": response_text, "tool_calls": native_tool_calls},
            )

            if native_tool_calls:
                # Handle native function calling sequentially
                for tc in native_tool_calls:
                    tc_id = tc.get("id")
                    func = tc.get("function", {})
                    name = func.get("name")
                    try:
                        import json

                        args_raw = func.get("arguments", {})
                        if isinstance(args_raw, dict):
                            args = args_raw
                        elif isinstance(args_raw, str) and args_raw.strip():
                            args = json.loads(args_raw)
                        else:
                            args = {}
                    except BaseException:
                        args = {}

                    if name == "dct_tool":
                        tool_name = args.get("tool_name", "")
                        kwargs = args.get("kwargs", {})
                        call = {"tool": tool_name, "raw_text": "", **kwargs}
                    else:
                        call = {"tool": name, "raw_text": "", **args}

                    if call["tool"] == "DONE":
                        return final_text

                    tool_name = call["tool"]
                    write_trace_entry(
                        self.session,
                        "tool_call",
                        {
                            "tool": tool_name,
                            "arguments": {
                                k: v
                                for k, v in call.items()
                                if k != "raw_text"
                            },
                        },
                    )
                    if self.on_tool:
                        self.on_tool(tool_name, str(call))

                    exec_status = con.status(
                        f"[{C['yellow']}]{get_funny_exec_msg(tool_name)}[/{C['yellow']}]",
                        spinner="bouncingBar",
                    )
                    exec_status.start()
                    try:
                        result = self._execute_tool(call)
                        if (
                            msgs
                            and msgs[0].get("role") == "system"
                            and self.session.system_prompt
                        ):
                            msgs[0]["content"] = self.session.system_prompt
                    finally:
                        exec_status.stop()

                    write_trace_entry(
                        self.session,
                        "tool_result",
                        {"tool": tool_name, "result": result},
                    )
                    if self.on_result:
                        self.on_result(tool_name, result)

                    if result == "__DONE__":
                        return final_text

                    safe_result = _sanitize_tool_result(result)
                    msgs.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": f"[TOOL RESULT: {tool_name}]\n{safe_result}",
                        }
                    )

                # Continue the multi-turn conversation with the tool responses appended
                continue

            if not _has_tool_call(response_text):
                break

            call = _parse_tool_call(response_text)
            if not call:
                break

            if call["tool"] == "DONE":
                break

            tool_name = call["tool"]
            write_trace_entry(
                self.session,
                "tool_call",
                {
                    "tool": tool_name,
                    "arguments": {
                        k: v for k, v in call.items() if k != "raw_text"
                    },
                },
            )
            if self.on_tool:
                self.on_tool(tool_name, str(call))

            exec_status = con.status(
                f"[{C['yellow']}]{get_funny_exec_msg(tool_name)}[/{C['yellow']}]",
                spinner="bouncingBar",
            )
            exec_status.start()
            try:
                result = self._execute_tool(call)
                if call.get("is_fuzzy"):
                    result = (
                        "[WARNING] Your tool call syntax was malformed or missing XML tags (e.g., using [TOOL] or missing </tool>). The system salvaged it fuzzily, but you MUST use proper <tool>name</tool> tags next time.\n\n"
                        + result
                    )

                # Sync system prompt in case a tool (like skill_load) mutated it mid-loop
                if (
                    msgs
                    and msgs[0].get("role") == "system"
                    and self.session.system_prompt
                ):
                    msgs[0]["content"] = self.session.system_prompt
            finally:
                exec_status.stop()

            write_trace_entry(
                self.session,
                "tool_result",
                {"tool": tool_name, "result": result},
            )
            if self.on_result:
                self.on_result(tool_name, result)

            if result == "__DONE__":
                break

            # Sanitize tool result to guard against prompt injection:
            # if the result contains XML-like <tool> tags, they could be
            # parsed as real tool calls by the regex-based extractor.
            safe_result = _sanitize_tool_result(result)
            msgs.append(
                {
                    "role": "user",
                    "content": f"[TOOL RESULT: {tool_name}]\n{safe_result}",
                }
            )

        return final_text
