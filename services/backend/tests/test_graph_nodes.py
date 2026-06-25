"""Tests for graph nodes."""

from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

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


def _fake_region(region_code, lat=None, lng=None, precision="point", display_name=None):
    """Helper: return a resolve_region-style dict."""
    return {
        "region_code": region_code,
        "lat": lat,
        "lng": lng,
        "precision": precision,
        "display_name": display_name,
    }


class TestResolveInputs:
    async def test_resolves_valid_region(self):
        with (
            patch.object(
                nodes,
                "resolve_region",
                new=AsyncMock(return_value=_fake_region("US-NY", lat=40.7, lng=-74.0)),
            ),
            patch.object(nodes, "_parse_date", new=AsyncMock(return_value="recent")),
        ):
            out = await nodes.resolve_inputs(
                {
                    "description": "red bird",
                    "location": "New York",
                    "observed_at": None,
                    "ask_rounds": 0,
                }
            )
        assert out["region"] == "US-NY"
        assert out["observed_window"] == "recent"

    async def test_missing_location_soft_ask_then_skip(self):
        # location empty -> interrupt; user "skips" -> proceed with region=None
        with (
            patch.object(nodes, "interrupt", return_value="skip") as intr,
            patch.object(
                nodes,
                "resolve_region",
                new=AsyncMock(return_value=_fake_region(None, precision="none")),
            ),
            patch.object(nodes, "_parse_date", new=AsyncMock(return_value="recent")),
        ):
            out = await nodes.resolve_inputs(
                {"description": "red bird", "location": "", "observed_at": None, "ask_rounds": 0}
            )
        intr.assert_called_once()
        assert out["region"] is None
        assert out["ask_rounds"] == 1

    async def test_ask_cap_proceeds_without_asking(self):
        # at the cap, do not interrupt even if region unresolved
        with (
            patch.object(nodes, "interrupt") as intr,
            patch.object(
                nodes,
                "resolve_region",
                new=AsyncMock(return_value=_fake_region(None, precision="none")),
            ),
            patch.object(nodes, "_parse_date", new=AsyncMock(return_value="recent")),
        ):
            out = await nodes.resolve_inputs(
                {
                    "description": "x",
                    "location": "gibberish",
                    "observed_at": None,
                    "ask_rounds": prompts.MAX_ASK_ROUNDS,
                }
            )
        intr.assert_not_called()
        assert out["region"] is None

    async def test_context_is_not_a_second_system_message(self):
        # The transcript already starts with SystemMessage(SYSTEM_PROMPT); resolve_inputs
        # must NOT emit another SystemMessage, or Anthropic rejects the transcript with
        # "multiple non-consecutive system messages". The resolved context is a human-turn note.
        with (
            patch.object(
                nodes,
                "resolve_region",
                new=AsyncMock(return_value=_fake_region("US-NY", lat=40.7, lng=-74.0)),
            ),
            patch.object(nodes, "_parse_date", new=AsyncMock(return_value="recent")),
        ):
            out = await nodes.resolve_inputs(
                {
                    "description": "red bird",
                    "location": "New York",
                    "observed_at": None,
                    "ask_rounds": 0,
                }
            )
        ctx = out["messages"][0]
        assert not isinstance(ctx, SystemMessage)
        assert isinstance(ctx, HumanMessage)


class TestInvestigateNode:
    async def test_seeds_system_prompt_and_user_message_first_turn(self):
        fake_model = MagicMock()
        fake_model.ainvoke = AsyncMock(return_value=AIMessage(content="thinking..."))
        with patch.object(nodes, "_agent_model", return_value=fake_model):
            out = await nodes.investigate(
                {"messages": [], "description": "red crested bird", "location": "NY"}
            )
        # The model was called with a SystemMessage seeded first.
        sent = fake_model.ainvoke.call_args.args[0]
        assert isinstance(sent[0], SystemMessage)
        assert any(isinstance(m, HumanMessage) for m in sent)
        # Node returns the AI response to append.
        assert isinstance(out["messages"][0], AIMessage)

    async def test_does_not_reseed_when_messages_exist(self):
        fake_model = MagicMock()
        fake_model.ainvoke = AsyncMock(return_value=AIMessage(content="more"))
        existing = [SystemMessage(content="sys"), HumanMessage(content="hi")]
        with patch.object(nodes, "_agent_model", return_value=fake_model):
            await nodes.investigate({"messages": existing, "description": "x", "location": "y"})
        sent = fake_model.ainvoke.call_args.args[0]
        # No duplicate system seeding: exactly the existing messages are sent.
        assert sent == existing


