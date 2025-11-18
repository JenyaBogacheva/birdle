# ADR-004: Implement Structured Logging and Lightweight LLM Monitoring

- **Status**: Accepted
- **Context**: The MVP relies on LLM responses and MCP interactions. We need visibility into request health, token spend, and moderation outcomes without introducing heavy observability tooling.
- **Decision**: Emit structured JSON logs from backend and MCP with fields such as timestamp, request_id, route, latency_ms, status, moderation result, and llm_cost. Provide a `/health/llm` endpoint exposing last-success timestamp and rolling error rate. Nightly GitHub Actions summarize usage and spend, while a `DEBUG_LLM` flag gates sampling of sanitized prompt/response snippets. Frontend logs only meaningful user-facing errors in production.
- **Consequences**: We obtain actionable insight into LLM performance and costs using tools already in place (stdout logs, simple scripts). Alert thresholds (error >5%, spend over limit) can hook into platform alerts. The tradeoff is limited long-term retention and analytics until we later integrate dedicated monitoring services.

