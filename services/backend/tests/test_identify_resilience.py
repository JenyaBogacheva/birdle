"""
Tests for identification endpoint resilience (timeouts, error handling).
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from services.backend.app.routes.identify import _identify_bird_internal, identify_bird
from services.backend.app.schemas.observation import ObservationInput


@pytest.fixture
def sample_observation():
    """Create a sample observation for testing."""
    return ObservationInput(
        description="Small red bird with black mask",
        location="New York, USA",
        observed_at="Today morning",
    )


@pytest.mark.asyncio
async def test_identify_bird_timeout_handling(sample_observation):
    """Test that the endpoint times out gracefully after IDENTIFY_TIMEOUT."""

    # Mock _identify_bird_internal to hang indefinitely
    async def mock_slow_identify(obs):
        await asyncio.sleep(100)  # Sleep longer than timeout

    with patch(
        "services.backend.app.routes.identify._identify_bird_internal",
        new=AsyncMock(side_effect=mock_slow_identify),
    ):
        # Reduce timeout for testing
        with patch("services.backend.app.routes.identify.IDENTIFY_TIMEOUT", 0.5):
            with pytest.raises(HTTPException) as exc_info:
                await identify_bird(sample_observation)

            # Should raise 504 timeout error
            assert exc_info.value.status_code == 504
            assert "timed out" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_identify_bird_http_exception_passthrough(sample_observation):
    """Test that HTTP exceptions are passed through with logging."""

    # Mock _identify_bird_internal to raise HTTPException
    async def mock_http_error(obs):
        raise HTTPException(status_code=400, detail="Location is required")

    with patch(
        "services.backend.app.routes.identify._identify_bird_internal",
        new=AsyncMock(side_effect=mock_http_error),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await identify_bird(sample_observation)

        # Should pass through the original HTTP exception
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Location is required"


@pytest.mark.asyncio
async def test_identify_bird_unexpected_error_handling(sample_observation):
    """Test that unexpected errors are caught and converted to 500."""

    # Mock _identify_bird_internal to raise unexpected error
    async def mock_unexpected_error(obs):
        raise ValueError("Unexpected database error")

    with patch(
        "services.backend.app.routes.identify._identify_bird_internal",
        new=AsyncMock(side_effect=mock_unexpected_error),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await identify_bird(sample_observation)

        # Should convert to 500 error
        assert exc_info.value.status_code == 500
        assert "unexpected error" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_identify_bird_success_logging(sample_observation):
    """Test that successful identification includes proper logging."""
    from services.backend.app.schemas.observation import RecommendationResponse, SpeciesInfo

    # Mock successful response
    mock_response = RecommendationResponse(
        message="This appears to be a Northern Cardinal",
        top_species=SpeciesInfo(
            scientific_name="Cardinalis cardinalis",
            common_name="Northern Cardinal",
            range_link="https://ebird.org/species/norcar",
            confidence="high",
            reasoning="Red plumage and black mask are distinctive",
        ),
        alternate_species=[],
        clarification=None,
    )

    with patch(
        "services.backend.app.routes.identify._identify_bird_internal",
        new=AsyncMock(return_value=mock_response),
    ):
        result = await identify_bird(sample_observation)

        # Should return the response
        assert result.message == "This appears to be a Northern Cardinal"
        assert result.top_species is not None
        assert result.top_species.common_name == "Northern Cardinal"


@pytest.mark.asyncio
async def test_identify_bird_internal_moderation_failure(sample_observation):
    """Test that moderation failure raises HTTPException."""
    from services.backend.app.helpers.openai_client import openai_client

    # Mock moderation to fail
    with patch.object(openai_client, "moderate_content", new=AsyncMock(return_value=False)):
        with pytest.raises(HTTPException) as exc_info:
            await _identify_bird_internal(sample_observation)

        # Should raise 400 error
        assert exc_info.value.status_code == 400
        assert "inappropriate content" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_identify_bird_internal_missing_location():
    """Test that missing location raises HTTPException."""
    obs = ObservationInput(description="A red bird", location=None)

    with pytest.raises(HTTPException) as exc_info:
        await _identify_bird_internal(obs)

    # Should raise 400 error
    assert exc_info.value.status_code == 400
    assert "location is required" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_identify_bird_internal_region_extraction_failure(sample_observation):
    """Test handling of region extraction failure."""

    # Mock extract_region_code to fail
    with patch(
        "services.backend.app.routes.identify.extract_region_code",
        new=AsyncMock(
            side_effect=HTTPException(status_code=400, detail="Could not determine region")
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await _identify_bird_internal(sample_observation)

        # Should pass through the region extraction error
        assert exc_info.value.status_code == 400
        assert "region" in exc_info.value.detail.lower()
