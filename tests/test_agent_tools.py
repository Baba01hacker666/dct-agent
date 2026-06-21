import sys
import os

# Add the parent directory to sys.path so we can import dct
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dct.agent.codeagent import CodeAgent, _has_tool_call, _parse_tool_call
from dct.agent.session import Session
from dct.core.registry import Server

def test_xml_tool_parsing():
    print("[TEST] Testing _has_tool_call and _parse_tool_call...")
    xml_text = """
    I will now run a bash command.
    <tool>run_bash</tool>
    <code>
    ls -la
    </code>
    """
    assert _has_tool_call(xml_text), "Failed to detect tool call in XML text"
    
    parsed = _parse_tool_call(xml_text)
    assert parsed is not None, "Failed to parse tool call"
    assert parsed["tool"] == "run_bash", f"Expected 'run_bash', got {parsed['tool']}"
    assert parsed["code"].strip() == "ls -la", "Failed to extract code tag"
    print("  => XML Parsing is working perfectly!\n")

def test_agent_execution_loop():
    print("[TEST] Testing Agent Execution Loop with mock LLM stream...")
    
    # We will mock the stream_fn to simulate the LLM streaming XML tool calls
    def mock_stream_fn(server, model, msgs, tools=None):
        chunks = [
            "I have decided ",
            "to check the ",
            "files.\n",
            "<tool>run_bash",
            "</tool>\n<code>",
            "echo 'Hello World'",
            "</code>"
        ]
        for chunk in chunks:
            yield chunk

    # Mock server and session
    server = Server("test", "http://localhost", "ollama")
    session = Session(mode="execute")
    
    # Keep track of executed tools
    executed_tools = []
    def mock_on_result(tool_name, result):
        executed_tools.append((tool_name, result))

    # Mock _execute_tool to avoid running real bash commands in the test
    class MockCodeAgent(CodeAgent):
        def _execute_tool(self, call: dict) -> str:
            return f"Mock output of {call['tool']}"
    
    agent = MockCodeAgent(
        server=server,
        model="test-model",
        session=session,
        stream_fn=mock_stream_fn,
        on_text=lambda text: None, # suppress output
        on_tool=lambda name, args: print(f"  [AGENT CAUGHT TOOL] {name}"),
        on_result=mock_on_result,
        max_turns=1 # Run only 1 turn so it returns after executing the tool
    )
    
    print("  => Starting Agent Run...")
    agent.run([{"role": "user", "content": "List files"}])
    
    assert len(executed_tools) == 1, "Agent failed to execute the tool"
    assert executed_tools[0][0] == "run_bash", "Agent executed the wrong tool"
    print("  => Agent Execution Loop correctly caught and executed the tool!\n")

if __name__ == "__main__":
    test_xml_tool_parsing()
    test_agent_execution_loop()
    print("[SUCCESS] All agent tool tests passed!")
