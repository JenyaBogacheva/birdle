"""Shared test fixtures for backend tests."""

import os

# Set fake API keys BEFORE any app imports to pass the settings validator.
# These are never used — all external calls are mocked in tests.
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-key-not-real")
os.environ.setdefault("TAVILY_API_KEY", "tvly-test-key-not-real")
os.environ.setdefault("EBIRD_TOKEN", "ebird-test-token-not-real")

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from services.backend.app.main import app


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def mock_bird_agent(monkeypatch):
    """Mock the bird_agent.identify method."""
    mock = AsyncMock()
    monkeypatch.setattr(
        "services.backend.app.routes.identify.bird_agent.identify",
        mock,
    )
    return mock


@pytest.fixture
def mock_bird_agent_stream(monkeypatch):
    """Mock the bird_agent.identify_stream method.

    Use ``mock.side_effect = my_async_gen_func`` in tests – the mock
    directly calls the async-generator function so the result is an
    async iterator (not a coroutine wrapping one).
    """
    from unittest.mock import MagicMock

    mock = MagicMock()
    monkeypatch.setattr(
        "services.backend.app.routes.identify.bird_agent.identify_stream",
        mock,
    )
    return mock


@pytest.fixture
def sample_agent_result():
    """Sample successful identification result from the agent."""
    return {
        "message": "Based on your description, this appears to be a Northern Cardinal!",
        "top_species": {
            "scientific_name": "Cardinalis cardinalis",
            "common_name": "Northern Cardinal",
            "confidence": "high",
            "reasoning": "Bright red plumage and crest matches Northern Cardinal.",
            "image_url": "https://example.com/cardinal.jpg",
            "image_credit": "John Doe",
        },
        "alternate_species": [
            {
                "scientific_name": "Haemorhous mexicanus",
                "common_name": "House Finch",
                "confidence": "medium",
                "reasoning": "Could be a House Finch but they are more rose-colored.",
            }
        ],
        "clarification": None,
    }
