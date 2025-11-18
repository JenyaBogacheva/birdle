"""
Tests for MCP client fallback scenarios and resilience.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.backend.app.helpers.mcp_client import eBirdMCPHelper


@pytest.fixture
def mcp_helper():
    """Create a fresh MCP helper instance for testing."""
    return eBirdMCPHelper()


@pytest.mark.asyncio
async def test_get_recent_observations_timeout(mcp_helper):
    """Test that timeout in MCP call returns empty fallback."""
    # Mock the call_tool method to timeout
    with patch.object(mcp_helper, "call_tool", new=AsyncMock(side_effect=asyncio.TimeoutError)):
        result = await mcp_helper.get_recent_observations(region="US-NY", days=14)

        # Should return empty fallback structure
        assert result["region"] == "US-NY"
        assert result["days_searched"] == 14
        assert result["total_observations"] == 0
        assert result["species_observed"] == []


@pytest.mark.asyncio
async def test_get_recent_observations_runtime_error(mcp_helper):
    """Test that RuntimeError in MCP call returns empty fallback."""
    # Mock the call_tool method to raise RuntimeError
    with patch.object(
        mcp_helper, "call_tool", new=AsyncMock(side_effect=RuntimeError("MCP server closed"))
    ):
        result = await mcp_helper.get_recent_observations(region="AU-NSW", days=7)

        # Should return empty fallback structure
        assert result["region"] == "AU-NSW"
        assert result["days_searched"] == 7
        assert result["total_observations"] == 0
        assert result["species_observed"] == []


@pytest.mark.asyncio
async def test_get_recent_observations_empty_response(mcp_helper):
    """Test that empty MCP response returns empty fallback."""
    # Mock the call_tool method to return empty content
    mock_result = {"content": []}

    with patch.object(mcp_helper, "call_tool", new=AsyncMock(return_value=mock_result)):
        result = await mcp_helper.get_recent_observations(region="GB", days=14)

        # Should return empty fallback structure
        assert result["region"] == "GB"
        assert result["days_searched"] == 14
        assert result["total_observations"] == 0
        assert result["species_observed"] == []


@pytest.mark.asyncio
async def test_get_recent_observations_malformed_json(mcp_helper):
    """Test that malformed JSON in MCP response returns empty fallback."""
    # Mock the call_tool method to return malformed JSON
    mock_result = {"content": [{"text": "not valid json {{{"}]}

    with patch.object(mcp_helper, "call_tool", new=AsyncMock(return_value=mock_result)):
        result = await mcp_helper.get_recent_observations(region="CA-ON", days=14)

        # Should return empty fallback structure
        assert result["region"] == "CA-ON"
        assert result["days_searched"] == 14
        assert result["total_observations"] == 0
        assert result["species_observed"] == []


@pytest.mark.asyncio
async def test_get_recent_observations_success(mcp_helper):
    """Test successful observation retrieval with proper logging."""
    # Mock successful response
    mock_result = {
        "content": [
            {
                "text": (
                    '{"region": "US-NY", "days_searched": 14, "total_observations": 100, '
                    '"species_observed": [{"common_name": "Northern Cardinal", '
                    '"species_code": "norcar", "observation_count": 10}]}'
                )
            }
        ]
    }

    with patch.object(mcp_helper, "call_tool", new=AsyncMock(return_value=mock_result)):
        result = await mcp_helper.get_recent_observations(region="US-NY", days=14)

        # Should return parsed data
        assert result["region"] == "US-NY"
        assert result["days_searched"] == 14
        assert result["total_observations"] == 100
        assert len(result["species_observed"]) == 1
        assert result["species_observed"][0]["common_name"] == "Northern Cardinal"


@pytest.mark.asyncio
async def test_get_species_image_timeout(mcp_helper):
    """Test that timeout in image fetch returns None gracefully."""
    # Mock the call_tool method to timeout
    with patch.object(mcp_helper, "call_tool", new=AsyncMock(side_effect=asyncio.TimeoutError)):
        result = await mcp_helper.get_species_image(species_code="norcar")

        # Should return None (image is optional)
        assert result is None


@pytest.mark.asyncio
async def test_get_species_image_runtime_error(mcp_helper):
    """Test that RuntimeError in image fetch returns None gracefully."""
    # Mock the call_tool method to raise RuntimeError
    with patch.object(
        mcp_helper, "call_tool", new=AsyncMock(side_effect=RuntimeError("Connection lost"))
    ):
        result = await mcp_helper.get_species_image(species_code="norcar")

        # Should return None (image is optional)
        assert result is None


@pytest.mark.asyncio
async def test_get_species_image_empty_response(mcp_helper):
    """Test that empty image response returns None."""
    # Mock the call_tool method to return empty content
    mock_result = {"content": []}

    with patch.object(mcp_helper, "call_tool", new=AsyncMock(return_value=mock_result)):
        result = await mcp_helper.get_species_image(species_code="norcar")

        # Should return None
        assert result is None


@pytest.mark.asyncio
async def test_get_species_image_no_image_found(mcp_helper):
    """Test that no image found returns None."""
    # Mock the call_tool method to return response without image
    mock_result = {"content": [{"text": '{"image_url": null, "photographer": null}'}]}

    with patch.object(mcp_helper, "call_tool", new=AsyncMock(return_value=mock_result)):
        result = await mcp_helper.get_species_image(species_code="unknown")

        # Should return None
        assert result is None


@pytest.mark.asyncio
async def test_get_species_image_success(mcp_helper):
    """Test successful image retrieval."""
    # Mock successful image response
    mock_result = {
        "content": [
            {"text": '{"image_url": "https://example.com/bird.jpg", "photographer": "John Doe"}'}
        ]
    }

    with patch.object(mcp_helper, "call_tool", new=AsyncMock(return_value=mock_result)):
        result = await mcp_helper.get_species_image(species_code="norcar")

        # Should return image data
        assert result is not None
        assert result["image_url"] == "https://example.com/bird.jpg"
        assert result["photographer"] == "John Doe"


@pytest.mark.asyncio
async def test_get_species_image_no_species_code(mcp_helper):
    """Test that empty species code returns None immediately."""
    result = await mcp_helper.get_species_image(species_code="")

    # Should return None without calling MCP
    assert result is None


@pytest.mark.asyncio
async def test_call_tool_timeout_handling(mcp_helper):
    """Test that call_tool handles timeout properly with structured logging."""
    # Mock the process to simulate timeout
    mock_process = MagicMock()
    mock_process.stdin = MagicMock()
    mock_process.stdout = MagicMock()
    mock_process.stdin.write = MagicMock()
    mock_process.stdin.drain = AsyncMock()
    mock_process.stdout.readline = AsyncMock(side_effect=asyncio.TimeoutError)

    mcp_helper.process = mock_process
    mcp_helper._started = True

    with pytest.raises(RuntimeError, match="Timeout calling MCP tool"):
        await mcp_helper.call_tool("test_tool", {"arg": "value"})


@pytest.mark.asyncio
async def test_call_tool_connection_closed(mcp_helper):
    """Test that call_tool handles closed connection properly."""
    # Mock the process to simulate closed connection
    mock_process = MagicMock()
    mock_process.stdin = MagicMock()
    mock_process.stdout = MagicMock()
    mock_process.stdin.write = MagicMock()
    mock_process.stdin.drain = AsyncMock()
    mock_process.stdout.readline = AsyncMock(return_value=b"")  # Empty response = closed

    mcp_helper.process = mock_process
    mcp_helper._started = True

    with pytest.raises(RuntimeError, match="MCP server closed connection"):
        await mcp_helper.call_tool("test_tool", {"arg": "value"})
