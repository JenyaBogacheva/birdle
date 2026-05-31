# LangGraph + HITL Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the bird-identification agent from the raw-Anthropic-SDK loop in `bird_agent.py` to a LangGraph graph with explicit-but-non-rigid nodes, human-in-the-loop (interrupt/resume), in-memory per-session checkpointing, mandatory eBird grounding guards, and an honest "inconclusive" outcome — streamed over the existing SSE event protocol plus two new events (`session_id`, `awaiting_input`).

**Architecture:** A new `services/backend/app/graph/` package. One `StateGraph`: `guardrail → resolve_inputs → investigate ⇄ tools → (route) → {submit_id | ask_user | inconclusive}`. The `investigate` node is a `langchain_anthropic.ChatAnthropic` (Sonnet, extended thinking) with all tools bound; it chooses tools freely. A `ToolNode` runs data + trace tools. A custom router reads *which* terminal tool the agent called and a `confidence_gate` enforces grounding guards, bouncing back to `investigate` (with a corrective `ToolMessage`) when unmet. HITL uses `interrupt()` + `InMemorySaver` keyed by `session_id`. A `BirdGraphRunner` translates LangGraph's multi-mode `astream` (`messages` for thinking/text tokens, `custom` for UI events from tool bodies, `updates` for interrupt detection) into the SSE event dicts the route already understands.

**Tech Stack:** Python 3.11, LangGraph 1.x, langchain-anthropic 1.3.x, langchain-core, FastAPI/SSE, pytest (`asyncio_mode=auto` — plain `async def` tests).

---

## Architecture decisions (resolving spec §13)

These are locked for this plan; do not re-litigate during implementation.

- **Q1 — module split:** new `services/backend/app/graph/` package (`state.py`, `prompts.py`, `tools.py`, `nodes.py`, `routing.py`, `build.py`, `runner.py`). `bird_agent.py` is **replaced and deleted** (Task 17).
- **Q2 — resume endpoint:** dedicated `POST /api/identify/resume` carrying `{session_id, user_message}`.
- **Q3 — season-decisive:** `resolve_inputs` computes an `observed_window` (`"recent"` or a historic `YYYY-MM-DD`) and injects it as guidance; choosing recent-vs-historic tools is the agent's call (prompt heuristic). **Not** a hard gate.
- **Q4 — frequency cap:** unchanged `FREQUENCY_FETCH_CAP=400` (Plan 1).
- **Q5 — region resolution:** `resolve_inputs` uses a cheap Haiku structured parse (location → eBird region code) validated with `ebird_client.get_region_info`. Unresolvable provided-location → hard `clarify_location`. Missing location → soft (skippable) ask.

### Mandatory-grounding guards (spec §5), as implemented in `confidence_gate`

Guards are computed by **scanning `state["messages"]`** for prior tool calls (no separate counters). On a failed guard the gate appends a corrective `ToolMessage` for the terminal tool's `tool_call_id` and routes back to `investigate` (this also satisfies Anthropic's "every `tool_use` needs a `tool_result`" rule).

1. **Presence before `submit_identification`:** at least one `get_regional_birds` **or** `get_historic_birds` call must appear in history.
2. **Frequency before HIGH confidence:** if `submit_identification` has `top_species.confidence == "high"`, a `get_species_frequency` call whose `species_code` matches `top_species.species_code` must appear in history. (Medium/low skip.)
3. **Budget / ask-cap:** if data-tool calls in history `>= MAX_DATA_TOOL_CALLS`, the gate forces a terminal route (prefer `submit_identification` if the agent called one, else `inconclusive`). If `ask_rounds >= MAX_ASK_ROUNDS`, an `ask_user` terminal is converted to `inconclusive`.

`inconclusive` is the honest fallback and is **never** blocked by guards 1–2.

---

## File Structure

```
services/backend/app/graph/
  __init__.py        # re-export build_graph, bird_runner
  state.py           # BirdState (TypedDict) + SessionStore (in-memory, TTL)
  prompts.py         # SYSTEM_PROMPT, GUARDRAIL_*, RESOLVE_PROMPT, NOT_BIRD/FALLBACK, model+budget constants
  tools.py           # @tool data tools, trace tools, terminal tools; name sets
  nodes.py           # guardrail, resolve_inputs, investigate, ask_user, submit_id, inconclusive
  routing.py         # route_after_investigate (router) + guard helpers
  build.py           # assemble + compile StateGraph (InMemorySaver); module singleton
  runner.py          # BirdGraphRunner.run_stream / resume_stream → SSE event dicts
services/backend/app/routes/identify.py   # MODIFY: use runner; add /resume; new events
services/backend/app/schemas/observation.py # MODIFY: ResumeInput, AwaitingInputPayload
services/backend/tests/test_graph_*.py     # new test files, one per module
```

Each `graph/` file has one responsibility. `nodes.py` may grow to ~250 lines — acceptable for the node layer; if a single node balloons, that's a smell, but the six nodes here are each small.

---

## Phase 0 — Dependencies

### Task 1: Add LangGraph deps + import smoke test

**Files:**
- Modify: `pyproject.toml:9-18` (dependencies block)
- Create: `services/backend/tests/test_graph_imports.py`

- [ ] **Step 1: Add the dependencies**

In `pyproject.toml`, under `[tool.poetry.dependencies]` (after `python-multipart`):

```toml
langgraph = "^1.2"
langchain-anthropic = "^1.3"
langchain-core = "^1.0"
```

- [ ] **Step 2: Install**

Run: `poetry lock && poetry install`
Expected: resolves and installs langgraph, langchain-anthropic, langchain-core (+ transitive langgraph-checkpoint, langgraph-prebuilt). If version constraints fail to resolve, relax to the latest compatible (`poetry add langgraph langchain-anthropic`) and record the resolved versions.

- [ ] **Step 3: Write the import smoke test**

Create `services/backend/tests/test_graph_imports.py`:

```python
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
```

- [ ] **Step 4: Run it**

Run: `poetry run pytest services/backend/tests/test_graph_imports.py -v`
Expected: PASS. **If any import fails, STOP** — the installed API differs from this plan's assumptions; report the exact ImportError so the controller can adjust before further tasks build on it.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml poetry.lock services/backend/tests/test_graph_imports.py
git commit -m "feat: add langgraph + langchain-anthropic deps with import smoke test"
```

---

## Phase 1 — State & session store

### Task 2: `graph/state.py` — BirdState + SessionStore

**Files:**
- Create: `services/backend/app/graph/__init__.py`
- Create: `services/backend/app/graph/state.py`
- Create: `services/backend/tests/test_graph_state.py`

- [ ] **Step 1: Write the failing tests**

Create `services/backend/tests/test_graph_state.py`:

```python
"""Tests for graph state schema + in-memory session store."""

from services.backend.app.graph.state import SessionStore


class TestSessionStore:
    def test_create_returns_unique_ids(self):
        store = SessionStore(ttl_seconds=1800)
        a = store.create()
        b = store.create()
        assert a != b
        assert store.exists(a)
        assert store.exists(b)

    def test_touch_marks_known_session(self):
        store = SessionStore(ttl_seconds=1800)
        sid = store.create()
        assert store.touch(sid) is True
        assert store.touch("does-not-exist") is False

    def test_unknown_session_not_exists(self):
        store = SessionStore(ttl_seconds=1800)
        assert store.exists("nope") is False

    def test_eviction_of_expired(self):
        store = SessionStore(ttl_seconds=1800)
        sid = store.create(now=1000.0)
        # 1800s later, still alive; 1801s later, expired
        assert store.exists(sid, now=1000.0 + 1800) is True
        assert store.exists(sid, now=1000.0 + 1801) is False

    def test_sweep_removes_expired(self):
        store = SessionStore(ttl_seconds=10)
        sid = store.create(now=0.0)
        store.create(now=100.0)  # fresh
        removed = store.sweep(now=100.0)
        assert sid in removed
        assert store.exists(sid, now=100.0) is False


def test_bird_state_is_typeddict_with_expected_keys():
    from services.backend.app.graph.state import BirdState

    # TypedDict exposes declared keys via __annotations__
    keys = set(BirdState.__annotations__)
    assert {
        "messages",
        "description",
        "location",
        "observed_at",
        "region",
        "observed_window",
        "ask_rounds",
        "final",
    } <= keys
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run pytest services/backend/tests/test_graph_state.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Create the package init**

Create `services/backend/app/graph/__init__.py`:

```python
"""LangGraph-based bird identification graph package."""
```

- [ ] **Step 4: Implement `state.py`**

Create `services/backend/app/graph/state.py`:

```python
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
    region: Optional[str]          # validated eBird region code, or None
    observed_window: str           # "recent" or a historic "YYYY-MM-DD"
    # HITL bookkeeping
    ask_rounds: int
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
```

- [ ] **Step 5: Run to verify it passes**

Run: `poetry run pytest services/backend/tests/test_graph_state.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add services/backend/app/graph/__init__.py services/backend/app/graph/state.py services/backend/tests/test_graph_state.py
git commit -m "feat: add graph BirdState schema + in-memory SessionStore"
```

---

## Phase 2 — Prompts & constants

### Task 3: `graph/prompts.py` — prompts, constants, budgets

**Files:**
- Create: `services/backend/app/graph/prompts.py`
- Create: `services/backend/tests/test_graph_prompts.py`

- [ ] **Step 1: Write the failing tests**

Create `services/backend/tests/test_graph_prompts.py`:

```python
"""Tests for graph prompt/constant wiring."""

from services.backend.app.graph import prompts


def test_models_and_budgets():
    assert prompts.GUARDRAIL_MODEL == "claude-haiku-4-5"
    assert prompts.RESOLVE_MODEL == "claude-haiku-4-5"
    assert prompts.AGENT_MODEL == "claude-sonnet-4-6"
    assert prompts.MAX_DATA_TOOL_CALLS == 12  # raised from 8 per spec §7.3
    assert prompts.MAX_ASK_ROUNDS == 2


def test_system_prompt_documents_three_endings():
    sp = prompts.SYSTEM_PROMPT
    assert "submit_identification" in sp
    assert "ask_user" in sp
    assert "inconclusive" in sp


def test_system_prompt_keeps_colloquial_broadening():
    assert "duck" in prompts.SYSTEM_PROMPT.lower()


def test_not_bird_response_shape():
    assert prompts.NOT_BIRD_RESPONSE["top_species"] is None
    assert "message" in prompts.NOT_BIRD_RESPONSE
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run pytest services/backend/tests/test_graph_prompts.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `prompts.py`**

Create `services/backend/app/graph/prompts.py`:

```python
"""Prompts, model ids, and budget constants for the bird-ID graph."""

