# Birdle AI

**Full-stack AI application built from scratch in ~10 days** -- Natural language -> Claude Sonnet agent -> Regional eBird data + Tavily web search -> Ranked species with images

**Live demo:** https://birdle-ai.vercel.app/ | **Key skills:** React, TypeScript, Python, FastAPI, Anthropic Claude, eBird API, Tavily, Testing, DevOps

---

## Live Demo

**Try it here:** https://birdle-ai.vercel.app/

**Quick test:** "I saw a small red bird with a crest in New York"

**Backend API:** https://bird-id-api.onrender.com

See `DEMO.md` for more test cases and what to expect.

---

## What This Is

An MVP demonstrating agentic bird identification that:
- Takes natural language descriptions
- Uses Claude Sonnet with extended thinking for reasoning and confidence assessment
- Queries live eBird regional data via direct API calls
- Searches the web via Tavily for unusual species or behavioral details
- Returns ranked species with high-quality images
- Works globally (all continents)
- Handles uncertainty gracefully with clarification requests

Built in 6 iterations following MVP-first principles.

## Setup

### Backend

```bash
# Install dependencies
poetry install

# Run the API server
poetry run uvicorn services.backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Run dev server
npm run dev
```

### Pre-commit Hooks

```bash
# Install pre-commit hooks (run once)
poetry run pre-commit install

# Manually run on all files
poetry run pre-commit run --all-files
```

The pre-commit hooks will automatically run:
- Trailing whitespace removal
- End of file fixer
- YAML validation
- Ruff linting & formatting (Python)
- MyPy type checking (Python)
- ESLint (TypeScript/React)

## Environment Variables

Copy `.env.example` to `.env.local` and configure:

Required keys:
- `ANTHROPIC_API_KEY` -- Anthropic API key for Claude Sonnet
- `TAVILY_API_KEY` -- Tavily API key for web search
- `EBIRD_TOKEN` -- eBird API token for regional bird data

Frontend: `frontend/.env.example` -> `frontend/.env.local`

## Development

See `docs/workflow.md` for the iteration-based development process.

## Project Structure

```
birdle/
├── frontend/              # React + Vite SPA
│   ├── src/
│   │   ├── components/   # UI components
│   │   ├── pages/        # Page components
│   │   ├── api/          # API client
│   │   └── types/        # TypeScript types
│   └── package.json
├── services/
│   └── backend/
│       └── app/
│           ├── main.py   # FastAPI entry
│           ├── routes/   # API endpoints
│           ├── schemas/  # Pydantic models
│           └── helpers/  # Bird agent, eBird client, web search
├── configs/              # Configuration templates
├── docs/                 # Documentation
└── pyproject.toml        # Python dependencies
```

## Quality Metrics

**Test Coverage:**
```bash
$ poetry run pytest services/backend/tests/
============================= 44 passed in 20s ==============================
```

**Type Safety:**
```bash
$ poetry run mypy services/backend/app --ignore-missing-imports
Success: no issues found in 13 source files
```

- **44 passing tests** (unit + integration)
- **Full type checking** (TypeScript + mypy)
- **Structured logging** (latency tracking, token usage)
- **Error handling** (retries, timeouts, fallbacks)
- **Content moderation** (Claude built-in safety)
- **Global coverage** (eBird regions worldwide)
- **Pre-commit hooks** (Ruff, Black, ESLint enforced)

## Architecture

```
User Input (React SPA)
    |
FastAPI Backend
    |
    --> Bird ID Agent (Claude Sonnet + extended thinking)
         |
         |-- get_regional_birds  (direct eBird API v2)
         |-- get_species_image   (Macaulay Library)
         |-- web_search          (Tavily API)
    |
Response with species, images, reasoning
```

**Key principles:**
- Agentic design (LLM decides what data to fetch)
- Stateless (scales horizontally)
- Linear request flow (no background workers)
- In-memory only (no database for MVP)
- One retry policy (transient errors)
- Graceful degradation (partial results on failures)

## Tech Stack

**Frontend:**
- React 18 + Vite (fast dev + build)
- TypeScript (type safety)
- Tailwind CSS (rapid styling)

**Backend:**
- FastAPI (async Python, OpenAPI docs)
- Poetry (dependency management)
- Pydantic (data validation)

**AI & Data:**
- Anthropic Claude Sonnet (agentic reasoning with extended thinking)
- Tavily Search API (web search for LLM agents)
- eBird API v2 (Cornell Lab, real-time observations)
- Macaulay Library (Cornell Lab, species images)

**Why these choices:**
- Familiar stack -> fast development
- Minimal abstractions -> easy to understand
- Free/cheap APIs -> low-cost MVP
- Standard protocols -> maintainable

## Deployment

See `docs/deployment-guide.md` for step-by-step instructions.

**Quick summary:**
1. Deploy backend to Render (15 min)
2. Deploy frontend to Vercel (10 min)
3. Test with demo cases (10 min)

Total: ~45 minutes to go live on free tiers.

## Current Status

| Iteration | Feature | Status |
|-----------|---------|--------|
| 1 | End-to-end stub | Complete |
| 2 | eBird + OpenAI integration | Complete |
| 3 | Multi-species + images | Complete |
| 4 | Resilience + observability | Complete |
| 5 | Retro Gen Z UI rebrand | Complete |
| 6 | Agentic architecture (Claude + Tavily) | Complete |

**Ready for:** Production deployment and user testing
