import os
import tempfile
import pytest
from dct.tools.board import AgentBoard, BoardMessage, get_board
from dct.agent.codeagent import CodeAgent
from dct.agent.parser import parse_tool_call
from dct.agent.session import Session
from dct.core.registry import Server
from dct.core.config import Config


def test_agent_board_crud(tmp_path):
    storage_path = str(tmp_path / "test_board.json")
    board = AgentBoard(storage_path=storage_path)

    # 1. Post messages
    m1 = board.post(sender="Architect", content="Proposal for modular architecture", channel="architecture", tags=["design"])
    assert m1.id == "msg_1"
    assert m1.sender == "Architect"
    assert m1.channel == "architecture"

    m2 = board.post(sender="Engineer", content="Agree, will build prototype", channel="architecture", reply_to="msg_1")
    assert m2.id == "msg_2"
    assert m2.reply_to == "msg_1"

    m3 = board.post(sender="GeneralAgent", content="General chat message", channel="general")
    assert m3.id == "msg_3"

    # 2. Read by channel
    arch_msgs = board.read(channel="architecture")
    assert len(arch_msgs) == 2
    assert arch_msgs[0]["id"] == "msg_1"
    assert arch_msgs[1]["id"] == "msg_2"

    # 3. Read with search
    search_msgs = board.read(channel="architecture", search="prototype")
    assert len(search_msgs) == 1
    assert search_msgs[0]["sender"] == "Engineer"

    # 4. List channels
    channels = board.list_channels()
    assert len(channels) == 2
    ch_names = {c["channel"] for c in channels}
    assert "architecture" in ch_names
    assert "general" in ch_names

    # 5. Format for prompt
    prompt_str = board.format_for_prompt(channel="architecture")
    assert "[AGENT DISCUSSION BOARD #architecture]" in prompt_str
    assert "@Architect" in prompt_str
    assert "@Engineer" in prompt_str

    # 6. Clear channel
    board.clear(channel="architecture")
    assert len(board.read(channel="architecture")) == 0
    assert len(board.read(channel="general")) == 1

    # 7. Clear all
    board.clear()
    assert len(board.read(channel="general")) == 0


def test_codeagent_board_tools():
    conf = Config()
    conf.set("enable_agent_board", True)
    conf.save()

    try:
        board = get_board()
        board.clear()

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

        # 1. board_post tool
        post_call = {
            "tool": "board_post",
            "channel": "swarms",
            "sender": "LeadAgent",
            "content": "Deploying worker nodes",
            "raw_text": "<tool>board_post</tool><channel>swarms</channel><sender>LeadAgent</sender><content>Deploying worker nodes</content>",
        }
        res = agent._execute_tool(post_call)
        assert "[SUCCESS] Posted to #swarms" in res

        # 2. board_read tool
        read_call = {
            "tool": "board_read",
            "channel": "swarms",
            "raw_text": "<tool>board_read</tool><channel>swarms</channel>",
        }
        read_res = agent._execute_tool(read_call)
        assert "[AGENT DISCUSSION BOARD #swarms]" in read_res
        assert "@LeadAgent" in read_res
        assert "Deploying worker nodes" in read_res

        # 3. board_list_channels tool
        list_ch_call = {
            "tool": "board_list_channels",
            "raw_text": "<tool>board_list_channels</tool>",
        }
        list_res = agent._execute_tool(list_ch_call)
        assert "[ACTIVE DISCUSSION CHANNELS]" in list_res
        assert "#swarms" in list_res

        # 4. board_clear tool
        clear_call = {
            "tool": "board_clear",
            "channel": "swarms",
            "raw_text": "<tool>board_clear</tool><channel>swarms</channel>",
        }
        clear_res = agent._execute_tool(clear_call)
        assert "[SUCCESS] Cleared discussion messages in #swarms" in clear_res
    finally:
        conf.set("enable_agent_board", False)
        conf.save()


def test_board_disabled_by_default():
    conf = Config()
    conf.set("enable_agent_board", False)
    conf.save()

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

    post_call = {
        "tool": "board_post",
        "channel": "swarms",
        "sender": "LeadAgent",
        "content": "Deploying worker nodes",
        "raw_text": "<tool>board_post</tool><channel>swarms</channel><sender>LeadAgent</sender><content>Deploying worker nodes</content>",
    }
    res = agent._execute_tool(post_call)
    assert "[TOOL ERROR] Agent discussion board feature is disabled in config" in res


def test_parser_board_xml():
    xml = """
    <tool>board_post</tool>
    <channel>debate</channel>
    <sender>Critic</sender>
    <content>Security risk in line 42</content>
    <reply_to>5</reply_to>
    <tags>security,audit</tags>
    """
    parsed = parse_tool_call(xml)
    assert parsed is not None
    assert parsed["tool"] == "board_post"
    assert parsed["channel"] == "debate"
    assert parsed["sender"] == "Critic"
    assert parsed["content"] == "Security risk in line 42"
    assert parsed["reply_to"] == "5"
    assert parsed["tags"] == "security,audit"
