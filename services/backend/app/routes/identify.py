"""
Bird identification endpoint.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..helpers.mcp_client import ebird_helper
from ..helpers.openai_client import openai_client
from ..schemas.observation import ObservationInput, RecommendationResponse, SpeciesInfo

logger = logging.getLogger(__name__)

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
        eBird region code (e.g., 'US-NY', 'AU', 'GB')
    """
    prompt = f"""Convert this location to an eBird region code.

Location: "{location}"

Rules:
- Countries: Use 2-letter ISO codes (e.g., AU, GB, CA, NZ, IN, BR, FR, DE, ES, IT, JP, CN, MX, ZA)
- US States: Use format US-XX (e.g., US-NY, US-CA, US-TX)
- If ambiguous or unknown: return "US"

Respond with ONLY the region code, nothing else.

Examples:
- "Australia" → AU
- "New York" → US-NY
- "California" → US-CA
- "United Kingdom" → GB
- "Sydney" → AU
- "London" → GB
- "Pennsylvania" → US-PA"""

    try:
        response = await openai_client.chat_completion(
            system_prompt="You are a location normalizer. Return only the eBird region code.",
            user_message=prompt,
        )

        region_code: str = str(response.get("content", "US")).strip().upper()
        logger.info(f"LLM extracted region code: {location} → {region_code}")
        return region_code

    except Exception as e:
        logger.warning(f"Failed to extract region code via LLM: {e}, defaulting to US")
        return "US"


@router.post("/identify", response_model=RecommendationResponse)
async def identify_bird(observation: ObservationInput) -> RecommendationResponse:
    """
    Identify a bird based on user observation description.

    Uses OpenAI for reasoning and eBird MCP for regional species data.
    """
    logger.info(
        f"Received identification request: description='{observation.description[:50]}...', "
        f"location={observation.location}, observed_at={observation.observed_at}"
    )

    try:
        # Step 1: Check content moderation
        is_safe = await openai_client.moderate_content(observation.description)
        if not is_safe:
            logger.warning("Content failed moderation check")
            raise HTTPException(
                status_code=400, detail="Description contains inappropriate content"
            )

        # Step 2: Get regional context from eBird
        region = "US"  # Default
        if observation.location:
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
        clarification = response.get("clarification")

        top_species = None
        if top_species_data:
            # Match the identified species to eBird data to get correct species code
            species_code = ""
            common_name = top_species_data.get("common_name", "Unknown")

            # Search eBird data for matching species
            if ebird_data and "species_observed" in ebird_data:
                for species in ebird_data["species_observed"]:
                    if species.get("common_name", "").lower() == common_name.lower():
                        species_code = species.get("species_code", "")
                        logger.info(f"Matched to eBird species code: {species_code}")
                        break

            # Build eBird link
            if species_code:
                # Direct species link if we found the code
                range_link = f"https://ebird.org/species/{species_code}"
            else:
                # Fallback: search link if species not in regional data
                logger.warning(
                    f"Species '{common_name}' not found in eBird data, using search link"
                )
                search_name = common_name.replace(" ", "+")
                range_link = f"https://ebird.org/explore?q={search_name}"

            top_species = SpeciesInfo(
                scientific_name=top_species_data.get("scientific_name", "Unknown"),
                common_name=common_name,
                range_link=range_link,
                confidence=top_species_data.get("confidence"),
                reasoning=top_species_data.get("reasoning"),
            )

            logger.info(
                f"Identified species: {top_species.common_name} "
                f"(confidence: {top_species.confidence}, code: {species_code})"
            )

        result = RecommendationResponse(
            message=message, top_species=top_species, clarification=clarification
        )

        return result

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error during bird identification: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error during identification")
