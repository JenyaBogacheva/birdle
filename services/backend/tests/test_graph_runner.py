"""Tests for the SSE runner that adapts graph astream output."""

from unittest.mock import AsyncMock, MagicMock

from services.backend.app.graph.runner import BirdGraphRunner


async def _aiter(items):
    for it in items:
        yield it


class TestRunnerTranslation:
    async def test_emits_session_id_first_then_custom_and_result(self):
        # Scripted astream: a custom UI event, a thinking token, then it ends.
        fake_graph = MagicMock()
        fake_graph.astream = MagicMock(
            return_value=_aiter(
                [
                    ("custom", {"type": "detective_note", "message": "Hmm."}),
                    (
                        "messages",
                        (
                            MagicMock(content="thinking", tool_call_chunks=[]),
                            {"langgraph_node": "investigate"},
                        ),
                    ),
                    (
                        "updates",
                        {
                            "submit_id": {
                                "final": {
                                    "message": "done",
                                    "top_species": None,
                                    "alternate_species": [],
                                }
                            }
                        },
                    ),
                ]
            )
        )
        # get_state returns the final payload after streaming.
        snap = MagicMock()
        snap.next = ()
        snap.values = {"final": {"message": "done", "top_species": None, "alternate_species": []}}
        fake_graph.aget_state = AsyncMock(return_value=snap)

        runner = BirdGraphRunner(graph=fake_graph)
        events = [
            e
            async for e in runner.run_stream(
                session_id="s1", description="red bird", location="NY", observed_at=None
            )
        ]

        types = [e["type"] for e in events]
        assert types[0] == "session_id"
        assert events[0]["session_id"] == "s1"
        assert "detective_note" in types
        assert "result" in types

    async def test_interrupt_emits_awaiting_input_and_no_result(self):
        fake_graph = MagicMock()
        fake_graph.astream = MagicMock(
            return_value=_aiter(
                [
                    (
                        "updates",
                        {
                            "__interrupt__": (
                                MagicMock(
                                    value={"reason": "disambiguate_species", "question": "crest?"}
                                ),
                            )
                        },
                    ),
                ]
            )
        )
        snap = MagicMock()
        snap.next = ("ask_user",)  # paused
        fake_graph.aget_state = AsyncMock(return_value=snap)

        runner = BirdGraphRunner(graph=fake_graph)
        events = [
            e
            async for e in runner.run_stream(
                session_id="s2", description="bird", location="NY", observed_at=None
            )
        ]
        types = [e["type"] for e in events]
        assert "awaiting_input" in types
        assert "result" not in types
        aw = next(e for e in events if e["type"] == "awaiting_input")
        assert aw["reason"] == "disambiguate_species"
        assert aw["question"] == "crest?"
