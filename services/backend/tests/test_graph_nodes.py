"""Tests for graph nodes."""

from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage

from services.backend.app.graph import nodes


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
