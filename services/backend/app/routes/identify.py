"""
Bird identification endpoint with resilience and observability.
"""

import asyncio
import logging
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..helpers.mcp_client import ebird_helper
from ..helpers.openai_client import openai_client
from ..schemas.observation import ObservationInput, RecommendationResponse, SpeciesInfo

logger = logging.getLogger(__name__)

# Timeout for the entire identification flow
IDENTIFY_TIMEOUT = 60.0  # 60 seconds total

router = APIRouter(prefix="/api", tags=["identification"])

# Load prompt templates
# Path: services/backend/app/routes/identify.py -> go up 4 levels to project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
PROMPTS_DIR = PROJECT_ROOT / "configs" / "prompts"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "identify_system.txt"
USER_PROMPT_PATH = PROMPTS_DIR / "identify_user.txt"

# Cache prompts at module load
SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
USER_PROMPT_TEMPLATE = USER_PROMPT_PATH.read_text(encoding="utf-8")


def format_ebird_context(ebird_data: dict, max_species: int = 30) -> str:
    """
    Format eBird observation data for prompt context.

    Args:
        ebird_data: eBird observations data
        max_species: Maximum number of species to include

    Returns:
        Formatted string with regional bird context
    """
    if not ebird_data or "species_observed" not in ebird_data:
        return "No recent observation data available for this region."

    species_list = ebird_data["species_observed"][:max_species]
    region = ebird_data.get("region", "the area")
    days = ebird_data.get("days_searched", 14)

    lines = [
        f"Recent observations in {region} (past {days} days):",
        f"Total unique species: {len(species_list)}",
        "",
        "Top observed species:",
    ]

    for i, species in enumerate(species_list, 1):
        common_name = species.get("common_name", "Unknown")
        scientific_name = species.get("scientific_name", "")
        obs_count = species.get("observation_count", 0)
        lines.append(f"{i}. {common_name} ({scientific_name}) - {obs_count} observations")

    return "\n".join(lines)


async def extract_region_code(location: str) -> str:
    """
    Use LLM to extract eBird region code from location string.

    Args:
        location: User-provided location

    Returns:
        eBird region code (e.g., 'US-NY', 'AU', 'GB', 'NZ', 'BR', 'IN', 'RS', etc.)

    Raises:
        HTTPException: If region cannot be determined
    """
    prompt = f"""Convert this location to an eBird region code.

Location: "{location}"

Rules:
- Countries: Use ISO 3166-1 alpha-2 codes (e.g., AU, GB, NZ, IN, BR, RS, PL, etc.)
- US States: Use format US-XX (e.g., US-NY, US-CA, US-TX)
- Canadian Provinces: Use format CA-XX (e.g., CA-ON, CA-BC, CA-QC)
- Australian States: Use format AU-XX (e.g., AU-NSW, AU-VIC, AU-QLD)
- For well-known cities without country: use the most populous/famous location
- Only return "UNKNOWN" for truly vague inputs (e.g., "downtown", "the park", "somewhere")

Respond with ONLY the region code, nothing else.

Examples:
- "Australia" → AU
- "Sydney, Australia" → AU-NSW
- "New York" → US-NY
- "London" → GB
- "Belgrade" → RS
- "Mumbai" → IN
- "Tokyo" → JP
- "Warsaw" → PL
- "Cape Town" → ZA
- "São Paulo" → BR
- "Auckland" → NZ
- "Paris" → FR
- "downtown" → UNKNOWN"""

    try:
        response = await openai_client.chat_completion(
            system_prompt=(
                "You are a location normalizer. " "Return only the eBird region code or UNKNOWN."
            ),
            user_message=prompt,
        )

        region_code: str = str(response.get("content", "UNKNOWN")).strip().upper()
        logger.info(f"LLM extracted region code: {location} → {region_code}")

        if region_code == "UNKNOWN":
            raise ValueError("Could not determine region")

        return region_code

    except Exception as e:
        logger.warning(f"Failed to extract region code: {e}")
        raise HTTPException(
            status_code=400,
            detail=(
                "Could not determine region from location. "
                "Please be more specific (e.g., 'Sydney, Australia' or 'London, UK')"
            ),
        )


