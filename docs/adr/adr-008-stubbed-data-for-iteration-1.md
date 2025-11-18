# ADR-008: Stubbed Data for Iteration 1 Validation

**Status:** Accepted

**Date:** 2025-11-18

## Context

Iteration 1 aims to validate the end-to-end architecture before integrating external APIs (eBird MCP, OpenAI). We need to prove the request flow works: frontend → backend → response → UI display.

The question is how to handle the bird identification logic when we don't yet have the eBird MCP or OpenAI integration implemented.

## Alternatives

1. **Mock eBird/OpenAI calls** - Use mocking libraries to simulate real API responses with test data
2. **Connect real APIs immediately** - Full integration with eBird and OpenAI from the start
3. **Return stubbed data** - Hard-coded Northern Cardinal response in the endpoint

## Decision

Return a hard-coded `Northern Cardinal` response from the `/api/identify` endpoint during iteration 1. No external API calls are made.

The stubbed response includes:
- A descriptive message about the bird
- Complete species information (scientific name, common name, range link)
- Proper schema structure matching the final API contract

## Reasoning

- **Fast validation**: Proves architecture without API complexity or credentials
- **Deterministic**: Same input always returns same output, making testing straightforward
- **No external dependencies**: Can test without API keys, network, or service availability
- **Clear transition**: Easy to replace stub with real implementation in iteration 2
- **Follows MVP-first**: Validate the smallest useful slice before adding complexity
- **Schema validation**: Still validates Pydantic models and TypeScript types

## Consequences

### Positive
- Rapid feedback on UI/backend integration
- No dependency on external service availability during development
- Simple to test and demonstrate to stakeholders
- Team can work on frontend/backend in parallel
- Clear baseline for comparing real API performance later

### Negative
- Must remember to replace stub in iteration 2
- Can't test real bird identification logic yet
- Risk of stub diverging from actual API response structure (mitigated by shared schemas)

### Neutral
- Requires explicit test data selection (we chose Northern Cardinal as a well-known, easy-to-validate example)
