# ADR-011: Type-Aligned Schemas Across Frontend and Backend

**Status:** Accepted

**Date:** 2025-11-18

## Context

The frontend (TypeScript) and backend (Python) need to communicate via JSON. We must ensure type safety on both sides and prevent runtime errors from schema mismatches.

## Alternatives

1. **No shared contract** - Define types independently, hope they match
2. **OpenAPI code generation** - Generate TypeScript from FastAPI OpenAPI spec
3. **Manual schema alignment** - Write Pydantic and TypeScript types that mirror each other
4. **Shared schema language** - Use protobuf or similar DSL

## Decision

Manually maintain aligned Pydantic (backend) and TypeScript (frontend) schemas:
- Backend: `services/backend/app/schemas/observation.py`
- Frontend: `frontend/src/types/observation.ts`

Schemas must be updated together. CI validates both sides independently.

## Reasoning

- **Explicit control**: Full control over both type definitions
- **Simple for MVP**: No code generation tooling needed
- **Type safety on both sides**: Pydantic validates at runtime, TypeScript at compile time
- **Easy to review**: Changes visible in both files during PR
- **FastAPI integration**: Pydantic models used directly in endpoint definitions
- **No build step complexity**: No code generation or additional tools

## Consequences

### Positive
- Strong type safety on both frontend and backend
- Clear API contract visible in code
- FastAPI auto-generates OpenAPI docs from Pydantic models
- TypeScript compilation catches frontend type errors
- Easy to understand and modify

### Negative
- Must manually keep schemas in sync (risk of divergence)
- Duplicate type definitions (DRY violation)
- No automatic validation that types match between layers
- Developer must remember to update both sides

### Mitigation
- Convention: Update schema files together in same commit
- Integration tests validate request/response structure
- Pre-commit hooks catch TypeScript compilation errors
- CI validates both sides independently

### Future consideration
- If schemas grow complex, consider OpenAPI code generation
- For now, simplicity wins over automation
