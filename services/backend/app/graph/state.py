"""Graph state schema + in-memory session store with TTL eviction.

The session store does NOT hold conversation state itself — LangGraph's
InMemorySaver owns the checkpointed graph state, keyed by thread_id (== the
session_id). This store only tracks which session_ids are live and when they
were last touched, so we can answer "unknown/expired session?" and sweep stale
threads. A process restart drops everything; clients recover by starting fresh.
"""

from __future__ import annotations

import time
import uuid
from typing import Annotated, Any, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class BirdState(TypedDict, total=False):
    """LangGraph state for one identification session (one thread)."""

    messages: Annotated[list[AnyMessage], add_messages]
    # Raw turn-1 inputs (kept for resolve_inputs + prompts)
    description: str
    location: str
    observed_at: Optional[str]
    # Resolved by resolve_inputs
    region: Optional[str]  # validated eBird region code, or None
    observed_window: str  # "recent" or a historic "YYYY-MM-DD"
    # HITL bookkeeping
    ask_rounds: int
    gate_bounces: int  # times a terminal was bounced back by a failed guard
    # Set by the runner on a follow-up turn; consumed by the follow_up node
    follow_up_message: Optional[str]
    # species_code of the last GROUNDED conclusion (set by submit_id). Lets a
    # follow-up that re-submits the same species skip a redundant presence check.
    last_species_code: Optional[str]
    # Terminal payload (set by submit_id / inconclusive / guardrail bail)
    final: Optional[dict[str, Any]]


class SessionStore:
    """Tracks live session ids and last-touch times for TTL eviction."""

    def __init__(self, ttl_seconds: int = 1800) -> None:
        self._ttl = ttl_seconds
        self._last_seen: dict[str, float] = {}

    def create(self, now: Optional[float] = None) -> str:
        sid = uuid.uuid4().hex
        self._last_seen[sid] = now if now is not None else time.time()
        return sid

    def touch(self, session_id: str, now: Optional[float] = None) -> bool:
        """Refresh last-seen. Returns False if the session is unknown."""
        if session_id not in self._last_seen:
            return False
        self._last_seen[session_id] = now if now is not None else time.time()
        return True

    def exists(self, session_id: str, now: Optional[float] = None) -> bool:
        ts = self._last_seen.get(session_id)
        if ts is None:
            return False
        current = now if now is not None else time.time()
        if current - ts > self._ttl:
            self._last_seen.pop(session_id, None)
            return False
        return True

    def sweep(self, now: Optional[float] = None) -> list[str]:
        """Drop all expired sessions; return the ids removed."""
        current = now if now is not None else time.time()
        expired = [s for s, ts in self._last_seen.items() if current - ts > self._ttl]
        for s in expired:
            self._last_seen.pop(s, None)
        return expired


# Module-level singleton (30-minute idle TTL per spec §8)
session_store = SessionStore(ttl_seconds=1800)