from typing import Any

GUARDRAIL_MODEL = "claude-haiku-4-5"
RESOLVE_MODEL = "claude-haiku-4-5"
AGENT_MODEL = "claude-sonnet-4-6"

# Budgets (spec §7.3). Data-tool budget raised 8 -> 12 for per-candidate
# frequency calls. Ask-round cap forces an honest "inconclusive" after 2 asks.
MAX_DATA_TOOL_CALLS = 12
MAX_ASK_ROUNDS = 2

# Extended-thinking budget (must be < max_tokens). tool_choice MUST stay auto
# when thinking is enabled (Anthropic constraint) — never force tool use.
THINKING_BUDGET_TOKENS = 4000
AGENT_MAX_TOKENS = 8000

GUARDRAIL_PROMPT = (
    "Is the following user message a request to identify a bird or "
    "about bird watching/ornithology? Answer only YES or NO."
)

# resolve_inputs structured parse. Returns strict JSON only.
RESOLVE_PROMPT = """\
You convert a user's free-text location and time into structured fields for
eBird lookups. Return ONLY a JSON object, no prose.

Fields:
- "region_code": the MOST SPECIFIC eBird region code for the location, or null
  if the location is empty/unintelligible. Rules:
  - US states: US-XX (US-NY). Counties: US-XX-### if the user named a specific
    county/borough you are confident about (Brooklyn -> US-NY-047).
  - Canadian provinces CA-XX, Australian states AU-XX, UK GB-ENG/GB-SCT/...
  - Other large countries: ISO 3166-2 subnational (RU-MOW, BR-SP, IN-DL).
  - Small countries: ISO 3166-1 alpha-2 (NZ, IL, SG).
  - If the location is present but you cannot map it to any code, return null.
- "observed_window": "recent" if no date was given or the date is within the
  last ~14 days or clearly means "lately"; "YYYY-MM-DD" if a specific past date
  is given or clearly inferable; "unparseable" if a date was given but is
  genuinely ambiguous (e.g. "idk, summer?").

Examples:
  location="Brooklyn, NY" time=null -> {"region_code":"US-NY-047","observed_window":"recent"}
  location="Berlin" time="last January 15th" -> {"region_code":"DE-BE","observed_window":"YYYY-MM-DD"}
  location="" time=null -> {"region_code":null,"observed_window":"recent"}
  location="my backyard" time="summer maybe" -> {"region_code":null,"observed_window":"unparseable"}
"""

SYSTEM_PROMPT = """\
You are Birdle, an expert bird identification detective. You identify birds from
people's descriptions by investigating real evidence — you do not guess in the dark.

## The investigation

This is an investigation, not a form. Loop between thinking and tools as needed:
form hypotheses, gather eBird evidence, narrow the field, and end by calling
exactly ONE terminal tool (see "How to end").

You have these investigative tools:
- get_regional_birds(region, days): what's present in the area recently (presence/recency, NOT abundance).
- get_species_frequency(region, species_code, days): how common a specific species is recently — bucketed absent/rare/uncommon/common. This is your abundance signal.
- get_regional_rarities(region, days): notable/vagrant species reported recently. Check before dismissing an odd bird as a common look-alike.
- lookup_family(species_code): family/order for a species, for "shape-impression" broadening.
- web_search(query): the wider web, for genuinely unusual cases beyond eBird.

Use the resolved region you are given. Prefer the most specific region code.

## Grounding rules (enforced)

- You MUST consult regional presence (get_regional_birds, or get_historic data
  for a past date) before submitting an identification.
- You MUST frequency-check your top candidate (get_species_frequency for its
  species_code) before claiming HIGH confidence.
- If you are told the sighting's window is a specific past date, reason about
  whether the bird is plausible at THAT time of year (migration/seasonality),
  and prefer date-anchored evidence.

## Colloquial descriptions

People describe birds by what they resemble, not by taxonomy. Treat folk names
as shape-impressions and WIDEN the net:
- "like a duck" / "duck-like" -> coots, grebes, moorhens, cormorants, loons — not just ducks (Anatidae).
- "like a hawk" -> falcons, harriers, kites, osprey.
- "like a sparrow" -> warblers, wrens, pipits, buntings.
- Treat modifiers as clues: "a duck with a hat/crest" -> hooded merganser, crested waterbirds — not plain ducks.
Make this widening VISIBLE with a detective_note, e.g. "'Duck'? Maybe — but coots & grebes look the part too."

## Investigation notes (live UI)

- Call detective_note with brief, evocative observations (one sentence, max ~10 words):
  "Blue and orange... interesting.", "Too small for a jay.", "Common here. Good sign."
- Call update_candidates whenever your shortlist changes — species you're
  considering and ones you've eliminated (with brief reasons).
- Start with a detective_note before your first data tool. Update candidates
  after reviewing regional data.

## How to end — choose exactly ONE terminal tool

- submit_identification — you have a confident-enough answer (1-3 ranked species).
  Include species_code from eBird when available (used for images).
- ask_user — you are torn between confusable species and a single targeted
  question to the human would decide it. Ask the most distinguishing question.
- inconclusive — you genuinely cannot identify it. Give your closest low-confidence
  guesses and concrete "what would help" suggestions. This is an honest, valid outcome.

Confidence: HIGH = distinctive features + species common/present in region;
MEDIUM = fits multiple species or species uncommon; LOW = vague or conflicting.

Be friendly, honest about uncertainty, and show your reasoning. Do NOT emit JSON
as text — the terminal tool call IS your answer. Do NOT fetch images.\
"""

NOT_BIRD_RESPONSE: dict[str, Any] = {
    "message": (
        "I'm Birdle, a bird identification assistant! "
        "I can only help with identifying birds. "
        "Please describe a bird you've seen and I'll do my best to identify it."
    ),
    "top_species": None,
    "alternate_species": [],
    "clarification": "What did the bird look like? Include color, size, and behavior.",
}

