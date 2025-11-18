"""
Integration tests for multi-species identification with images.
"""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_identify_multi_species_with_images():
    """Test identification returns multiple species with images."""
    from services.backend.app.routes.identify import identify_bird
    from services.backend.app.schemas.observation import ObservationInput

    observation = ObservationInput(
        description="A red bird with a crest", location="New York, USA", observed_at="2024-01-15"
    )

    # Mock OpenAI responses
    mock_openai_moderate = AsyncMock(return_value=True)
    mock_openai_identify = AsyncMock(
        return_value={
            "message": "Based on your description, here are the most likely species.",
            "top_species": {
                "scientific_name": "Cardinalis cardinalis",
                "common_name": "Northern Cardinal",
                "confidence": "high",
                "reasoning": "Red plumage with prominent crest matches perfectly.",
            },
            "alternate_species": [
                {
                    "scientific_name": "Piranga rubra",
                    "common_name": "Summer Tanager",
                    "confidence": "medium",
                    "reasoning": "All-red male but lacks crest.",
                },
                {
                    "scientific_name": "Piranga olivacea",
                    "common_name": "Scarlet Tanager",
                    "confidence": "low",
                    "reasoning": "Has black wings, less likely with a crest.",
                },
            ],
        }
    )

    # Mock eBird observations
    mock_ebird_obs = AsyncMock(
        return_value={
            "region": "US-NY",
            "days_searched": 14,
            "total_observations": 100,
            "species_observed": [
                {
                    "common_name": "Northern Cardinal",
                    "scientific_name": "Cardinalis cardinalis",
                    "species_code": "norcar",
                    "observation_count": 50,
                },
                {
                    "common_name": "Summer Tanager",
                    "scientific_name": "Piranga rubra",
                    "species_code": "sumtan",
                    "observation_count": 20,
                },
                {
                    "common_name": "Scarlet Tanager",
                    "scientific_name": "Piranga olivacea",
                    "species_code": "scatan",
                    "observation_count": 10,
                },
            ],
        }
    )

    # Mock image fetching - return actual values, not coroutines
    async def mock_get_image(species_code):
        if species_code == "norcar":
            return {"image_url": "https://example.com/norcar.jpg", "photographer": "Jane Smith"}
        elif species_code == "sumtan":
            return {"image_url": "https://example.com/sumtan.jpg", "photographer": "Bob Johnson"}
        elif species_code == "scatan":
            return {"image_url": "https://example.com/scatan.jpg", "photographer": "Alice Brown"}
        return None

    with (
        patch(
            "services.backend.app.routes.identify.openai_client.moderate_content",
            mock_openai_moderate,
        ),
        patch(
            "services.backend.app.routes.identify.openai_client.chat_completion",
            side_effect=[{"content": "US-NY"}, mock_openai_identify.return_value],
        ),
        patch(
            "services.backend.app.routes.identify.ebird_helper.get_recent_observations",
            mock_ebird_obs,
        ),
        patch(
            "services.backend.app.routes.identify.ebird_helper.get_species_image",
            side_effect=mock_get_image,
        ),
    ):
        result = await identify_bird(observation)

        # Verify structure
        assert result.message == "Based on your description, here are the most likely species."
        assert result.top_species is not None
        assert len(result.alternate_species) == 2

        # Verify top species
        assert result.top_species.common_name == "Northern Cardinal"
        assert result.top_species.confidence == "high"
        assert result.top_species.image_url == "https://example.com/norcar.jpg"
        assert result.top_species.image_credit == "Jane Smith"

        # Verify alternates
        assert result.alternate_species[0].common_name == "Summer Tanager"
        assert result.alternate_species[0].confidence == "medium"
        assert result.alternate_species[0].image_url == "https://example.com/sumtan.jpg"

        assert result.alternate_species[1].common_name == "Scarlet Tanager"
        assert result.alternate_species[1].confidence == "low"
        assert result.alternate_species[1].image_url == "https://example.com/scatan.jpg"


@pytest.mark.asyncio
async def test_identify_requires_location():
    """Test that location is required for identification."""
    from fastapi import HTTPException

    from services.backend.app.routes.identify import identify_bird
    from services.backend.app.schemas.observation import ObservationInput

    observation = ObservationInput(description="A red bird with a crest")

    # Mock moderation to pass
    mock_openai_moderate = AsyncMock(return_value=True)

    with (
        patch(
            "services.backend.app.routes.identify.openai_client.moderate_content",
            mock_openai_moderate,
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await identify_bird(observation)

    assert exc_info.value.status_code == 400
    assert "Location is required" in exc_info.value.detail


@pytest.mark.asyncio
async def test_identify_global_region():
    """Test identification with non-US location."""
    from services.backend.app.routes.identify import identify_bird
    from services.backend.app.schemas.observation import ObservationInput

    observation = ObservationInput(
        description="A large black and white bird", location="Sydney, Australia"
    )

    # Mock OpenAI responses for Australia
    mock_openai_moderate = AsyncMock(return_value=True)
    mock_openai_identify = AsyncMock(
        return_value={
            "message": "This appears to be an Australian Magpie.",
            "top_species": {
                "scientific_name": "Gymnorhina tibicen",
                "common_name": "Australian Magpie",
                "confidence": "high",
                "reasoning": "Large black and white bird, common in Sydney.",
            },
            "alternate_species": [],
        }
    )

    # Mock eBird observations for Australia
    mock_ebird_obs = AsyncMock(
        return_value={
            "region": "AU-NSW",
            "days_searched": 14,
            "total_observations": 80,
            "species_observed": [
                {
                    "common_name": "Australian Magpie",
                    "scientific_name": "Gymnorhina tibicen",
                    "species_code": "ausmag",
                    "observation_count": 45,
                }
            ],
        }
    )

    # Mock image fetching
    mock_image = AsyncMock(
        return_value={
            "image_url": "https://example.com/ausmag.jpg",
            "photographer": "Aussie Birder",
        }
    )

    with (
        patch(
            "services.backend.app.routes.identify.openai_client.moderate_content",
            mock_openai_moderate,
        ),
        patch(
            "services.backend.app.routes.identify.openai_client.chat_completion",
            side_effect=[{"content": "AU-NSW"}, mock_openai_identify.return_value],
        ),
        patch(
            "services.backend.app.routes.identify.ebird_helper.get_recent_observations",
            mock_ebird_obs,
        ),
        patch("services.backend.app.routes.identify.ebird_helper.get_species_image", mock_image),
    ):
        result = await identify_bird(observation)

        # Verify Australian species identified
        assert result.top_species is not None
        assert result.top_species.common_name == "Australian Magpie"
        assert result.top_species.confidence == "high"
        assert result.top_species.image_url == "https://example.com/ausmag.jpg"
