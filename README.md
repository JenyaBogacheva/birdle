# Bird-ID MVP

LLM-powered bird identification assistant that helps users identify bird species from plain-text descriptions.

## Overview

This application combines:
- **React + Vite** frontend with Tailwind CSS
- **FastAPI** backend with integrated MCP helpers for eBird API
- **OpenAI ChatGPT** (GPT-4o/GPT-4.1) for natural language understanding
- Linear request flow: SPA ➝ FastAPI ➝ LLM/eBird ➝ Response

## Quick Start

### Prerequisites

- **Node.js** 18+ with pnpm installed (`npm install -g pnpm`)
- **Python** 3.11+ with Poetry installed (`pip install poetry`)
- **OpenAI API key**
- **eBird API token** (optional for MVP iteration 1)

### Setup

1. **Clone and install dependencies**:
   ```bash
   # Install Python dependencies
   poetry install
   
   # Install frontend dependencies
   pnpm install
   ```

2. **Configure environment**:
   ```bash
   # Copy example environment file
   cp .env.example .env.local
   
   # Edit .env.local and add your API keys
   ```

3. **Run locally**:
   ```bash
   # Terminal 1: Start backend (from project root)
   poetry run uvicorn services.backend.app.main:app --reload --port 8000
   
   # Terminal 2: Start frontend (from project root)
   cd frontend && pnpm dev
   ```

4. **Access the app**:
   - Frontend: http://localhost:5173
   - Backend API: http://localhost:8000
   - API docs: http://localhost:8000/docs

## Project Structure

```
birds/
├── frontend/              # React + Vite SPA
│   ├── public/
│   └── src/
│       ├── components/
│       └── pages/
├── services/
│   └── backend/
│       └── app/
│           ├── main.py    # FastAPI entry point
│           ├── routes/    # API endpoints
│           ├── schemas/   # Pydantic models
│           └── mcp/       # eBird MCP helpers
├── configs/
│   └── prompts/           # LLM prompt templates
├── docs/
│   ├── vision.md          # Technical vision (READ THIS FIRST)
│   ├── tasklist.md        # Iteration plan
│   ├── conventions.md     # Coding standards
│   ├── workflow.md        # Development process
│   └── adr/               # Architecture Decision Records
├── .env.example           # Environment variables template
├── pyproject.toml         # Python dependencies (Poetry)
└── pnpm-workspace.yaml    # pnpm workspace config
```

## Documentation

- **[Vision](docs/vision.md)** - Authoritative technical blueprint
- **[Task List](docs/tasklist.md)** - Iteration plan and progress
- **[Conventions](docs/conventions.md)** - Development standards
- **[Workflow](docs/workflow.md)** - Iteration process
- **[ADRs](docs/adr/)** - Architecture decisions

## Development Principles

- **MVP-first**: Ship the smallest useful slice
- **KISS**: Straightforward code, familiar libraries
- **YAGNI**: Defer features until proven necessary
- **Iterate**: Thin vertical slices with fast feedback

## Current Status

**Phase**: Foundation setup complete
**Next**: Iteration 1 - Stubbed end-to-end flow

See [tasklist.md](docs/tasklist.md) for detailed iteration plan.

## Tech Stack

- **Frontend**: React 18, Vite, TypeScript, Tailwind CSS
- **Backend**: Python 3.11+, FastAPI, Pydantic, uvicorn
- **AI**: OpenAI ChatGPT API (GPT-4o/GPT-4.1)
- **Data**: eBird API via MCP helpers
- **Package Management**: pnpm (frontend), Poetry (backend)

## Deployment

- **Backend**: Fly.io (Docker container)
- **Frontend**: Vercel (static hosting)
- Manual CLI deploys initially; CI/CD to be added later

See [ADR-005](docs/adr/adr-005-deployment-strategy.md) for details.

## License

Private project - All rights reserved

