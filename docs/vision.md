## 🦜 Birdle AI Vision ✨🦩

### 1. Technologies
- **Frontend**: React + Vite (TypeScript) with Tailwind for quick styling.
- **Backend**: Single FastAPI app (Python) that serves REST endpoints.
- **AI**: Anthropic Claude Sonnet with extended thinking for agentic reasoning; direct eBird API calls for regional data; Tavily for web search.
- **Tooling**: pnpm for frontend deps, Poetry for Python, uvicorn for local runs.

### 2. Development Principles
- **MVP-first**: ship the smallest slice that validates bird ID flow.
- **KISS**: one service, familiar libraries, minimal abstractions.
- **YAGNI**: defer advanced ranking, analytics, or storage until real demand.
- **Fail fast**: prototype quickly, accept rework, log just enough to learn.
- **Iterate**: deliver thin vertical slices, gather feedback, repeat.

### 3. Project Structure

```
birdle/
├── frontend/             # React + Vite SPA
│   ├── public/
│   └── src/              # components/, pages/
├── services/
│   └── backend/
│       └── app/
│           ├── main.py   # FastAPI entry
│           ├── routes/   # HTTP endpoints
│           ├── schemas/  # Pydantic models
│           └── helpers/  # Bird agent, eBird client, web search
├── configs/
│   └── settings.example.env
├── docs/                 # vision, ADRs, product idea
├── pnpm-workspace.yaml
├── pyproject.toml
└── README.md
```

### 4. Project Architecture

```
┌─────────────┐   HTTPS   ┌──────────────────────────────────┐
│ Browser SPA │ ─────────▶│ FastAPI App (REST)                │
└─────────────┘◀─────────┤                                  │
                          │  Bird ID Agent                    │
                          │  (Claude Sonnet + extended thinking)
                          │     │                             │
                          │     ├── get_regional_birds → eBird API
                          │     ├── get_species_image  → Macaulay Library
                          │     └── web_search         → Tavily API
                          └──────────────────────────────────┘

Observability: structured logging to stdout for manual review.
```

Architecture principles:
- Agentic flow: SPA -> FastAPI -> Claude agent (with tools) -> Response.
- Agent decides what data to fetch (eBird, images, web search).
- Stateless handling: each request contains needed context.
- In-memory only: no database, temporary structures per call.
- Single process: eliminate cross-service coordination.

### 5. Data Model

```python
# Request from SPA
ObservationInput = {
    "description": str,
    "location": str,       # required for regional bird identification
    "observed_at": Optional[str],
}

# Response envelope
RecommendationResponse = {
    "message": str,
    "top_species": Optional[SpeciesInfo],  # scientific/common name, image, range link
    "alternate_species": list[SpeciesInfo],
    "clarification": Optional[str],
}
```

Principles:
- Minimal keys, human-readable values.
- Everything request-scoped; discard after response.
- Optional fields only when they add value for MVP.

### 6. LLM Flow

```python
async def identify_bird(payload: ObservationInput) -> RecommendationResponse:
    messages = [system_prompt, user_message(payload)]
    while tool_calls_remaining > 0:
        response = anthropic.messages.create(
            model="claude-sonnet-4-6",
            messages=messages,
            tools=[get_regional_birds, get_species_image, web_search],
            thinking={"type": "adaptive"},
        )
        if response has tool_use blocks:
            execute tools, append results to messages
        else:
            break  # final answer
    return parse_structured_output(response)
```

Principles:
- Agent decides what data to fetch based on the description.
- Tools: eBird regional data, Macaulay Library images, Tavily web search.
- Max 8 tool calls per request; 60s total timeout.
- One retry on transient API errors.
- Content moderation via Claude's built-in safety + explicit check.

### 7. Monitoring & Logging
- Use Python `logging` to stdout with `info()` per LLM call (tokens, latency).
- Provide `/health` endpoint; cache timestamp in memory.
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
- `settings.py` (Pydantic) loads `ANTHROPIC_API_KEY`, `TAVILY_API_KEY`, `EBIRD_TOKEN`, `FRONTEND_BASE_URL`.
- `.env.example` documents required keys; copy to `.env.local` for local runs.
- System prompt lives in `services/backend/app/helpers/bird_agent.py`.
- Frontend reads `VITE_API_BASE_URL` from `.env.local` or hosting UI.
