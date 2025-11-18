## Bird-ID MVP Vision

### 1. Technologies
- **Frontend**: React + Vite (TypeScript) with Tailwind for quick styling.
- **Backend**: Single FastAPI app (Python) that serves REST + MCP endpoints.
- **AI**: OpenAI ChatGPT (GPT-4o/GPT-4.1) for reasoning; MCP calls the eBird API.
- **Tooling**: pnpm for frontend deps, Poetry for Python, uvicorn for local runs.

### 2. Development Principles
- **MVP-first**: ship the smallest slice that validates bird ID flow.
- **KISS**: one service, familiar libraries, minimal abstractions.
- **YAGNI**: defer advanced ranking, analytics, or storage until real demand.
- **Fail fast**: prototype quickly, accept rework, log just enough to learn.
- **Iterate**: deliver thin vertical slices, gather feedback, repeat.

### 3. Project Structure

```
birds/
├── frontend/             # React + Vite SPA
│   ├── public/
│   └── src/              # components/, pages/
├── services/
│   └── backend/
│       └── app/
│           ├── main.py   # FastAPI entry + MCP wiring
│           ├── routes/   # HTTP endpoints
│           ├── schemas/  # Pydantic models
│           └── mcp/      # eBird helpers
├── configs/
│   ├── prompts/
│   └── settings.example.env
├── docs/                 # vision, ADRs, product idea
├── pnpm-workspace.yaml
├── pyproject.toml
└── README.md
```

### 4. Project Architecture

```
┌─────────────┐   HTTPS   ┌─────────────────────────────┐
│ Browser SPA │ ─────────▶│ FastAPI App (REST + MCP)    │
└─────────────┘◀─────────┤                             │
                          ├─────────┐                   │
                          │ prompt  │                   │
                          ▼         │ MCP call
                ┌──────────────────────┐        ┌───────────────┐
                │ OpenAI ChatGPT API   │◀──────▶│ eBird API     │
                └──────────────────────┘        └───────────────┘

Observability: print key events to stdout for manual review.
```

Architecture principles:
- Linear flow: SPA ➝ FastAPI ➝ LLM/eBird ➝ Response.
- Stateless handling: each request contains needed context.
- In-memory only: no database, temporary structures per call.
- Single process: eliminate cross-service coordination.

### 5. Data Model

```python
# Request from SPA
ObservationInput = {
    "description": str,
    "location": Optional[str],
    "observed_at": Optional[str],
}

# Traits returned by MCP helper
TraitExtraction = {
    "traits": Dict[str, str],
    "confidence": float,
}

# Response envelope
RecommendationResponse = {
    "message": str,
    "top_species": Optional[Dict[str, str]],  # scientific/common name, range link
    "clarification": Optional[str],
}
```

Principles:
- Minimal keys, human-readable values.
- Everything request-scoped; discard after response.
- Optional fields only when they add value for MVP.

### 6. LLM Flow

```python
def identify_bird(payload: ObservationInput) -> RecommendationResponse:
    traits = mcp_lookup(payload["description"], payload.get("location"))
    prompt = build_prompt(payload, traits)

    reply = openai_client.chat(prompt, temperature=0.4)

    if traits.low_confidence():
        return {"message": reply.summary, "clarification": reply.question}

    return {
        "message": reply.summary,
        "top_species": reply.top_species,
    }
```

Principles:
- Short prompt with latest description + trait summary.
- One retry on transient OpenAI errors.
- Basic moderation via OpenAI moderation endpoint before returning text.

### 7. Monitoring & Logging
- Use Python `logging` to stdout with `info()` per LLM call (tokens, latency).
- Provide `/health` that pings eBird and OpenAI once; cache timestamp in memory.
- Review logs manually; defer dashboards until after MVP launch.

### 8. Usage Scenarios
- **Quick match**: user submits a description; system replies with top species + rationale.
- **Clarifier**: low confidence triggers a follow-up question; rerun after answer.
- **No match**: respond politely with tips and external birding resources.

### 9. Deployment
- Local: `pnpm dev` (frontend) and `poetry run uvicorn app.main:app --reload`.
- Hosting: single Fly.io (or Render/Heroku) app running FastAPI; serve SPA from Vercel or static host.
- Manual CLI deploys; automate later.
- Secrets via environment variables locally and in host dashboards.

### 10. Configuration
- `settings.py` (Pydantic) loads `OPENAI_API_KEY`, `EBIRD_TOKEN`, `FRONTEND_BASE_URL`.
- `.env.example` documents required keys; copy to `.env.local` for local runs.
- Prompts stored as plain text under `configs/prompts/` and loaded at startup.
- Frontend reads `VITE_API_BASE_URL` from `.env.local` or hosting UI.
