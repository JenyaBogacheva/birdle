# Bird-ID MVP 🐦✨

AI-powered bird identification using natural language • Describe what you saw, get instant species matches with confidence levels

---

## 🚀 Live Demo

**Try it here:** [Add URL after deployment]

**Quick test:** "I saw a small red bird with a crest in New York"

See `DEMO.md` for more test cases and what to expect.

---

## 🎯 What This Is

An MVP demonstrating LLM-powered bird identification that:
- ✅ Takes natural language descriptions
- ✅ Queries live eBird regional data via MCP
- ✅ Uses GPT-4o-mini for reasoning and confidence assessment
- ✅ Returns ranked species with high-quality images
- ✅ Works globally (all continents)
- ✅ Handles uncertainty gracefully with clarification requests

Built in 4 iterations following MVP-first principles.

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

Copy `.env.example` files and configure:

**Backend:** `configs/settings.example.env` → `.env.local`
**Frontend:** `frontend/.env.example` → `frontend/.env.local`

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
│           └── mcp/      # eBird helpers
├── configs/              # Configuration templates
├── docs/                 # Documentation
└── pyproject.toml        # Python dependencies
```

## 📊 Quality Metrics

- ✅ **44 passing tests** (unit + integration)
- ✅ **Full type checking** (TypeScript + mypy)
- ✅ **Structured logging** (latency tracking, token usage)
- ✅ **Error handling** (retries, timeouts, fallbacks)
- ✅ **Content moderation** (OpenAI moderation API)
- ✅ **Global coverage** (eBird regions worldwide)

## 🏗️ Architecture

```
User Input (React SPA)
    ↓
FastAPI Backend
    ↓
├─→ Content Moderation (OpenAI)
├─→ eBird MCP Server (regional bird data)
└─→ GPT-4o-mini (identification + confidence)
    ↓
Response with species, images, reasoning
```

**Key principles:**
- Stateless design (scales horizontally)
- Linear request flow (no background workers)
- In-memory only (no database for MVP)
- One retry policy (transient errors)
- Graceful degradation (partial results on failures)

## 🛠️ Tech Stack

**Frontend:**
- React 18 + Vite (fast dev + build)
- TypeScript (type safety)
- Tailwind CSS (rapid styling)

**Backend:**
- FastAPI (async Python, OpenAPI docs)
- Poetry (dependency management)
- MCP (Model Context Protocol for eBird)
- Pydantic (data validation)

**AI & Data:**
- OpenAI GPT-4o-mini (cost-effective reasoning)
- eBird API v2 (Cornell Lab, real-time observations)
- Macaulay Library (Cornell Lab, species images)

**Why these choices:**
- Familiar stack → fast development
- Minimal abstractions → easy to understand
- Free/cheap APIs → low-cost MVP
- Standard protocols → maintainable

## 🚢 Deployment

See `docs/deployment-guide.md` for step-by-step instructions.

**Quick summary:**
1. Deploy backend to Render (15 min)
2. Deploy frontend to Vercel (10 min)
3. Test with demo cases (10 min)

Total: ~45 minutes to go live on free tiers.

## 📈 Current Status

| Iteration | Feature | Status |
|-----------|---------|--------|
| 1 | End-to-end stub | ✅ Complete |
| 2 | eBird + OpenAI integration | ✅ Complete |
| 3 | Multi-species + images | ✅ Complete |
| 4 | Resilience + observability | ✅ Complete |

**Ready for:** Production deployment and user testing
