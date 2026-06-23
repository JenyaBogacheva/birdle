# Birdle AI

Birdle identifies birds from a plain-language description. You say what you saw and where — *"a small red bird with a crest, in New York this morning"* — and an AI agent investigates real evidence (regional eBird data and the web) to work out what it most likely was. It shows its reasoning, asks a question when one detail would settle it, and keeps the conversation going so you can refine or ask more.

**Live:** https://birdle-ai.vercel.app/

## How it works

Birdle treats identification as an investigation, not a lookup. A LangGraph agent (Claude Sonnet with extended thinking) forms hypotheses from your description, then grounds them against live data before committing:

- A Haiku guardrail bows out if it isn't a bird question; your location is parsed into an eBird region (and the agent asks if it's ambiguous).
- Claude loops between thinking and tools — what's present in your area, how common each candidate is, what rarities have turned up, and the wider web for unusual cases.
- Grounding guards enforce a careful birder's rules: regional presence is checked before concluding, and abundance before any high-confidence claim.
- It concludes by submitting a ranked ID, asking one targeted question, or saying honestly that it can't be sure — and after a result you can ask follow-ups in the same session.

Everything streams to the UI live over SSE — the thinking, each tool call, and the final card with photos.

## Architecture

```
React SPA  ──POST /api/identify/stream (SSE)──►  FastAPI
                                                    │
                                          LangGraph turn-based graph
                                                    │
   guardrail (Haiku: is it a bird?)
     → resolve_inputs (Haiku: location → eBird region; may ask via interrupt)
     → investigate (Claude Sonnet + extended thinking)  ⇄  tools
          ├── get_regional_birds / get_species_frequency / get_regional_rarities
          ├── lookup_family            ← direct httpx → eBird API v2
          └── web_search(query)        ← Tavily API
     → confidence_gate (grounding guards)
          → { submit_id | ask_user | inconclusive }
                                                    │
   SSE stream → species + photos (Wikimedia) + reasoning
   follow-ups:  /api/identify/resume (answer a question) · /continue (refine after a result)
```

- **Turn-based sessions** — LangGraph `InMemorySaver` keyed by `session_id`, 30-min idle TTL, no database; a restart drops in-flight sessions and the client starts fresh.
- **Human-in-the-loop** — the agent pauses via `interrupt()` to ask, and resumes with your reply.
- **Resilient** — one-retry on transient errors, timeouts, and graceful degradation when eBird or Tavily is down.

The graph lives in `services/backend/app/graph/` (`state`, `prompts`, `tools`, `nodes`, `routing`, `build`, `runner`); `runner.py` adapts LangGraph's `astream` into the SSE protocol.

## Tech stack

- **Frontend** — React 18 + Vite, TypeScript, Tailwind, SSE streaming.
- **Backend** — FastAPI (async, Python 3.14), LangGraph, Pydantic v2, uv.
- **AI & data** — Anthropic Claude (Sonnet + Haiku), eBird API v2, Tavily web search, Wikimedia photos.

## Setup

```bash
# Backend — uv installs Python 3.14 automatically
uv sync
uv run uvicorn services.backend.app.main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev   # http://localhost:5173
```

Copy `.env.example` → `.env.local` and set `ANTHROPIC_API_KEY`, `EBIRD_TOKEN`, `TAVILY_API_KEY` (frontend: `frontend/.env.example` → `frontend/.env.local`).

## Development

`docs/vision.md` is the authoritative blueprint; `docs/workflow.md` and `docs/conventions.md` cover the process and conventions. Pre-commit hooks (`uv run pre-commit install`) and CI run Ruff, Black, MyPy, ESLint, and the test suites. Deployment: backend on Render, frontend on Vercel — see `docs/deployment-guide.md`.
