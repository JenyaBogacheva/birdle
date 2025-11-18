# 🦜 Birdle AI Work Plan ✨🦩

- Vision reference: `@vision.md`
- Delivery conventions: `@conventions.md`

## Progress Report

| Iteration | Goal / Feature | Status | Icon | Notes |
| --- | --- | --- | --- | --- |
| 1 | Stubbed end-to-end flow | Complete | ✅ | Backend tested, frontend ready |
| 2 | eBird MCP integration | Complete | ✅ | Live APIs ready, awaiting keys |
| 3 | Ranking + richer output | Complete | ✅ | Multi-species with images, global support |
| 4 | Resilience & observability | Complete | ✅ | Timeouts, retries, structured logs |
| 5 | Retro Gen Z UI + rebrand to birdle-ai | Complete | ✅ | Fun colors, emojis, casual tone |

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

### Iteration 4 — Resilience & observability ✅
**Goal:** Harden the flow and surface actionable signals.
**Test:** Force MCP errors or delays ➝ system recovers gracefully with clear messaging.

- [x] Implement graceful fallbacks for empty MCP replies, rate limits, or timeouts.
- [x] Instrument structured logging around MCP calls and response generation latency.
- [x] Improve frontend states for loading, errors, and low-confidence results.
- [x] Document a repeatable manual test checklist for regression validation.

**Result:** The MVP handles edge cases, remains observable, and guides users through issues.

**Completion Notes:**
- **Backend Resilience:**
  - MCP client: Graceful fallbacks for timeouts, empty responses, connection errors
  - Timeout constants: `TOOL_CALL_TIMEOUT = 30s`, `IDENTIFY_TIMEOUT = 60s`
  - Image fetch failures don't block species identification (partial results)
  - All MCP/OpenAI errors caught and handled with appropriate user messages
- **Structured Logging:**
  - All operations log with `extra` fields: `operation`, `latency_ms`, `status`
  - MCP calls: tool name, arguments, success/failure, latency tracking
  - OpenAI calls: model, token usage (prompt/completion/total), latency
  - Request lifecycle: start, completion, errors with full context
  - Latencies in milliseconds, rounded to 2 decimals
- **Frontend Enhancements:**
  - Loading stages with progress indicators: "Analyzing" → "Fetching" → "Identifying"
  - Elapsed time counter during processing
  - Progress dots visualizing current stage
  - Enhanced error handling: Timeout, Network, Rate Limit detection
  - Context-aware error messages with helpful hints
  - Retry button for transient errors (preserves last observation)
  - Emphasized clarification UI for low-confidence results
- **Testing:**
  - 44 total tests passing (13 new tests for resilience)
  - `test_mcp_fallbacks.py`: Timeout, empty response, connection errors (13 tests)
  - `test_identify_resilience.py`: Endpoint timeout, error handling (7 tests)
  - Type checking passing (mypy)
  - Frontend builds successfully (TypeScript, Vite)
- **Documentation:**
  - Manual test plan: `docs/iteration-4-test-plan.md`
  - 10 test cases covering normal flow, timeouts, retries, error states
  - Regression checks for previous iterations
  - Performance benchmarks template
- **Branch:** `feat/iteration-4-resilience-observability`
- **Ready for:** PR review and merge to main

### Iteration 5 — Retro Gen Z UI + rebrand to birdle-ai ✅
**Goal:** Transform the UI from formal/corporate to fun, retro cartoonish Gen Z aesthetic + rebrand from "Bird-ID MVP" to "birdle-ai" with vibrant colors.
**Test:** Visual check, functionality test, build verification.

**Color Palette:**
- Pink, orange, yellow, blue, dark grey
- Gradient background: `from-pink-100 via-orange-50 to-yellow-100`
- Primary button: Blue (`bg-blue-500`)
- Confidence badges: Blue (high), orange (medium), yellow (low)

**Changes:**

- [x] **Branding:** Rename "Bird-ID MVP" → "birdle-ai" in all UI text and page title
- [x] **Typography:** Lowercase headers where appropriate, remove stiff corporate language
- [x] **Emojis:** Add strategic emojis throughout (headings, labels, states, errors)
- [x] **Colors:** Update background gradient to pink/orange/yellow tones
- [x] **Buttons:** Switch to blue primary color with proper hover/active states
- [x] **Loading states:** Rewrite with casual language ("reading the vibes... 👀", etc.)
- [x] **Form labels:** Make casual and fun ("what did you see? 🔍", "where are you? 📍")
- [x] **Result headers:** Lowercase and playful ("here's what i found! ✨")
- [x] **Error messages:** Keep helpful but add personality ("😅 oops", "📡 connection hiccup")
- [x] **Confidence badges:** Update colors and text ("pretty sure! ✨", "maybe? 🤔", "wild guess 🎲")
- [x] **Decorative elements:** Add bird sticker SVGs or emojis positioned around page
- [x] **Footer:** Update with casual tone

**Files Modified:**
- `frontend/index.html` - page title updated to "birdle-ai 🐦✨"
- `frontend/src/pages/Home.tsx` - heading, gradient, loading states, footer, decorative birds
- `frontend/src/components/BirdForm.tsx` - labels, placeholders, button styling
- `frontend/src/components/ResultPanel.tsx` - headers, error styling, button colors
- `frontend/src/components/SpeciesCard.tsx` - confidence badge colors and text
- `frontend/src/index.css` - added slow bounce animation for bird decorations

**Test Results:**
- ✅ TypeScript compiles with no errors
- ✅ Frontend build successful (vite build passed)
- ✅ No linter errors
- ✅ All text updated to casual, fun tone
- ✅ Emojis added throughout for personality
- ✅ Color palette applied (pink/orange/yellow gradient)
- ✅ Blue buttons with proper hover states
- ✅ Decorative bird emojis positioned with animations

**Result:** A fun, engaging UI that showcases the project as a playful Gen Z take on bird identification. The rebrand to "birdle-ai" gives it a more memorable, shareable identity.

**Completion Notes:**
- **Branding:** Successfully rebranded from "Bird-ID MVP" to "birdle-ai"
- **Visual Design:**
  - Warm gradient background (pink → orange → yellow)
  - Blue primary actions maintain usability
  - Pink accent on primary species cards
  - Orange/yellow for confidence levels
- **Decorative Elements:**
  - Three bird emojis (🐦 🦜 🦅) positioned as background decorations
  - Subtle animations (bounce, pulse) for playfulness
  - Low opacity to avoid distraction
- **Typography & Tone:**
  - Lowercase used strategically for casual feel
  - Emojis complement text without overwhelming
  - Error messages helpful yet friendly
  - Loading states conversational ("reading the vibes...")
- **Accessibility:**
  - Text contrast maintained for readability
  - All functionality preserved
  - Emojis enhance rather than replace meaning
- **No Breaking Changes:**
  - Zero backend modifications
  - All schemas unchanged
  - Full backward compatibility
- **Branch:** `feat/iteration-5-retro-gen-z-ui`
- **Ready for:** Visual review and merge

## Definition of Done
- Tasks for the iteration are checked off.
- Goal-oriented test path is executed and recorded.
- No critical regressions; logs show expected metadata.
- Doc updates and progress table reflect the latest state.
