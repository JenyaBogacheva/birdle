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
            logger.info(
                "Non-bird query rejected",
                extra={"operation": "graph_guardrail", "status": "rejected"},
            )
            return {"final": dict(prompts.NOT_BIRD_RESPONSE)}
    except Exception as e:  # fail open
        logger.warning(f"Guardrail failed, allowing request: {e}")
    return {"final": None}


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
        logger.warning(
            f"Input parse failed: {e}", extra={"operation": "resolve_inputs", "status": "error"}
        )
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
        payload: dict[str, Any]
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
    # and let the agent ask via ask_user only if season proves decisive.
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


_AGENT_MODEL_SINGLETON: Optional[Any] = None


def _agent_model() -> Any:
    """Lazily build the tool-bound, thinking-enabled Sonnet model (cached).

    tool_choice is left at its default (auto): Anthropic forbids forcing tool
    use while extended thinking is enabled.
    """
    global _AGENT_MODEL_SINGLETON
    if _AGENT_MODEL_SINGLETON is None:
        model = ChatAnthropic(  # type: ignore[call-arg]
            model=prompts.AGENT_MODEL,
            max_tokens=prompts.AGENT_MAX_TOKENS,
            thinking={"type": "enabled", "budget_tokens": prompts.THINKING_BUDGET_TOKENS},
            api_key=settings.anthropic_api_key,  # type: ignore[arg-type]
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
