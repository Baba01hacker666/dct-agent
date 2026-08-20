"""
dct.tools.subagent
Autonomous Subagent Spawning and Delegation Engine for DCT Agent.
"""

from __future__ import annotations

import itertools
import threading
import time
from typing import Any, Dict, List, NamedTuple, Optional

from dct.core.config import Config
from dct.core.logging import get_logger
from dct.core.registry import ServerRegistry

logger = get_logger("dct.tools.subagent")

_subagent_counter = itertools.count(1)
_ACTIVE_SUBAGENTS: Dict[str, Dict[str, Any]] = {}
_SUBAGENT_LOCK = threading.Lock()


class SubagentResult(NamedTuple):
    ok: bool
    message: str
    output: str = ""
    subagent_id: str = ""
    duration_sec: float = 0.0


def list_subagents() -> List[Dict[str, Any]]:
    """Return list of active and recent subagents."""
    with _SUBAGENT_LOCK:
        return [
            {
                "id": sid,
                "role": data.get("role", "General Subagent"),
                "task": data.get("task", ""),
                "model": data.get("model", ""),
                "status": data.get("status", "running"),
                "started_at": data.get("started_at", 0),
                "completed_at": data.get("completed_at", 0),
                "result": data.get("result", ""),
            }
            for sid, data in _ACTIVE_SUBAGENTS.items()
        ]


def get_subagent(subagent_id: str) -> Optional[Dict[str, Any]]:
    """Get details and log output of a specific subagent."""
    with _SUBAGENT_LOCK:
        return _ACTIVE_SUBAGENTS.get(subagent_id)


def spawn_subagent(
    task: str,
    role: Optional[str] = None,
    model: Optional[str] = None,
    skill: Optional[str] = None,
    system_prompt: Optional[str] = None,
    background: bool = False,
    max_turns: int = 8,
) -> SubagentResult:
    """
    Spawn an autonomous subagent with a dedicated task, persona, and execution context.
    """
    if not task or not task.strip():
        return SubagentResult(ok=False, message="Task description cannot be empty.")

    from dct.agent.codeagent import CodeAgent, get_system_prompt
    from dct.agent.session import Session
    from dct.cli.shell import SKILL_PRESETS
    from dct.core.client import chat_stream

    registry = ServerRegistry()
    conf = Config()
    pref = conf.get("default_server", "")
    server = registry.resolve(pref) if pref else registry.first_online()
    if not server and registry.servers:
        server = registry.servers[0]

    if not server:
        return SubagentResult(
            ok=False, message="No online server available to run subagent."
        )

    sub_model = (
        model
        or conf.get("default_model")
        or (server.models[0] if server.models else "default")
    )
    role_title = role or "Specialized Assistant"

    sub_session = Session(mode="execute")
    base_sys = f"You are a subagent acting as: {role_title}.\nGoal: {task}\nExecute necessary tools to accomplish the task completely and accurately."
    if skill:
        skill_info = SKILL_PRESETS.get(skill) or conf.get(
            "custom_skills", {}
        ).get(skill)
        if skill_info:
            base_sys = f"{skill_info.get('prompt', '')}\n\n{base_sys}"

    if system_prompt:
        base_sys = f"{base_sys}\n\n{system_prompt}"

    dyn_prompt = get_system_prompt(sub_session, user_system_prompt=base_sys)
    sub_session.set_system(dyn_prompt)
    sub_session.add("user", task)

    with _SUBAGENT_LOCK:
        sub_id = f"subagent_{next(_subagent_counter)}"
        _ACTIVE_SUBAGENTS[sub_id] = {
            "id": sub_id,
            "role": role_title,
            "task": task,
            "model": sub_model,
            "status": "running",
            "log": [],
            "result": "",
            "started_at": time.time(),
            "completed_at": 0,
        }

    sub_entry = _ACTIVE_SUBAGENTS[sub_id]

    def sub_on_text(chunk: str):
        with _SUBAGENT_LOCK:
            sub_entry["log"].append(chunk)

    def sub_on_tool(tool_name: str, call_data: str):
        with _SUBAGENT_LOCK:
            sub_entry["log"].append(f"\n[Tool: {tool_name}] {call_data}\n")

    def sub_on_result(tool_name: str, result_data: str):
        with _SUBAGENT_LOCK:
            sub_entry["log"].append(f"\n[Result: {tool_name}]\n{result_data}\n")

    agent = CodeAgent(
        server=server,
        model=sub_model,
        session=sub_session,
        stream_fn=chat_stream,
        on_text=sub_on_text,
        on_tool=sub_on_tool,
        on_result=sub_on_result,
        max_turns=max_turns,
    )

    t0 = time.time()

    if background:

        def _bg_run():
            try:
                res = agent.run(sub_session.as_messages())
                with _SUBAGENT_LOCK:
                    sub_entry["status"] = "completed"
                    sub_entry["result"] = res
                    sub_entry["completed_at"] = time.time()
            except Exception as e:
                with _SUBAGENT_LOCK:
                    sub_entry["status"] = "failed"
                    sub_entry["result"] = f"Subagent error: {str(e)}"
                    sub_entry["completed_at"] = time.time()

        th = threading.Thread(target=_bg_run, daemon=True)
        th.start()
        return SubagentResult(
            ok=True,
            message=f"Subagent '{role_title}' launched in background (ID: {sub_id}).",
            subagent_id=sub_id,
        )

    # Synchronous run
    try:
        res = agent.run(sub_session.as_messages())
        dur = round(time.time() - t0, 2)
        with _SUBAGENT_LOCK:
            sub_entry["status"] = "completed"
            sub_entry["result"] = res
            sub_entry["completed_at"] = time.time()
        return SubagentResult(
            ok=True,
            message=f"Subagent '{role_title}' completed successfully in {dur}s.",
            output=res,
            subagent_id=sub_id,
            duration_sec=dur,
        )
    except Exception as e:
        dur = round(time.time() - t0, 2)
        with _SUBAGENT_LOCK:
            sub_entry["status"] = "failed"
            sub_entry["result"] = str(e)
            sub_entry["completed_at"] = time.time()
        return SubagentResult(
            ok=False,
            message=f"Subagent '{role_title}' failed: {str(e)}",
            subagent_id=sub_id,
            duration_sec=dur,
        )
