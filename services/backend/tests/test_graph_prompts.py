"""Tests for graph prompt/constant wiring."""

from services.backend.app.graph import prompts


def test_models_and_budgets():
    assert prompts.GUARDRAIL_MODEL == "claude-haiku-4-5"
    assert prompts.RESOLVE_MODEL == "claude-haiku-4-5"
    assert prompts.AGENT_MODEL == "claude-sonnet-4-6"
    assert prompts.MAX_DATA_TOOL_CALLS == 12  # raised from 8 per spec §7.3
    assert prompts.MAX_ASK_ROUNDS == 2


def test_system_prompt_documents_three_endings():
    sp = prompts.SYSTEM_PROMPT
    assert "submit_identification" in sp
    assert "ask_user" in sp
    assert "inconclusive" in sp


def test_system_prompt_keeps_colloquial_broadening():
    assert "duck" in prompts.SYSTEM_PROMPT.lower()


def test_not_bird_response_shape():
    assert prompts.NOT_BIRD_RESPONSE["top_species"] is None
    assert "message" in prompts.NOT_BIRD_RESPONSE
