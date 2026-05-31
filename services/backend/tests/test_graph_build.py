"""Integration tests: compiled graph drives happy-path and non-bird bail."""

from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage

import services.backend.app.graph.nodes as N  # noqa: N812  (concise test alias)
from services.backend.app.graph import build


def _ai_tool(name, args, call_id="c1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


class TestCompiledGraph:
    async def test_non_bird_short_circuits_to_final(self):
        graph = build.build_graph()
        with (
            patch.object(N, "_first_text", return_value="NO"),
            patch.object(N, "_raw_anthropic") as raw,
        ):
            raw.messages.create = AsyncMock(return_value=MagicMock())
            state = await graph.ainvoke(
                {
                    "description": "cook pasta",
                    "location": "",
                    "observed_at": None,
                    "messages": [],
                    "ask_rounds": 0,
                    "final": None,
                },
                config={"configurable": {"thread_id": "t-nonbird"}},
            )
        assert state["final"]["top_species"] is None

    async def test_happy_path_reaches_submit(self):
        """guardrail YES -> resolve -> investigate(regional) -> tools -> investigate(submit)."""
        graph = build.build_graph()

        # Scripted agent: first call a data tool, then submit (medium confidence).
        calls = [
            _ai_tool("get_regional_birds", {"region": "US-NY"}, "c0"),
            _ai_tool(
                "submit_identification",
                {
                    "message": "It's a cardinal.",
                    "top_species": {
                        "scientific_name": "Cardinalis cardinalis",
                        "common_name": "Northern Cardinal",
                        "species_code": "norcar",
                        "confidence": "medium",
                        "reasoning": "red + crest",
                    },
                    "alternate_species": [],
                },
                "c1",
            ),
        ]
        fake_model = MagicMock()
        fake_model.ainvoke = AsyncMock(side_effect=calls)

        with (
            patch.object(N, "_first_text", return_value="YES"),
            patch.object(N, "_raw_anthropic") as raw,
            patch.object(
                N,
                "_parse_inputs",
                new=AsyncMock(return_value={"region_code": "US-NY", "observed_window": "recent"}),
            ),
            patch.object(N, "ebird_client") as eb,
            patch.object(N, "_agent_model", return_value=fake_model),
            patch("services.backend.app.graph.tools.ebird_client") as teb,
        ):
            raw.messages.create = AsyncMock(return_value=MagicMock())
            eb.get_region_info = AsyncMock(return_value={"code": "US-NY"})
            teb.get_regional_birds = AsyncMock(
                return_value={
                    "region": "US-NY",
                    "species_observed": [{"common_name": "Northern Cardinal"}],
                }
            )

            state = await graph.ainvoke(
                {
                    "description": "red crested bird",
                    "location": "New York",
                    "observed_at": None,
                    "messages": [],
                    "ask_rounds": 0,
                    "final": None,
                },
                config={"configurable": {"thread_id": "t-happy"}},
            )

        assert state["final"]["top_species"]["common_name"] == "Northern Cardinal"
