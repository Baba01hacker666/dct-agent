from dct.agent.codeagent import CodeAgent
from dct.agent.parser import parse_tool_call
from dct.agent.session import Session
from dct.core.registry import Server
from dct.tools.tasks import get_tracker


def test_task_management_tools():
    tracker = get_tracker()
    tracker.tasks.clear()
    tracker._next_id = 1

    server = Server("test", "http://localhost", "ollama")
    session = Session(mode="execute")
    agent = CodeAgent(
        server=server,
        model="test-model",
        session=session,
        stream_fn=lambda s, m, msg, t=None: iter([]),
        on_text=lambda _: None,
        on_tool=lambda *_: None,
        on_result=lambda *_: None,
    )

    # 1. task_create
    create_call = {
        "tool": "task_create",
        "subject": "Implement authentication",
        "description": "Add JWT token validation",
        "active_form": "tasks",
        "raw_text": "<tool>task_create</tool><subject>Implement authentication</subject><description>Add JWT token validation</description>",
    }
    res = agent._execute_tool(create_call)
    assert "[SUCCESS] Created Task #1" in res
    assert len(tracker.tasks) == 1
    assert tracker.tasks[0].subject == "Implement authentication"
    assert tracker.tasks[0].status == "pending"

    # 2. task_list
    list_call = {"tool": "task_list", "raw_text": "<tool>task_list</tool>"}
    list_res = agent._execute_tool(list_call)
    assert "1. [ ] Implement authentication (pending)" in list_res

    # 3. task_update
    update_call = {
        "tool": "task_update",
        "task_id": "1",
        "status": "in_progress",
        "raw_text": "<tool>task_update</tool><task_id>1</task_id><status>in_progress</status>",
    }
    update_res = agent._execute_tool(update_call)
    assert "[SUCCESS] Updated Task #1 (Status: in_progress)" in update_res
    assert tracker.tasks[0].status == "in_progress"

    # 4. task_get
    get_call = {
        "tool": "task_get",
        "task_id": "1",
        "raw_text": "<tool>task_get</tool><task_id>1</task_id>",
    }
    get_res = agent._execute_tool(get_call)
    assert "[TASK #1]" in get_res
    assert "Implement authentication" in get_res
    assert "in_progress" in get_res


def test_sleep_and_tool_search():
    server = Server("test", "http://localhost", "ollama")
    session = Session(mode="execute")
    agent = CodeAgent(
        server=server,
        model="test-model",
        session=session,
        stream_fn=lambda s, m, msg, t=None: iter([]),
        on_text=lambda _: None,
        on_tool=lambda *_: None,
        on_result=lambda *_: None,
    )

    # 1. sleep
    sleep_call = {
        "tool": "sleep",
        "seconds": "0.01",
        "raw_text": "<tool>sleep</tool><seconds>0.01</seconds>",
    }
    sleep_res = agent._execute_tool(sleep_call)
    assert "[SUCCESS] Slept for 0.0 second(s)." in sleep_res

    # 2. tool_search
    search_call = {
        "tool": "tool_search",
        "query": "grep",
        "raw_text": "<tool>tool_search</tool><query>grep</query>",
    }
    search_res = agent._execute_tool(search_call)
    assert "[TOOL SEARCH RESULTS" in search_res
    assert "grep" in search_res
    assert "ripgrep" in search_res


def test_parser_new_keys():
    xml = """
    <tool>task_update</tool>
    <task_id>42</task_id>
    <status>completed</status>
    <subject>Fix bug</subject>
    <seconds>5</seconds>
    """
    parsed = parse_tool_call(xml)
    assert parsed is not None
    assert parsed["tool"] == "task_update"
    assert parsed["task_id"] == "42"
    assert parsed["status"] == "completed"
    assert parsed["subject"] == "Fix bug"
    assert parsed["seconds"] == "5"
