"""Graph nodes: guardrail, resolve_inputs, investigate, ask_user, terminals."""

from __future__ import annotations

import logging
from typing import Any, Optional

import anthropic
from anthropic.types import TextBlock
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.config import get_stream_writer
from langgraph.types import interrupt

from ..helpers.ebird_client import ebird_client
from ..helpers.geocoder import resolve_region
from ..settings import settings
from . import prompts
from .state import BirdState
from .tools import ALL_TOOLS, TERMINAL_TOOL_NAMES

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


async def _parse_date(observed_at: Optional[str]) -> str:
    """Haiku parse: free-text time -> 'recent' | 'YYYY-MM-DD' | 'unparseable'."""
    if not observed_at or not observed_at.strip():
        return "recent"
    try:
        resp = await _raw_anthropic.messages.create(
            model=prompts.RESOLVE_MODEL,
            max_tokens=40,
            system=prompts.RESOLVE_PROMPT,
            messages=[{"role": "user", "content": f"time={observed_at!r}"}],
        )
        window = _first_text(resp).strip().strip('"')
        return window or "recent"
    except Exception as e:
        logger.warning(
            f"Date parse failed: {e}", extra={"operation": "resolve_inputs", "status": "error"}
        )
        return "recent"


async def resolve_inputs(state: BirdState) -> dict[str, Any]:
    """Deterministically resolve region (+point) via geocoding; clarify via interrupt."""
    location = state.get("location", "") or ""
    observed_at = state.get("observed_at")
    ask_rounds = state.get("ask_rounds", 0)
    lat_in, lng_in = state.get("lat"), state.get("lng")

    resolved = await resolve_region(text=location, lat=lat_in, lng=lng_in)
    window = await _parse_date(observed_at)
    if window == "unparseable":
        window = "recent"

    region = resolved["region_code"]
    lat, lng = resolved["lat"], resolved["lng"]
    display = resolved.get("display_name")

    if display:
        _emit({"type": "status", "message": f"Looking around {display}…"})

    answer: Optional[str] = None
    if region is None and ask_rounds < prompts.MAX_ASK_ROUNDS:
        if location.strip():
            payload: dict[str, Any] = {
                "reason": "clarify_location",
                "question": (
                    f'I couldn\'t pin down "{location}" to a birding region. '
                    "Which country/state (or nearest city) was it?"
                ),
            }
        else:
            payload = {
                "reason": "clarify_location",
                "question": "Where did you see it? A location helps a lot -- or skip and I'll do my best.",
                "options": ["Skip — no location"],
            }
        answer = interrupt(payload)
        ask_rounds += 1
        if answer and answer.strip().lower() not in {"skip", "skip — no location", "not sure"}:
            reparsed = await resolve_region(text=answer)
            region, lat, lng = reparsed["region_code"], reparsed["lat"], reparsed["lng"]

    context = HumanMessage(
        content=(
            f"Resolved region: {region or 'UNKNOWN (proceed description-only, lower confidence)'}. "
            f"Observation window: {window}. "
            + (
                "Use get_regional_birds for what's present near the sighting."
                if window == "recent"
                else f"The sighting was on {window}; prefer date-anchored evidence and reason about seasonality."
            )
        )
    )
    return {
        "region": region,
        "lat": lat,
        "lng": lng,
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


# ---------------------------------------------------------------- visual check
# Raw Anthropic tool schema for the vision verdict. Forced tool_choice gives
# structured JSON; thinking stays OFF here so forcing a tool is allowed.
_VISUAL_VERDICT_TOOL: dict[str, Any] = {
    "name": "visual_verdict",
    "description": "Report which candidate's reference photo best matches the described bird.",
    "input_schema": {
        "type": "object",
        "properties": {
            "best_match": {
                "type": "string",
                "description": (
                    "Common name of the candidate whose reference photo best fits the "
                    "description, exactly as labelled; or 'none' if none fit well."
                ),
            },
            "top_still_best": {
                "type": "boolean",
                "description": (
                    "True if the proposed top candidate (the first photo) is still among "
                    "the best visual matches for the description."
                ),
            },
            "note": {
                "type": "string",
                "description": (
                    "One sentence: what the photos show versus the description. Judge "
                    "structure/shape/bill first; treat plumage colour as soft evidence."
                ),
            },
        },
        "required": ["best_match", "top_still_best", "note"],
    },
}


async def _candidate_images(args: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(name, base64_data, media_type) for the submitted candidates (top first).

    Pulls the top species plus alternates, dedupes by name, resolves each Wikimedia
    lead photo and downloads its bytes (Anthropic's URL fetcher is blocked by
    Wikimedia, so we inline base64). Keeps up to three that actually downloaded.
    """
    top = args.get("top_species") or {}
    candidates = [top, *(args.get("alternate_species") or [])]
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for cand in candidates:
        name = (cand or {}).get("common_name") or (cand or {}).get("name")
        if not name or name in seen:
            continue
        seen.add(name)
        img = await ebird_client.get_species_image(name)
        if img and img.get("image_url"):
            fetched = await ebird_client.fetch_image_b64(img["image_url"])
            if fetched:
                out.append((name, fetched[0], fetched[1]))
        if len(out) >= 3:
            break
    return out


async def _run_visual_verdict(
    state: BirdState, images: list[tuple[str, str, str]]
) -> dict[str, Any]:
    """Vision call: compare the candidate photos against the description."""
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": prompts.VISUAL_VERIFY_PROMPT.format(
                description=state.get("description") or "(none given)",
                region=state.get("region") or "unknown",
            ),
        }
    ]
    for i, (name, data, media_type) in enumerate(images):
        label = "Top candidate" if i == 0 else f"Alternative {i}"
        content.append({"type": "text", "text": f"{label}: {name}"})
        content.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": data},
            }
        )

    resp = await _raw_anthropic.messages.create(  # type: ignore[call-overload]
        model=prompts.VISUAL_VERIFY_MODEL,
        max_tokens=500,
        tools=[_VISUAL_VERDICT_TOOL],
        tool_choice={"type": "tool", "name": "visual_verdict"},
        messages=[{"role": "user", "content": content}],
    )
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "visual_verdict":
            return dict(block.input)  # type: ignore[arg-type]
    return {"top_still_best": True}  # malformed -> don't block the ID


def _closing_messages(last: Any, terminal_content: str) -> list[ToolMessage]:
    """Close every open tool call on ``last`` so the transcript stays valid for the
    next investigate turn; the terminal (submit) call carries the corrective text."""
    closed: list[ToolMessage] = []
    for call in getattr(last, "tool_calls", None) or []:
        call_id = call.get("id")
        if not call_id:
            continue
        content = terminal_content if call.get("name") in TERMINAL_TOOL_NAMES else "noted"
        closed.append(ToolMessage(content=content, tool_call_id=call_id))
    return closed


async def verify_visual(state: BirdState) -> dict[str, Any]:
    """Compare the submitted candidates' reference photos against the description.

    Confirms the ID (-> submit_id) or, when a different candidate's photo fits the
    description better, bounces it back to investigate with a correction. Degrades
    gracefully: any skip condition or failure just confirms, never blocking an ID.
    """
    messages = state.get("messages", [])
    call = _last_terminal_tool_call(messages) or {}
    args = call.get("args", {})
    top = args.get("top_species") or {}
    top_name = top.get("common_name") or top.get("name")
    top_code = top.get("species_code")
    bounces = state.get("visual_bounces", 0)

    # Skip (confirm) when there's nothing to verify, we already concluded this exact
    # bird this session, or we've spent our one correction.
    if (
        not top_name
        or (top_code and top_code == state.get("last_species_code"))
        or bounces >= prompts.MAX_VISUAL_BOUNCES
    ):
        return {"visual_verdict": "confirm"}

    images = await _candidate_images(args)
    if not images:
        return {"visual_verdict": "confirm"}  # no photo to look at -> don't block

    _emit({"type": "status", "message": "Comparing your description with reference photos…"})
    try:
        verdict = await _run_visual_verdict(state, images)
    except Exception as e:  # graceful degradation — accept the ID
        logger.warning(
            f"Visual verification failed, accepting ID: {e}",
            extra={"operation": "verify_visual", "status": "error", "error_type": type(e).__name__},
        )
        return {"visual_verdict": "confirm"}

    best = (verdict.get("best_match") or "").strip()
    note = (verdict.get("note") or "").strip()
    top_still = verdict.get("top_still_best", True)

    logger.info(
        "Visual verification verdict",
        extra={
            "operation": "verify_visual",
            "status": "success",
            "top_candidate": top_name,
            "best_match": best,
            "top_still_best": bool(top_still),
        },
    )

    # Confirm when the top pick still fits the photo (or the verdict named the top
    # pick itself as the best match — no real disagreement).
    if top_still or best.lower() == str(top_name).lower():
        if note:
            _emit({"type": "detective_note", "message": "Reference photos fit the description."})
        return {"visual_verdict": "confirm"}

    # The top pick's photo does NOT fit the description. Bounce with a correction:
    #  - a different shown candidate fits better -> steer the agent to it;
    #  - nothing shown fits -> tell the agent to widen / lower confidence.
    if best and best.lower() != "none":
        _emit({"type": "detective_note", "message": f"The photos: {best} fits better."})
        feedback = prompts.visual_feedback_message(str(top_name), best, note)
    else:
        _emit({"type": "detective_note", "message": "The photos don't fit the description."})
        feedback = prompts.visual_mismatch_message(str(top_name), note)
    return {
        "messages": _closing_messages(messages[-1], feedback),
        "visual_bounces": bounces + 1,
        "visual_verdict": "revise",
    }


def _last_terminal_tool_call(messages: list[Any]) -> Optional[dict[str, Any]]:
    """The first tool_call on the last AIMessage, if it's an AIMessage with calls."""
    if not messages:
        return None
    last = messages[-1]
    calls: Optional[list[dict[str, Any]]] = getattr(last, "tool_calls", None)
    if calls:
        return calls[0]
    return None


async def ask_user(state: BirdState) -> dict[str, Any]:
    """Disambiguation HITL: close the ask_user tool call, interrupt, resume w/ answer."""
    messages = state.get("messages", [])
    call = _last_terminal_tool_call(messages) or {}
    call_id = call.get("id", "ask_user")
    args = call.get("args", {})

    payload: dict[str, Any] = {
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


def _close_pending_tool_calls(messages: list[Any], verdict_note: str) -> list[ToolMessage]:
    """Close every open tool call on the last AIMessage so the transcript stays
    valid for a later follow-up turn.

    Returns ``[]`` when the agent concluded with plain prose (no tool call to
    close) -- emitting a ToolMessage with no matching ``tool_use`` block would
    corrupt the transcript and make the next ``/continue`` turn 400. A terminal
    tool call gets ``verdict_note``; a non-terminal call that never ran (e.g. a
    data tool reached after the data budget was spent) is closed honestly rather
    than fabricating a result for it.
    """
    if not messages:
        return []
    last = messages[-1]
    calls: list[dict[str, Any]] = getattr(last, "tool_calls", None) or []
    closed: list[ToolMessage] = []
    for call in calls:
        call_id = call.get("id")
        if not call_id:
            continue
        note = (
            verdict_note
            if call.get("name") in TERMINAL_TOOL_NAMES
            else "Investigation concluded before this tool ran."
        )
        closed.append(ToolMessage(content=note, tool_call_id=call_id))
    return closed


async def submit_id(state: BirdState) -> dict[str, Any]:
    """Terminal: map submit_identification args into the final response payload."""
    messages = state.get("messages", [])
    call = _last_terminal_tool_call(messages) or {}
    args = call.get("args", {})
    final: dict[str, Any] = {
        "message": args.get("message", ""),
        "top_species": args.get("top_species"),
        "alternate_species": args.get("alternate_species") or [],
        "clarification": args.get("clarification"),
    }
    out: dict[str, Any] = {
        "final": final,
        "messages": _close_pending_tool_calls(messages, "identification submitted"),
    }
    # Remember the grounded species so a same-species follow-up can skip a
    # redundant presence check (only update when a code is present, so we keep
    # the last *coded* conclusion across a code-less or inconclusive turn).
    code = (args.get("top_species") or {}).get("species_code")
    if code:
        out["last_species_code"] = code
    return out


async def inconclusive(state: BirdState) -> dict[str, Any]:
    """Terminal: honest "can't identify" -- closest guesses + what would help."""
    messages = state.get("messages", [])
    call = _last_terminal_tool_call(messages) or {}
    args = call.get("args", {})
    final: dict[str, Any] = {
        "message": args.get("message") or prompts.FALLBACK_RESPONSE["message"],
        "top_species": None,
        # Surface closest guesses as alternates so the existing card renders them.
        "alternate_species": args.get("closest_guesses") or [],
        # Always give concrete "what would help" examples -- fall back to the
        # standard prompts when the agent didn't spell them out itself.
        "clarification": args.get("what_would_help") or prompts.FALLBACK_RESPONSE["clarification"],
    }
    return {
        "final": final,
        "messages": _close_pending_tool_calls(messages, "concluded inconclusive"),
    }


async def follow_up(state: BirdState) -> dict[str, Any]:
    """Re-entry for a follow-up turn on a concluded session: append the user's
    new message and hand back to investigate (which may re-identify or answer).

    Terminal nodes close their own tool call, so the transcript is already valid
    here -- we only add the (framed) human message and clear the prior verdict."""
    message = state.get("follow_up_message") or ""
    return {
        "messages": [HumanMessage(content=prompts.FOLLOW_UP_PROMPT.format(message=message))],
        "final": None,
        "follow_up_message": None,
    }
