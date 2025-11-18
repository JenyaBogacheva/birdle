"""
Tests for OpenAI client helper.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import OpenAIError

from services.backend.app.helpers.openai_client import OpenAIClient


@pytest.fixture
def openai_client():
    """Create OpenAI client instance."""
    return OpenAIClient()


@pytest.mark.asyncio
async def test_chat_completion_success(openai_client):
    """Test successful chat completion."""
    # Mock response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='{"result": "success"}'))]
    mock_response.usage = MagicMock(total_tokens=100, prompt_tokens=50, completion_tokens=50)

    with patch.object(
        openai_client.client.chat.completions, "create", new=AsyncMock(return_value=mock_response)
    ):
        result = await openai_client.chat_completion(
            system_prompt="You are helpful",
            user_message="Hello",
            response_format={"type": "json_object"},
        )

        assert result == {"result": "success"}


@pytest.mark.asyncio
async def test_chat_completion_plain_text(openai_client):
    """Test chat completion without JSON mode."""
    # Mock response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Plain text response"))]
    mock_response.usage = MagicMock(total_tokens=100, prompt_tokens=50, completion_tokens=50)

    with patch.object(
        openai_client.client.chat.completions, "create", new=AsyncMock(return_value=mock_response)
    ):
        result = await openai_client.chat_completion(
            system_prompt="You are helpful", user_message="Hello"
        )

        assert result == {"content": "Plain text response"}


@pytest.mark.asyncio
async def test_chat_completion_retry_on_transient_error(openai_client):
    """Test retry logic on transient errors."""
    # First call fails, second succeeds
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='{"result": "success"}'))]
    mock_response.usage = MagicMock(total_tokens=100, prompt_tokens=50, completion_tokens=50)

    mock_create = AsyncMock(side_effect=[OpenAIError("Temporary error"), mock_response])

    with patch.object(openai_client.client.chat.completions, "create", new=mock_create):
        result = await openai_client.chat_completion(
            system_prompt="You are helpful",
            user_message="Hello",
            response_format={"type": "json_object"},
        )

        assert result == {"result": "success"}
        assert mock_create.call_count == 2


@pytest.mark.asyncio
async def test_chat_completion_no_retry_on_rate_limit(openai_client):
    """Test no retry on rate limit error."""
    error = OpenAIError("Rate limit")
    error.status_code = 429

    with patch.object(
        openai_client.client.chat.completions, "create", new=AsyncMock(side_effect=error)
    ):
        with pytest.raises(OpenAIError):
            await openai_client.chat_completion(
                system_prompt="You are helpful", user_message="Hello"
            )


@pytest.mark.asyncio
async def test_chat_completion_invalid_json(openai_client):
    """Test handling of invalid JSON response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Not valid JSON"))]
    mock_response.usage = MagicMock(total_tokens=100, prompt_tokens=50, completion_tokens=50)

    with patch.object(
        openai_client.client.chat.completions, "create", new=AsyncMock(return_value=mock_response)
    ):
        with pytest.raises(ValueError, match="Invalid JSON response"):
            await openai_client.chat_completion(
                system_prompt="You are helpful",
                user_message="Hello",
                response_format={"type": "json_object"},
            )


@pytest.mark.asyncio
async def test_moderate_content_safe(openai_client):
    """Test content moderation with safe content."""
    mock_response = MagicMock()
    mock_response.results = [MagicMock(flagged=False)]

    with patch.object(
        openai_client.client.moderations, "create", new=AsyncMock(return_value=mock_response)
    ):
        result = await openai_client.moderate_content("Safe content")
        assert result is True


@pytest.mark.asyncio
async def test_moderate_content_flagged(openai_client):
    """Test content moderation with flagged content."""
    mock_response = MagicMock()
    mock_response.results = [MagicMock(flagged=True, categories=MagicMock(violence=True))]

    with patch.object(
        openai_client.client.moderations, "create", new=AsyncMock(return_value=mock_response)
    ):
        result = await openai_client.moderate_content("Unsafe content")
        assert result is False


@pytest.mark.asyncio
async def test_moderate_content_error_fail_open(openai_client):
    """Test moderation fails open on errors."""
    with patch.object(
        openai_client.client.moderations,
        "create",
        new=AsyncMock(side_effect=OpenAIError("Moderation error")),
    ):
        result = await openai_client.moderate_content("Any content")
        assert result is True  # Fail open
