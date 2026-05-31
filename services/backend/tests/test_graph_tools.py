"""Tests for graph tool wrappers."""

from unittest.mock import AsyncMock, patch

from services.backend.app.graph import tools


class TestDataTools:
    async def test_get_regional_birds_calls_client(self):
        with patch.object(tools, "ebird_client") as mock:
            mock.get_regional_birds = AsyncMock(
                return_value={"region": "US-NY", "species_observed": [{"common_name": "Robin"}]}
            )
            # @tool wraps the fn; call the underlying coroutine via .ainvoke
            result = await tools.get_regional_birds.ainvoke({"region": "US-NY", "days": 7})
            mock.get_regional_birds.assert_awaited_once_with(region="US-NY", days=7)
            assert result["species_observed"][0]["common_name"] == "Robin"

    async def test_get_species_frequency_calls_client(self):
        with patch.object(tools, "ebird_client") as mock:
            mock.get_species_frequency = AsyncMock(
                return_value={"species_code": "norcar", "abundance": "common"}
            )
            result = await tools.get_species_frequency.ainvoke(
                {"region": "US-NY", "species_code": "norcar", "days": 14}
            )
            assert result["abundance"] == "common"

    async def test_web_search_calls_client(self):
        with patch.object(tools, "web_search_client") as mock:
            mock.search = AsyncMock(return_value=[{"title": "x"}])
            result = await tools.web_search.ainvoke({"query": "rare bird"})
            assert len(result) == 1


def test_tool_name_sets():
    assert tools.DATA_TOOL_NAMES == {
        "get_regional_birds",
        "get_species_frequency",
        "get_regional_rarities",
        "lookup_family",
        "web_search",
    }
    assert "detective_note" in tools.TRACE_TOOL_NAMES
    assert "update_candidates" in tools.TRACE_TOOL_NAMES
    assert tools.TERMINAL_TOOL_NAMES == {
        "submit_identification",
        "ask_user",
        "inconclusive",
    }


def test_executable_tools_excludes_terminal():
    # ToolNode runs data + trace tools only; terminal tools are routing signals.
    names = {t.name for t in tools.EXECUTABLE_TOOLS}
    assert "submit_identification" not in names
    assert "get_regional_birds" in names
    assert "detective_note" in names
