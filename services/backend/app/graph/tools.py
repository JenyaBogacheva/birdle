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
    _emit(
        {
            "type": "tool_call",
            "tool": "get_regional_birds",
            "input": {"region": region, "days": days},
        }
    )
    result = await ebird_client.get_regional_birds(region=region, days=days)
    n = len(result.get("species_observed", [])) if isinstance(result, dict) else 0
    _emit(
        {
            "type": "tool_result",
            "tool": "get_regional_birds",
            "summary": f"Found {n} species in {region}",
        }
    )
    return result


@tool
async def get_species_frequency(region: str, species_code: str, days: int = 14) -> dict[str, Any]:
    """How commonly a species was reported in a region recently — bucketed abundance."""
    _emit(
        {
            "type": "tool_call",
            "tool": "get_species_frequency",
            "input": {"region": region, "species_code": species_code, "days": days},
        }
    )
    result = await ebird_client.get_species_frequency(
        region=region, species_code=species_code, days=days
    )
    band = result.get("abundance", "unknown") if isinstance(result, dict) else "unknown"
    _emit(
        {
            "type": "tool_result",
            "tool": "get_species_frequency",
            "summary": f"{species_code}: {band} in {region}",
        }
    )
    return result


@tool
async def get_regional_rarities(region: str, days: int = 14) -> dict[str, Any]:
    """Notable/vagrant species reported in a region recently (rarity radar)."""
    _emit(
        {
            "type": "tool_call",
            "tool": "get_regional_rarities",
            "input": {"region": region, "days": days},
        }
    )
    result = await ebird_client.get_regional_rarities(region=region, days=days)
    n = len(result.get("rarities", [])) if isinstance(result, dict) else 0
    _emit(
        {
            "type": "tool_result",
            "tool": "get_regional_rarities",
            "summary": f"{n} rarities in {region}",
        }
    )
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
    _emit(
        {"type": "tool_result", "tool": "web_search", "summary": f"Found {n} results for '{query}'"}
    )
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


DATA_TOOLS = [
    get_regional_birds,
    get_species_frequency,
    get_regional_rarities,
    lookup_family,
    web_search,
]
TRACE_TOOLS = [detective_note, update_candidates]
TERMINAL_TOOLS = [submit_identification, ask_user, inconclusive]

# ToolNode executes data + trace only.
EXECUTABLE_TOOLS = DATA_TOOLS + TRACE_TOOLS
# All tools are bound to the model so it can call any of them.
ALL_TOOLS = DATA_TOOLS + TRACE_TOOLS + TERMINAL_TOOLS

DATA_TOOL_NAMES = {t.name for t in DATA_TOOLS}
TRACE_TOOL_NAMES = {t.name for t in TRACE_TOOLS}
TERMINAL_TOOL_NAMES = {t.name for t in TERMINAL_TOOLS}
