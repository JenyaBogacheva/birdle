# Birdle Evals

Offline evaluation of the bird-ID agent against **real** identification requests
collected verbatim from public birding forums, Reddit and Q&A sites. Each case
pairs a person's natural-language description + location with the species the
source thread ultimately confirmed (the ground truth).

## Files

| File | Purpose |
| --- | --- |
| `cases.jsonl` | The dataset — one real case per line (description, location, time, confirmed species, source URL). |
| `upload_dataset.py` | Push `cases.jsonl` to a LangSmith dataset (`birdle-real-world`). Idempotent. |
| `run_eval.py` | Run the live agent over the dataset and score it with two evaluators. |

## Prerequisites

LangSmith must be configured in `.env.local` (see the root `.env.example`):

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=birdle
```

Real `ANTHROPIC_API_KEY`, `EBIRD_TOKEN` and `TAVILY_API_KEY` are also required —
`run_eval.py` drives the actual agent, so it makes real model + API calls.

Install the eval dependency group once:

```bash
uv sync --group evals
```

## Usage

```bash
# 1. Upload / refresh the dataset in LangSmith
uv run --group evals python evals/upload_dataset.py

# 2. Run the agent over every case and score it
uv run --group evals python evals/run_eval.py
```

The second command prints the experiment name and traces every run to your
LangSmith project. Open the experiment in the LangSmith UI to see per-example
scores and drill into the full agent reasoning + tool calls for any case.

## Evaluators

- **`species_match`** — LLM-as-judge comparing the agent's top species against
  the confirmed species. Synonyms, sex/age qualifiers and common/scientific name
  variants count as a match; different species do not. Skipped (`None`) for cases
  whose correct response is to ask a clarifying question.
- **`clarification_behavior`** — checks the agent asks for more detail exactly on
  the cases a human expert would (vague descriptions) and commits to an ID
  otherwise.

## Adding cases

Append a line to `cases.jsonl` with this shape and re-run `upload_dataset.py`:

```json
{"source": "...", "url": "...", "category": "...", "description": "<verbatim>", "location": "...", "time": null, "confirmed_species": "...", "confidence_in_answer": "high"}
```

Set `confirmed_species` to `"clarification needed"` for cases where the right
behavior is to ask rather than guess.