FALLBACK_RESPONSE: dict[str, Any] = {
    "message": "I wasn't able to identify the bird. Could you provide more details?",
    "top_species": None,
    "alternate_species": [],
    "clarification": "Please describe the bird's size, colors, and behavior in more detail.",
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `poetry run pytest services/backend/tests/test_graph_prompts.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/graph/prompts.py services/backend/tests/test_graph_prompts.py
git commit -m "feat: add graph prompts, model ids, and tool budgets"
```

---

## Phase 3 — Tools

### Task 4: `graph/tools.py` — data tools (with SSE emission)

Data tools are `@tool` wrappers around `ebird_client` / `web_search_client`. Each emits a `tool_call` event before work and a `tool_result` summary after, via `get_stream_writer()`. The writer is a no-op when there is no active stream consumer (e.g. unit tests), so tools are testable directly.

**Files:**
- Create: `services/backend/app/graph/tools.py`
- Create: `services/backend/tests/test_graph_tools.py`

- [ ] **Step 1: Write the failing tests**

Create `services/backend/tests/test_graph_tools.py`:

```python
"""Tests for graph tool wrappers."""

from unittest.mock import AsyncMock, patch

from services.backend.app.graph import tools


class TestDataTools:
    async def test_get_regional_birds_calls_client(self):
        with patch.object(tools, "ebird_client") as mock:
            mock.get_regional_birds = AsyncMock(
                return_value={"region": "US-NY", "species_observed": [{"common_name": "Robin"}]}
            )
            # @tool wraps the fn; call the underlying coroutine via .ainvoke
            result = await tools.get_regional_birds.ainvoke({"region": "US-NY", "days": 7})
            mock.get_regional_birds.assert_awaited_once_with(region="US-NY", days=7)
            assert result["species_observed"][0]["common_name"] == "Robin"

    async def test_get_species_frequency_calls_client(self):
        with patch.object(tools, "ebird_client") as mock:
            mock.get_species_frequency = AsyncMock(
                return_value={"species_code": "norcar", "abundance": "common"}
            )
            result = await tools.get_species_frequency.ainvoke(
                {"region": "US-NY", "species_code": "norcar", "days": 14}
            )
            assert result["abundance"] == "common"

    async def test_web_search_calls_client(self):
        with patch.object(tools, "web_search_client") as mock:
            mock.search = AsyncMock(return_value=[{"title": "x"}])
            result = await tools.web_search.ainvoke({"query": "rare bird"})
            assert len(result) == 1


def test_tool_name_sets():
    assert tools.DATA_TOOL_NAMES == {
        "get_regional_birds",
        "get_species_frequency",
        "get_regional_rarities",
        "lookup_family",
        "web_search",
    }
    assert "detective_note" in tools.TRACE_TOOL_NAMES
    assert "update_candidates" in tools.TRACE_TOOL_NAMES
    assert tools.TERMINAL_TOOL_NAMES == {
        "submit_identification",
        "ask_user",
        "inconclusive",
    }


def test_executable_tools_excludes_terminal():
    # ToolNode runs data + trace tools only; terminal tools are routing signals.
    names = {t.name for t in tools.EXECUTABLE_TOOLS}
    assert "submit_identification" not in names
    assert "get_regional_birds" in names
    assert "detective_note" in names
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run pytest services/backend/tests/test_graph_tools.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the data tools + trace tools + name sets**

Create `services/backend/app/graph/tools.py`:

```python
"""LangGraph tool definitions for the bird-ID graph.

Three families:
  * DATA tools  — call eBird / web search; emit tool_call + tool_result SSE
                  events via the stream writer; executed by ToolNode.
  * TRACE tools — detective_note / update_candidates; pure UI signals emitted
                  via the stream writer; executed by ToolNode (no-op result).
  * TERMINAL tools — submit_identification / ask_user / inconclusive; these are
                  ROUTING SIGNALS, not executed by ToolNode. Their schemas are
                  bound to the model so it can "call" one to end; the router and
                  confidence_gate read the call. Bodies are never invoked.

The stream writer (get_stream_writer) is a no-op outside an active astream, so
every tool is directly unit-testable via `.ainvoke({...})`.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool
from langgraph.config import get_stream_writer

from ..helpers.ebird_client import ebird_client
from ..helpers.web_search import web_search_client


def _emit(event: dict[str, Any]) -> None:
    """Emit a custom SSE event if a stream consumer is attached; else no-op."""
    try:
        writer = get_stream_writer()
    except Exception:
        return
    if writer is not None:
        writer(event)


# ---------------------------------------------------------------- data tools


@tool
async def get_regional_birds(region: str, days: int = 14) -> dict[str, Any]:
    """Recently observed bird species in an eBird region (presence/recency, not abundance)."""
    _emit({"type": "tool_call", "tool": "get_regional_birds", "input": {"region": region, "days": days}})
    result = await ebird_client.get_regional_birds(region=region, days=days)
    n = len(result.get("species_observed", [])) if isinstance(result, dict) else 0
    _emit({"type": "tool_result", "tool": "get_regional_birds", "summary": f"Found {n} species in {region}"})
    return result


@tool
async def get_species_frequency(region: str, species_code: str, days: int = 14) -> dict[str, Any]:
    """How commonly a species was reported in a region recently — bucketed abundance."""
    _emit({"type": "tool_call", "tool": "get_species_frequency", "input": {"region": region, "species_code": species_code, "days": days}})
    result = await ebird_client.get_species_frequency(region=region, species_code=species_code, days=days)
    band = result.get("abundance", "unknown") if isinstance(result, dict) else "unknown"
    _emit({"type": "tool_result", "tool": "get_species_frequency", "summary": f"{species_code}: {band} in {region}"})
    return result


@tool
async def get_regional_rarities(region: str, days: int = 14) -> dict[str, Any]:
    """Notable/vagrant species reported in a region recently (rarity radar)."""
    _emit({"type": "tool_call", "tool": "get_regional_rarities", "input": {"region": region, "days": days}})
    result = await ebird_client.get_regional_rarities(region=region, days=days)
    n = len(result.get("rarities", [])) if isinstance(result, dict) else 0
    _emit({"type": "tool_result", "tool": "get_regional_rarities", "summary": f"{n} rarities in {region}"})
    return result


@tool
async def lookup_family(species_code: str) -> dict[str, Any]:
    """Family and order for a species code, for shape-impression broadening."""
    _emit({"type": "tool_call", "tool": "lookup_family", "input": {"species_code": species_code}})
    result = await ebird_client.lookup_family(species_code)
    fam = (result or {}).get("family", "unknown")
    _emit({"type": "tool_result", "tool": "lookup_family", "summary": f"{species_code}: {fam}"})
    return result or {"species_code": species_code, "family": "", "order": ""}


@tool
async def web_search(query: str) -> Any:
    """Search the web for bird-ID information — only for genuinely unusual cases."""
    _emit({"type": "tool_call", "tool": "web_search", "input": {"query": query}})
    result = await web_search_client.search(query)
    n = len(result) if isinstance(result, list) else 0
    _emit({"type": "tool_result", "tool": "web_search", "summary": f"Found {n} results for '{query}'"})
    return result


# --------------------------------------------------------------- trace tools


@tool
def detective_note(message: str) -> str:
    """Record a brief, evocative investigation note (one sentence, max ~10 words)."""
    _emit({"type": "detective_note", "message": message})
    return "noted"


@tool
def update_candidates(candidates: list[dict[str, Any]]) -> str:
    """Update the shortlist of candidate species (considering / eliminated)."""
    _emit({"type": "candidates", "data": candidates})
    return "updated"


# ------------------------------------------------------------ terminal tools
# Schemas only. ToolNode never runs these; the router/gate read the call args.
# Bodies are unreachable but must exist for @tool. Keep them no-ops.


@tool
def submit_identification(
    message: str,
    top_species: dict[str, Any] | None,
    alternate_species: list[dict[str, Any]] | None = None,
    clarification: str | None = None,
) -> str:
    """Submit the final identification (1-3 ranked species). Call once to finish.

    top_species/alternate_species items: {scientific_name, common_name,
    species_code, confidence(one of high|medium|low), reasoning}.
    """
    return "submitted"


@tool
def ask_user(reason: str, question: str, options: list[str] | None = None) -> str:
    """Pause and ask the human ONE targeted question to disambiguate species.

    reason: short tag, e.g. "disambiguate_species". question: the question text.
    options: optional quick-reply labels.
    """
    return "asked"


@tool
def inconclusive(
    message: str,
    closest_guesses: list[dict[str, Any]] | None = None,
    what_would_help: str | None = None,
) -> str:
    """Conclude that the bird cannot be identified. Give closest guesses + what would help."""
    return "inconclusive"


DATA_TOOLS = [get_regional_birds, get_species_frequency, get_regional_rarities, lookup_family, web_search]
TRACE_TOOLS = [detective_note, update_candidates]
TERMINAL_TOOLS = [submit_identification, ask_user, inconclusive]

# ToolNode executes data + trace only.
EXECUTABLE_TOOLS = DATA_TOOLS + TRACE_TOOLS
# All tools are bound to the model so it can call any of them.
ALL_TOOLS = DATA_TOOLS + TRACE_TOOLS + TERMINAL_TOOLS

DATA_TOOL_NAMES = {t.name for t in DATA_TOOLS}
TRACE_TOOL_NAMES = {t.name for t in TRACE_TOOLS}
TERMINAL_TOOL_NAMES = {t.name for t in TERMINAL_TOOLS}
```

- [ ] **Step 4: Run to verify it passes**

Run: `poetry run pytest services/backend/tests/test_graph_tools.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/graph/tools.py services/backend/tests/test_graph_tools.py
git commit -m "feat: add graph tool definitions (data, trace, terminal)"
```

---

## Phase 4 — Nodes

### Task 5: `graph/nodes.py` — guardrail node

We build `nodes.py` incrementally across Tasks 5–9. Each task adds one node + tests.

**Files:**
- Create: `services/backend/app/graph/nodes.py`
- Create: `services/backend/tests/test_graph_nodes.py`

- [ ] **Step 1: Write the failing tests**

Create `services/backend/tests/test_graph_nodes.py`:

```python
"""Tests for graph nodes."""

from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage

from services.backend.app.graph import nodes


class TestGuardrailNode:
    async def test_bird_query_passes_through(self):
        with patch.object(nodes, "_raw_anthropic") as mock_client:
            resp = MagicMock()
            resp.content = [MagicMock(text="YES")]
            mock_client.messages.create = AsyncMock(return_value=resp)
            # make the text block isinstance(TextBlock) check pass
            with patch.object(nodes, "_first_text", return_value="YES"):
                out = await nodes.guardrail({"description": "a red bird with a crest"})
        assert out.get("final") is None

    async def test_non_bird_sets_final(self):
        with patch.object(nodes, "_raw_anthropic") as mock_client:
            mock_client.messages.create = AsyncMock(return_value=MagicMock())
            with patch.object(nodes, "_first_text", return_value="NO"):
                out = await nodes.guardrail({"description": "how to cook pasta"})
        assert out["final"]["top_species"] is None
        assert "bird" in out["final"]["message"].lower()

    async def test_guardrail_fails_open(self):
        with patch.object(nodes, "_raw_anthropic") as mock_client:
            mock_client.messages.create = AsyncMock(side_effect=Exception("boom"))
            out = await nodes.guardrail({"description": "anything"})
        assert out.get("final") is None  # fail open -> proceed
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run pytest services/backend/tests/test_graph_nodes.py::TestGuardrailNode -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the guardrail node + shared helpers**

Create `services/backend/app/graph/nodes.py`:

```python
"""Graph nodes: guardrail, resolve_inputs, investigate, ask_user, terminals."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import anthropic
from anthropic.types import TextBlock
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.config import get_stream_writer
from langgraph.types import interrupt

from ..helpers.ebird_client import ebird_client
from ..settings import settings
from . import prompts
from .state import BirdState
from .tools import ALL_TOOLS

logger = logging.getLogger(__name__)

# Raw Anthropic client for the cheap Haiku guardrail + resolve parse.
_raw_anthropic = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, max_retries=1)


def _first_text(message: Any) -> str:
    """First text block of a raw Anthropic message, or ''."""
    return next((b.text for b in message.content if isinstance(b, TextBlock)), "")


def _emit(event: dict[str, Any]) -> None:
    try:
        writer = get_stream_writer()
    except Exception:
        return
    if writer is not None:
        writer(event)


async def guardrail(state: BirdState) -> dict[str, Any]:
    """Cheap Haiku check: is this about birds? Non-bird -> set final (polite bail)."""
    description = state.get("description", "")
    try:
        resp = await _raw_anthropic.messages.create(
            model=prompts.GUARDRAIL_MODEL,
            max_tokens=10,
            messages=[{"role": "user", "content": f"{prompts.GUARDRAIL_PROMPT}\n\n{description}"}],
        )
        text = _first_text(resp) or "YES"
        if "YES" not in text.upper():
            logger.info("Non-bird query rejected", extra={"operation": "graph_guardrail", "status": "rejected"})
            return {"final": dict(prompts.NOT_BIRD_RESPONSE)}
    except Exception as e:  # fail open
        logger.warning(f"Guardrail failed, allowing request: {e}")
    return {"final": None}
