import re
import time
from unittest.mock import MagicMock, patch
from dct.agent.codeagent import CodeAgent, BACKGROUND_TASKS, BACKGROUND_TASKS_LOCK


def test_background_task_lifecycle():
    # Setup agent session mock
    session_mock = MagicMock()
    session_mock.mode = "chat"

    agent = CodeAgent(server=None, model="test-model", session=session_mock, stream_fn=lambda *a, **k: iter([]))

    # Make readline block slightly on the first call so the task stays running for the check
    mock_proc = MagicMock()

    def side_effect():
        time.sleep(0.2)
        yield "hello\n"
        yield "world\n"
        while True:
            yield ""

    gen = side_effect()
    mock_proc.stdout.readline.side_effect = lambda: next(gen)
    mock_proc.wait.return_value = 0
    mock_proc.stdin = MagicMock()

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen, \
         patch("dct.tools.executor.prepare_background_command", return_value=(["python"], None)):

        # 1. Run Python command in background
        call = {
            "tool": "run_python",
            "code": "print('hello')\nprint('world')",
            "background": "true"
        }
        res = agent._execute_tool(call)

        assert "Task started in background" in res

        # Extract task_id (should be task_X)
        m = re.search(r"Task ID: (task_\d+)", res)
        assert m is not None
        task_id = m.group(1)

        # Verify task is created in BACKGROUND_TASKS and is running
        with BACKGROUND_TASKS_LOCK:
            assert task_id in BACKGROUND_TASKS
            task = BACKGROUND_TASKS[task_id]
            assert task["status"] == "running"

        # Give the background thread time to read and run to completion
        time.sleep(0.5)

        # 2. Check bg_status
        status_call = {
            "tool": "bg_status",
            "id": task_id
        }
        status_res = agent._execute_tool(status_call)
        assert "Background Task Details" in status_res
        assert "hello\nworld\n" in status_res
        assert "completed" in status_res


def test_background_task_kill():
    session_mock = MagicMock()
    session_mock.mode = "chat"
    agent = CodeAgent(server=None, model="test-model", session=session_mock, stream_fn=lambda *a, **k: iter([]))

    mock_proc = MagicMock()
    mock_proc.stdout.readline.side_effect = lambda: time.sleep(10)
    mock_proc.wait.return_value = -15
    mock_proc.stdin = MagicMock()

    with patch("subprocess.Popen", return_value=mock_proc), \
         patch("dct.tools.executor.prepare_background_command", return_value=(["python"], None)):

        call = {
            "tool": "run_python",
            "code": "import time; time.sleep(10)",
            "background": "true"
        }
        res = agent._execute_tool(call)
        m = re.search(r"Task ID: (task_\d+)", res)
        task_id = m.group(1)

        # Kill the task
        kill_call = {
            "tool": "bg_kill",
            "id": task_id
        }
        kill_res = agent._execute_tool(kill_call)
        assert "Terminated background task" in kill_res

        # Verify it is killed
        with BACKGROUND_TASKS_LOCK:
            assert BACKGROUND_TASKS[task_id]["status"] == "killed"


def test_background_task_send_input():
    session_mock = MagicMock()
    session_mock.mode = "chat"
    agent = CodeAgent(server=None, model="test-model", session=session_mock, stream_fn=lambda *a, **k: iter([]))

    mock_proc = MagicMock()

    # Sleep on first call to keep it running
    def side_effect():
        time.sleep(0.5)
        while True:
            yield ""

    gen = side_effect()
    mock_proc.stdout.readline.side_effect = lambda: next(gen)
    mock_proc.wait.return_value = 0
    mock_proc.stdin = MagicMock()

    with patch("subprocess.Popen", return_value=mock_proc), \
         patch("dct.tools.executor.prepare_background_command", return_value=(["python"], None)):

        call = {
            "tool": "run_python",
            "code": "import sys; print(sys.stdin.read())",
            "background": "true"
        }
        res = agent._execute_tool(call)
        m = re.search(r"Task ID: (task_\d+)", res)
        task_id = m.group(1)

        # Send input
        input_call = {
            "tool": "bg_send_input",
            "id": task_id,
            "input": "test input data"
        }
        input_res = agent._execute_tool(input_call)
        assert "Sent input to background task" in input_res
        mock_proc.stdin.write.assert_called_with("test input data\n")
