"""Tests for the post-investigate router and confidence_gate guards."""

from langchain_core.messages import AIMessage, ToolMessage

from services.backend.app.graph import routing


def _ai(name=None, args=None, call_id="c1"):
    if name is None:
        return AIMessage(content="just text, no tools")
    return AIMessage(content="", tool_calls=[{"name": name, "args": args or {}, "id": call_id}])


def _tool_result(name, call_id="c1"):
    # ToolMessage carries the tool name so guard-scans can see prior data calls.
    return ToolMessage(content="{}", name=name, tool_call_id=call_id)


class TestRouteAfterInvestigate:
    def test_data_tool_routes_to_tools(self):
        state = {"messages": [_ai("get_regional_birds", {"region": "US-NY"})], "ask_rounds": 0}
        assert routing.route_after_investigate(state) == "tools"

    def test_trace_tool_routes_to_tools(self):
        state = {"messages": [_ai("detective_note", {"message": "hm"})], "ask_rounds": 0}
        assert routing.route_after_investigate(state) == "tools"

    def test_no_tool_call_routes_to_inconclusive(self):
        state = {"messages": [_ai()], "ask_rounds": 0}
        assert routing.route_after_investigate(state) == "inconclusive"

    def test_submit_without_presence_bounces_to_investigate(self):
        state = {
            "messages": [
                _ai("submit_identification", {"top_species": None, "alternate_species": []})
            ],
            "ask_rounds": 0,
        }
        # presence guard unmet -> back to investigate
        assert routing.route_after_investigate(state) == "investigate"

    def test_submit_with_presence_routes_to_submit(self):
        msgs = [
            _ai("get_regional_birds", {"region": "US-NY"}, call_id="c0"),
            _tool_result("get_regional_birds", call_id="c0"),
            _ai(
                "submit_identification",
                {
                    "top_species": {"species_code": "norcar", "confidence": "medium"},
                    "alternate_species": [],
                },
                call_id="c1",
            ),
        ]
        assert routing.route_after_investigate({"messages": msgs, "ask_rounds": 0}) == "submit_id"

    def test_high_confidence_without_frequency_bounces(self):
        msgs = [
            _ai("get_regional_birds", {"region": "US-NY"}, call_id="c0"),
            _tool_result("get_regional_birds", call_id="c0"),
            _ai(
                "submit_identification",
                {
                    "top_species": {"species_code": "norcar", "confidence": "high"},
                    "alternate_species": [],
                },
                call_id="c1",
            ),
        ]
        # presence met, but no frequency check for norcar -> bounce
        assert routing.route_after_investigate({"messages": msgs, "ask_rounds": 0}) == "investigate"

    def test_high_confidence_with_frequency_routes_to_submit(self):
        msgs = [
            _ai("get_regional_birds", {"region": "US-NY"}, call_id="c0"),
            _tool_result("get_regional_birds", call_id="c0"),
            _ai(
                "get_species_frequency", {"region": "US-NY", "species_code": "norcar"}, call_id="c1"
            ),
            _tool_result("get_species_frequency", call_id="c1"),
            _ai(
                "submit_identification",
                {
                    "top_species": {"species_code": "norcar", "confidence": "high"},
                    "alternate_species": [],
                },
                call_id="c2",
            ),
        ]
        assert routing.route_after_investigate({"messages": msgs, "ask_rounds": 0}) == "submit_id"

    def test_ask_user_under_cap_routes_to_ask(self):
        state = {"messages": [_ai("ask_user", {"question": "crest?"})], "ask_rounds": 0}
        assert routing.route_after_investigate(state) == "ask_user"

    def test_ask_user_at_cap_routes_to_inconclusive(self):
        state = {"messages": [_ai("ask_user", {"question": "crest?"})], "ask_rounds": 2}
        assert routing.route_after_investigate(state) == "inconclusive"

    def test_data_budget_exhausted_forces_terminal(self):
        # 12 data calls already; another data-tool call is forced to inconclusive
        msgs = []
        for i in range(routing.MAX_DATA_TOOL_CALLS):
            msgs.append(_ai("get_regional_birds", {"region": "US-NY"}, call_id=f"c{i}"))
            msgs.append(_tool_result("get_regional_birds", call_id=f"c{i}"))
        msgs.append(_ai("get_regional_birds", {"region": "US-NY"}, call_id="cX"))
        assert (
            routing.route_after_investigate({"messages": msgs, "ask_rounds": 0}) == "inconclusive"
        )

    def test_submit_guard_failure_inconclusive_after_bounce_cap(self):
        # Presence guard unmet, but we've already bounced the cap -> stop looping.
        state = {
            "messages": [
                _ai("submit_identification", {"top_species": None, "alternate_species": []})
            ],
            "ask_rounds": 0,
            "gate_bounces": routing.MAX_GATE_BOUNCES,
        }
        assert routing.route_after_investigate(state) == "inconclusive"

    def test_submit_guard_failure_bounces_while_under_cap(self):
        # One bounce so far (< cap) -> still bounce back to investigate.
        state = {
            "messages": [
                _ai("submit_identification", {"top_species": None, "alternate_species": []})
            ],
            "ask_rounds": 0,
            "gate_bounces": routing.MAX_GATE_BOUNCES - 1,
        }
        assert routing.route_after_investigate(state) == "investigate"
