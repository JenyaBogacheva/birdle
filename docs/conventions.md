# Development Conventions — Bird-ID MVP

`@vision.md` is the authoritative blueprint. Update it first, then code.

## Development Principles (`@vision.md` §2)

- ✅ Deliver the smallest useful slice (`MVP-first`) with straightforward code (`KISS`).
- ✅ Cut ideas that are not justified by real feedback (`YAGNI`).
- ✅ Iterate fast: small PRs, quick reviews, visible logging of outcomes.

## Stack & Tooling (`@vision.md` §1)

- ✅ Use only the documented stack: React + Vite + Tailwind, FastAPI + Poetry, OpenAI ChatGPT, eBird MCP helper.
- ✅ Manage deps with pnpm (frontend) and Poetry (backend).
- ❌ Don't introduce parallel toolchains or alternative package managers.

## Architecture Guardrails (`@vision.md` §3–4,6)

- ✅ Keep the linear request flow: SPA ➝ FastAPI ➝ LLM/eBird ➝ response.
- ✅ Stay stateless and in-memory; no background workers or external DBs.
- ✅ Maintain the one-app layout; extend directories exactly where `@vision.md` places them.
- ✅ Route all LLM/eBird access through the shared helpers; implement the one-retry policy and moderation check there.

## Code Structure (`@vision.md` §3,5)

- ✅ Mirror the documented tree: frontend components/pages under `frontend/src/`, backend routers under `services/backend/app/routes/`, schemas under `services/backend/app/schemas/`, prompts in `configs/prompts/`.
- ✅ Keep TypeScript and Pydantic models aligned with the data contracts; expand them only after the vision file is revised.
- ✅ Use descriptive names, single responsibility per module, and avoid circular imports.

## Configuration (`@vision.md` §9–10)

- ✅ Load settings via `settings.py` and `.env.local`.
- ❌ Don't hardcode secrets, tokens, or environment-specific paths.
- ✅ Keep `.env.example` current when adding required keys.

## Environment Setup

If the virtual environment appears broken, reinitialize it:
```bash
cd /mnt/nfs/users/jenya/birds && source .venv/bin/activate && (unset VIRTUAL_ENV && poetry -v install) && pre-commit install
```

## Error Handling & Logging (`@vision.md` §6–7)

- ✅ Prefer explicit control flow over clever abstractions; bubble unexpected errors.
- ✅ Log with Python `logging` (info for call metadata, warning for retries/failures); capture request, latency, and token metrics only.
- ✅ Let React error boundaries surface frontend issues; show actionable messages to users.

## Code Quality & Testing

- ✅ Run pre-commit hooks before every commit.
- ✅ All tests must pass before committing or merging.
- ✅ Test frontend builds locally: `cd frontend && npm run build`
- ✅ Test backend type checking: `poetry run mypy services/backend/app --ignore-missing-imports`
- ✅ Write automated tests for each iteration (backend unit tests, integration tests)
- ✅ Test new endpoints and components before considering iteration complete
- ❌ **NEVER** skip pre-commit hooks (`--no-verify`).
- ❌ **NEVER** commit with failing tests.
- ❌ **NEVER** bypass CI checks to merge.
- ❌ **NEVER** merge directly to main - ALWAYS create a Pull Request for review.

## Do

- ✅ Small, readable functions and hooks.
- ✅ One network call per backend endpoint.
- ✅ Focused tests on data transforms, schema validation, and API contracts.
- ✅ Review logs to drive the next iteration.

## Avoid

- ❌ Don't add new services, queues, or storage.
- ❌ Don't swap frameworks or add competing build tooling.
- ❌ Don't create excessive configuration files or global state.
- ❌ Don't expand testing beyond the MVP flow without vision approval.
