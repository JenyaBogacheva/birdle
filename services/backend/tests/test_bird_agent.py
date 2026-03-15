"""Tests for the bird agent."""

from unittest.mock import AsyncMock, MagicMock, patch

from anthropic.types import TextBlock

from services.backend.app.helpers.bird_agent import _execute_tool, _parse_response


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
