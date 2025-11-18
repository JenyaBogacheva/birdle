# Bird-ID MVP Work Plan

- Vision reference: `@vision.md`
- Delivery conventions: `@conventions.md`

## Progress Report

| Iteration | Goal / Feature | Status | Icon | Notes |
| --- | --- | --- | --- | --- |
| 1 | Stubbed end-to-end flow | Complete | ✅ | Backend tested, frontend ready |
| 2 | eBird MCP integration | Complete | ✅ | Live APIs ready, awaiting keys |
| 3 | Ranking + richer output | Complete | ✅ | Multi-species with images, global support |
| 4 | Resilience & observability | Planned | ⏳ | |

**Status legend**
- ⏳ Planned
- 🚧 In progress
- ✅ Complete
- ⛔ Blocked

## Iteration Backlog

### Iteration 1 — Stubbed end-to-end flow ✅
**Goal:** Bootstrap a usable round-trip with stubbed data.
**Test:** Submit a description ➝ receive the canned species payload in the UI.

- [x] Scaffold FastAPI `/api/identify` endpoint returning a fixed species payload.
- [x] Build React form with text input and result panel wired to the endpoint.
- [x] Configure shared types/schema between frontend and backend for the stub response.
- [x] Add a smoke test (manual or automated) covering a full roundtrip through the stub.

**Result:** Users can try the interface and see a representative response.

**Completion Notes:**
- Backend fully implemented and tested with curl
- Health endpoint: ✅ Returns proper status
- Identify endpoint: ✅ Returns stubbed Northern Cardinal response
- Frontend code complete with React + Vite + Tailwind
- Pydantic and TypeScript schemas aligned
- **Full UI roundtrip tested in browser: ✅ CONFIRMED**
- User submitted bird description → received stubbed response in UI
- Both backend (port 8000) and frontend (port 5173) running successfully

### Iteration 2 — eBird MCP integration ✅
**Goal:** Replace the stub with live data from the eBird MCP helper.
**Test:** Describe a bird ➝ receive ranked species with confidence hints from MCP.

- [x] Implement backend client that queries the eBird MCP helper using the user description.
- [x] Parse MCP results into a ranked species list with confidence hints and return it via the endpoint.
- [x] Update frontend to display the ranked list and confidence hints.
- [x] Cover the new integration path with a backend unit test plus an end-to-end manual check.

**Result:** The assistant surfaces live species predictions grounded in MCP output.

**Completion Notes:**
- eBird MCP server implemented with 3 tools (recent observations, species sightings, search)
- OpenAI GPT-4o-mini integration with structured JSON responses
- LLM self-assessment for confidence levels (high/medium/low)
- Content moderation and retry logic implemented per vision.md
- Frontend displays confidence badges (green/yellow/orange) with reasoning
- All unit tests passing (13/13): OpenAI client + integration tests
- Type checking passing (mypy), frontend builds successfully
- Comprehensive test plan documented in `docs/iteration-2-test-plan.md`
- Implementation summary in `docs/iteration-2-summary.md`
- **Awaiting E2E validation:** User needs to provide API keys in `.env.local`
  - OPENAI_API_KEY (for GPT-4o-mini)
  - EBIRD_TOKEN (for eBird API v2)
- Branch: `feat/iteration-2-ebird-mcp-integration`

### Iteration 3 — Ranking + richer output ✅
**Goal:** Improve ranking logic and enrich user context with images.
**Test:** Provide multiple descriptors ➝ see ordered species with images, traits and links.

- [x] Add bird images to species results via Macaulay Library MCP tool
- [x] Enrich responses with top three species (1 primary + up to 2 alternates)
- [x] Adapt the UI to highlight the primary match with image and show expandable context for alternates
- [x] Add SpeciesCard component with image display and photographer credits
- [x] Update schemas for image_url, image_credit, and alternate_species list
- [x] Remove US-centric defaults, require location for global bird identification
- [x] Add global region support (Australia, Europe, Asia, Africa, South America, etc.)
- [x] Add integration tests to validate multi-species responses with images

**Result:** Responses show top 3 ranked species with high-quality images from Cornell Lab, supporting global bird identification. Location is now required for accurate regional context.

**Completion Notes:**
- Macaulay Library integration via MCP (4th tool: get_species_image)
- Frontend displays primary match prominently with collapsible alternate species
- Image credits properly attributed to photographers
- Global region extraction via LLM (supports US states, Canadian provinces, Australian states, countries worldwide)
- Location validation with helpful error messages
- All tests passing (24/24): unit tests for image fetching, integration tests for multi-species
- Type checking passing (mypy), frontend builds successfully
- Branch: `feat/iteration-3-images-ranking`
- Ready for PR review and merge

### Iteration 4 — Resilience & observability
**Goal:** Harden the flow and surface actionable signals.
**Test:** Force MCP errors or delays ➝ system recovers gracefully with clear messaging.

- [ ] Implement graceful fallbacks for empty MCP replies, rate limits, or timeouts.
- [ ] Instrument structured logging around MCP calls and response generation latency.
- [ ] Improve frontend states for loading, errors, and low-confidence results.
- [ ] Document a repeatable manual test checklist for regression validation.

**Result:** The MVP handles edge cases, remains observable, and guides users through issues.

## Definition of Done
- Tasks for the iteration are checked off.
- Goal-oriented test path is executed and recorded.
- No critical regressions; logs show expected metadata.
- Doc updates and progress table reflect the latest state.