async def _identify_bird_internal(observation: ObservationInput) -> RecommendationResponse:
    """
    Internal identification logic with error handling.

    Args:
        observation: User observation input

    Returns:
        Recommendation response with species information
    """
    try:
        # Step 1: Check content moderation
        is_safe = await openai_client.moderate_content(observation.description)
        if not is_safe:
            logger.warning("Content failed moderation check")
            raise HTTPException(
                status_code=400, detail="Description contains inappropriate content"
            )

        # Step 2: Require location for bird identification (global support)
        if not observation.location:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Location is required for bird identification. "
                    "Please specify where you saw the bird "
                    "(e.g., 'Sydney, Australia' or 'New York, USA')"
                ),
            )

        region = await extract_region_code(observation.location)

        logger.info(f"Fetching eBird data for region: {region}")
        ebird_data = await ebird_helper.get_recent_observations(region=region, days=14)

        # Step 3: Format prompt with eBird context
        ebird_context = format_ebird_context(ebird_data)

        location_info = f"**Location:** {observation.location}" if observation.location else ""
        time_info = f"**Observed at:** {observation.observed_at}" if observation.observed_at else ""

        user_message = USER_PROMPT_TEMPLATE.format(
            description=observation.description,
            location_info=location_info,
            time_info=time_info,
            ebird_context=ebird_context,
        )

        # Step 4: Call OpenAI for identification
        logger.info("Calling OpenAI for bird identification")
        response = await openai_client.chat_completion(
            system_prompt=SYSTEM_PROMPT,
            user_message=user_message,
            response_format={"type": "json_object"},
        )

        # Step 5: Parse and validate response
        message = response.get("message", "")
        top_species_data = response.get("top_species")
        alternate_species_data = response.get("alternate_species", [])
        clarification = response.get("clarification")

        # Helper function to build species info with image
        async def build_species_info(species_data: dict) -> SpeciesInfo:
            common_name = species_data.get("common_name", "Unknown")

            # Match species to eBird data to get correct species code
            species_code = ""
            if ebird_data and "species_observed" in ebird_data:
                for species in ebird_data["species_observed"]:
                    if species.get("common_name", "").lower() == common_name.lower():
                        species_code = species.get("species_code", "")
                        logger.info(f"Matched '{common_name}' to eBird code: {species_code}")
                        break

            # Build eBird link
            if species_code:
                range_link = f"https://ebird.org/species/{species_code}"
            else:
                logger.warning(f"Species '{common_name}' not in eBird data, using search link")
                search_name = common_name.replace(" ", "+")
                range_link = f"https://ebird.org/explore?q={search_name}"

            # Fetch image from Macaulay Library via MCP
            image_url = None
            image_credit = None
            if species_code:
                image_data = await ebird_helper.get_species_image(species_code)
                if image_data:
                    image_url = image_data.get("image_url")
                    image_credit = image_data.get("photographer")
                    logger.info(f"Retrieved image for '{common_name}'")

            return SpeciesInfo(
                scientific_name=species_data.get("scientific_name", "Unknown"),
                common_name=common_name,
                range_link=range_link,
                confidence=species_data.get("confidence"),
                reasoning=species_data.get("reasoning"),
                image_url=image_url,
                image_credit=image_credit,
            )

        # Build top species with image
        top_species = None
        if top_species_data:
            top_species = await build_species_info(top_species_data)
            logger.info(
                f"Top species: {top_species.common_name} (confidence: {top_species.confidence})"
            )

        # Build alternate species with images
        alternate_species = []
        for alt_data in alternate_species_data:
            alt_species = await build_species_info(alt_data)
            alternate_species.append(alt_species)
            logger.info(
                f"Alternate species: {alt_species.common_name} "
                f"(confidence: {alt_species.confidence})"
            )

        result = RecommendationResponse(
            message=message,
            top_species=top_species,
            alternate_species=alternate_species,
            clarification=clarification,
        )

        return result

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error during bird identification: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error during identification")


@router.post("/identify", response_model=RecommendationResponse)
async def identify_bird(observation: ObservationInput) -> RecommendationResponse:
    """
    Identify a bird based on user observation description with timeout and observability.

    Uses OpenAI for reasoning and eBird MCP for regional species data and images.
    Includes timeout protection and structured logging for production resilience.
    """
    request_start = time.time()

    logger.info(
        "Identification request started",
        extra={
            "operation": "identify_bird",
            "description_length": len(observation.description),
            "location": observation.location,
            "has_timestamp": bool(observation.observed_at),
        },
    )

    try:
        # Wrap the entire identification flow with a timeout
        result = await asyncio.wait_for(
            _identify_bird_internal(observation), timeout=IDENTIFY_TIMEOUT
        )

        total_latency_ms = (time.time() - request_start) * 1000
        logger.info(
            "Identification request completed successfully",
            extra={
                "operation": "identify_bird",
                "total_latency_ms": round(total_latency_ms, 2),
                "has_top_species": result.top_species is not None,
                "alternate_count": len(result.alternate_species) if result.alternate_species else 0,
                "has_clarification": result.clarification is not None,
                "status": "success",
            },
        )
        return result

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
            detail=f"Request timed out after {IDENTIFY_TIMEOUT} seconds. Please try again.",
        )

    except HTTPException:
        # Re-raise HTTP exceptions with logging
        total_latency_ms = (time.time() - request_start) * 1000
        logger.warning(
            "Identification request failed with HTTP exception",
            extra={
                "operation": "identify_bird",
                "total_latency_ms": round(total_latency_ms, 2),
                "status": "http_error",
            },
        )
        raise

    except Exception as e:
        total_latency_ms = (time.time() - request_start) * 1000
        logger.error(
            f"Identification request failed with unexpected error: {e}",
            extra={
                "operation": "identify_bird",
                "total_latency_ms": round(total_latency_ms, 2),
                "error": str(e),
                "error_type": type(e).__name__,
                "status": "error",
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail="An unexpected error occurred. Please try again later."
        )