def _ai_with_tool_call(name, args, call_id="call_1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


class TestAskUserNode:
    async def test_closes_tool_call_and_appends_answer(self):
        ai = _ai_with_tool_call(
            "ask_user", {"reason": "disambiguate_species", "question": "Crest or no crest?"}
        )
        with patch.object(nodes, "interrupt", return_value="It had a crest"):
            out = await nodes.ask_user({"messages": [ai], "ask_rounds": 0})
        kinds = [type(m).__name__ for m in out["messages"]]
        assert "ToolMessage" in kinds  # the ask_user tool call is closed
        assert "HumanMessage" in kinds  # the user's answer is appended
        assert out["ask_rounds"] == 1
        human = next(m for m in out["messages"] if isinstance(m, HumanMessage))
        assert "crest" in human.content.lower()


class TestTerminalNodes:
    async def test_submit_id_maps_args_to_final(self):
        ai = _ai_with_tool_call(
            "submit_identification",
            {
                "message": "It's a Northern Cardinal.",
                "top_species": {
                    "scientific_name": "Cardinalis cardinalis",
                    "common_name": "Northern Cardinal",
                    "species_code": "norcar",
                    "confidence": "high",
                    "reasoning": "red + crest + common",
                },
                "alternate_species": [],
                "clarification": None,
            },
        )
        out = await nodes.submit_id({"messages": [ai]})
        assert out["final"]["top_species"]["common_name"] == "Northern Cardinal"
        assert out["final"]["alternate_species"] == []

    async def test_inconclusive_maps_args_to_final(self):
        ai = _ai_with_tool_call(
            "inconclusive",
            {
                "message": "I can't be sure.",
                "closest_guesses": [{"common_name": "Some Sparrow", "species_code": "x"}],
                "what_would_help": "A photo of the tail.",
            },
        )
        out = await nodes.inconclusive({"messages": [ai]})
        assert out["final"]["top_species"] is None
        assert "what_would_help" not in out["final"]  # folded into clarification/message
        assert "tail" in (out["final"]["clarification"] or "").lower()

    async def test_inconclusive_from_plain_prose_emits_no_tool_message(self):
        # Agent stopped with plain prose (no tool call). Closing a tool call that
        # doesn't exist would orphan a ToolMessage and 400 the next /continue turn.
        ai = AIMessage(content="I'm honestly not sure what this was.")
        out = await nodes.inconclusive({"messages": [ai]})
        assert out["messages"] == []  # nothing to close — no orphan
        assert out["final"]["top_species"] is None

    async def test_terminal_close_matches_the_open_tool_call_id(self):
        ai = _ai_with_tool_call("inconclusive", {"message": "no"}, call_id="abc123")
        out = await nodes.inconclusive({"messages": [ai]})
        assert len(out["messages"]) == 1
        assert out["messages"][0].tool_call_id == "abc123"

    async def test_inconclusive_via_data_budget_does_not_fabricate_a_data_result(self):
        # Reached with a pending DATA tool call (budget spent): the call must be
        # closed to keep the transcript valid, but NOT with a fake data result.
        ai = _ai_with_tool_call(
            "get_species_frequency", {"region": "US-NY", "species_code": "norcar"}, call_id="d1"
        )
        out = await nodes.inconclusive({"messages": [ai]})
        assert len(out["messages"]) == 1
        assert out["messages"][0].tool_call_id == "d1"
        assert out["messages"][0].content != "concluded inconclusive"


def _submit_ai(top, alternates=None, call_id="sub_1"):
    """An AIMessage carrying a submit_identification call (what verify_visual reads)."""
    return _ai_with_tool_call(
        "submit_identification",
        {
            "message": "here's my ID",
            "top_species": top,
            "alternate_species": alternates or [],
        },
        call_id=call_id,
    )


_TIT = {"common_name": "Black-throated Tit", "species_code": "blttit1"}
_SHRIKE = {"common_name": "Burmese Shrike", "species_code": "burshr1"}


class TestVerifyVisual:
    async def test_confirms_when_top_photo_still_fits(self):
        ai = _submit_ai(_TIT, [_SHRIKE])
        verdict = {"best_match": "Black-throated Tit", "top_still_best": True, "note": "fits"}
        with (
            patch.object(
                nodes,
                "_candidate_images",
                new=AsyncMock(
                    return_value=[
                        ("Black-throated Tit", "d1", "image/jpeg"),
                        ("Burmese Shrike", "d2", "image/jpeg"),
                    ]
                ),
            ),
            patch.object(nodes, "_run_visual_verdict", new=AsyncMock(return_value=verdict)),
        ):
            out = await nodes.verify_visual({"messages": [ai], "description": "round brown bird"})
        assert out["visual_verdict"] == "confirm"
        assert "messages" not in out  # nothing appended -> submit_id reads the open call

    async def test_bounces_when_another_candidate_fits_better(self):
        # The shrike case: top pick is the Tit, but the Shrike's photo matches better.
        ai = _submit_ai(_TIT, [_SHRIKE], call_id="sub_xyz")
        verdict = {
            "best_match": "Burmese Shrike",
            "top_still_best": False,
            "note": "Round, hooded, thick hooked bill fits the shrike.",
        }
        with (
            patch.object(
                nodes,
                "_candidate_images",
                new=AsyncMock(
                    return_value=[
                        ("Black-throated Tit", "d1", "image/jpeg"),
                        ("Burmese Shrike", "d2", "image/jpeg"),
                    ]
                ),
            ),
            patch.object(nodes, "_run_visual_verdict", new=AsyncMock(return_value=verdict)),
        ):
            out = await nodes.verify_visual(
                {"messages": [ai], "description": "round brown bird, black head, long tail"}
            )
        assert out["visual_verdict"] == "revise"
        assert out["visual_bounces"] == 1
        # The open submit call is closed with the corrective feedback, by id.
        tm = next(m for m in out["messages"] if isinstance(m, ToolMessage))
        assert tm.tool_call_id == "sub_xyz"
        assert "Burmese Shrike" in tm.content
        assert "Black-throated Tit" in tm.content

    async def test_bounces_when_no_candidate_photo_fits(self):
        # Top is wrong AND nothing shown fits -> bounce the agent to widen / lower
        # confidence, rather than rubber-stamp a contradicted ID.
        ai = _submit_ai(_TIT, [_SHRIKE], call_id="sub_none")
        verdict = {"best_match": "none", "top_still_best": False, "note": "neither fits well"}
        with (
            patch.object(
                nodes,
                "_candidate_images",
                new=AsyncMock(return_value=[("Black-throated Tit", "d1", "image/jpeg")]),
            ),
            patch.object(nodes, "_run_visual_verdict", new=AsyncMock(return_value=verdict)),
        ):
            out = await nodes.verify_visual({"messages": [ai], "description": "x"})
        assert out["visual_verdict"] == "revise"
        assert out["visual_bounces"] == 1
        tm = next(m for m in out["messages"] if isinstance(m, ToolMessage))
        assert tm.tool_call_id == "sub_none"
        assert "does not match" in tm.content
        assert "Black-throated Tit" in tm.content

    async def test_skips_when_no_photo_available(self):
        ai = _submit_ai(_TIT)
        with (
            patch.object(nodes, "_candidate_images", new=AsyncMock(return_value=[])),
            patch.object(nodes, "_run_visual_verdict", new=AsyncMock()) as verdict,
        ):
            out = await nodes.verify_visual({"messages": [ai], "description": "x"})
        assert out["visual_verdict"] == "confirm"
        verdict.assert_not_called()  # never even made the vision call

    async def test_skips_when_bounce_budget_spent(self):
        ai = _submit_ai(_TIT, [_SHRIKE])
        with (
            patch.object(nodes, "_candidate_images", new=AsyncMock()) as imgs,
            patch.object(nodes, "_run_visual_verdict", new=AsyncMock()) as verdict,
        ):
            out = await nodes.verify_visual(
                {"messages": [ai], "visual_bounces": prompts.MAX_VISUAL_BOUNCES}
            )
        assert out["visual_verdict"] == "confirm"
        imgs.assert_not_called()
        verdict.assert_not_called()

    async def test_skips_when_same_species_already_concluded(self):
        ai = _submit_ai(_TIT)
        with (
            patch.object(nodes, "_candidate_images", new=AsyncMock()) as imgs,
            patch.object(nodes, "_run_visual_verdict", new=AsyncMock()) as verdict,
        ):
            out = await nodes.verify_visual({"messages": [ai], "last_species_code": "blttit1"})
        assert out["visual_verdict"] == "confirm"
        imgs.assert_not_called()
        verdict.assert_not_called()

    async def test_degrades_to_confirm_when_vision_call_fails(self):
        ai = _submit_ai(_TIT, [_SHRIKE])
        with (
            patch.object(
                nodes,
                "_candidate_images",
                new=AsyncMock(return_value=[("Black-throated Tit", "d1", "image/jpeg")]),
            ),
            patch.object(
                nodes, "_run_visual_verdict", new=AsyncMock(side_effect=Exception("vision boom"))
            ),
        ):
            out = await nodes.verify_visual({"messages": [ai], "description": "x"})
        assert out["visual_verdict"] == "confirm"  # never block an ID on our own failure