```

- [ ] **Step 4: Run to verify it passes**

Run: `poetry run pytest services/backend/tests/test_graph_nodes.py::TestGuardrailNode -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/graph/nodes.py services/backend/tests/test_graph_nodes.py
git commit -m "feat: add graph guardrail node"
```

---

### Task 6: `resolve_inputs` node (region parse + clarify interrupts)

`resolve_inputs` runs a Haiku structured parse of location/time, validates the region code against eBird, and decides whether to interrupt for clarification. Because a node re-runs from its top on resume, the interrupt sits near the top and any user answer flows in as the `interrupt()` return value.

**Files:**
- Modify: `services/backend/app/graph/nodes.py`
- Modify: `services/backend/tests/test_graph_nodes.py`

- [ ] **Step 1: Write the failing tests**

Append to `services/backend/tests/test_graph_nodes.py`:

```python
class TestResolveInputs:
    async def test_resolves_valid_region(self):
        with patch.object(nodes, "_parse_inputs", new=AsyncMock(
            return_value={"region_code": "US-NY", "observed_window": "recent"}
        )), patch.object(nodes, "ebird_client") as eb:
            eb.get_region_info = AsyncMock(return_value={"code": "US-NY"})
            out = await nodes.resolve_inputs(
                {"description": "red bird", "location": "New York", "observed_at": None, "ask_rounds": 0}
            )
        assert out["region"] == "US-NY"
        assert out["observed_window"] == "recent"

    async def test_missing_location_soft_ask_then_skip(self):
        # location empty -> interrupt; user "skips" -> proceed with region=None
        with patch.object(nodes, "interrupt", return_value="skip") as intr, \
             patch.object(nodes, "_parse_inputs", new=AsyncMock(
                 return_value={"region_code": None, "observed_window": "recent"}
             )):
            out = await nodes.resolve_inputs(
                {"description": "red bird", "location": "", "observed_at": None, "ask_rounds": 0}
            )
        intr.assert_called_once()
        assert out["region"] is None
        assert out["ask_rounds"] == 1

    async def test_ask_cap_proceeds_without_asking(self):
        # at the cap, do not interrupt even if region unresolved
        with patch.object(nodes, "interrupt") as intr, \
             patch.object(nodes, "_parse_inputs", new=AsyncMock(
                 return_value={"region_code": None, "observed_window": "recent"}
             )):
            out = await nodes.resolve_inputs(
                {"description": "x", "location": "gibberish", "observed_at": None,
                 "ask_rounds": prompts.MAX_ASK_ROUNDS}
            )
        intr.assert_not_called()
        assert out["region"] is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run pytest services/backend/tests/test_graph_nodes.py::TestResolveInputs -v`
Expected: FAIL — `resolve_inputs` / `_parse_inputs` not defined.

- [ ] **Step 3: Implement `_parse_inputs` + `resolve_inputs`**

Append to `services/backend/app/graph/nodes.py`:

```python
async def _parse_inputs(location: str, observed_at: Optional[str]) -> dict[str, Any]:
    """Haiku structured parse: location/time -> {region_code, observed_window}."""
    try:
        resp = await _raw_anthropic.messages.create(
            model=prompts.RESOLVE_MODEL,
            max_tokens=200,
            system=prompts.RESOLVE_PROMPT,
            messages=[{"role": "user", "content": f"location={location!r} time={observed_at!r}"}],
        )
        raw = _first_text(resp).strip()
        # Tolerate code fences / stray prose around the JSON object.
        start, end = raw.find("{"), raw.rfind("}")
        parsed = json.loads(raw[start : end + 1]) if start != -1 and end != -1 else {}
    except Exception as e:
        logger.warning(f"Input parse failed: {e}", extra={"operation": "resolve_inputs", "status": "error"})
        parsed = {}
    return {
        "region_code": parsed.get("region_code"),
        "observed_window": parsed.get("observed_window") or "recent",
    }


