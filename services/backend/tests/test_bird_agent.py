"""Tests for the bird agent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic.types import TextBlock

from services.backend.app.helpers.bird_agent import (
    BirdAgent,
    _execute_tool,
    _parse_response,
    _tool_result_summary,
)


class TestParseResponse:
    def test_valid_json(self):
        response = MagicMock()
        text_block = TextBlock(type="text", text='{"message": "Found it!", "top_species": null}')
        response.content = [text_block]

        result = _parse_response(response)
        assert result["message"] == "Found it!"

    def test_json_in_code_fence(self):
        response = MagicMock()
        text_block = TextBlock(type="text", text='```json\n{"message": "Found it!"}\n```')
        response.content = [text_block]

        result = _parse_response(response)
        assert result["message"] == "Found it!"

    def test_invalid_json_returns_fallback(self):
        response = MagicMock()
        text_block = TextBlock(type="text", text="I think it might be a robin")
        response.content = [text_block]

        result = _parse_response(response)
        assert result["top_species"] is None
        assert "clarification" in result

    def test_skips_non_text_blocks(self):
        response = MagicMock()
        # A non-TextBlock instance (e.g. thinking block) should be skipped
        thinking_block = MagicMock()
        thinking_block.type = "thinking"
        text_block = TextBlock(type="text", text='{"message": "hi"}')
        response.content = [thinking_block, text_block]

        result = _parse_response(response)
        assert result["message"] == "hi"

    def test_empty_content_returns_fallback(self):
        response = MagicMock()
        response.content = []

        result = _parse_response(response)
        assert result["top_species"] is None
        assert "clarification" in result


class TestToolResultSummary:
    def test_regional_birds_summary(self):
        result = {"species_observed": [{"common_name": "Robin"}, {"common_name": "Sparrow"}]}
        summary = _tool_result_summary("get_regional_birds", {"region": "US-NY"}, result)
        assert summary == "Found 2 species in US-NY"

    def test_regional_birds_empty(self):
        result = {"species_observed": []}
        summary = _tool_result_summary("get_regional_birds", {"region": "AU-NSW"}, result)
        assert summary == "Found 0 species in AU-NSW"

    def test_web_search_summary(self):
        result = [{"title": "a"}, {"title": "b"}, {"title": "c"}]
        summary = _tool_result_summary("web_search", {"query": "red bird NY"}, result)
        assert summary == "Found 3 results for 'red bird NY'"

    def test_web_search_empty(self):
        result = []
        summary = _tool_result_summary("web_search", {"query": "rare bird"}, result)
        assert summary == "Found 0 results for 'rare bird'"

    def test_unknown_tool_summary(self):
        summary = _tool_result_summary("unknown_tool", {}, {})
        assert "unknown_tool" in summary.lower() or "completed" in summary.lower()

    def test_error_result_summary(self):
        result = {"error": "timeout"}
        summary = _tool_result_summary("get_regional_birds", {"region": "XX"}, result)
        assert "error" in summary.lower() or "failed" in summary.lower()


class TestExecuteTool:
    async def test_get_regional_birds(self):
        with patch("services.backend.app.helpers.bird_agent.ebird_client") as mock:
            mock.get_regional_birds = AsyncMock(return_value={"species_observed": []})
            result = await _execute_tool("get_regional_birds", {"region": "US-NY"})
            assert result == {"species_observed": []}

    async def test_get_regional_birds_with_days(self):
        with patch("services.backend.app.helpers.bird_agent.ebird_client") as mock:
            mock.get_regional_birds = AsyncMock(return_value={"species_observed": []})
            result = await _execute_tool("get_regional_birds", {"region": "US-NY", "days": 7})
            mock.get_regional_birds.assert_called_once_with(region="US-NY", days=7)
            assert result == {"species_observed": []}

    async def test_web_search(self):
        with patch("services.backend.app.helpers.bird_agent.web_search_client") as mock:
            mock.search = AsyncMock(return_value=[{"title": "Bird info", "content": "details"}])
            result = await _execute_tool("web_search", {"query": "red bird NY"})
            assert len(result) == 1

    async def test_unknown_tool(self):
        result = await _execute_tool("nonexistent", {})
        assert "error" in result

    async def test_tool_error_returns_error_dict(self):
        with patch("services.backend.app.helpers.bird_agent.ebird_client") as mock:
            mock.get_regional_birds = AsyncMock(side_effect=Exception("boom"))
            result = await _execute_tool("get_regional_birds", {"region": "XX"})
            assert "error" in result


class TestIdentifyStream:
    """Tests for the streaming identify method."""

    @pytest.fixture
    def agent(self):
        with patch("services.backend.app.helpers.bird_agent.settings") as mock_settings:
            mock_settings.anthropic_api_key = "test-key"
            return BirdAgent()

    async def _collect_events(self, agent, **kwargs):
        """Collect all events from identify_stream into a list."""
        events = []
        async for event in agent.identify_stream(**kwargs):
            events.append(event)
        return events

    @pytest.mark.asyncio
    async def test_non_bird_query_yields_result_immediately(self, agent):
        """Non-bird queries should yield a status, then result, no thinking."""
        agent._is_bird_related = AsyncMock(return_value=False)

        events = await self._collect_events(
            agent, description="how do I cook pasta", location="Italy"
        )

        types = [e["type"] for e in events]
        assert "status" in types
        assert "result" in types
        assert "thinking" not in types
        result_event = next(e for e in events if e["type"] == "result")
        assert "bird" in result_event["data"]["message"].lower()

    @pytest.mark.asyncio
    async def test_stream_yields_status_events(self, agent):
        """Should yield status events at key pipeline stages."""
        agent._is_bird_related = AsyncMock(return_value=True)

        # Mock the streaming context manager
        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=False)

        # The final message after streaming completes
        final_msg = MagicMock()
        final_msg.stop_reason = "end_turn"
        final_msg.content = [
            MagicMock(
                type="text",
                text='{"message":"hi","top_species":null,"alternate_species":[],"clarification":null}',
            )
        ]
        final_msg.usage = MagicMock(input_tokens=100, output_tokens=50)
        mock_stream.get_final_message = AsyncMock(return_value=final_msg)

        # No streaming events (no thinking, no tool_use)
        async def empty_stream():
            return
            yield  # make it an async generator

        mock_stream.__aiter__ = lambda self: empty_stream()

        agent._client.messages.stream = MagicMock(return_value=mock_stream)

        events = await self._collect_events(agent, description="red bird", location="New York")

        types = [e["type"] for e in events]
        assert types[0] == "status"
        assert "result" in types

    @pytest.mark.asyncio
    async def test_stream_error_yields_error_event(self, agent):
        """Exceptions should yield an error event, not raise."""
        agent._is_bird_related = AsyncMock(return_value=True)
        agent._client.messages.stream = MagicMock(side_effect=Exception("API down"))

        events = await self._collect_events(agent, description="red bird", location="New York")

        types = [e["type"] for e in events]
        assert "error" in types
        error_event = next(e for e in events if e["type"] == "error")
        assert "unexpected error" in error_event["message"].lower()
