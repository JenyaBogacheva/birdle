"""
Integration tests for the identify endpoint with mocked external services.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from services.backend.app.main import app

client = TestClient(app)


@pytest.mark.asyncio
async def test_identify_bird_success():
    """Test successful bird identification with mocked services."""
    # Mock eBird data
    mock_ebird_data = {
        "region": "US",
        "days_searched": 14,
        "total_observations": 100,
        "species_observed": [
            {
                "common_name": "Northern Cardinal",
                "scientific_name": "Cardinalis cardinalis",
                "species_code": "norcar",
                "observation_count": 50,
            }
        ],
    }

    # Mock OpenAI response
    mock_openai_response = {
        "message": "Based on your description, this is likely a Northern Cardinal.",
        "top_species": {
            "scientific_name": "Cardinalis cardinalis",
            "common_name": "Northern Cardinal",
            "species_code": "norcar",
            "confidence": "high",
            "reasoning": "Red plumage and crest are distinctive features of Northern Cardinals.",
        },
        "clarification": None,
    }

    with (
        patch(
            "services.backend.app.routes.identify.openai_client.moderate_content",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "services.backend.app.routes.identify.ebird_helper.get_recent_observations",
            new=AsyncMock(return_value=mock_ebird_data),
        ),
        patch(
            "services.backend.app.routes.identify.openai_client.chat_completion",
            new=AsyncMock(return_value=mock_openai_response),
        ),
    ):
        response = client.post(
            "/api/identify",
            json={
                "description": "Small red bird with a crest",
                "location": "Pennsylvania",
                "observed_at": "2024-01-15",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert "message" in data
        assert data["top_species"]["common_name"] == "Northern Cardinal"
        assert data["top_species"]["confidence"] == "high"
        assert data["top_species"]["reasoning"] is not None
        assert data["clarification"] is None


@pytest.mark.asyncio
async def test_identify_bird_needs_clarification():
    """Test identification when more information is needed."""
    mock_ebird_data = {
        "region": "US",
        "days_searched": 14,
        "species_observed": [],
    }

    mock_openai_response = {
        "message": "I need more information to identify this bird.",
        "top_species": None,
        "clarification": "Can you describe the bird's size and color?",
    }

    with (
        patch(
            "services.backend.app.routes.identify.openai_client.moderate_content",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "services.backend.app.routes.identify.ebird_helper.get_recent_observations",
            new=AsyncMock(return_value=mock_ebird_data),
        ),
        patch(
            "services.backend.app.routes.identify.openai_client.chat_completion",
            new=AsyncMock(return_value=mock_openai_response),
        ),
    ):
        response = client.post(
            "/api/identify",
            json={"description": "I saw a bird"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["top_species"] is None
        assert data["clarification"] is not None


@pytest.mark.asyncio
async def test_identify_bird_fails_moderation():
    """Test that inappropriate content is rejected."""
    with patch(
        "services.backend.app.routes.identify.openai_client.moderate_content",
        new=AsyncMock(return_value=False),
    ):
        response = client.post(
            "/api/identify",
            json={"description": "Inappropriate content"},
        )

        assert response.status_code == 400
        assert "inappropriate" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_identify_bird_medium_confidence():
    """Test identification with medium confidence."""
    mock_ebird_data = {
        "region": "US-NY",
        "days_searched": 14,
        "species_observed": [
            {
                "common_name": "American Goldfinch",
                "scientific_name": "Spinus tristis",
                "species_code": "amegfi",
                "observation_count": 30,
            }
        ],
    }

    mock_openai_response = {
        "message": "This could be an American Goldfinch.",
        "top_species": {
            "scientific_name": "Spinus tristis",
            "common_name": "American Goldfinch",
            "species_code": "amegfi",
            "confidence": "medium",
            "reasoning": "Yellow coloring matches, but more details would help confirm.",
        },
        "clarification": None,
    }

    with (
        patch(
            "services.backend.app.routes.identify.openai_client.moderate_content",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "services.backend.app.routes.identify.ebird_helper.get_recent_observations",
            new=AsyncMock(return_value=mock_ebird_data),
        ),
        patch(
            "services.backend.app.routes.identify.openai_client.chat_completion",
            new=AsyncMock(return_value=mock_openai_response),
        ),
    ):
        response = client.post(
            "/api/identify",
            json={
                "description": "Small yellow bird",
                "location": "New York",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["top_species"]["confidence"] == "medium"
        assert data["top_species"]["common_name"] == "American Goldfinch"


def test_identify_bird_missing_description():
    """Test that description is required."""
    response = client.post(
        "/api/identify",
        json={"location": "New York"},
    )

    assert response.status_code == 422  # Validation error
