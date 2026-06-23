"""Tests for follow-up turns: terminal tool-call closing + the follow_up node."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from services.backend.app.graph import nodes


async def test_submit_id_closes_its_tool_call():
    # A concluded turn must leave the terminal tool call closed so the next
    # turn's transcript is valid for Anthropic.
    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "submit_identification",
                    "args": {"message": "It's a cardinal", "top_species": {"common_name": "x"}},
                    "id": "call_1",
                }
            ],
        ),
    ]
    out = await nodes.submit_id({"messages": messages})

    assert out["final"]["message"] == "It's a cardinal"
    closing = out["messages"][0]
    assert isinstance(closing, ToolMessage)
    assert closing.tool_call_id == "call_1"


async def test_inconclusive_closes_its_tool_call():
    messages = [
        AIMessage(content="", tool_calls=[{"name": "inconclusive", "args": {}, "id": "call_2"}]),
    ]
    out = await nodes.inconclusive({"messages": messages})

    assert out["final"]["top_species"] is None
    assert isinstance(out["messages"][0], ToolMessage)
    assert out["messages"][0].tool_call_id == "call_2"


async def test_follow_up_appends_framed_message():
    out = await nodes.follow_up({"follow_up_message": "is it a juvenile?"})

    assert out["final"] is None
    assert out["follow_up_message"] is None
    msg = out["messages"][0]
    assert isinstance(msg, HumanMessage)
    assert "is it a juvenile?" in msg.content
