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

IDENTIFY_TIMEOUT = 120.0

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

    # eBird's canonical species page is keyed by species code; the `explore?q=`
    # search endpoint does not deep-link to a species, so fall back to it only
    # when we somehow lack a code.
    range_link = (
        f"https://ebird.org/species/{species_code}"
        if species_code
        else f"https://ebird.org/explore?q={quote_plus(common_name)}"
    )

    return SpeciesInfo(
        scientific_name=data.get("scientific_name", "Unknown"),
        common_name=common_name,
        range_link=range_link,
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
            extra={
                "operation": "identify_sse",
                "total_latency_ms": round((time.time() - request_start) * 1000, 2),
                "status": "error",
            },
        )
        yield f'data: {json.dumps({"type": "error", "message": "An unexpected error occurred. Please try again."})}\n\n'
        yield f'data: {json.dumps({"type": "done"})}\n\n'


@router.post("/identify", response_model=RecommendationResponse)
async def identify_bird(observation: ObservationInput) -> RecommendationResponse:
    """Non-streaming identify: run the graph to completion and return the final."""
    session_id = session_store.create()
    try:
        final: dict | None = None

        async def _run() -> None:
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
        raise HTTPException(
            status_code=504, detail=f"Request timed out after {IDENTIFY_TIMEOUT} seconds."
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Identification failed: {e}",
            exc_info=True,
            extra={"operation": "identify_bird", "status": "error"},
        )
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.post("/identify/stream")
async def identify_bird_stream(observation: ObservationInput) -> StreamingResponse:
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
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/identify/resume")
async def identify_bird_resume(payload: ResumeInput) -> StreamingResponse:
    """Turn 2+: resume a paused session with the user's reply (SSE)."""
    request_start = time.time()
    events = bird_runner.resume_stream(
        session_id=payload.session_id, user_message=payload.user_message
    )
    return StreamingResponse(
        _sse_from_runner(events, request_start),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
