"""Tests for graph nodes."""

from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

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
        with (
            patch.object(
                nodes,
                "_parse_inputs",
                new=AsyncMock(return_value={"region_code": "US-NY", "observed_window": "recent"}),
            ),
            patch.object(nodes, "ebird_client") as eb,
        ):
            eb.get_region_info = AsyncMock(return_value={"code": "US-NY"})
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
                "_parse_inputs",
                new=AsyncMock(return_value={"region_code": None, "observed_window": "recent"}),
            ),
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
                "_parse_inputs",
                new=AsyncMock(return_value={"region_code": None, "observed_window": "recent"}),
            ),
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
