# ADR-005: Fly.io Container Deployment with Vercel Frontend Hosting

- **Status**: Accepted
- **Context**: We need a straightforward deployment path for the MVP without managing complex infrastructure. The backend and MCP run on FastAPI, and the frontend is a static Vite build. Team members have limited hosting experience, so the process must be beginner-friendly.
- **Decision**: Package backend and MCP as a single Docker image runnable via `docker compose` locally. Deploy the container to Fly.io using its CLI with one shared-CPU instance in a single region. Host the static frontend on Vercel, configured to target the Fly backend URL. Manage secrets through Fly and Vercel dashboards, and trigger deployments via GitHub Actions after lint/tests pass. Document a Render.com fallback if Docker/Fly become blockers.
- **Consequences**: Deployment requires only basic CLI usage and avoids manual server management while enabling quick rollbacks. We rely on Fly.io and Vercel services, and deploying both layers requires coordinating two platforms, but the overhead stays minimal for MVP needs.
