# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Birdle AI is an LLM-powered bird identification app. Users describe a bird sighting (description + location + optional time), and the backend identifies likely species using an agentic architecture: Anthropic Claude Sonnet with extended thinking, direct eBird API calls for regional observation data, and Tavily web search for additional context.

## Architecture

**Stack:** React 18 + Vite + Tailwind (frontend) | FastAPI + Python 3.11 + Pydantic v2 (backend) | Anthropic Claude + eBird API + Tavily

**Request flow (LangGraph, turn-based sessions):**
```
React SPA → FastAPI POST /api/identify/stream → guardrail node (Haiku: is it a bird?)
  → resolve_inputs (Haiku location→eBird region parse, eBird-validated; may ask via interrupt)
  → investigate (Claude Sonnet + extended thinking) ⇄ tools (LangGraph ToolNode)
       ├── get_regional_birds / get_species_frequency / get_regional_rarities
       ├── lookup_family                       ← direct httpx → eBird
       └── web_search(query)                   ← Tavily API
  → confidence_gate (grounding guards) → { submit_id | ask_user | inconclusive }
  → SSE stream → (on ask_user) POST /api/identify/resume {session_id, user_message}
                 (after a result)  POST /api/identify/continue {session_id, user_message}
                                   → follow_up node → investigate (refine or answer)
```

- Turn-based per session: an in-memory LangGraph `InMemorySaver` keyed by `session_id`
  (30-min idle TTL, no DB; a restart drops in-flight sessions and the client starts fresh).
- Human-in-the-loop via `interrupt()`: the agent pauses to ask a clarifying or
  disambiguation question and resumes with the user's reply.
- Follow-up turns: after a conclusion, `/api/identify/continue` re-enters the graph
  at the `follow_up` node (appends the message, routes to `investigate`); the agent
  refines the ID or answers. Terminal nodes (`submit_id`/`inconclusive`) close their
  own tool call so the transcript stays valid across turns.
- Mandatory grounding guards: regional presence checked before concluding;
  frequency checked before HIGH confidence.
- The graph lives in `services/backend/app/graph/` (`state`, `prompts`, `tools`,
  `nodes`, `routing`, `build`, `runner`). `runner.py` adapts LangGraph's multi-mode
  `astream` into the SSE event protocol.
- eBird access via direct httpx calls in `services/backend/app/helpers/ebird_client.py`;
  species photos come from the public Wikimedia REST API (Macaulay's API was retired)
- Web search via Tavily in `services/backend/app/helpers/web_search.py`
- Settings loaded via Pydantic BaseSettings from `.env.local`
- TypeScript interfaces and Pydantic schemas must stay aligned

## Common Commands

### Frontend (from `frontend/`)
```bash
npm run dev          # Dev server on port 5173
npm run build        # TypeScript compile + Vite production build
npm run lint         # ESLint (--max-warnings 0)
```

### Backend (from project root)
Dependencies are managed with **uv** (Python 3.14, pinned in `.python-version`).
Run `uv sync` once to create `.venv` and install deps + the `dev` group.
```bash
uv sync                                                # Create/refresh .venv from uv.lock
uv run uvicorn services.backend.app.main:app --reload --host 0.0.0.0 --port 8000
uv run pytest services/backend/tests/ -v               # Run all tests
uv run pytest services/backend/tests/test_identify.py -v  # Single test file
uv run ruff check services/                            # Lint
uv run black --check services/                         # Format check
uv run mypy services/backend/app --ignore-missing-imports  # Type check
uv run pre-commit run --all-files                      # All pre-commit hooks
```

### CI (GitHub Actions)
Backend: uv sync → ruff → black → mypy → pytest. Frontend: npm ci → tsc build → eslint.

## Development Workflow

This project follows a strict iteration-based workflow (see `docs/workflow.md`):

1. **Plan first** — read `docs/tasklist.md` + `docs/vision.md`, draft a proposal, **wait for approval**
2. **Branch** — create `feat/iteration-X-<description>` from main
3. **Implement** — follow `docs/conventions.md`, scope changes to the iteration only
4. **Test** — all tests must pass; run pre-commit hooks
5. **PR** — never merge directly to main; always create a Pull Request
6. **Transition** — ask before starting the next iteration

## Key Conventions

- `docs/vision.md` is the authoritative blueprint — update it before making architectural changes
- MVP-first, KISS, YAGNI — no new services, queues, storage, or framework swaps without vision approval
- Never skip pre-commit hooks (`--no-verify`), never commit with failing tests, never bypass CI
- One-retry policy for transient API errors; graceful degradation when eBird/Tavily fails
- 120s total timeout per identification request; turn-based, multi-turn agent runs
- Structured logging: operation, latency_ms, token counts, status
- Commit format: `feat: iteration X — <short goal>` (adjust type as needed)

## Environment Variables

Copy `.env.example` to `.env.local`. Required keys: `ANTHROPIC_API_KEY`, `TAVILY_API_KEY`, `EBIRD_TOKEN`. See `.env.example` for all options.
