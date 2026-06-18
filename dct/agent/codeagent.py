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
import re
import threading
import time
from typing import Callable, Optional, TYPE_CHECKING

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
from dct.tools.tasks import get_tracker
from dct.skills.notebook import edit_notebook_cell
from dct.skills.web import fetch_and_extract

if TYPE_CHECKING:
    from dct.core.registry import Server
    from dct.agent.session import Session

MAX_AGENT_TURNS = 12  # safety cap on autonomous iterations

BACKGROUND_TASKS: dict[str, dict] = {}
BACKGROUND_TASKS_LOCK = threading.Lock()
next_task_id = 1

BACKGROUND_SUBAGENTS: dict[str, dict] = {}
BACKGROUND_SUBAGENTS_LOCK = threading.Lock()
next_bg_id = 1

# Cleanup: remove completed/failed entries older than this (seconds)
BG_CLEANUP_TTL = 300
# Max chars per background log
BG_LOG_MAX_CHARS = 10000


def _cleanup_background_state() -> None:
    """Remove stale completed/failed background tasks and sub-agents."""
    now = time.time()
    with BACKGROUND_TASKS_LOCK:
        stale = [
            tid
            for tid, t in BACKGROUND_TASKS.items()
            if t["status"] in ("completed", "failed")
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

    prompt = f"""You are DCT-Agent, a coding and security assistant built by Doraemon Cyber Team.
You can use tools by emitting structured XML tags.

[ENVIRONMENT]
OS: {os_info}
Current Working Directory: {cwd}
Current Time: {now}
Current Mode: {mode}

AVAILABLE TOOLS:
  <tool>run_python</tool><code>...</code><background>true|false</background>  — execute Python 3 code (background optional)
  <tool>run_bash</tool><code>...</code><background>true|false</background>    — execute bash script (background optional)
  <tool>run_shell</tool><code>...</code><background>true|false</background>   — run a shell command (background optional)
  <tool>read_file</tool><path>...</path><start_line>...</start_line><end_line>...</end_line><tail>...</tail> — read a file (lines are optional)
  <tool>read_image</tool><path>...</path>        — read an image file, returns base64 data URL for vision models
  <tool>write_file</tool><path>...</path><code>...</code>  — write/create a file
  <tool>patch_file</tool><path>...</path><old>...</old><new>...</new>  — find+replace in file
  <tool>list_dir</tool><path>...</path>          — list directory
  <tool>tree</tool><path>...</path>              — directory tree
  <tool>glob</tool><pattern>...</pattern><path>...</path>      — fast file discovery using ripgrep
  <tool>task_create</tool><subject>...</subject><description>...</description> — Create tracking tasks
  <tool>task_update</tool><id>...</id><status>...</status>       — Update task (pending|in_progress|completed)
  <tool>task_list</tool>                                         — List all tasks
  <tool>notebook_edit</tool><path>...</path><index>...</index><mode>replace|insert|delete</mode><source>...</source> — Edit jupyter notebooks
  <tool>web_extract</tool><url>...</url><selector>...</selector> — Fetch webpage and optionally extract via CSS selector
  <tool>grep</tool><pattern>...</pattern><path>...</path><glob>...</glob><output_mode>content|files_with_matches</output_mode><context>2</context>  — fast regex search using ripgrep
  <tool>fetch_url</tool><url>...</url>           — fetch a URL
  <tool>ask_user</tool><question>...</question><choices>a,b,c</choices>  — Ask the user a question (choices optional)
  <tool>get_cwd</tool>                           — Get current working directory
  <tool>run_subagent</tool><instruction>...</instruction><model>...</model><system_prompt>...</system_prompt><background>true|false</background> — spawn a sub-agent to perform a sub-task (background, model, and system_prompt are optional)
  <tool>bg_status</tool><id>...</id>             — check status and logs of background tasks/sub-agents (id optional)
  <tool>enter_plan_mode</tool>                   — Enter PLAN mode to explore and write a plan before coding
  <tool>exit_plan_mode</tool>                    — Exit PLAN mode once a plan is approved and you are ready to code

TOOL CALL FORMAT:
- Always output exactly one tool call at a time when calling tools.
- Use this shape:
  <tool>run_shell</tool>
  <code>pwd</code>
- For file reads:
  <tool>read_file</tool>
  <path>README.md</path>
  <start_line>1</start_line>
  <end_line>50</end_line>
- For web:
  <tool>web_extract</tool>
  <url>https://example.com</url>
  <selector>main</selector>
- Finish only when truly done:
  <tool>DONE</tool>

WORKFLOW:
1) Understand the user goal and constraints.
2) If information is missing, use read/search tools first.
3) Make small, verifiable steps and inspect results.
4) Prefer minimal safe edits; do not overwrite unrelated content.
5) Summarize what changed and what remains, then emit <tool>DONE</tool>.

IMPORTANT BEHAVIOR:
- Never invent tool output. If unsure, run a tool.
- If a tool fails, explain briefly and try an alternative.
- Keep responses compact between tool calls.
- When modifying files, prefer patch_file for targeted edits.
"""

    if session.mode == "plan":
        prompt += f"""
[PLAN MODE ACTIVE]
You are currently in PLAN mode.
- You CANNOT execute code (run_python, run_bash, run_shell are BLOCKED).
- You CANNOT modify files, EXCEPT for the designated plan file: {plan_file}
- Your goal is to use read_file, grep, list_dir, and tree to explore the codebase, understand patterns, and write a concrete implementation strategy into the plan file using write_file.
- Once the user approves the plan, use <tool>exit_plan_mode</tool> to return to execution mode.
"""

    if user_system_prompt.strip():
        prompt += f"""
[USER SYSTEM PREFERENCES]
Apply the following additional instructions while still obeying all tool and safety rules above:
{user_system_prompt.strip()}
"""

    return prompt


def _extract_tag(text: str, tag: str) -> Optional[str]:
    m = re.search(rf"<{tag}(?:\s+[^>]*)?>(.*?)</{tag}>", text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else None


def _has_tool_call(text: str) -> bool:
    return bool(re.search(r"<tool(?:\s+[^>]*)?>(.+?)</tool>", text, re.DOTALL | re.IGNORECASE))


def _parse_tool_call(text: str) -> Optional[dict]:
    """Extract the first tool call from model output."""
    tool = _extract_tag(text, "tool")
    if not tool:
        return None
    return {
        "raw_text": text,
        "tool": tool.strip(),
        "code": _extract_tag(text, "code"),
        "path": _extract_tag(text, "path"),
        "url": _extract_tag(text, "url"),
        "query": _extract_tag(text, "query"),
        "old": _extract_tag(text, "old"),
        "new": _extract_tag(text, "new"),
        "question": _extract_tag(text, "question"),
        "pattern": _extract_tag(text, "pattern"),
        "glob": _extract_tag(text, "glob"),
        "output_mode": _extract_tag(text, "output_mode"),
        "context": _extract_tag(text, "context"),
        "head_limit": _extract_tag(text, "head_limit"),
        "start_line": _extract_tag(text, "start_line"),
        "end_line": _extract_tag(text, "end_line"),
        "tail": _extract_tag(text, "tail"),
        "instruction": _extract_tag(text, "instruction"),
        "system_prompt": _extract_tag(text, "system_prompt"),
        "model": _extract_tag(text, "model"),
        "background": _extract_tag(text, "background"),
        "id": _extract_tag(text, "id"),
    }


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

        elif tool == "run_subagent":
            instruction = call.get("instruction") or call.get("prompt") or call.get("code") or ""
            if not instruction:
                return "[TOOL ERROR] <instruction> is required."

            sub_model = call.get("model") or self.model
            sub_system = call.get("system_prompt") or ""
            is_bg = (call.get("background") or "").strip().lower() == "true"

            from dct.agent.session import Session
            sub_session = Session(mode=self.session.mode)

            sub_dynamic_prompt = get_system_prompt(sub_session, user_system_prompt=sub_system)
            sub_session.set_system(sub_dynamic_prompt)
            sub_session.add("user", instruction)

            if is_bg:
                _cleanup_background_state()
                global next_bg_id
                with BACKGROUND_SUBAGENTS_LOCK:
                    bg_id = f"subagent_{next_bg_id}"
                    next_bg_id += 1
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
                    _append_log_safe(bg_sub_data, f"\n⚡ tool: {sub_tool_name}\nCall: {sub_call_str}\n")

                def bg_on_result(sub_tool_name: str, sub_result: str):
                    _append_log_safe(bg_sub_data, f"\nresult: {sub_tool_name}\n{sub_result}\n")

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
                            BACKGROUND_SUBAGENTS[b_id]["completed_at"] = time.time()
                    except Exception as e:
                        with BACKGROUND_SUBAGENTS_LOCK:
                            BACKGROUND_SUBAGENTS[b_id]["status"] = "failed"
                            BACKGROUND_SUBAGENTS[b_id]["result"] = str(e)
                            BACKGROUND_SUBAGENTS[b_id]["completed_at"] = time.time()

                sub_thread = threading.Thread(target=run_subagent_bg, args=(bg_id, sub_agent, sub_session.as_messages()), daemon=True)
                sub_thread.start()

                from dct.core.theme import con, C
                con.print(f"\n  [{C['purple']}][SUB-AGENT STARTED IN BACKGROUND][/{C['purple']}] Task ID: {bg_id} | Model: {sub_model}")
                return f"[Sub-agent started in background. Task ID: {bg_id}]"

            else:
                from dct.core.theme import con, C, info, section
                con.print(f"\n  [{C['purple']}][SUB-AGENT STARTING][/{C['purple']}] Model: {sub_model} | Mode: {sub_session.mode.upper()}")
                con.print(f"  [{C['dim']}]Instruction: {instruction}[/{C['dim']}]")
                con.print(f"  [{C['dim']}]{'─' * 66}[/{C['dim']}]")

                def sub_on_text(chunk: str):
                    con.print(f"[{C['purple']}]{chunk}[/{C['purple']}]", end="")

                def sub_on_tool(sub_tool_name: str, sub_call_str: str):
                    con.print()
                    con.print(
                        f"\n  [{C['purple']}]⚡ sub-agent tool:[/{C['purple']}] [{C['fg']}]{sub_tool_name}[/{C['fg']}]"
                    )

                def sub_on_result(sub_tool_name: str, sub_result: str):
                    section(f"sub-agent result: {sub_tool_name}")
                    if len(sub_result) > 2000:
                        con.print(f"[{C['code']}]{sub_result[:2000]}[/{C['code']}]")
                        info(f"… ({len(sub_result)} chars total)")
                    else:
                        con.print(f"[{C['code']}]{sub_result}[/{C['code']}]")
                    con.print()
                    con.print(f"  [{C['dim']}]continuing sub-agent…[/{C['dim']}]")
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
                    con.print(f"\n  [{C['purple']}][SUB-AGENT COMPLETED][/{C['purple']}]")
                    con.print(f"  [{C['dim']}]{'─' * 66}[/{C['dim']}]")
                    return f"[Sub-agent completed task successfully]\nResponse: {sub_response}"
                except Exception as e:
                    con.print(f"\n  [{C['err']}][SUB-AGENT FAILED]: {str(e)}[/{C['err']}]")
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
                    lines.append(f"- {t_id} (Task): {task['status']} | Command: {task['command'][:60]}")
            with BACKGROUND_SUBAGENTS_LOCK:
                for s_id, sub in BACKGROUND_SUBAGENTS.items():
                    lines.append(f"- {s_id} (Sub-agent): {sub['status']} | Instruction: {sub['instruction'][:60]}")

            if len(lines) == 1:
                return "No active or completed background tasks or sub-agents."
            return "\n".join(lines)

        if tool in ("run_python", "run_bash", "run_shell", "python", "bash", "shell"):
            if mode == "plan":
                return "[TOOL ERROR] Execution is blocked in PLAN mode. You must use <tool>exit_plan_mode</tool> first."

            lang = (
                "python" if "python" in tool else "bash" if "bash" in tool else "shell"
            )
            code = call.get("code") or ""
            if not code:
                return "[TOOL ERROR] No code provided."

            is_bg = (call.get("background") or "").strip().lower() == "true"
            if is_bg:
                _cleanup_background_state()
                global next_task_id
                with BACKGROUND_TASKS_LOCK:
                    task_id = f"task_{next_task_id}"
                    next_task_id += 1
                    BACKGROUND_TASKS[task_id] = {
                        "command": code,
                        "lang": lang,
                        "status": "running",
                        "result": "",
                        "log": [],
                        "completed_at": 0,
                    }

                def run_cmd_bg(t_id, lang_name, cmd_code):
                    try:
                        res: ExecResult = dispatch(lang_name, cmd_code, timeout=300)
                        out = res.summary()
                        status = "completed" if res.ok else "failed"
                        with BACKGROUND_TASKS_LOCK:
                            BACKGROUND_TASKS[t_id]["status"] = status
                            BACKGROUND_TASKS[t_id]["result"] = out
                            BACKGROUND_TASKS[t_id]["completed_at"] = time.time()
                            BACKGROUND_TASKS[t_id]["log"].append(f"[Exit code: {res.returncode}]")
                    except Exception as e:
                        with BACKGROUND_TASKS_LOCK:
                            BACKGROUND_TASKS[t_id]["status"] = "failed"
                            BACKGROUND_TASKS[t_id]["result"] = str(e)
                            BACKGROUND_TASKS[t_id]["completed_at"] = time.time()

                cmd_thread = threading.Thread(target=run_cmd_bg, args=(task_id, lang, code), daemon=True)
                cmd_thread.start()
                return f"[Task started in background. Task ID: {task_id}]"

            result: ExecResult = dispatch(lang, code, timeout=30)
            out = result.summary()
            status = "✓" if result.ok else "✗"
            return f"[{status} {lang} exit={result.returncode} {result.duration_ms}ms]\n{out}"

        elif tool == "read_image":
            path = call.get("path") or ""
            if not path:
                return "[TOOL ERROR] <path> is required for read_image tool."
            r = read_image(path)
            if not r.ok:
                return f"[TOOL ERROR] {r.message}"
            return f"[image: {r.path}  {r.mime_type}  data_url length: {len(r.data_url)} chars]\n{r.data_url}"

        elif tool == "read_file":
            path = call.get("path") or ""
            r = read_file(path)
            if not r.ok:
                return f"[TOOL ERROR] {r.message}"
            lines = r.content.splitlines()
            total_lines = len(lines)

            start_str = call.get("start_line")
            end_str = call.get("end_line")
            tail_str = call.get("tail")

            try:
                if tail_str:
                    tail_idx = int(tail_str)
                    start_idx = max(0, total_lines - tail_idx)
                    lines_to_show = lines[start_idx:]
                else:
                    start_idx = max(0, int(start_str) - 1) if start_str else 0
                    end_idx = min(total_lines, int(end_str)) if end_str else total_lines
                    lines_to_show = lines[start_idx:end_idx]
            except ValueError:
                return "[TOOL ERROR] start_line, end_line, and tail must be integers."

            line_limit = 2000
            truncated = False
            if len(lines_to_show) > line_limit:
                lines_to_show = lines_to_show[:line_limit]
                truncated = True

            numbered = "\n".join(
                f"{i + start_idx + 1:4d}  {line_text}" for i, line_text in enumerate(lines_to_show)
            )
            if truncated:
                numbered += "\n...[TRUNCATED]..."
            return f"[file: {r.path}  showing lines {start_idx + 1}-{start_idx + len(lines_to_show)} of {total_lines}]\n{numbered}"

        elif tool == "write_file":
            path = call.get("path") or ""

            if mode == "plan":
                import os

                if os.path.abspath(path) != plan_file:
                    return f"[TOOL ERROR] In PLAN mode, you may only modify the designated plan file: {plan_file}"

            content = call.get("code") or ""
            r = write_file(path, content)
            if not r.ok:
                return f"[TOOL ERROR] {r.message}"
            size_info = f"  {len(content.encode('utf-8', errors='replace')) / 1024:.1f} KB"
            return f"[written: {r.path}{size_info}]\n{r.diff[:1200] if r.diff else '(new file)'}"

        elif tool == "patch_file":
            path = call.get("path") or ""

            if mode == "plan":
                import os

                if os.path.abspath(path) != plan_file:
                    return f"[TOOL ERROR] In PLAN mode, you may only modify the designated plan file: {plan_file}"

            old = call.get("old") or ""
            new = call.get("new") or ""
            r = patch_file(path, old, new)
            if not r.ok:
                return f"[TOOL ERROR] {r.message}"
            size_info = f"  {len(r.content.encode('utf-8', errors='replace')) / 1024:.1f} KB" if r.content else ""
            return f"[patched: {r.path}{size_info}]\n{r.diff[:1200]}"

        elif tool == "grep":
            pattern = call.get("pattern")
            if not pattern:
                return "[TOOL ERROR] <pattern> is required for grep tool."

            path = call.get("path") or "."
            glob_pattern = call.get("glob")
            output_mode = call.get("output_mode") or "files_with_matches"

            context_str = call.get("context")
            context = (
                int(context_str) if context_str and context_str.isdigit() else None
            )

            head_limit_str = call.get("head_limit")
            head_limit = (
                int(head_limit_str)
                if head_limit_str and head_limit_str.isdigit()
                else 250
            )

            r = run_grep(pattern, path, glob_pattern, output_mode, context, head_limit)
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
            for i, res in enumerate(results, 1):
                lines.append(
                    f"{i}. {res['title']}\n   {res['url']}\n   {res['snippet']}"
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
            choices_str = _extract_tag(call["raw_text"], "choices")

            if choices_str:
                from prompt_toolkit.shortcuts import radiolist_dialog

                choices = [c.strip() for c in choices_str.split(",") if c.strip()]
                if choices:
                    try:
                        dialog_res = radiolist_dialog(
                            title="Agent Question",
                            text=question,
                            values=[(c, c) for c in choices],
                        ).run()
                        if dialog_res:
                            return f"[User responded]\n{dialog_res}"
                    except Exception:
                        pass

            print(f"\n  [?] Agent asks: {question}")
            if choices_str:
                print(f"  [Choices: {choices_str}]")
            answer = input("  › ")
            return f"[User responded]\n{answer}"

        elif tool == "notebook_edit":
            path = _extract_tag(call["raw_text"], "path")
            index = _extract_tag(call["raw_text"], "index")
            mode = _extract_tag(call["raw_text"], "mode") or "replace"
            source = _extract_tag(call["raw_text"], "source") or ""

            if not path or not index:
                return "[TOOL ERROR] <path> and <index> are required."
            try:
                idx = int(index)
            except ValueError:
                return "[TOOL ERROR] <index> must be an integer."

            r_nb = edit_notebook_cell(path, idx, source, mode)
            if not r_nb.ok:
                return f"[TOOL ERROR] {r_nb.message}"
            return "[SUCCESS] Notebook updated."
        elif tool == "task_create":
            subject = _extract_tag(call["raw_text"], "subject")
            desc = _extract_tag(call["raw_text"], "description")
            if not subject or not desc:
                return "[TOOL ERROR] <subject> and <description> are required."
            new_task = get_tracker().create(subject, desc)
            return f"Task created: ID {new_task.id} - {new_task.subject}"
        elif tool == "task_update":
            tid = _extract_tag(call["raw_text"], "id")
            new_status: str | None = _extract_tag(call["raw_text"], "status")
            if not tid or not new_status:
                return "[TOOL ERROR] <id> and <status> are required."
            if new_status not in ["pending", "in_progress", "completed"]:
                return f"[TOOL ERROR] Invalid status: {new_status}"
            t_updated = get_tracker().update(tid, status=new_status)
            if not t_updated:
                return f"[TOOL ERROR] Task ID {tid} not found."
            return f"Task {t_updated.id} updated to {t_updated.status}."
        elif tool == "task_list":
            return get_tracker().summary()
        elif tool == "DONE":
            return "__DONE__"

        else:
            return f"[TOOL ERROR] Unknown tool: {tool!r}"

    def _summarize_dropped(self, dropped: list[dict]) -> str:
        from dct.core.client import chat_once

        text = ""
        for m in dropped:
            text += f"{m.get('role', 'unknown').upper()}:\n{m.get('content', '')}\n\n"

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
            return chat_once(self.server, self.model, [{"role": "user", "content": prompt}])
        except Exception as e:
            return f"(Summary failed: {e})"

    def run(self, messages: list[dict]) -> str:
        """
        Run agentic loop. `messages` should already include system prompt + user message.
        Returns final accumulated text.
        """
        msgs = list(messages)
        final_text = ""

        for turn in range(self.max_turns):
            # ── CONTEXT PRUNING (Sliding Window) ──
            # Prevent context window exhaustion during long agentic loops
            total_chars = sum(len(m.get("content", "")) for m in msgs)
            if total_chars > 120000:  # Roughly 30k tokens
                dropped = []
                while total_chars > 80000 and len(msgs) > 3:
                    for i, m in enumerate(msgs):
                        if m.get("role") != "system":
                            removed = msgs.pop(i)
                            dropped.append(removed)
                            total_chars -= len(removed.get("content", ""))
                            break

                if dropped:
                    self.on_text("\n\n[System] Context limit reached. Summarizing older interactions...\n")
                    summary = self._summarize_dropped(dropped)
                    insert_idx = 1 if msgs and msgs[0].get("role") == "system" else 0
                    msgs.insert(insert_idx, {"role": "system", "content": f"[PREVIOUS CONTEXT SUMMARY]\n{summary}"})

            response_text = ""
            for chunk in self.stream_fn(self.server, self.model, msgs):
                self.on_text(chunk)
                response_text += chunk

            final_text = response_text
            msgs.append({"role": "assistant", "content": response_text})

            if not _has_tool_call(response_text):
                break

            call = _parse_tool_call(response_text)
            if not call:
                break

            if call["tool"] == "DONE":
                break

            tool_name = call["tool"]
            if self.on_tool:
                self.on_tool(tool_name, str(call))

            result = self._execute_tool(call)

            if self.on_result:
                self.on_result(tool_name, result)

            if result == "__DONE__":
                break

            msgs.append(
                {
                    "role": "user",
                    "content": f"[TOOL RESULT: {tool_name}]\n{result}",
                }
            )

        return final_text
