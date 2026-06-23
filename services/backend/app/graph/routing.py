"""Post-investigate routing + confidence_gate grounding guards (spec §5).

route_after_investigate is the single conditional-edge function out of the
investigate node. It inspects the last AIMessage's tool call and the history of
prior tool calls (scanned from state["messages"]) to decide the next node:

    data/trace tool call            -> "tools"        (ToolNode executes it)
    submit_identification + guards  -> "submit_id"    (or "investigate" if a guard fails)
    ask_user (under cap)            -> "ask_user"     (else "inconclusive")
    inconclusive                    -> "inconclusive"
    no tool call / data budget hit  -> "inconclusive"

When a guard fails we route back to "investigate"; the corrective ToolMessage
that closes the open terminal tool call is appended by `gate_feedback` (called
from the investigate-bounce path in build.py).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from .prompts import FOLLOW_UP_PROMPT, MAX_ASK_ROUNDS, MAX_DATA_TOOL_CALLS, MAX_GATE_BOUNCES
from .tools import DATA_TOOL_NAMES, TRACE_TOOL_NAMES

# Stable prefix of the message the follow_up node injects — marks the boundary
# of a new follow-up turn so grounding guards re-verify per turn (see
# _current_turn_messages).
_FOLLOW_UP_MARKER = FOLLOW_UP_PROMPT.split("{message}")[0]

# Re-export for tests / build.py
__all__ = ["route_after_investigate", "MAX_DATA_TOOL_CALLS", "guard_feedback_message"]


def _data_tool_calls_so_far(messages: list[Any]) -> int:
    """Count completed data-tool calls (by their ToolMessage results)."""
    return sum(
        1
        for m in messages
        if isinstance(m, ToolMessage) and getattr(m, "name", None) in DATA_TOOL_NAMES
    )


def _called_tool(messages: list[Any], name: str) -> bool:
    return any(isinstance(m, ToolMessage) and getattr(m, "name", None) == name for m in messages)


def _current_turn_messages(messages: list[Any]) -> list[Any]:
    """Messages belonging to the active turn: everything after the most recent
    follow-up re-entry.

    The presence guard scans for a grounding tool call; on a follow-up turn the
    agent may propose a *different* species, so evidence gathered for an earlier
    turn must not satisfy the guard. On turn 1 (no follow-up marker yet) this
    returns the whole history.
    """
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if (
            isinstance(m, HumanMessage)
            and isinstance(m.content, str)
            and m.content.startswith(_FOLLOW_UP_MARKER)
        ):
            return messages[i:]
    return messages


def _frequency_checked_for(messages: list[Any], species_code: str) -> bool:
    """Did a get_species_frequency call target this species_code?"""
    for m in messages:
        if isinstance(m, AIMessage):
            for call in getattr(m, "tool_calls", []) or []:
                if (
                    call.get("name") == "get_species_frequency"
                    and call.get("args", {}).get("species_code") == species_code
                ):
                    return True
    return False


def _last_tool_call(messages: list[Any]) -> Optional[dict[str, Any]]:
    if not messages:
        return None
    last = messages[-1]
    calls = getattr(last, "tool_calls", None) if isinstance(last, AIMessage) else None
    return calls[0] if calls else None


def failed_guard(state: Mapping[str, Any]) -> Optional[str]:
    """Which grounding guard blocks the current submit_identification, if any.

    Returns "presence" | "frequency" | None. Shared by route_after_investigate
    and build.gate_feedback so the bounce decision and the corrective message
    never drift.

    Presence is satisfied by a grounding call *this turn* OR by the submitted
    species matching the last grounded conclusion (re-confirming the same bird
    within a session needs no fresh regional check — presence doesn't change in
    a 30-minute window). Frequency (for HIGH confidence) is species-scoped over
    the whole history for the same reason.
    """
    messages = state.get("messages", [])
    call = _last_tool_call(messages)
    if not call or call.get("name") != "submit_identification":
        return None

    top = call.get("args", {}).get("top_species") or {}
    code = top.get("species_code", "")

    turn_messages = _current_turn_messages(messages)
    grounded_this_turn = _called_tool(turn_messages, "get_regional_birds") or _called_tool(
        turn_messages, "get_historic_birds"
    )
    already_grounded = bool(code) and code == state.get("last_species_code")
    if not (grounded_this_turn or already_grounded):
        return "presence"

    if top.get("confidence") == "high" and (not code or not _frequency_checked_for(messages, code)):
        return "frequency"

    return None


def guard_feedback_message(reason: str) -> str:
    """Human-readable corrective instruction emitted when a guard bounces."""
    return {
        "presence": (
            "Before concluding, check regional presence: call get_regional_birds "
            "(or date-anchored data) for the resolved region first."
        ),
        "frequency": (
            "You claimed HIGH confidence. First call get_species_frequency for your "
            "top candidate's species_code to confirm it is actually common there, "
            "or lower your confidence."
        ),
    }.get(reason, "Please gather more grounding evidence before concluding.")


def route_after_investigate(state: dict[str, Any]) -> str:
    """Conditional edge out of investigate. Returns a node name."""
    messages = state.get("messages", [])
    call = _last_tool_call(messages)
    data_calls = _data_tool_calls_so_far(messages)

    # No tool call at all -> the agent stopped without a terminal; conclude honestly.
    if call is None:
        return "inconclusive"

    name = call.get("name", "")

    # Non-terminal tool (data or trace): run it — unless the data budget is spent.
    if name in DATA_TOOL_NAMES or name in TRACE_TOOL_NAMES:
        if name in DATA_TOOL_NAMES and data_calls >= MAX_DATA_TOOL_CALLS:
            return "inconclusive"  # out of budget; stop investigating
        return "tools"

    # Terminal tools below.
    if name == "inconclusive":
        return "inconclusive"

    if name == "ask_user":
        if state.get("ask_rounds", 0) >= MAX_ASK_ROUNDS:
            return "inconclusive"
        return "ask_user"

    if name == "submit_identification":
        # A failed guard normally bounces back to investigate (via gate_feedback),
        # but after MAX_GATE_BOUNCES we stop looping and conclude honestly.
        if failed_guard(state):
            bounced_out = state.get("gate_bounces", 0) >= MAX_GATE_BOUNCES
            return "inconclusive" if bounced_out else "investigate"
        return "submit_id"

    # Unknown tool name -> conclude honestly rather than loop.
    return "inconclusive"
