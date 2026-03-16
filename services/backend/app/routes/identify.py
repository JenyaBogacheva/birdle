"""Bird identification endpoint."""

import asyncio
import json
import logging
import time
from urllib.parse import quote_plus

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..helpers.bird_agent import bird_agent
from ..helpers.ebird_client import ebird_client
from ..schemas.observation import ObservationInput, RecommendationResponse, SpeciesInfo

logger = logging.getLogger(__name__)

# Timeout for the entire identification flow
IDENTIFY_TIMEOUT = 90.0  # 90 seconds total

router = APIRouter(prefix="/api", tags=["identification"])


async def _build_species_info(data: dict) -> SpeciesInfo:
    """Build SpeciesInfo from agent result dict, fetching image by species_code."""
    common_name = data.get("common_name", "Unknown")
    species_code = data.get("species_code", "")

    # Fetch image from Macaulay Library if we have a species code
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


@router.post("/identify", response_model=RecommendationResponse)
async def identify_bird(observation: ObservationInput) -> RecommendationResponse:
    """Identify a bird based on user observation."""
    request_start = time.time()

    logger.info(
        "Identification request started",
        extra={
            "operation": "identify_bird",
            "description_length": len(observation.description),
            "location": observation.location,
        },
    )

    try:
        result = await asyncio.wait_for(
            bird_agent.identify(
                description=observation.description,
                location=observation.location,
                observed_at=observation.observed_at,
            ),
            timeout=IDENTIFY_TIMEOUT,
        )

        # Build response — fetch images in parallel (outside agent loop)
        top_species = None
        image_tasks = []
        if result.get("top_species"):
            image_tasks.append(_build_species_info(result["top_species"]))
        for alt in result.get("alternate_species", []):
            image_tasks.append(_build_species_info(alt))

        built = await asyncio.gather(*image_tasks) if image_tasks else []

        if result.get("top_species") and built:
            top_species = built[0]
            alternate_species = list(built[1:])
        else:
            alternate_species = list(built)

        response = RecommendationResponse(
            message=result.get("message", ""),
            top_species=top_species,
            alternate_species=alternate_species,
            clarification=result.get("clarification"),
        )

        total_latency_ms = (time.time() - request_start) * 1000
        logger.info(
            "Identification request completed",
            extra={
                "operation": "identify_bird",
                "total_latency_ms": round(total_latency_ms, 2),
                "has_top_species": top_species is not None,
                "status": "success",
            },
        )
        return response

    except asyncio.TimeoutError:
        total_latency_ms = (time.time() - request_start) * 1000
        logger.error(
            "Identification request timeout",
            extra={
                "operation": "identify_bird",
                "total_latency_ms": round(total_latency_ms, 2),
                "timeout_seconds": IDENTIFY_TIMEOUT,
                "status": "timeout",
            },
        )
        raise HTTPException(
            status_code=504,
            detail=f"Request timed out after {IDENTIFY_TIMEOUT} seconds.",
        )

    except HTTPException:
        raise

    except Exception as e:
        total_latency_ms = (time.time() - request_start) * 1000
        logger.error(
            f"Identification request failed: {e}",
            extra={
                "operation": "identify_bird",
                "total_latency_ms": round(total_latency_ms, 2),
                "error": str(e),
                "error_type": type(e).__name__,
                "status": "error",
            },
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.post("/identify/stream")
async def identify_bird_stream(observation: ObservationInput):
    """Stream bird identification progress via SSE."""
    request_start = time.time()

    logger.info(
        "Streaming identification request started",
        extra={
            "operation": "identify_bird_stream",
            "description_length": len(observation.description),
            "location": observation.location,
        },
    )

    async def event_generator():
        start_time = time.time()
        try:
            async for event in bird_agent.identify_stream(
                description=observation.description,
                location=observation.location,
                observed_at=observation.observed_at,
            ):
                if time.time() - start_time > IDENTIFY_TIMEOUT:
                    logger.error(
                        "Streaming request timeout",
                        extra={
                            "operation": "identify_bird_stream",
                            "total_latency_ms": round((time.time() - request_start) * 1000, 2),
                            "status": "timeout",
                        },
                    )
                    timeout_msg = "Request timed out. Please try again."
                    payload = {"type": "error", "message": timeout_msg}
                    yield f"data: {json.dumps(payload)}\n\n"
                    yield f'data: {json.dumps({"type": "done"})}\n\n'
                    return

                # Intercept result events to fetch images and build RecommendationResponse
                if event.get("type") == "result":
                    agent_data = event["data"]

                    status_msg = {"type": "status", "message": "Fetching photos..."}
                    yield f"data: {json.dumps(status_msg)}\n\n"

                    # Build species info with images (same as non-streaming path)
                    top_species = None
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
                        alternate_species = list(built)

                    response = RecommendationResponse(
                        message=agent_data.get("message", ""),
                        top_species=top_species,
                        alternate_species=alternate_species,
                        clarification=agent_data.get("clarification"),
                    )

                    result_payload = {
                        "type": "result",
                        "data": response.model_dump(),
                    }
                    yield f"data: {json.dumps(result_payload)}\n\n"
                else:
                    yield f"data: {json.dumps(event)}\n\n"

            total_latency_ms = (time.time() - request_start) * 1000
            logger.info(
                "Streaming identification completed",
                extra={
                    "operation": "identify_bird_stream",
                    "total_latency_ms": round(total_latency_ms, 2),
                    "status": "success",
                },
            )
            yield f'data: {json.dumps({"type": "done"})}\n\n'

        except Exception as e:
            logger.error(
                f"Streaming identification failed: {e}",
                exc_info=True,
                extra={
                    "operation": "identify_bird_stream",
                    "total_latency_ms": round((time.time() - request_start) * 1000, 2),
                    "status": "error",
                },
            )
            err_msg = "An unexpected error occurred. Please try again."
            err_payload = {"type": "error", "message": err_msg}
            yield f"data: {json.dumps(err_payload)}\n\n"
            yield f'data: {json.dumps({"type": "done"})}\n\n'

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
