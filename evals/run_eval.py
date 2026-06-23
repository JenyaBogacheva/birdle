"""Run the Birdle agent over the real-world dataset and score it in LangSmith.

The target drives the actual LangGraph agent (the same ``BirdGraphRunner`` the
API uses) for each example's first turn, then two evaluators score the result:

  * species_match    — LLM-as-judge: does the predicted species match the
                       species the source thread confirmed? (synonyms, sex/age
                       qualifiers and common/scientific variants count as a match)
  * clarification    — did the agent ask for more detail exactly when the case
                       calls for it (and commit to an ID when it shouldn't)?

Every run is also traced to the configured LangSmith project, so you can open any
example and inspect the full agent reasoning + tool calls.

Usage (from the project root, with real API keys + LangSmith in .env.local):
    uv run --group evals python evals/run_eval.py
"""

from __future__ import annotations

import asyncio
import json
import uuid

from anthropic import AsyncAnthropic
from langsmith import aevaluate

# Importing the runner pulls in settings, which exports LANGSMITH_* to the env.
from services.backend.app.graph.runner import BirdGraphRunner
from services.backend.app.settings import settings

DATASET_NAME = "birdle-real-world"
JUDGE_MODEL = "claude-haiku-4-5-20251001"

_runner = BirdGraphRunner()
_judge = AsyncAnthropic(api_key=settings.anthropic_api_key)


async def birdle_target(inputs: dict) -> dict:
    """Run one fresh identification turn and summarise what the agent did."""
    session_id = f"eval-{uuid.uuid4().hex[:12]}"
    predicted_species: str | None = None
    confidence: str | None = None
    asked_clarification = False

    async for event in _runner.run_stream(
        session_id,
        description=inputs["description"],
        location=inputs.get("location") or "",
        observed_at=inputs.get("time"),
    ):
        kind = event.get("type")
        if kind == "awaiting_input":
            asked_clarification = True
        elif kind == "result":
            data = event.get("data") or {}
            top = data.get("top_species") or {}
            predicted_species = top.get("common_name")
            confidence = top.get("confidence")
            if data.get("clarification") and not predicted_species:
                asked_clarification = True

    return {
        "predicted_species": predicted_species,
        "confidence": confidence,
        "asked_clarification": asked_clarification,
    }


async def species_match(outputs: dict, reference_outputs: dict) -> dict:
    """LLM-as-judge: predicted species == thread-confirmed species?"""
    if reference_outputs.get("expected_action") == "clarify":
        # No single right answer — scored by the clarification evaluator instead.
        return {"key": "species_match", "score": None, "comment": "clarification case"}

    predicted = outputs.get("predicted_species")
    expected = reference_outputs.get("expected_species")
    if not predicted:
        return {"key": "species_match", "score": 0, "comment": "no species returned"}

    prompt = (
        "You are grading a bird-identification system against a known answer.\n"
        f'Confirmed species (ground truth): "{expected}"\n'
        f'System\'s predicted species: "{predicted}"\n\n'
        "Do these refer to the same bird? Treat as a MATCH if they are the same "
        "species despite differences in sex/age qualifiers (e.g. 'female'), "
        "common/scientific naming, or regional name variants (e.g. 'Common "
        "Blackbird' vs 'Eurasian Blackbird'). Treat distinct species as NO MATCH "
        "even if closely related.\n"
        'Respond with ONLY a JSON object: {"match": true|false, "reason": "<brief>"}'
    )
    msg = await _judge.messages.create(
        model=JUDGE_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in msg.content if block.type == "text").strip()
    try:
        verdict = json.loads(text[text.find("{") : text.rfind("}") + 1])
        match = bool(verdict.get("match"))
        reason = verdict.get("reason", "")
    except (ValueError, KeyError):
        match, reason = False, f"unparseable judge output: {text[:120]}"
    return {"key": "species_match", "score": 1 if match else 0, "comment": reason}


def clarification_behavior(outputs: dict, reference_outputs: dict) -> dict:
    """Reward asking for detail iff the case is one where a human would ask."""
    should_ask = reference_outputs.get("expected_action") == "clarify"
    did_ask = bool(outputs.get("asked_clarification"))
    ok = did_ask == should_ask
    return {
        "key": "clarification_behavior",
        "score": 1 if ok else 0,
        "comment": f"should_ask={should_ask}, did_ask={did_ask}",
    }


async def main() -> None:
    if not (settings.langsmith_tracing and settings.langsmith_api_key):
        raise SystemExit(
            "LangSmith is not configured. Set LANGSMITH_TRACING=true and "
            "LANGSMITH_API_KEY in .env.local before running the eval."
        )

    results = await aevaluate(
        birdle_target,
        data=DATASET_NAME,
        evaluators=[species_match, clarification_behavior],
        experiment_prefix="birdle",
        # Keep concurrency modest — each example is a full agent run with tools.
        max_concurrency=4,
    )
    print(f"\nExperiment complete: {results.experiment_name}")
    print("Open the experiment in LangSmith to inspect per-example traces + scores.")


if __name__ == "__main__":
    asyncio.run(main())
