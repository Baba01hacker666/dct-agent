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
from dct.tools.web import fetch_url, search_ddg
from dct.tools.tasks import get_tracker
from dct.skills.notebook import edit_notebook_cell
from dct.skills.web import fetch_and_extract

if TYPE_CHECKING:
    from dct.core.registry import Server
    from dct.agent.session import Session

MAX_AGENT_TURNS = 12  # safety cap on autonomous iterations


def get_system_prompt(session) -> str:
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
  <tool>run_python</tool><code>...</code>        — execute Python 3 code
  <tool>run_bash</tool><code>...</code>          — execute bash script
  <tool>run_shell</tool><code>...</code>         — run a shell command
  <tool>read_file</tool><path>...</path>         — read a file
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

    return prompt


def _extract_tag(text: str, tag: str) -> Optional[str]:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else None


def _has_tool_call(text: str) -> bool:
    return bool(re.search(r"<tool>(.+?)</tool>", text, re.DOTALL | re.IGNORECASE))


def _parse_tool_call(text: str) -> Optional[dict]:
    """Extract the first tool call from model output."""
    tool = _extract_tag(text, "tool")
    if not tool:
        return None
    return {
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

        if tool in ("run_python", "run_bash", "run_shell", "python", "bash", "shell"):
            if mode == "plan":
                return "[TOOL ERROR] Execution is blocked in PLAN mode. You must use <tool>exit_plan_mode</tool> first."

            lang = (
                "python" if "python" in tool else "bash" if "bash" in tool else "shell"
            )
            code = call.get("code") or ""
            if not code:
                return "[TOOL ERROR] No code provided."
            result: ExecResult = dispatch(lang, code, timeout=30)
            out = result.summary()
            status = "✓" if result.ok else "✗"
            return f"[{status} {lang} exit={result.returncode} {result.duration_ms}ms]\n{out}"

        elif tool == "read_file":
            path = call.get("path") or ""
            r = read_file(path)
            if not r.ok:
                return f"[TOOL ERROR] {r.message}"
            lines = r.content.splitlines()
            numbered = "\n".join(
                f"{i + 1:4d}  {line_text}" for i, line_text in enumerate(lines)
            )
            return f"[file: {r.path}  {len(lines)} lines]\n{numbered}"

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
            return f"[written: {r.path}]\n{r.diff[:1200] if r.diff else '(new file)'}"

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
            return f"[patched: {r.path}]\n{r.diff[:1200]}"

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
            pattern = _extract_tag(str(call), "pattern")
            path = _extract_tag(str(call), "path") or "."
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
            r = fetch_url(url)
            if not r.ok:
                return f"[TOOL ERROR] {r.message}"
            return f"[fetched: {r.url}  title={r.title!r}]\n{r.content[:6000]}"

        elif tool == "web_extract":
            url = _extract_tag(str(call), "url")
            selector = _extract_tag(str(call), "selector")
            if not url:
                return "[TOOL ERROR] <url> is required."

            r = fetch_and_extract(url, selector)
            if not r.ok:
                return f"[TOOL ERROR] {r.message}"
            return r.content
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
                _extract_tag(str(call), "question")
                or call.get("question")
                or call.get("code")
                or ""
            )
            choices_str = _extract_tag(str(call), "choices")

            if choices_str:
                from prompt_toolkit.shortcuts import radiolist_dialog

                choices = [c.strip() for c in choices_str.split(",") if c.strip()]
                if choices:
                    try:
                        result = radiolist_dialog(
                            title="Agent Question",
                            text=question,
                            values=[(c, c) for c in choices],
                        ).run()
                        if result:
                            return f"[User responded]\n{result}"
                    except Exception:
                        pass

            print(f"\n  [?] Agent asks: {question}")
            if choices_str:
                print(f"  [Choices: {choices_str}]")
            answer = input("  › ")
            return f"[User responded]\n{answer}"

        elif tool == "notebook_edit":
            path = _extract_tag(str(call), "path")
            index = _extract_tag(str(call), "index")
            mode = _extract_tag(str(call), "mode") or "replace"
            source = _extract_tag(str(call), "source") or ""

            if not path or not index:
                return "[TOOL ERROR] <path> and <index> are required."
            try:
                idx = int(index)
            except ValueError:
                return "[TOOL ERROR] <index> must be an integer."

            r = edit_notebook_cell(path, idx, source, mode)
            if not r.ok:
                return f"[TOOL ERROR] {r.message}"
            return "[SUCCESS] Notebook updated."
        elif tool == "task_create":
            subject = _extract_tag(str(call), "subject")
            desc = _extract_tag(str(call), "description")
            if not subject or not desc:
                return "[TOOL ERROR] <subject> and <description> are required."
            t = get_tracker().create(subject, desc)
            return f"Task created: ID {t.id} - {t.subject}"
        elif tool == "task_update":
            tid = _extract_tag(str(call), "id")
            status = _extract_tag(str(call), "status")
            if not tid or not status:
                return "[TOOL ERROR] <id> and <status> are required."
            if status not in ["pending", "in_progress", "completed"]:
                return f"[TOOL ERROR] Invalid status: {status}"
            t = get_tracker().update(tid, status=status)
            if not t:
                return f"[TOOL ERROR] Task ID {tid} not found."
            return f"Task {t.id} updated to {t.status}."
        elif tool == "task_list":
            return get_tracker().summary()
        elif tool == "DONE":
            return "__DONE__"

        else:
            return f"[TOOL ERROR] Unknown tool: {tool!r}"

    def run(self, messages: list[dict]) -> str:
        """
        Run agentic loop. `messages` should already include system prompt + user message.
        Returns final accumulated text.
        """
        msgs = list(messages)
        final_text = ""

        for turn in range(self.max_turns):
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
