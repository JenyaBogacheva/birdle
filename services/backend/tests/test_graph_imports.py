"""Smoke test: the LangGraph API surface this plan relies on is importable."""


def test_core_langgraph_imports():
    from langgraph.graph import END, START, StateGraph  # noqa: F401
    from langgraph.graph.message import add_messages  # noqa: F401
    from langgraph.checkpoint.memory import InMemorySaver  # noqa: F401
    from langgraph.types import Command, interrupt  # noqa: F401
    from langgraph.config import get_stream_writer  # noqa: F401
    from langgraph.prebuilt import ToolNode, tools_condition  # noqa: F401


def test_langchain_anthropic_imports():
    from langchain_anthropic import ChatAnthropic  # noqa: F401
    from langchain_core.messages import (  # noqa: F401
        AIMessage,
        AIMessageChunk,
        HumanMessage,
        SystemMessage,
        ToolMessage,
    )
    from langchain_core.tools import tool  # noqa: F401
