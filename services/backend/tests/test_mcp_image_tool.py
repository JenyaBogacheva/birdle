"""
Tests for MCP image fetching tool.
"""

import json
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_get_species_image_success():
    """Test successful image fetch via MCP."""
    from services.backend.app.helpers.mcp_client import ebird_helper

    # Mock the MCP tool call response
    mock_result = {
        "content": [
            {
                "text": json.dumps(
                    {
                        "species_code": "norcar",
                        "image_url": "https://cdn.download.ams.birds.cornell.edu/api/v1/asset/123/preview",
                        "photographer": "John Doe",
                    }
                )
            }
        ]
    }

    with patch.object(ebird_helper, "call_tool", return_value=mock_result):
        result = await ebird_helper.get_species_image("norcar")

        assert result is not None
        assert (
            result["image_url"]
            == "https://cdn.download.ams.birds.cornell.edu/api/v1/asset/123/preview"
        )
        assert result["photographer"] == "John Doe"


@pytest.mark.asyncio
async def test_get_species_image_not_found():
    """Test when no image is found for species."""
    from services.backend.app.helpers.mcp_client import ebird_helper

    # Mock the MCP tool call response with no image
    mock_result = {
        "content": [
            {
                "text": json.dumps(
                    {"species_code": "norcar", "image_url": None, "photographer": None}
                )
            }
        ]
    }

    with patch.object(ebird_helper, "call_tool", return_value=mock_result):
        result = await ebird_helper.get_species_image("norcar")

        assert result is None


@pytest.mark.asyncio
async def test_get_species_image_empty_code():
    """Test with empty species code."""
    from services.backend.app.helpers.mcp_client import ebird_helper

    result = await ebird_helper.get_species_image("")

    assert result is None


@pytest.mark.asyncio
async def test_get_species_image_error():
    """Test error handling during image fetch."""
    from services.backend.app.helpers.mcp_client import ebird_helper

    with patch.object(ebird_helper, "call_tool", side_effect=Exception("Network error")):
        result = await ebird_helper.get_species_image("norcar")

        assert result is None  # Should return None on error