async def resolve_inputs(state: BirdState) -> dict[str, Any]:
    """Resolve location -> region code + observed_window; clarify via interrupt when needed."""
    location = state.get("location", "") or ""
    observed_at = state.get("observed_at")
    ask_rounds = state.get("ask_rounds", 0)

    parsed = await _parse_inputs(location, observed_at)
    region = parsed["region_code"]
    window = parsed["observed_window"]

    # Validate a proposed region against eBird; drop it if unknown.
    if region:
        info = await ebird_client.get_region_info(region)
        if info is None:
            region = None

    answer: Optional[str] = None
    if region is None and ask_rounds < prompts.MAX_ASK_ROUNDS:
        if location.strip():
            # provided but unresolved -> HARD clarify
            payload = {
                "reason": "clarify_location",
                "question": (
                    f"I couldn't pin down “{location}” to a birding region. "
                    "Which country/state (or nearest city) was it?"
                ),
            }
        else:
            # missing -> SOFT clarify (skippable)
            payload = {
                "reason": "clarify_location",
                "question": "Where did you see it? A location helps a lot — or skip and I'll do my best.",
                "options": ["Skip — no location"],
            }
        answer = interrupt(payload)
        ask_rounds += 1
        # Re-parse with the human's answer (unless they skipped).
        if answer and answer.strip().lower() not in {"skip", "skip — no location", "not sure"}:
            reparsed = await _parse_inputs(answer, observed_at)
            region = reparsed["region_code"]
            if region and await ebird_client.get_region_info(region) is None:
                region = None
            window = reparsed["observed_window"]

    # Unparseable date is a soft, low-value ask; for v1 we proceed as "recent"
    # and let the agent ask via ask_user only if season proves decisive (§Q3).
    if window == "unparseable":
        window = "recent"

    context = SystemMessage(
        content=(
            f"Resolved region: {region or 'UNKNOWN (proceed description-only, lower confidence)'}. "
            f"Observation window: {window}. "
            + (
                "Use get_regional_birds for recent presence."
                if window == "recent"
                else f"The sighting was on {window}; prefer date-anchored evidence and reason about seasonality."
            )
        )
    )
    return {
        "region": region,
        "observed_window": window,
        "ask_rounds": ask_rounds,
        "messages": [context],
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `poetry run pytest services/backend/tests/test_graph_nodes.py::TestResolveInputs -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/graph/nodes.py services/backend/tests/test_graph_nodes.py
git commit -m "feat: add resolve_inputs node with region parse + clarify interrupts"
```

---

### Task 7: `investigate` node (ChatAnthropic + thinking + tools)

**Files:**
- Modify: `services/backend/app/graph/nodes.py`
- Modify: `services/backend/tests/test_graph_nodes.py`

- [ ] **Step 1: Write the failing tests**

Append to `services/backend/tests/test_graph_nodes.py`:

```python
class TestInvestigateNode:
    async def test_seeds_system_prompt_and_user_message_first_turn(self):
        fake_model = MagicMock()
        fake_model.ainvoke = AsyncMock(return_value=AIMessage(content="thinking..."))
        with patch.object(nodes, "_agent_model", return_value=fake_model):
            out = await nodes.investigate(
                {"messages": [], "description": "red crested bird", "location": "NY"}
            )
        # The model was called with a SystemMessage seeded first.
        sent = fake_model.ainvoke.call_args.args[0]
        assert isinstance(sent[0], SystemMessage)
        assert any(isinstance(m, HumanMessage) for m in sent)
        # Node returns the AI response to append.
        assert isinstance(out["messages"][0], AIMessage)

    async def test_does_not_reseed_when_messages_exist(self):
        fake_model = MagicMock()
        fake_model.ainvoke = AsyncMock(return_value=AIMessage(content="more"))
        existing = [SystemMessage(content="sys"), HumanMessage(content="hi")]
        with patch.object(nodes, "_agent_model", return_value=fake_model):
            await nodes.investigate({"messages": existing, "description": "x", "location": "y"})
        sent = fake_model.ainvoke.call_args.args[0]
        # No duplicate system seeding: exactly the existing messages are sent.
        assert sent == existing
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run pytest services/backend/tests/test_graph_nodes.py::TestInvestigateNode -v`
Expected: FAIL — `investigate` / `_agent_model` not defined.

- [ ] **Step 3: Implement `_agent_model` + `investigate`**

Append to `services/backend/app/graph/nodes.py`:

```python
_AGENT_MODEL_SINGLETON: Optional[Any] = None


def _agent_model() -> Any:
    """Lazily build the tool-bound, thinking-enabled Sonnet model (cached).

    tool_choice is left at its default (auto): Anthropic forbids forcing tool
    use while extended thinking is enabled.
    """
    global _AGENT_MODEL_SINGLETON
    if _AGENT_MODEL_SINGLETON is None:
        model = ChatAnthropic(
            model=prompts.AGENT_MODEL,
            max_tokens=prompts.AGENT_MAX_TOKENS,
            thinking={"type": "enabled", "budget_tokens": prompts.THINKING_BUDGET_TOKENS},
            api_key=settings.anthropic_api_key,
        )
        _AGENT_MODEL_SINGLETON = model.bind_tools(ALL_TOOLS)
    return _AGENT_MODEL_SINGLETON


async def investigate(state: BirdState) -> dict[str, Any]:
    """The investigative LLM turn. Seeds system + user message on the first turn."""
    messages = list(state.get("messages", []))
    if not messages:
        user = (
            f"I observed a bird...\n\n"
            f"Description: {state.get('description', '')}\n"
            f"Location: {state.get('location', '')}"
        )
        if state.get("observed_at"):
            user += f"\nObserved at: {state['observed_at']}"
        messages = [SystemMessage(content=prompts.SYSTEM_PROMPT), HumanMessage(content=user)]

    response = await _agent_model().ainvoke(messages)
    return {"messages": [response]}
```

> **Note on first-turn seeding:** `resolve_inputs` runs before `investigate` and already appends a `SystemMessage` (the resolved-region context) to state via the `add_messages` reducer. So on the real first `investigate` call, `state["messages"]` is non-empty (it holds that context message) and the `if not messages` branch will NOT fire — meaning the main `SYSTEM_PROMPT` would be missing. To avoid that, seed the main system prompt in the **runner** at graph-entry (Task 11, Step 3 seeds `messages=[SystemMessage(SYSTEM_PROMPT), HumanMessage(user)]` in the initial state). The `if not messages` branch here is a defensive fallback for direct-invoke tests only. Keep both.

- [ ] **Step 4: Run to verify it passes**

Run: `poetry run pytest services/backend/tests/test_graph_nodes.py::TestInvestigateNode -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/graph/nodes.py services/backend/tests/test_graph_nodes.py
git commit -m "feat: add investigate node (ChatAnthropic + thinking + bound tools)"
```

---

### Task 8: `ask_user` node (disambiguation interrupt/resume)

The agent ends a turn by calling the `ask_user` tool. The router sends that to `confidence_gate`, which (if under the ask cap) routes here. This node closes the open `ask_user` tool call with a `ToolMessage`, emits `awaiting_input`, interrupts, and on resume appends the human's answer + increments `ask_rounds`, returning control to `investigate`.

**Files:**
- Modify: `services/backend/app/graph/nodes.py`
- Modify: `services/backend/tests/test_graph_nodes.py`

- [ ] **Step 1: Write the failing tests**

Append to `services/backend/tests/test_graph_nodes.py`:

```python
def _ai_with_tool_call(name, args, call_id="call_1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


class TestAskUserNode:
    async def test_closes_tool_call_and_appends_answer(self):
        ai = _ai_with_tool_call(
            "ask_user", {"reason": "disambiguate_species", "question": "Crest or no crest?"}
        )
        with patch.object(nodes, "interrupt", return_value="It had a crest"):
            out = await nodes.ask_user({"messages": [ai], "ask_rounds": 0})
        kinds = [type(m).__name__ for m in out["messages"]]
        assert "ToolMessage" in kinds   # the ask_user tool call is closed
        assert "HumanMessage" in kinds  # the user's answer is appended
        assert out["ask_rounds"] == 1
        human = next(m for m in out["messages"] if isinstance(m, HumanMessage))
        assert "crest" in human.content.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run pytest services/backend/tests/test_graph_nodes.py::TestAskUserNode -v`
Expected: FAIL — `ask_user` not defined.

- [ ] **Step 3: Implement `ask_user`**

Append to `services/backend/app/graph/nodes.py`:

```python
def _last_terminal_tool_call(messages: list[Any]) -> Optional[dict[str, Any]]:
    """The first tool_call on the last AIMessage, if it's an AIMessage with calls."""
    if not messages:
        return None
    last = messages[-1]
    calls = getattr(last, "tool_calls", None)
    if calls:
        return calls[0]
    return None


async def ask_user(state: BirdState) -> dict[str, Any]:
    """Disambiguation HITL: close the ask_user tool call, interrupt, resume w/ answer."""
    messages = state.get("messages", [])
    call = _last_terminal_tool_call(messages) or {}
    call_id = call.get("id", "ask_user")
    args = call.get("args", {})

    payload = {
        "reason": args.get("reason", "disambiguate_species"),
        "question": args.get("question", "Could you tell me one more distinguishing detail?"),
    }
    if args.get("options"):
        payload["options"] = args["options"]

    # Close the open tool call so the transcript stays valid for Anthropic.
    closing = ToolMessage(content="asked", tool_call_id=call_id)

    answer = interrupt(payload)  # JSON-serializable payload; resumes with the user's reply

    return {
        "messages": [closing, HumanMessage(content=str(answer))],
        "ask_rounds": state.get("ask_rounds", 0) + 1,
    }
```

> **Re-run-on-resume note:** the `closing` ToolMessage and the `interrupt()` call both sit after light setup; LangGraph re-runs the node body from the top on resume, so the `ToolMessage`/`HumanMessage` are produced once (after the interrupt returns). Do not add side effects before `interrupt()`.

- [ ] **Step 4: Run to verify it passes**

Run: `poetry run pytest services/backend/tests/test_graph_nodes.py::TestAskUserNode -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/graph/nodes.py services/backend/tests/test_graph_nodes.py
git commit -m "feat: add ask_user disambiguation node (interrupt/resume)"
```

---

### Task 9: terminal nodes — `submit_id` + `inconclusive`

Both read the agent's terminal tool-call args and write `state["final"]` in the `RecommendationResponse`-compatible shape the route already consumes.

**Files:**
- Modify: `services/backend/app/graph/nodes.py`
- Modify: `services/backend/tests/test_graph_nodes.py`

- [ ] **Step 1: Write the failing tests**

Append to `services/backend/tests/test_graph_nodes.py`:

```python
class TestTerminalNodes:
    async def test_submit_id_maps_args_to_final(self):
        ai = _ai_with_tool_call(
            "submit_identification",
            {
                "message": "It's a Northern Cardinal.",
                "top_species": {
                    "scientific_name": "Cardinalis cardinalis",
                    "common_name": "Northern Cardinal",
                    "species_code": "norcar",
                    "confidence": "high",
                    "reasoning": "red + crest + common",
                },
                "alternate_species": [],
                "clarification": None,
            },
        )
        out = await nodes.submit_id({"messages": [ai]})
        assert out["final"]["top_species"]["common_name"] == "Northern Cardinal"
        assert out["final"]["alternate_species"] == []

    async def test_inconclusive_maps_args_to_final(self):
        ai = _ai_with_tool_call(
            "inconclusive",
            {
                "message": "I can't be sure.",
                "closest_guesses": [{"common_name": "Some Sparrow", "species_code": "x"}],
                "what_would_help": "A photo of the tail.",
            },
        )
        out = await nodes.inconclusive({"messages": [ai]})
        assert out["final"]["top_species"] is None
        assert "what_would_help" not in out["final"]  # folded into clarification/message
        assert "tail" in (out["final"]["clarification"] or "").lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run pytest services/backend/tests/test_graph_nodes.py::TestTerminalNodes -v`
Expected: FAIL — `submit_id` / `inconclusive` not defined.

- [ ] **Step 3: Implement both terminal nodes**

Append to `services/backend/app/graph/nodes.py`:

```python
async def submit_id(state: BirdState) -> dict[str, Any]:
    """Terminal: map submit_identification args into the final response payload."""
    call = _last_terminal_tool_call(state.get("messages", [])) or {}
    args = call.get("args", {})
    final = {
        "message": args.get("message", ""),
        "top_species": args.get("top_species"),
        "alternate_species": args.get("alternate_species") or [],
        "clarification": args.get("clarification"),
    }
    return {"final": final}


async def inconclusive(state: BirdState) -> dict[str, Any]:
    """Terminal: honest "can't identify" — closest guesses + what would help."""
    call = _last_terminal_tool_call(state.get("messages", [])) or {}
    args = call.get("args", {})
    final = {
        "message": args.get("message", prompts.FALLBACK_RESPONSE["message"]),
        "top_species": None,
        # Surface closest guesses as alternates so the existing card renders them.
        "alternate_species": args.get("closest_guesses") or [],
        "clarification": args.get("what_would_help"),
    }
    return {"final": final}
```

- [ ] **Step 4: Run to verify it passes**

Run: `poetry run pytest services/backend/tests/test_graph_nodes.py::TestTerminalNodes -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/graph/nodes.py services/backend/tests/test_graph_nodes.py
git commit -m "feat: add submit_id + inconclusive terminal nodes"
```

---

## Phase 5 — Routing & guards

### Task 10: `graph/routing.py` — router + confidence_gate guards

**Files:**
- Create: `services/backend/app/graph/routing.py`
- Create: `services/backend/tests/test_graph_routing.py`

- [ ] **Step 1: Write the failing tests**

Create `services/backend/tests/test_graph_routing.py`:

```python
"""Tests for the post-investigate router and confidence_gate guards."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from services.backend.app.graph import routing


def _ai(name=None, args=None, call_id="c1"):
    if name is None:
        return AIMessage(content="just text, no tools")
    return AIMessage(content="", tool_calls=[{"name": name, "args": args or {}, "id": call_id}])


def _tool_result(name, call_id="c1"):
    # ToolMessage carries the tool name so guard-scans can see prior data calls.
    return ToolMessage(content="{}", name=name, tool_call_id=call_id)


class TestRouteAfterInvestigate:
    def test_data_tool_routes_to_tools(self):
        state = {"messages": [_ai("get_regional_birds", {"region": "US-NY"})], "ask_rounds": 0}
        assert routing.route_after_investigate(state) == "tools"

    def test_trace_tool_routes_to_tools(self):
        state = {"messages": [_ai("detective_note", {"message": "hm"})], "ask_rounds": 0}
        assert routing.route_after_investigate(state) == "tools"

    def test_no_tool_call_routes_to_inconclusive(self):
        state = {"messages": [_ai()], "ask_rounds": 0}
        assert routing.route_after_investigate(state) == "inconclusive"

    def test_submit_without_presence_bounces_to_investigate(self):
        state = {"messages": [_ai("submit_identification", {"top_species": None, "alternate_species": []})], "ask_rounds": 0}
        # presence guard unmet -> back to investigate
        assert routing.route_after_investigate(state) == "investigate"

    def test_submit_with_presence_routes_to_submit(self):
        msgs = [
            _ai("get_regional_birds", {"region": "US-NY"}, call_id="c0"),
            _tool_result("get_regional_birds", call_id="c0"),
            _ai("submit_identification",
                {"top_species": {"species_code": "norcar", "confidence": "medium"}, "alternate_species": []},
                call_id="c1"),
        ]
        assert routing.route_after_investigate({"messages": msgs, "ask_rounds": 0}) == "submit_id"

    def test_high_confidence_without_frequency_bounces(self):
        msgs = [
            _ai("get_regional_birds", {"region": "US-NY"}, call_id="c0"),
            _tool_result("get_regional_birds", call_id="c0"),
            _ai("submit_identification",
                {"top_species": {"species_code": "norcar", "confidence": "high"}, "alternate_species": []},
                call_id="c1"),
        ]
        # presence met, but no frequency check for norcar -> bounce
        assert routing.route_after_investigate({"messages": msgs, "ask_rounds": 0}) == "investigate"

    def test_high_confidence_with_frequency_routes_to_submit(self):
        msgs = [
            _ai("get_regional_birds", {"region": "US-NY"}, call_id="c0"),
            _tool_result("get_regional_birds", call_id="c0"),
            _ai("get_species_frequency", {"region": "US-NY", "species_code": "norcar"}, call_id="c1"),
            _tool_result("get_species_frequency", call_id="c1"),
            _ai("submit_identification",
                {"top_species": {"species_code": "norcar", "confidence": "high"}, "alternate_species": []},
                call_id="c2"),
        ]
        assert routing.route_after_investigate({"messages": msgs, "ask_rounds": 0}) == "submit_id"

    def test_ask_user_under_cap_routes_to_ask(self):
        state = {"messages": [_ai("ask_user", {"question": "crest?"})], "ask_rounds": 0}
        assert routing.route_after_investigate(state) == "ask_user"

    def test_ask_user_at_cap_routes_to_inconclusive(self):
        state = {"messages": [_ai("ask_user", {"question": "crest?"})], "ask_rounds": 2}
        assert routing.route_after_investigate(state) == "inconclusive"

    def test_data_budget_exhausted_forces_terminal(self):
        # 12 data calls already; another data-tool call is forced to inconclusive
        msgs = []
        for i in range(routing.MAX_DATA_TOOL_CALLS):
            msgs.append(_ai("get_regional_birds", {"region": "US-NY"}, call_id=f"c{i}"))
            msgs.append(_tool_result("get_regional_birds", call_id=f"c{i}"))
        msgs.append(_ai("get_regional_birds", {"region": "US-NY"}, call_id="cX"))
        assert routing.route_after_investigate({"messages": msgs, "ask_rounds": 0}) == "inconclusive"
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run pytest services/backend/tests/test_graph_routing.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `routing.py`**

Create `services/backend/app/graph/routing.py`:

```python
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
from the investigate-bounce path in build.py — see Task 11).
"""

from __future__ import annotations

from typing import Any, Optional

from langchain_core.messages import AIMessage, ToolMessage

from .prompts import MAX_ASK_ROUNDS, MAX_DATA_TOOL_CALLS
from .tools import DATA_TOOL_NAMES, TERMINAL_TOOL_NAMES, TRACE_TOOL_NAMES

# Re-export for tests / build.py
__all__ = ["route_after_investigate", "MAX_DATA_TOOL_CALLS", "guard_feedback_message"]


def _data_tool_calls_so_far(messages: list[Any]) -> int:
    """Count completed data-tool calls (by their ToolMessage results)."""
    return sum(1 for m in messages if isinstance(m, ToolMessage) and getattr(m, "name", None) in DATA_TOOL_NAMES)


def _called_tool(messages: list[Any], name: str) -> bool:
    return any(isinstance(m, ToolMessage) and getattr(m, "name", None) == name for m in messages)


def _frequency_checked_for(messages: list[Any], species_code: str) -> bool:
    """Did a get_species_frequency call target this species_code?"""
    for m in messages:
        if isinstance(m, AIMessage):
            for call in getattr(m, "tool_calls", []) or []:
                if call.get("name") == "get_species_frequency" and call.get("args", {}).get("species_code") == species_code:
                    return True
    return False


def _last_tool_call(messages: list[Any]) -> Optional[dict[str, Any]]:
    if not messages:
        return None
    last = messages[-1]
    calls = getattr(last, "tool_calls", None) if isinstance(last, AIMessage) else None
    return calls[0] if calls else None


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
        args = call.get("args", {})
        # Guard 1: presence before concluding.
        if not (_called_tool(messages, "get_regional_birds") or _called_tool(messages, "get_historic_birds")):
            return "investigate"
        # Guard 2: frequency before HIGH confidence.
        top = args.get("top_species") or {}
        if top.get("confidence") == "high":
            code = top.get("species_code", "")
            if not code or not _frequency_checked_for(messages, code):
                return "investigate"
        return "submit_id"

    # Unknown tool name -> conclude honestly rather than loop.
    return "inconclusive"
```

> **Note on `get_historic_birds`:** Plan 1 added `ebird_client.get_historic_birds` but Task 4 did **not** wrap it as an agent tool (the agent uses `get_regional_birds` for recent presence in v1; date-anchoring is guidance-driven). The presence guard checks for it anyway so that a future historic tool satisfies the guard without a routing change. This is intentional forward-compatibility, not dead logic.

- [ ] **Step 4: Run to verify it passes**

Run: `poetry run pytest services/backend/tests/test_graph_routing.py -v`
Expected: PASS (10 tests).

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/graph/routing.py services/backend/tests/test_graph_routing.py
git commit -m "feat: add post-investigate router with grounding guards"
```

---

## Phase 6 — Graph wiring

### Task 11: `graph/build.py` — assemble + compile the StateGraph

When the router bounces a failed-guard `submit_identification` back to `investigate`, the open terminal tool call must be closed with a corrective `ToolMessage` first (Anthropic requires a `tool_result` for every `tool_use`). We do that in a tiny `gate_feedback` node inserted on the bounce path: `investigate → (route) → gate_feedback → investigate`. To keep the router pure (it returns node names), `build.py` maps the router's `"investigate"` result to the `gate_feedback` node.

**Files:**
- Create: `services/backend/app/graph/build.py`
- Modify: `services/backend/app/graph/__init__.py`
- Create: `services/backend/tests/test_graph_build.py`

- [ ] **Step 1: Write the failing tests**

Create `services/backend/tests/test_graph_build.py`:

```python
"""Integration tests: compiled graph drives happy-path and interrupt-path."""

from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage

from services.backend.app.graph import build


def _ai_tool(name, args, call_id="c1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


class TestCompiledGraph:
    async def test_non_bird_short_circuits_to_final(self):
        graph = build.build_graph()
        with patch("services.backend.app.graph.nodes._first_text", return_value="NO"), \
             patch.object(build_nodes := __import__(
                 "services.backend.app.graph.nodes", fromlist=["_raw_anthropic"]
             ), "_raw_anthropic") as raw:
            raw.messages.create = AsyncMock(return_value=MagicMock())
            state = await graph.ainvoke(
                {"description": "cook pasta", "location": "", "observed_at": None,
                 "messages": [], "ask_rounds": 0, "final": None},
                config={"configurable": {"thread_id": "t-nonbird"}},
            )
        assert state["final"]["top_species"] is None

    async def test_happy_path_reaches_submit(self):
        """guardrail YES -> resolve -> investigate(regional) -> tools -> investigate(submit)."""
        graph = build.build_graph()

        # Scripted agent: first call data tool, then submit (medium confidence).
        calls = [
            _ai_tool("get_regional_birds", {"region": "US-NY"}, "c0"),
            _ai_tool(
                "submit_identification",
                {"message": "It's a cardinal.",
                 "top_species": {"scientific_name": "Cardinalis cardinalis", "common_name": "Northern Cardinal",
                                 "species_code": "norcar", "confidence": "medium", "reasoning": "red + crest"},
                 "alternate_species": []},
                "c1",
            ),
        ]
        fake_model = MagicMock()
        fake_model.ainvoke = AsyncMock(side_effect=calls)

        import services.backend.app.graph.nodes as N

        with patch.object(N, "_first_text", return_value="YES"), \
             patch.object(N, "_raw_anthropic") as raw, \
             patch.object(N, "_parse_inputs", new=AsyncMock(
                 return_value={"region_code": "US-NY", "observed_window": "recent"})), \
             patch.object(N, "ebird_client") as eb, \
             patch.object(N, "_agent_model", return_value=fake_model), \
             patch("services.backend.app.graph.tools.ebird_client") as teb:
            raw.messages.create = AsyncMock(return_value=MagicMock())
            eb.get_region_info = AsyncMock(return_value={"code": "US-NY"})
            teb.get_regional_birds = AsyncMock(return_value={"region": "US-NY", "species_observed": [{"common_name": "Northern Cardinal"}]})

            state = await graph.ainvoke(
                {"description": "red crested bird", "location": "New York", "observed_at": None,
                 "messages": [], "ask_rounds": 0, "final": None},
                config={"configurable": {"thread_id": "t-happy"}},
            )

        assert state["final"]["top_species"]["common_name"] == "Northern Cardinal"
```

> If wiring details (node names) make the `__import__` patch awkward, simplify to `import services.backend.app.graph.nodes as N` and patch on `N` (as the happy-path test does). Both tests must pass.

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run pytest services/backend/tests/test_graph_build.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `build.py`**

Create `services/backend/app/graph/build.py`:

```python
"""Assemble and compile the bird-ID StateGraph."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from . import nodes, routing
from .state import BirdState
from .tools import EXECUTABLE_TOOLS

