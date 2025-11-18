# ADR-001: Adopt React Frontend with FastAPI Backend and MCP Server

- **Status**: Accepted
- **Context**: The bird-ID MVP requires a thin web UI, an orchestrator for LLM calls, and an eBird integration layer. We aim for minimal complexity and quick iteration while meeting the goals in `idea.md` and `vision.md`.
- **Decision**: Use a React + Vite single-page app for the frontend, backed by a Python FastAPI service that proxies OpenAI requests and coordinates flows. Implement the eBird integration as a dedicated FastAPI-based MCP server within the same repository. Manage Python dependencies with Poetry and frontend packages with pnpm.
- **Consequences**: We gain a lightweight stack suitable for rapid development, shared Python utilities across backend and MCP, and straightforward deployment as a single container. The tradeoff is maintaining both React and Python toolchains and coordinating shared dependency updates.

