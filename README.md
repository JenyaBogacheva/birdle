# Birdle 🐦✨

AI-powered bird identification • describe a bird, get instant results • React + FastAPI + OpenAI

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

## Current Status

✅ **Iteration 1:** Stubbed end-to-end flow complete
- Backend API with `/health` and `/api/identify` endpoints
- React frontend with form and results display
- Full roundtrip tested

🚧 **Next:** Iteration 2 - eBird MCP integration
