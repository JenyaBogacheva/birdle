"""Tests for graph nodes."""

from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage

from services.backend.app.graph import nodes, prompts


class TestGuardrailNode:
    async def test_bird_query_passes_through(self):
        with patch.object(nodes, "_raw_anthropic") as mock_client:
            resp = MagicMock()
            resp.content = [MagicMock(text="YES")]
            mock_client.messages.create = AsyncMock(return_value=resp)
            # make the text block isinstance(TextBlock) check pass
            with patch.object(nodes, "_first_text", return_value="YES"):
                out = await nodes.guardrail({"description": "a red bird with a crest"})
        assert out.get("final") is None

    async def test_non_bird_sets_final(self):
        with patch.object(nodes, "_raw_anthropic") as mock_client:
            mock_client.messages.create = AsyncMock(return_value=MagicMock())
            with patch.object(nodes, "_first_text", return_value="NO"):
                out = await nodes.guardrail({"description": "how to cook pasta"})
        assert out["final"]["top_species"] is None
        assert "bird" in out["final"]["message"].lower()

    async def test_guardrail_fails_open(self):
        with patch.object(nodes, "_raw_anthropic") as mock_client:
            mock_client.messages.create = AsyncMock(side_effect=Exception("boom"))
            out = await nodes.guardrail({"description": "anything"})
        assert out.get("final") is None  # fail open -> proceed


class TestResolveInputs:
    async def test_resolves_valid_region(self):
        with patch.object(nodes, "_parse_inputs", new=AsyncMock(
            return_value={"region_code": "US-NY", "observed_window": "recent"}
        )), patch.object(nodes, "ebird_client") as eb:
            eb.get_region_info = AsyncMock(return_value={"code": "US-NY"})
            out = await nodes.resolve_inputs(
                {"description": "red bird", "location": "New York", "observed_at": None, "ask_rounds": 0}
            )
        assert out["region"] == "US-NY"
        assert out["observed_window"] == "recent"

    async def test_missing_location_soft_ask_then_skip(self):
        # location empty -> interrupt; user "skips" -> proceed with region=None
        with patch.object(nodes, "interrupt", return_value="skip") as intr, \
             patch.object(nodes, "_parse_inputs", new=AsyncMock(
                 return_value={"region_code": None, "observed_window": "recent"}
             )):
            out = await nodes.resolve_inputs(
                {"description": "red bird", "location": "", "observed_at": None, "ask_rounds": 0}
            )
        intr.assert_called_once()
        assert out["region"] is None
        assert out["ask_rounds"] == 1

    async def test_ask_cap_proceeds_without_asking(self):
        # at the cap, do not interrupt even if region unresolved
        with patch.object(nodes, "interrupt") as intr, \
             patch.object(nodes, "_parse_inputs", new=AsyncMock(
                 return_value={"region_code": None, "observed_window": "recent"}
             )):
            out = await nodes.resolve_inputs(
                {"description": "x", "location": "gibberish", "observed_at": None,
                 "ask_rounds": prompts.MAX_ASK_ROUNDS}
            )
        intr.assert_not_called()
        assert out["region"] is None
