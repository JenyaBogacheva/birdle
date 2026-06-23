"""Upload the real-world bird-ID cases to a LangSmith dataset.

Reads ``cases.jsonl`` (one JSON object per line) and creates / refreshes a
LangSmith dataset whose examples drive ``run_eval.py``. Idempotent: re-running
replaces the dataset's examples so the dataset always mirrors the file.

Usage (from the project root, with LangSmith env configured in .env.local):
    uv run --group evals python evals/upload_dataset.py
"""

from __future__ import annotations

import json
import pathlib

from langsmith import Client

# Importing settings exports LANGSMITH_* into os.environ (see app/settings.py),
# which the LangSmith client reads directly.
from services.backend.app.settings import settings

DATASET_NAME = "birdle-real-world"
DATASET_DESCRIPTION = (
    "Real bird-identification requests collected verbatim from public birding "
    "forums, Reddit and Q&A sites. Each example pairs a person's natural-language "
    "description + location with the species the thread confirmed."
)
CASES_PATH = pathlib.Path(__file__).parent / "cases.jsonl"


def _is_clarify(species: str) -> bool:
    """A case whose 'answer' is really 'ask for more detail'."""
    return "clarif" in species.lower()


def load_cases() -> list[dict]:
    lines = CASES_PATH.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def main() -> None:
    if not (settings.langsmith_tracing and settings.langsmith_api_key):
        raise SystemExit(
            "LangSmith is not configured. Set LANGSMITH_TRACING=true and "
            "LANGSMITH_API_KEY in .env.local before uploading."
        )

    client = Client()
    cases = load_cases()
    print(f"Loaded {len(cases)} cases from {CASES_PATH.name}")

    if client.has_dataset(dataset_name=DATASET_NAME):
        dataset = client.read_dataset(dataset_name=DATASET_NAME)
        # Clear existing examples so the dataset mirrors cases.jsonl exactly.
        existing = list(client.list_examples(dataset_id=dataset.id))
        if existing:
            client.delete_examples(example_ids=[ex.id for ex in existing])
            print(f"Cleared {len(existing)} existing examples")
    else:
        dataset = client.create_dataset(dataset_name=DATASET_NAME, description=DATASET_DESCRIPTION)
        print(f"Created dataset '{DATASET_NAME}'")

    client.create_examples(
        dataset_id=dataset.id,
        inputs=[
            {
                "description": c["description"],
                "location": c["location"],
                "time": c.get("time"),
            }
            for c in cases
        ],
        outputs=[
            {
                "expected_species": c["confirmed_species"],
                "expected_action": "clarify" if _is_clarify(c["confirmed_species"]) else "identify",
            }
            for c in cases
        ],
        metadata=[
            {
                "source": c.get("source"),
                "url": c.get("url"),
                "category": c.get("category"),
                "thread_confidence": c.get("confidence_in_answer"),
            }
            for c in cases
        ],
    )
    print(f"Uploaded {len(cases)} examples to dataset '{DATASET_NAME}'.")
    print(f"View at: {settings.langsmith_endpoint.replace('api.', '')}/datasets")


if __name__ == "__main__":
    main()
