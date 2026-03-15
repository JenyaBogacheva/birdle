"""Bird identification endpoint."""

import asyncio
import logging
import time
from urllib.parse import quote_plus

from fastapi import APIRouter, HTTPException

from ..helpers.bird_agent import bird_agent
from ..schemas.observation import ObservationInput, RecommendationResponse, SpeciesInfo

logger = logging.getLogger(__name__)

# Timeout for the entire identification flow
IDENTIFY_TIMEOUT = 60.0  # 60 seconds total

router = APIRouter(prefix="/api", tags=["identification"])


def _build_species_info(data: dict) -> SpeciesInfo:
    """Build SpeciesInfo from agent result dict."""
    common_name = data.get("common_name", "Unknown")
    return SpeciesInfo(
        scientific_name=data.get("scientific_name", "Unknown"),
        common_name=common_name,
        range_link=f"https://ebird.org/explore?q={quote_plus(common_name)}",
        confidence=data.get("confidence"),
        reasoning=data.get("reasoning"),
        image_url=data.get("image_url"),
        image_credit=data.get("image_credit"),
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

        # Build response from agent result
        top_species = None
        if result.get("top_species"):
            top_species = _build_species_info(result["top_species"])

        alternate_species = [
            _build_species_info(alt) for alt in result.get("alternate_species", [])
        ]

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
