"""Integration tests: compiled graph drives happy-path and non-bird bail."""

from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import Command

import services.backend.app.graph.nodes as N  # noqa: N812  (concise test alias)
from services.backend.app.graph import build, prompts


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
                "resolve_region",
                new=AsyncMock(
                    return_value={
                        "region_code": "US-NY",
                        "lat": 40.7,
                        "lng": -74.0,
                        "precision": "point",
                        "display_name": "New York",
                    }
                ),
            ),
            patch.object(N, "_parse_date", new=AsyncMock(return_value="recent")),
            patch.object(N, "_agent_model", return_value=fake_model),
            patch("services.backend.app.graph.tools.ebird_client") as teb,
            patch.object(N, "ebird_client") as neb,
        ):
            raw.messages.create = AsyncMock(return_value=MagicMock())
            # verify_visual fetches candidate photos; no photo -> it confirms offline.
            neb.get_species_image = AsyncMock(return_value=None)
            teb.get_regional_birds = AsyncMock(
                return_value={
                    "region": "US-NY",
                    "species_observed": [{"common_name": "Northern Cardinal"}],
                }
            )
            teb.get_nearby_birds = AsyncMock(
                return_value={
                    "region": "geo",
                    "total_species": 1,
                    "species_observed": [{"common_name": "Northern Cardinal"}],
                }
            )

            state = await graph.ainvoke(
                {
                    "description": "red crested bird",
                    "location": "New York",
                    "observed_at": None,
                    # Seed the transcript the way runner.run_stream does in production:
                    # SystemMessage(SYSTEM_PROMPT) first, then the observation HumanMessage.
                    "messages": [
                        SystemMessage(content=prompts.SYSTEM_PROMPT),
                        HumanMessage(content="red crested bird in New York"),
                    ],
                    "ask_rounds": 0,
                    "final": None,
                },
                config={"configurable": {"thread_id": "t-happy"}},
            )

        assert state["final"]["top_species"]["common_name"] == "Northern Cardinal"

        # Regression: the transcript reaching the agent must contain exactly one
        # SystemMessage. resolve_inputs previously appended a second (non-consecutive)
        # SystemMessage, which Anthropic rejects ("multiple non-consecutive system messages").
        first_investigate_messages = fake_model.ainvoke.call_args_list[0].args[0]
        assert sum(isinstance(m, SystemMessage) for m in first_investigate_messages) == 1

    async def test_visual_check_bounces_then_re_ids(self):
        """submit(Tit) -> verify_visual prefers the Shrike -> investigate -> submit(Shrike).

        The shrike regression: the agent's first pick is overturned by looking at
        the candidates' reference photos, and the corrected ID reaches submit_id.
        """
        graph = build.build_graph()

        def _submit(common, code, conf="medium"):
            return _ai_tool(
                "submit_identification",
                {
                    "message": f"It's a {common}.",
                    "top_species": {
                        "scientific_name": "x",
                        "common_name": common,
                        "species_code": code,
                        "confidence": conf,
                        "reasoning": "...",
                    },
                    "alternate_species": [
                        {"common_name": "Burmese Shrike", "species_code": "burshr1"}
                    ],
                },
            )

        calls = [
            _ai_tool("get_regional_birds", {"region": "VN-68"}, "c0"),
            _submit("Black-throated Tit", "blttit1"),  # first pick
            _submit("Burmese Shrike", "burshr1"),  # corrected after the photo check
        ]
        fake_model = MagicMock()
        fake_model.ainvoke = AsyncMock(side_effect=calls)

        with (
            patch.object(N, "_first_text", return_value="YES"),
            patch.object(N, "_raw_anthropic") as raw,
            patch.object(
                N,
                "resolve_region",
                new=AsyncMock(
                    return_value={
                        "region_code": "VN-68",
                        "lat": 11.9,
                        "lng": 108.4,
                        "precision": "point",
                        "display_name": "Lâm Đồng",
                    }
                ),
            ),
            patch.object(N, "_parse_date", new=AsyncMock(return_value="recent")),
            patch.object(N, "_agent_model", return_value=fake_model),
            patch.object(N, "ebird_client") as neb,
            patch.object(
                N,
                "_run_visual_verdict",
                new=AsyncMock(
                    return_value={
                        "best_match": "Burmese Shrike",
                        "top_still_best": False,
                        "note": "Round, hooded, hooked bill — the shrike.",
                    }
                ),
            ) as verdict,
            patch("services.backend.app.graph.tools.ebird_client") as teb,
        ):
            raw.messages.create = AsyncMock(return_value=MagicMock())
            neb.get_species_image = AsyncMock(return_value={"image_url": "u", "photographer": "W"})
            neb.fetch_image_b64 = AsyncMock(return_value=("b64", "image/jpeg"))
            teb.get_regional_birds = AsyncMock(
                return_value={"region": "VN-68", "species_observed": [{"common_name": "X"}]}
            )
            teb.get_nearby_birds = AsyncMock(
                return_value={
                    "region": "geo",
                    "total_species": 1,
                    "species_observed": [{"common_name": "X"}],
                }
            )

            state = await graph.ainvoke(
                {
                    "description": "round brown bird, black head, long tail, funny voices",
                    "location": "Lâm Đồng",
                    "observed_at": None,
                    "messages": [
                        SystemMessage(content=prompts.SYSTEM_PROMPT),
                        HumanMessage(content="round brown bird"),
                    ],
                    "ask_rounds": 0,
                    "final": None,
                },
                config={"configurable": {"thread_id": "t-visual"}},
            )

        # The visual check ran once and the corrected ID reached the terminal.
        verdict.assert_awaited_once()
        assert state["final"]["top_species"]["common_name"] == "Burmese Shrike"

    async def test_interrupt_then_resume_round_trip(self):
        """ask_user pauses the compiled graph; Command(resume=...) continues to submit.

        Exercises the real interrupt() + InMemorySaver checkpoint + resume path
        and the ask_user transcript closure (tool_result for the ask_user call).
        """
        graph = build.build_graph()
        config = {"configurable": {"thread_id": "t-resume"}}

        calls = [
            _ai_tool(
                "ask_user",
                {"reason": "disambiguate_species", "question": "Crest or no crest?"},
                "c0",
            ),
            _ai_tool("get_regional_birds", {"region": "US-NY"}, "c1"),
            _ai_tool(
                "submit_identification",
                {
                    "message": "It's a cardinal.",
                    "top_species": {
                        "scientific_name": "Cardinalis cardinalis",
                        "common_name": "Northern Cardinal",
                        "species_code": "norcar",
                        "confidence": "medium",
                        "reasoning": "crest confirmed",
                    },
                    "alternate_species": [],
                },
                "c2",
            ),
        ]
        fake_model = MagicMock()
        fake_model.ainvoke = AsyncMock(side_effect=calls)

        with (
            patch.object(N, "_first_text", return_value="YES"),
            patch.object(N, "_raw_anthropic") as raw,
            patch.object(
                N,
                "resolve_region",
                new=AsyncMock(
                    return_value={
                        "region_code": "US-NY",
                        "lat": 40.7,
                        "lng": -74.0,
                        "precision": "point",
                        "display_name": "New York",
                    }
                ),
            ),
            patch.object(N, "_parse_date", new=AsyncMock(return_value="recent")),
            patch.object(N, "_agent_model", return_value=fake_model),
            patch("services.backend.app.graph.tools.ebird_client") as teb,
            patch.object(N, "ebird_client") as neb,
        ):
            raw.messages.create = AsyncMock(return_value=MagicMock())
            neb.get_species_image = AsyncMock(return_value=None)
            teb.get_regional_birds = AsyncMock(
                return_value={
                    "region": "US-NY",
                    "species_observed": [{"common_name": "Northern Cardinal"}],
                }
            )
            teb.get_nearby_birds = AsyncMock(
                return_value={
                    "region": "geo",
                    "total_species": 1,
                    "species_observed": [{"common_name": "Northern Cardinal"}],
                }
            )

            # Turn 1: runs until the ask_user interrupt.
            first = await graph.ainvoke(
                {
                    "description": "red crested bird",
                    "location": "New York",
                    "observed_at": None,
                    "messages": [],
                    "ask_rounds": 0,
                    "final": None,
                },
                config=config,
            )
            assert "__interrupt__" in first

            # Turn 2: resume -> ask_user closes its tool call -> investigate -> tools -> submit.
            second = await graph.ainvoke(Command(resume="It had a crest"), config=config)

        assert second["final"]["top_species"]["common_name"] == "Northern Cardinal"