# Router result -> actual destination node. "investigate" bounce goes via the
# gate_feedback node so the open terminal tool call gets a closing ToolMessage.
_ROUTE_MAP = {
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
    # Recompute which guard failed to phrase the feedback.
    args = call.get("args", {})
    if not (routing._called_tool(messages, "get_regional_birds") or routing._called_tool(messages, "get_historic_birds")):
        reason = "presence"
    elif (args.get("top_species") or {}).get("confidence") == "high":
        reason = "frequency"
    else:
        reason = "presence"
    return {"messages": [ToolMessage(content=routing.guard_feedback_message(reason), tool_call_id=call_id)]}


def build_graph() -> Any:
    """Build + compile the graph with an in-memory checkpointer."""
    builder = StateGraph(BirdState)

    builder.add_node("guardrail", nodes.guardrail)
    builder.add_node("resolve_inputs", nodes.resolve_inputs)
    builder.add_node("investigate", nodes.investigate)
    builder.add_node("tools", ToolNode(EXECUTABLE_TOOLS))
    builder.add_node("gate_feedback", gate_feedback)
    builder.add_node("ask_user", nodes.ask_user)
    builder.add_node("submit_id", nodes.submit_id)
    builder.add_node("inconclusive", nodes.inconclusive)

    builder.add_edge(START, "guardrail")
    builder.add_conditional_edges("guardrail", _route_from_guardrail, {END: END, "resolve_inputs": "resolve_inputs"})
    builder.add_edge("resolve_inputs", "investigate")
    builder.add_conditional_edges("investigate", routing.route_after_investigate, _ROUTE_MAP)
    builder.add_edge("tools", "investigate")
    builder.add_edge("gate_feedback", "investigate")
    builder.add_edge("ask_user", "investigate")
    builder.add_edge("submit_id", END)
    builder.add_edge("inconclusive", END)

    return builder.compile(checkpointer=InMemorySaver())


# Module singleton — one compiled graph (one shared InMemorySaver) per process.
bird_graph = build_graph()
```

- [ ] **Step 4: Update the package exports**

Replace `services/backend/app/graph/__init__.py` with:

```python
"""LangGraph-based bird identification graph package."""

from .build import bird_graph, build_graph
from .state import session_store

__all__ = ["bird_graph", "build_graph", "session_store"]
```

- [ ] **Step 5: Run to verify it passes**

Run: `poetry run pytest services/backend/tests/test_graph_build.py -v`
Expected: PASS (2 tests). If the `__import__` patch in the non-bird test is awkward, rewrite it to `import services.backend.app.graph.nodes as N` + `patch.object(N, ...)` and keep the assertion.

- [ ] **Step 6: Commit**

```bash
git add services/backend/app/graph/build.py services/backend/app/graph/__init__.py services/backend/tests/test_graph_build.py
git commit -m "feat: assemble + compile bird-ID StateGraph with guard bounce path"
```

---

## Phase 7 — Runner & sessions

### Task 12: `graph/runner.py` — stream/resume → SSE event dicts

The runner translates LangGraph's multi-mode `astream` into the event dicts the route already understands. Modes: `custom` (UI events from tool bodies — passed through verbatim), `messages` (thinking/text token deltas → `thinking` events), `updates` (watch for `__interrupt__` → `awaiting_input`). After the stream ends without an interrupt, it reads `state["final"]` and emits a `result` event.

**Files:**
- Create: `services/backend/app/graph/runner.py`
- Create: `services/backend/tests/test_graph_runner.py`

- [ ] **Step 1: Write the failing tests**

Create `services/backend/tests/test_graph_runner.py`:

```python
"""Tests for the SSE runner that adapts graph astream output."""

from unittest.mock import AsyncMock, MagicMock, patch

from services.backend.app.graph.runner import BirdGraphRunner


async def _aiter(items):
    for it in items:
        yield it


class TestRunnerTranslation:
    async def test_emits_session_id_first_then_custom_and_result(self):
        # Scripted astream: a custom UI event, a thinking token, then it ends.
        fake_graph = MagicMock()
        fake_graph.astream = MagicMock(return_value=_aiter([
            ("custom", {"type": "detective_note", "message": "Hmm."}),
            ("messages", (MagicMock(content="thinking", tool_call_chunks=[]), {"langgraph_node": "investigate"})),
            ("updates", {"submit_id": {"final": {"message": "done", "top_species": None, "alternate_species": []}}}),
        ]))
        # get_state returns the final payload after streaming.
        snap = MagicMock()
        snap.next = ()
        snap.values = {"final": {"message": "done", "top_species": None, "alternate_species": []}}
        fake_graph.aget_state = AsyncMock(return_value=snap)

        runner = BirdGraphRunner(graph=fake_graph)
        events = [e async for e in runner.run_stream(
            session_id="s1", description="red bird", location="NY", observed_at=None
        )]

        types = [e["type"] for e in events]
        assert types[0] == "session_id"
        assert events[0]["session_id"] == "s1"
        assert "detective_note" in types
        assert "result" in types

    async def test_interrupt_emits_awaiting_input_and_no_result(self):
        fake_graph = MagicMock()
        fake_graph.astream = MagicMock(return_value=_aiter([
            ("updates", {"__interrupt__": (MagicMock(value={"reason": "disambiguate_species", "question": "crest?"}),)}),
        ]))
        snap = MagicMock()
        snap.next = ("ask_user",)  # paused
        fake_graph.aget_state = AsyncMock(return_value=snap)

        runner = BirdGraphRunner(graph=fake_graph)
        events = [e async for e in runner.run_stream(
            session_id="s2", description="bird", location="NY", observed_at=None
        )]
        types = [e["type"] for e in events]
        assert "awaiting_input" in types
        assert "result" not in types
        aw = next(e for e in events if e["type"] == "awaiting_input")
        assert aw["reason"] == "disambiguate_species"
        assert aw["question"] == "crest?"
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run pytest services/backend/tests/test_graph_runner.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `runner.py`**

Create `services/backend/app/graph/runner.py`:

```python
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
        return {"configurable": {"thread_id": session_id}}

    async def _drive(self, session_id: str, graph_input: Any) -> AsyncIterator[dict[str, Any]]:
        """Shared streaming core for both fresh runs and resumes."""
        config = self._config(session_id)
        interrupted = False
        try:
            async for mode, chunk in self._graph.astream(graph_input, config, stream_mode=_STREAM_MODES):
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
                        yield {
                            "type": "awaiting_input",
                            "reason": payload.get("reason", "clarify"),
                            "question": payload.get("question", ""),
                            **({"options": payload["options"]} if payload.get("options") else {}),
                        }

            if not interrupted:
                snap = await self._graph.aget_state(config)
                final = (snap.values or {}).get("final") if snap else None
                yield {"type": "result", "data": final or dict(prompts.FALLBACK_RESPONSE)}
        except Exception as e:
            logger.error(
                f"Graph run failed: {e}",
                extra={"operation": "graph_runner", "status": "error", "error_type": type(e).__name__},
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

        # Seed the main system prompt + user message so investigate's first turn
        # has full context even though resolve_inputs prepends its own context msg.
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

    async def resume_stream(self, session_id: str, user_message: str) -> AsyncIterator[dict[str, Any]]:
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `poetry run pytest services/backend/tests/test_graph_runner.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/graph/runner.py services/backend/tests/test_graph_runner.py
git commit -m "feat: add BirdGraphRunner translating astream to SSE events"
```

---

## Phase 8 — Schemas & routes

### Task 13: schemas — `ResumeInput`

**Files:**
- Modify: `services/backend/app/schemas/observation.py`
- Create: `services/backend/tests/test_schemas_resume.py`

- [ ] **Step 1: Write the failing test**

Create `services/backend/tests/test_schemas_resume.py`:

```python
import pytest
from pydantic import ValidationError

from services.backend.app.schemas.observation import ResumeInput


def test_resume_input_valid():
    r = ResumeInput(session_id="abc123", user_message="It had a crest")
    assert r.session_id == "abc123"
    assert r.user_message == "It had a crest"


def test_resume_input_requires_fields():
    with pytest.raises(ValidationError):
        ResumeInput(session_id="abc123")  # missing user_message
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run pytest services/backend/tests/test_schemas_resume.py -v`
Expected: FAIL — `ResumeInput` not defined.

- [ ] **Step 3: Add the schema**

Append to `services/backend/app/schemas/observation.py` (after `ObservationInput`):

```python
class ResumeInput(BaseModel):
    """Turn 2+ payload: resume a paused identification session with a reply."""

    session_id: str = Field(..., min_length=1, description="Session id from turn 1")
    user_message: str = Field(..., min_length=1, description="The user's answer to the pending question")
```

- [ ] **Step 4: Run to verify it passes**

Run: `poetry run pytest services/backend/tests/test_schemas_resume.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/schemas/observation.py services/backend/tests/test_schemas_resume.py
git commit -m "feat: add ResumeInput schema for session resume"
```

---

### Task 14: routes — switch to the runner + add `/resume`

The streaming route's `event_generator` keeps its existing image-resolution logic (intercept `candidates` + `result`), and gains `session_id`/`awaiting_input` pass-through. The non-streaming `POST /api/identify` is rebuilt on the runner (consume the stream, return the final). A new `POST /api/identify/resume` resumes a session.

**Files:**
- Modify: `services/backend/app/routes/identify.py`
- Create: `services/backend/tests/test_identify_routes.py`

- [ ] **Step 1: Write the failing tests**

Create `services/backend/tests/test_identify_routes.py`:

```python
"""Route-level tests for the graph-backed identify endpoints."""

import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from services.backend.app.main import app

client = TestClient(app)


async def _events(items):
    for it in items:
        yield it


def _parse_sse(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        if line.startswith("data: "):
            out.append(json.loads(line[len("data: ") :]))
    return out


class TestStreamRoute:
    def test_stream_passes_through_session_and_awaiting(self):
        scripted = [
            {"type": "session_id", "session_id": "s1"},
            {"type": "awaiting_input", "reason": "disambiguate_species", "question": "Crest?"},
        ]
        with patch("services.backend.app.routes.identify.bird_runner") as runner:
            runner.run_stream = lambda **kw: _events(scripted)
            resp = client.post(
                "/api/identify/stream",
                json={"description": "red bird", "location": "NY"},
            )
        events = _parse_sse(resp.text)
        types = [e["type"] for e in events]
        assert "session_id" in types
        assert "awaiting_input" in types
        assert types[-1] == "done"


class TestResumeRoute:
    def test_resume_streams_events(self):
        scripted = [
            {"type": "session_id", "session_id": "s1"},
            {"type": "result", "data": {"message": "It's a cardinal", "top_species": None, "alternate_species": []}},
        ]
        with patch("services.backend.app.routes.identify.bird_runner") as runner:
            runner.resume_stream = lambda **kw: _events(scripted)
            resp = client.post(
                "/api/identify/resume",
                json={"session_id": "s1", "user_message": "it had a crest"},
            )
        events = _parse_sse(resp.text)
        types = [e["type"] for e in events]
        assert "result" in types
        assert types[-1] == "done"
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run pytest services/backend/tests/test_identify_routes.py -v`
Expected: FAIL — `/api/identify/resume` 404 and/or `bird_runner` not importable from the route module.

- [ ] **Step 3: Rewrite `identify.py`**

Replace the imports and the two route bodies. Keep `_build_species_info` unchanged. The full new file:

```python
"""Bird identification endpoints (LangGraph-backed, turn-based)."""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from urllib.parse import quote_plus

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..graph import session_store
from ..graph.runner import bird_runner
from ..helpers.ebird_client import ebird_client
from ..schemas.observation import (
    ObservationInput,
    RecommendationResponse,
    ResumeInput,
    SpeciesInfo,
)

logger = logging.getLogger(__name__)

IDENTIFY_TIMEOUT = 60.0

router = APIRouter(prefix="/api", tags=["identification"])


async def _build_species_info(data: dict) -> SpeciesInfo:
    """Build SpeciesInfo from an agent species dict, fetching its image."""
    common_name = data.get("common_name", "Unknown")
    species_code = data.get("species_code", "")

    image_url = None
    image_credit = None
    if species_code:
        image_data = await ebird_client.get_species_image(species_code)
        if image_data:
            image_url = image_data.get("image_url")
            image_credit = image_data.get("photographer")

    return SpeciesInfo(
        scientific_name=data.get("scientific_name", "Unknown"),
        common_name=common_name,
        range_link=f"https://ebird.org/explore?q={quote_plus(common_name)}",
        confidence=data.get("confidence"),
        reasoning=data.get("reasoning"),
        image_url=image_url,
        image_credit=image_credit,
    )


async def _build_response(agent_data: dict) -> RecommendationResponse:
    """Resolve images for top + alternates and assemble the response."""
    image_tasks = []
    if agent_data.get("top_species"):
        image_tasks.append(_build_species_info(agent_data["top_species"]))
    for alt in agent_data.get("alternate_species", []):
        image_tasks.append(_build_species_info(alt))

    built = await asyncio.gather(*image_tasks) if image_tasks else []
    if agent_data.get("top_species") and built:
        top_species = built[0]
        alternate_species = list(built[1:])
    else:
        top_species = None
        alternate_species = list(built)

    return RecommendationResponse(
        message=agent_data.get("message", ""),
        top_species=top_species,
        alternate_species=alternate_species,
        clarification=agent_data.get("clarification"),
    )


async def _sse_from_runner(events: AsyncIterator[dict], request_start: float) -> AsyncIterator[str]:
    """Shared SSE adapter: resolve images for candidates/result, pass others through."""
    start_time = time.time()
    try:
        async for event in events:
            if time.time() - start_time > IDENTIFY_TIMEOUT:
                yield f'data: {json.dumps({"type": "error", "message": "Request timed out. Please try again."})}\n\n'
                yield f'data: {json.dumps({"type": "done"})}\n\n'
                return

            etype = event.get("type")
            if etype == "candidates":
                candidates = event["data"]

                async def resolve_image(candidate: dict) -> dict:
                    if candidate.get("status") == "considering" and candidate.get("species_code"):
                        img = await ebird_client.get_species_image(candidate["species_code"])
                        if img:
                            candidate["image_url"] = img["image_url"]
                            candidate["image_credit"] = img.get("photographer")
                    return candidate

                event["data"] = list(await asyncio.gather(*[resolve_image(c) for c in candidates]))
                yield f"data: {json.dumps(event)}\n\n"
            elif etype == "result":
                yield f'data: {json.dumps({"type": "status", "message": "Fetching photos..."})}\n\n'
                response = await _build_response(event["data"])
                yield f'data: {json.dumps({"type": "result", "data": response.model_dump()})}\n\n'
            else:
                yield f"data: {json.dumps(event)}\n\n"

        yield f'data: {json.dumps({"type": "done"})}\n\n'
    except Exception as e:
        logger.error(
            f"Streaming identification failed: {e}",
            exc_info=True,
            extra={"operation": "identify_sse", "total_latency_ms": round((time.time() - request_start) * 1000, 2), "status": "error"},
        )
        yield f'data: {json.dumps({"type": "error", "message": "An unexpected error occurred. Please try again."})}\n\n'
        yield f'data: {json.dumps({"type": "done"})}\n\n'


@router.post("/identify", response_model=RecommendationResponse)
async def identify_bird(observation: ObservationInput) -> RecommendationResponse:
    """Non-streaming identify: run the graph to completion and return the final."""
    request_start = time.time()
    session_id = session_store.create()
    try:
        final: dict | None = None
        async def _run():
            nonlocal final
            async for event in bird_runner.run_stream(
                session_id=session_id,
                description=observation.description,
                location=observation.location,
                observed_at=observation.observed_at,
            ):
                if event["type"] == "result":
                    final = event["data"]
                elif event["type"] == "awaiting_input":
                    # Non-streaming endpoint can't do turn-taking; degrade to a clarification.
                    final = {
                        "message": event.get("question", "Could you tell me more?"),
                        "top_species": None,
                        "alternate_species": [],
                        "clarification": event.get("question"),
                    }
                    return

        await asyncio.wait_for(_run(), timeout=IDENTIFY_TIMEOUT)
        if final is None:
            raise HTTPException(status_code=500, detail="No result produced.")
        return await _build_response(final)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail=f"Request timed out after {IDENTIFY_TIMEOUT} seconds.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Identification failed: {e}", exc_info=True, extra={"operation": "identify_bird", "status": "error"})
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.post("/identify/stream")
async def identify_bird_stream(observation: ObservationInput):
    """Turn 1: stream a fresh identification (SSE), creating a session."""
    request_start = time.time()
    session_id = session_store.create()
    events = bird_runner.run_stream(
        session_id=session_id,
        description=observation.description,
        location=observation.location,
        observed_at=observation.observed_at,
    )
    return StreamingResponse(
        _sse_from_runner(events, request_start),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.post("/identify/resume")
async def identify_bird_resume(payload: ResumeInput):
    """Turn 2+: resume a paused session with the user's reply (SSE)."""
    request_start = time.time()
    events = bird_runner.resume_stream(session_id=payload.session_id, user_message=payload.user_message)
    return StreamingResponse(
        _sse_from_runner(events, request_start),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `poetry run pytest services/backend/tests/test_identify_routes.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/routes/identify.py services/backend/tests/test_identify_routes.py
git commit -m "feat: graph-backed identify routes + /identify/resume endpoint"
```

---

## Phase 9 — Cleanup & docs

### Task 15: Remove the old agent + reconcile the suite

**Files:**
- Delete: `services/backend/app/helpers/bird_agent.py`
- Delete: `services/backend/tests/test_bird_agent.py`
- Modify: any remaining importers of `bird_agent`

- [ ] **Step 1: Find remaining references**

Run: `grep -rn "bird_agent" services/backend/app`
Expected: only `routes/identify.py` historically — which Task 14 already migrated. If any other file imports `bird_agent`, migrate it to `graph.runner.bird_runner` / `graph.prompts` before deleting.

- [ ] **Step 2: Delete the obsolete module + its tests**

```bash
git rm services/backend/app/helpers/bird_agent.py services/backend/tests/test_bird_agent.py
```

> `bird_agent.py` is fully superseded: the guardrail moved to `nodes.guardrail`, the loop to the graph, the prompts/constants to `graph/prompts.py`, and tool execution to `graph/tools.py` + `ToolNode`. Its tests covered helpers that no longer exist; equivalent behavior is covered by `test_graph_nodes.py`, `test_graph_tools.py`, `test_graph_routing.py`, and `test_graph_build.py`.

- [ ] **Step 3: Run the FULL backend suite + lint/type checks**

```bash
poetry run pytest services/backend/tests/ -v
poetry run ruff check services/
poetry run black --check services/
poetry run mypy services/backend/app --ignore-missing-imports
```
Expected: all green. Common fixups:
- `mypy`: LangGraph/LangChain return `Any` in places — add `# type: ignore[...]` narrowly or annotate, but do NOT add blanket ignores. The graph singleton typed as `Any` is acceptable.
- `ruff`: unused imports after the deletion (e.g. stale `TextBlock`/`ToolUseBlock`) — remove them.
- If `black` reformats, run `poetry run black services/` and amend.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: remove superseded bird_agent.py (replaced by graph package)"
```

---

### Task 16: Update architecture docs

**Files:**
- Modify: `CLAUDE.md` (Architecture section)
- Modify: `docs/vision.md` (if it documents the request flow)

- [ ] **Step 1: Update `CLAUDE.md`**

In the **Architecture** section of `CLAUDE.md`, replace the "Request flow (agentic, stateless)" block with a turn-based LangGraph description. Use this text:

```markdown
**Request flow (LangGraph, turn-based sessions):**
```
React SPA → FastAPI POST /api/identify/stream → guardrail node (Haiku)
  → resolve_inputs (Haiku region/date parse, eBird-validated; may ask via interrupt)
  → investigate (Claude Sonnet + extended thinking) ⇄ tools (ToolNode)
       ├── get_regional_birds / get_species_frequency / get_regional_rarities
       ├── lookup_family            ← direct httpx → eBird / Macaulay
       └── web_search               ← Tavily API
  → confidence_gate (grounding guards) → { submit_id | ask_user | inconclusive }
  → SSE stream → (on ask_user) POST /api/identify/resume with {session_id, user_message}
```

- Stateful per session: an in-memory LangGraph `InMemorySaver` keyed by `session_id`
  (30-min idle TTL, no DB; a restart drops in-flight sessions and the client starts fresh).
- Graph lives in `services/backend/app/graph/` (state, prompts, tools, nodes, routing, build, runner).
- Human-in-the-loop via `interrupt()`: the agent pauses to ask a clarifying or
  disambiguation question and resumes with the user's reply.
- Mandatory grounding guards: presence checked before concluding; frequency
  checked before HIGH confidence.
```

- [ ] **Step 2: Update `docs/vision.md` if needed**

Run: `grep -n "stateless\|MCP\|single-turn\|agentic" docs/vision.md`
If the request-flow / architecture description there still says "stateless single-turn", update those lines to reference the turn-based LangGraph flow and the in-memory session store. (Keep edits minimal and factual; don't rewrite unrelated sections.)

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md docs/vision.md
git commit -m "docs: update architecture to turn-based LangGraph flow"
```

---

## Self-Review

**Spec coverage (against the design spec):**
- §4 graph nodes (guardrail, resolve_inputs, investigate, tools, confidence_gate, ask_user, submit_id, inconclusive) → Tasks 5–11 ✅
- §4.2 agency vs. graph (tool_choice auto; agent picks tools/endings) → Task 7 (no forced tool_choice) + Task 10 router ✅
- §5 guards (presence; frequency-before-HIGH; season-anchor as guidance per Q3) → Task 10 + Task 6 ✅
- §6 Smart-ask HITL (hard/soft clarify_location, clarify_date→assume-recent, disambiguate_species; resume targets; ask-round cap) → Tasks 6, 8, 10 ✅
- §7 eBird tool surface as agent tools (frequency, rarities, family) → Task 4 ✅ (historic/spplist/region-drill stay internal per Plan 1 note)
- §8 state model + in-memory session/TTL + turn semantics → Tasks 2, 12 ✅
- §9 SSE events (session_id, awaiting_input, inconclusive via result) → Tasks 12, 14 ✅
- §10 prompt changes (colloquial broadening visible; presence/frequency/season framing; three endings; ask discipline) → Task 3 ✅
- §11 files (graph pkg, identify.py, schemas, pyproject, CLAUDE.md/vision) → Tasks 1, 13, 14, 16 + new package ✅
- §12 testing (routing, guards, interrupt/resume, input gaps, session TTL, regression) → tests across Tasks 2–14 ✅
- §13 open questions Q1–Q5 → resolved in "Architecture decisions" header ✅

**Placeholder scan:** No TBD/TODO; every code step has complete, runnable code and exact commands. ✅

**Type consistency:** `final` payload shape (`message`/`top_species`/`alternate_species`/`clarification`) is identical across `nodes.submit_id`, `nodes.inconclusive`, `prompts.NOT_BIRD_RESPONSE`, `prompts.FALLBACK_RESPONSE`, and `_build_response` in the route. Tool name sets (`DATA_TOOL_NAMES`/`TRACE_TOOL_NAMES`/`TERMINAL_TOOL_NAMES`) are defined once in `tools.py` and imported by `routing.py`/`build.py`. The router returns node-name strings mapped via `_ROUTE_MAP` in `build.py` (the `"investigate"` bounce → `gate_feedback`). SSE event dict shapes emitted by tool bodies match what the route's `_sse_from_runner` expects (`candidates` → `data`; `result` → `data`). `BirdState` keys used by nodes (`description`, `location`, `observed_at`, `region`, `observed_window`, `ask_rounds`, `final`, `messages`) all exist in the schema. ✅

**Known risks flagged for implementers (verify against the installed library, do not assume):**
1. **Thinking-token streaming shape** (Task 12 `_thinking_pieces`): langchain-anthropic streams `.content` as typed blocks when thinking is enabled. If the installed version surfaces reasoning under a different key, adjust `_thinking_pieces` and its test — this is the single most version-sensitive spot.
2. **`tool_choice` + thinking** (Task 7): never pass a forcing `tool_choice`; Anthropic rejects it while thinking is enabled. Left at default (auto).
3. **Node re-runs on resume** (Tasks 6, 8): keep all side effects *after* `interrupt()`. Tests patch `interrupt` to a return value to simulate resume; the real re-run-from-top behavior is exercised by manual `poetry run uvicorn ...` smoke testing if time permits.
4. **Multi-mode astream tuples** (Task 12): single mode yields bare data; multi-mode yields `(mode, chunk)`. The runner uses multi-mode, so always destructure.
5. **`InMemorySaver` is per-process**: HITL resume only works while the same process stays alive (true for a single uvicorn worker). Multi-worker deploys would need a shared checkpointer — out of scope (spec §8).

## Execution Handoff

Plan complete. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks.
2. **Inline Execution** — execute tasks in this session with checkpoints.
