"""Adapt the compiled graph's astream output into SSE event dicts.

Event dicts match the existing protocol (status/thinking/tool_call/tool_result/
detective_note/candidates/result/error) plus new session_id + awaiting_input.
The route layer (identify.py) consumes these unchanged, still resolving images.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.errors import GraphRecursionError
from langgraph.types import Command

from . import prompts
from .build import bird_graph
from .state import session_store

logger = logging.getLogger(__name__)

_STREAM_MODES = ["custom", "messages", "updates"]


class BirdGraphRunner:
    def __init__(self, graph: Any = bird_graph, store: Any = session_store) -> None:
        self._graph = graph
        self._store = store

    def _config(self, session_id: str) -> dict[str, Any]:
        # recursion_limit must comfortably exceed the tool budgets: each tool
        # call is two supersteps (investigate + tools), so 12 data + ~20 trace
        # calls is ~64 visits. 150 leaves headroom; a true runaway loop trips it
        # and is translated into an honest "inconclusive" below.
        return {"configurable": {"thread_id": session_id}, "recursion_limit": 150}

    async def _drive(self, session_id: str, graph_input: Any) -> AsyncIterator[dict[str, Any]]:
        """Shared streaming core for both fresh runs and resumes."""
        config = self._config(session_id)
        interrupted = False
        try:
            async for mode, chunk in self._graph.astream(
                graph_input, config, stream_mode=_STREAM_MODES
            ):
                if mode == "custom":
                    # Tool bodies emit fully-formed SSE event dicts.
                    yield chunk
                elif mode == "messages":
                    msg, meta = chunk
                    if meta.get("langgraph_node") != "investigate":
                        continue
                    for piece in _thinking_pieces(msg):
                        yield {"type": "thinking", "content": piece}
                elif mode == "updates":
                    if isinstance(chunk, dict) and "__interrupt__" in chunk:
                        interrupted = True
                        payload = chunk["__interrupt__"][0].value
                        event: dict[str, Any] = {
                            "type": "awaiting_input",
                            "reason": payload.get("reason", "clarify"),
                            "question": payload.get("question", ""),
                        }
                        if payload.get("options"):
                            event["options"] = payload["options"]
                        yield event

            if not interrupted:
                snap = await self._graph.aget_state(config)
                final = (snap.values or {}).get("final") if snap else None
                yield {"type": "result", "data": final or dict(prompts.FALLBACK_RESPONSE)}
        except GraphRecursionError:
            # Runaway investigation/bounce loop — conclude honestly rather than
            # surfacing a generic error.
            logger.warning(
                "Graph hit recursion limit; returning inconclusive",
                extra={"operation": "graph_runner", "status": "recursion_limit"},
            )
            yield {"type": "result", "data": dict(prompts.FALLBACK_RESPONSE)}
        except Exception as e:
            logger.error(
                f"Graph run failed: {e}",
                extra={
                    "operation": "graph_runner",
                    "status": "error",
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            yield {"type": "error", "message": "An unexpected error occurred. Please try again."}

    async def run_stream(
        self, session_id: str, description: str, location: str, observed_at: Optional[str] = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Turn 1: fresh graph run for a new session."""
        self._store.touch(session_id)
        yield {"type": "session_id", "session_id": session_id}
        yield {"type": "status", "message": "Checking your description..."}

        user = f"I observed a bird...\n\nDescription: {description}\nLocation: {location}"
        if observed_at:
            user += f"\nObserved at: {observed_at}"
        graph_input = {
            "description": description,
            "location": location,
            "observed_at": observed_at,
            "messages": [SystemMessage(content=prompts.SYSTEM_PROMPT), HumanMessage(content=user)],
            "ask_rounds": 0,
            "final": None,
        }
        async for event in self._drive(session_id, graph_input):
            yield event

    async def resume_stream(
        self, session_id: str, user_message: str
    ) -> AsyncIterator[dict[str, Any]]:
        """Turn 2+: resume a paused session with the user's answer."""
        if not self._store.exists(session_id):
            yield {
                "type": "error",
                "message": "This session expired. Please start a new identification.",
            }
            return
        self._store.touch(session_id)
        yield {"type": "session_id", "session_id": session_id}
        yield {"type": "status", "message": "Picking up where we left off..."}
        async for event in self._drive(session_id, Command(resume=user_message)):
            yield event

    async def continue_stream(
        self, session_id: str, user_message: str
    ) -> AsyncIterator[dict[str, Any]]:
        """Follow-up turn. If the session is paused at a question, resume it;
        if it already concluded, re-enter the investigation with the new message
        (the agent may refine the identification or simply answer)."""
        if not self._store.exists(session_id):
            yield {
                "type": "error",
                "message": "This session expired. Please start a new identification.",
            }
            return
        self._store.touch(session_id)
        yield {"type": "session_id", "session_id": session_id}

        snap = await self._graph.aget_state(self._config(session_id))
        pending = bool(snap.next) if snap else False

        if pending:
            # Paused at a clarifying question — a normal resume.
            yield {"type": "status", "message": "Picking up where we left off..."}
            graph_input: Any = Command(resume=user_message)
        else:
            # Concluded — re-enter via the follow_up node, which appends the new
            # message and hands back to investigate (the agent may re-identify or
            # just answer). Terminal nodes already closed their tool calls.
            yield {"type": "status", "message": "Taking another look..."}
            graph_input = Command(goto="follow_up", update={"follow_up_message": user_message})

        async for event in self._drive(session_id, graph_input):
            yield event


def _thinking_pieces(msg: Any) -> list[str]:
    """Extract human-visible thinking/text token text from an AIMessageChunk.

    langchain-anthropic streams .content as a list of typed blocks when thinking
    is enabled (e.g. {"type": "thinking", "thinking": "..."} / {"type": "text",
    "text": "..."}). Fall back to a plain string content.
    """
    content = getattr(msg, "content", None)
    if isinstance(content, str):
        return [content] if content else []
    pieces: list[str] = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                text = block.get("thinking") or block.get("text") or ""
                if text:
                    pieces.append(text)
            elif isinstance(block, str) and block:
                pieces.append(block)
    return pieces


# Module singleton
bird_runner = BirdGraphRunner()
