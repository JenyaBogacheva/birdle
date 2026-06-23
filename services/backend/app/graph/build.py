"""Assemble and compile the bird-ID StateGraph."""

from __future__ import annotations

from typing import Any, Hashable

from langchain_core.messages import ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from . import nodes, routing
from .state import BirdState
from .tools import EXECUTABLE_TOOLS

# Router result -> actual destination node. "investigate" bounce goes via the
# gate_feedback node so the open terminal tool call gets a closing ToolMessage.
_ROUTE_MAP: dict[Hashable, str] = {
    "tools": "tools",
    "submit_id": "submit_id",
    "ask_user": "ask_user",
    "inconclusive": "inconclusive",
    "investigate": "gate_feedback",
}


def _route_from_guardrail(state: BirdState) -> str:
    """After guardrail: bail to END if final was set (not a bird), else resolve."""
    return END if state.get("final") else "resolve_inputs"


def gate_feedback(state: BirdState) -> dict[str, Any]:
    """Close a guard-rejected terminal tool call with a corrective ToolMessage."""
    messages = state.get("messages", [])
    call = routing._last_tool_call(messages) or {}
    call_id = call.get("id", "guard")
    # Reuse the router's own verdict so the corrective message names the guard
    # that actually failed (e.g. presence on a species-changing follow-up).
    reason = routing.failed_guard(state) or "presence"
    return {
        "messages": [
            ToolMessage(content=routing.guard_feedback_message(reason), tool_call_id=call_id)
        ],
        "gate_bounces": state.get("gate_bounces", 0) + 1,
    }


def build_graph() -> Any:
    """Build + compile the graph with an in-memory checkpointer."""
    builder = StateGraph(BirdState)

    builder.add_node("guardrail", nodes.guardrail)
    builder.add_node("resolve_inputs", nodes.resolve_inputs)
    builder.add_node("follow_up", nodes.follow_up)
    builder.add_node("investigate", nodes.investigate)
    builder.add_node("tools", ToolNode(EXECUTABLE_TOOLS))
    builder.add_node("gate_feedback", gate_feedback)
    builder.add_node("ask_user", nodes.ask_user)
    builder.add_node("submit_id", nodes.submit_id)
    builder.add_node("inconclusive", nodes.inconclusive)

    builder.add_edge(START, "guardrail")
    builder.add_conditional_edges(
        "guardrail",
        _route_from_guardrail,
        {END: END, "resolve_inputs": "resolve_inputs"},  # type: ignore[arg-type]
    )
    builder.add_edge("resolve_inputs", "investigate")
    # Follow-up turns re-enter here (via Command(goto="follow_up")): the agent
    # gets the new message + full prior context and re-runs the investigation.
    builder.add_edge("follow_up", "investigate")
    builder.add_conditional_edges("investigate", routing.route_after_investigate, _ROUTE_MAP)
    builder.add_edge("tools", "investigate")
    builder.add_edge("gate_feedback", "investigate")
    builder.add_edge("ask_user", "investigate")
    builder.add_edge("submit_id", END)
    builder.add_edge("inconclusive", END)

    return builder.compile(checkpointer=InMemorySaver())


# Module singleton — one compiled graph (one shared InMemorySaver) per process.
bird_graph = build_graph()
