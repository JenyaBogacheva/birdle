# ADR-006: Configuration via Environment Variables with Cached YAML Prompts

- **Status**: Accepted
- **Context**: The MVP needs to manage API keys, URLs, and prompt variants without introducing heavy configuration tooling. Developers should set up quickly, and deployments across Fly.io/Vercel must remain straightforward.
- **Decision**: Load settings through Pydantic `BaseSettings` classes that pull from environment variables, seeded by a `.env` file in local development. Provide `.env.example` enumerating required keys. Store prompts and tweakable constants as small YAML files in `configs/`, loaded once at startup and cached in memory. Frontend uses Vite’s `import.meta.env` conventions with a single `VITE_API_BASE_URL`.
- **Consequences**: Configuration stays transparent and lightweight; developers copy `.env.example` to get started, and hosting platforms provide built-in env management. We accept manual sync of env vars across platforms and rely on runtime reloads for prompt changes, which is acceptable for the MVP.

