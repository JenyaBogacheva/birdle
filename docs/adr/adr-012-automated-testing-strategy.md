# ADR-012: Automated Testing Strategy for MVP

**Status:** Accepted

**Date:** 2025-11-18

## Context

Iteration 1 initially relied on manual testing (curl, browser). CI expected automated tests but found none. We need a testing strategy that validates functionality without over-engineering the MVP.

## Alternatives

1. **Manual testing only** - No automated tests, rely on QA
2. **Unit tests only** - Test individual functions in isolation
3. **Integration tests only** - Test full request/response cycle
4. **Full test pyramid** - Unit + integration + E2E tests
5. **API contract tests** - Focus on endpoint behavior

## Decision

Write **API integration tests** for each backend endpoint using FastAPI TestClient:
- Test happy path with valid input
- Test validation (required fields, error responses)
- Test response structure matches schemas
- Focus on API contracts, not internal implementation

Start with backend tests. Add frontend tests in later iterations.

## Reasoning

- **MVP-appropriate**: Tests what matters without overengineering
- **Fast to run**: Integration tests with TestClient are milliseconds
- **High value**: Validates actual API behavior users experience
- **Catches regressions**: Changes that break API are immediately detected
- **CI gate**: Prevents merging broken endpoints
- **Simple to write**: Straightforward test structure using pytest
- **Lesson learned**: CI failure taught us to write tests upfront

## Consequences

### Positive
- API contract validated automatically
- Refactoring safe (tests catch breaks)
- CI enforces quality gate (0 tests → 4 tests passing)
- New endpoints must include tests (convention established)
- Documentation value (tests show expected behavior)

### Negative
- No frontend unit tests yet (deferred to later iterations)
- No E2E tests across full stack (acceptable for MVP)
- Test maintenance overhead (must update when API changes)

### Test coverage (Iteration 1)
- ✅ Health endpoint validation
- ✅ Identify endpoint happy path
- ✅ Request validation (required fields)
- ✅ Minimal payload acceptance

### Future additions
- Frontend component tests (if complexity grows)
- E2E tests with Playwright (if critical paths emerge)
- Performance tests (if response time matters)
