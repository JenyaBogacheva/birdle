"""
Bird identification endpoint.
"""

import logging

from fastapi import APIRouter

from ..schemas.observation import ObservationInput, RecommendationResponse, SpeciesInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["identification"])


@router.post("/identify", response_model=RecommendationResponse)
async def identify_bird(observation: ObservationInput) -> RecommendationResponse:
    """
    Identify a bird based on user observation description.

    For Iteration 1, this returns stubbed data to validate the end-to-end flow.
    """
    logger.info(
        f"Received identification request: description='{observation.description[:50]}...', "
        f"location={observation.location}, observed_at={observation.observed_at}"
    )

    # Stubbed response for MVP iteration 1
    stubbed_response = RecommendationResponse(
        message=(
            "Based on your description, this is likely a Northern Cardinal. "
            "This is a common bird across eastern North America, known for its "
            "brilliant red plumage and distinctive crest."
        ),
        top_species=SpeciesInfo(
            scientific_name="Cardinalis cardinalis",
            common_name="Northern Cardinal",
            range_link="https://ebird.org/species/norcar",
        ),
        clarification=None,
    )

    if stubbed_response.top_species:
        logger.info(
            f"Returning stubbed response: species={stubbed_response.top_species.common_name}"
        )
    else:
        logger.info("Returning stubbed response: no species identified")

    return stubbed_response
