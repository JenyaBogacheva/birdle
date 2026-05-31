# LangGraph + Human-in-the-Loop Bird ID — Design Spec

**Status:** Draft for review.
**Date:** 2026-05-31.
**Supersedes:** `docs/superpowers/specs/2026-03-15-similar-species-comparison-design.md` (the stateless "refinement field + full re-render" approach). Its feature ideas survive (feature-by-feature comparison, follow-up question + options) but are delivered through the turn-based `ask_user` interrupt rather than a stateless re-submit.
**Builds on:** `docs/conversation-state-spec.md` (turn-based session model, decided 2026-05-15).

## 1. Why this exists

Today the bird agent is a single-turn, stateless loop: free-text in (description + location + optional time), structured answer out, streamed over SSE. Two limitations motivate this iteration:

1. **No turn-taking.** The agent can't pause to ask the user a question and resume with their answer. Similar-species disambiguation, missing-input clarification, and "I don't know yet" are all impossible without round-trips that re-run from scratch.
2. **Thin, partly-phantom grounding.** The agent leans on eBird, but only via a presence list whose "observation_count" is always `1` (the `/recent` endpoint returns one row per species). Regional *abundance* reasoning is built on a number that doesn't exist, and the API has far richer signals we don't use.

This iteration ports the agent to **LangGraph** to get first-class turn-taking (human-in-the-loop via `interrupt()`), restructures identification as an explicit-but-non-rigid graph, and substantially deepens eBird usage (real abundance, rarity, taxonomy, seasonality).

## 2. Goals

- Model identification as **one LangGraph** with explicit macro nodes, while preserving the agent's investigative agency (it chooses which tools to call and when).
- Add **human-in-the-loop**: the agent can pause to ask the user a question (missing/garbled inputs, or similar-species disambiguation) and resume with the answer.
- Make eBird grounding **real and mandatory at the gate** — the agent cannot conclude without consulting eBird, and cannot claim high confidence without frequency-checking its pick.
- Support an honest **"I can't identify this"** outcome.
- Be **season-aware**, anchored to when the bird was seen.

## 3. Non-goals (this iteration)

- The hand-drawn detective-notebook **frontend** (rough.js + Caveat). The backend trace tools (`detective_note`, `update_candidates`) stay and are committed; the notebook UI is the **next** iteration.
- Theme redesign (pink → bird/detective aesthetic). Later.
- Geo lat/lng precision queries (model-supplied coordinates). Noted as a future enhancement; v1 uses region codes with county drill-down.
- Multi-session history, user accounts, persistence across restarts, auth. (Per `conversation-state-spec.md`.)
- Replacing the post-agent image-fetch flow (Macaulay images stay fetched by the route handler after the agent concludes).

## 4. Architecture

### 4.1 The graph

```
 guardrail ──▶ resolve_inputs ──▶ investigate ⇄ tools ──▶ confidence_gate
     │              │                  ▲                        │
     │              │                  │                        │
 not a bird     missing/garbled    (loop with eBird +      route on the
 → polite bail  location or date   web_search results)     terminal tool
                → ask_user(...)                             the agent called
                                                                 │
                          ┌──────────────────┬───────────────────┤
                          ▼                  ▼                    ▼
                       submit_id          ask_user          inconclusive
                       (final card)     (interrupt, then    (best guesses +
                                         resume → investigate) what would help)
```

**Nodes:**

| Node | Responsibility |
|------|----------------|
| `guardrail` | Cheap Haiku check: is this about birds? Not a bird → terminal polite bail (existing `NOT_BIRD_RESPONSE`). |
| `resolve_inputs` | Resolve location → eBird region code; interpret `observed_at`. On unparseable/missing inputs that matter, route to `ask_user`. (See §6.) |
| `investigate` | The agent LLM (Claude Sonnet + extended thinking). Reads the description, forms hypotheses, decides which tools to call, emits `detective_note` / `update_candidates`, and ends by calling exactly one terminal tool: `submit_identification`, `ask_user`, or `inconclusive`. |
| `tools` | LangGraph `ToolNode` executing the eBird + web_search tools the agent requested, then looping back to `investigate`. **The agent chooses the tools; this node just runs them.** |
| `confidence_gate` | Conditional edge (routing + guard checks). Reads which terminal tool the agent called and whether mandatory-grounding guards are satisfied. Routes to `submit_id`, `ask_user`, or `inconclusive`, or bounces back to `investigate` if a guard is unmet. |
| `ask_user` | Builds the question payload (reason + question text + options/comparison) and calls `interrupt()`. On resume, appends the user's answer and re-enters the node appropriate to the `reason`: **`resolve_inputs`** for `clarify_location` / `clarify_date` (the answer changes input resolution), **`investigate`** for `disambiguate_species`. Increments `ask_rounds`. |
| `submit_id` | Terminal. Emits the structured identification (existing `submit_identification` shape). |
| `inconclusive` | Terminal. Emits closest low-confidence guesses + concrete "what would help" suggestions. |

**Non-rigidity:** the agent may loop `investigate ⇄ tools` any number of times in any order, and may bounce from `ask_user` back into more investigation. The graph enforces only the hard truths (§5).

### 4.2 What stays the agent's call vs. the graph's

- **Agent:** which tools to call, in what order, how many times; when it's done investigating; which of the three endings to take; what to compare and what to ask the human.
- **Graph:** that it's a bird; that eBird was consulted before concluding; that high-confidence claims were frequency-checked; that queries are season-anchored; that asking stops after the round cap.

## 5. Mandatory grounding (gate guards)

The `confidence_gate` enforces these before allowing a terminal route. If a guard fails, it routes back to `investigate` with a system message stating what's required.

1. **Presence before concluding** — at least one regional observation lookup (`get_regional_birds` or county/geo variant) must have run. No identifying "in the dark."
2. **Frequency before HIGH confidence** — `get_species_frequency` must have been called for the top candidate before a `submit_identification` with `confidence: high` is accepted. Medium/low may skip.
3. **Season-anchor** — if `observed_at` resolves to a date, eBird queries use that date's window (recent vs historic, §7.2), and the agent must reconcile "is this plausible *that* time of year?"

**Not a hard gate (prompt nudge only):** rarity cross-check against `recent/notable` so a genuine rarity isn't casually dismissed as a common look-alike.

## 6. Human-in-the-loop & input gaps ("Smart-ask")

`ask_user` is a single reusable interrupt node, parameterized by `reason`:

| `reason` | Trigger | Hardness |
|----------|---------|----------|
| `clarify_location` | Location provided but can't be parsed/verified to a region | **Hard** — we won't ground on an unverifiable region |
| `clarify_location` | Location not provided | **Soft (skippable)** — else description-only ID, reduced confidence, "a location would help" |
| `clarify_date` | Date provided but unparseable (genuinely ambiguous, e.g. "idk, summer?") | **Soft (skippable)** |
| `clarify_date` | Date missing | Don't ask up front; **assume recent**. Ask only if season is decisive to the ID |
| `disambiguate_species` | Agent torn between confusable species | Agent-initiated (calls `ask_user` as its terminal tool) |

**Guiding principle:** ask only when the missing input would change the answer.

**Skippable asks** present a "skip / not sure" option. Choosing it resumes with that signal; the agent proceeds degraded (lower confidence, a note about what would have helped).

**Resume target:** `clarify_location` / `clarify_date` answers resume into `resolve_inputs` (re-parse the new input, which may then proceed or — if still unparseable and not skipped — ask again, subject to the round cap); `disambiguate_species` answers resume into `investigate`.

**Quick-reply chips** are a render-layer concern only: a chip's label becomes the user message on resume. Free text always wins (per `conversation-state-spec` Q1).

**Ask-round cap:** `ask_rounds` is tracked in state. After the cap (default **2**) the gate forces `inconclusive` instead of asking again.

## 7. eBird tool surface (focused set)

All tools live in `ebird_client.py` (extended) and are exposed to the agent as individual tools (max agency). Each maps to one investigative question. Probed live against the v2 API on 2026-05-31; all return HTTP 200.

### 7.1 Tools

| Tool | eBird endpoint | Returns | Notes |
|------|----------------|---------|-------|
| `get_regional_birds(region, days)` | `/data/obs/{region}/recent` | Species present recently (presence list) | **Drop the phantom `observation_count`.** Frame as presence/recency, not abundance. |
| `get_species_frequency(region, species_code, days)` | `/data/obs/{region}/recent/{speciesCode}` | **Bucketed abundance** | Count recent reports, capped at ~400 → bucket: absent(0) / rare(<50) / uncommon(50–300) / common(300+). One call per shortlisted candidate. |
| `get_regional_rarities(region, days)` | `/data/obs/{region}/recent/notable` | Notable/vagrant species reported recently | Vagrant radar; reduces speculative web_search. |
| `lookup_family(species_code or name)` | `/ref/taxonomy/ebird` | family/order for a species | Powers "duck-like → grebes/coots/mergansers" broadening and family-level grouping. Taxonomy is static-ish → fetch once and cache in-process. |
| `web_search(query)` | Tavily (existing) | Text snippets | Unchanged. For truly unusual cases beyond eBird. |

**Supporting (used inside `resolve_inputs`, not necessarily agent-facing tools):**

- `/product/spplist/{region}` — all-time species list (675 for US-NY). Plausibility backstop ("ever recorded here?").
- `/ref/region/list/{regionType}/{parentRegionCode}` + `/ref/region/info/{regionCode}` — drill country → state → county (subnational2) for precision when the user names a specific place.

**Explicitly skipped** (not ID-relevant): `/product/top100`, hotspot endpoints, `/product/stats` activity counts.

### 7.2 Seasonality

- The recency window is itself a seasonal filter: *recent* observations reflect what's around **now**.
- **Anchor to `observed_at`:** if the bird was seen at a date materially different from now, query the **historic** endpoint `/data/obs/{region}/historic/{y}/{m}/{d}` for that date instead of `/recent`. (Verified live: US-NY on Jan 15 → Scarlet Tanager absent, Dark-eyed Junco present — season-correct.)
- **Bucketing caveat:** at state scale over a 14-day window, common species saturate the ~400 cap (Cardinal, Tanager, even Junco all hit it). That's acceptable — the buckets that matter for ID (absent / rare / uncommon / common) still separate cleanly. County drill-down sharpens further when needed.

### 7.3 Cost / budget

- Raise the data-tool budget to **~12** (was 8) to accommodate per-candidate frequency calls (~3–4) + presence + rarities + family lookups.
- Trace-tool budget (`detective_note` / `update_candidates`) unchanged (~20).
- Per-candidate frequency fetch capped at ~400 rows (~100 KB) to bound payload/latency. 60s total timeout unchanged; note it now spans multiple turns' worth of agent work per turn, not across the whole session.

## 8. State model & transport

Per `conversation-state-spec.md`, with LangGraph as the implementation:

- **Session** keyed by `session_id` (uuid), returned to the client and sent back each turn.
- **LangGraph checkpointer:** in-memory (`MemorySaver`-style), keyed by `session_id` as the thread id. 30-minute idle TTL eviction. No DB. A restart drops in-flight sessions; the client recovers by starting fresh. (Move to a durable checkpointer only when we run multiple instances or want cross-deploy durability.)
- **State** (LangGraph state schema): `messages` (the canonical transcript replayed into Claude), `detective_notes`, `candidates` (considering/eliminated), `final`, `region` (resolved), `observed_window` (resolved date/recency), `data_tool_calls`, `trace_tool_calls`, `ask_rounds`. Budgets carry across turns.

**Turn semantics:**

- **Turn 1:** `POST /api/identify/stream` with `{description, location, observed_at?}`. Backend creates a session, runs the graph, streams SSE events including `session_id`. Stream ends when the graph hits an interrupt (`ask_user`) or a terminal node.
- **Turn 2+:** `POST /api/identify/resume` (or `/api/identify/stream` with a `session_id`) carrying `{session_id, user_message}`. Backend resumes the graph from its checkpoint (`Command(resume=...)`), streams new events. Budgets and `ask_rounds` continue.

**Prompt across turns:** lives in `system`, re-sent each turn; prompt caching keeps it cheap (per `conversation-state-spec` Q3).

## 9. SSE event protocol

Existing events stay (`status`, `thinking`, `tool_call`, `tool_result`, `detective_note`, `candidates`, `result`, `done`, `error`). Add:

- `session_id` — emitted once near the start of turn 1 so the client can resume.
- `awaiting_input` — emitted when the graph interrupts at `ask_user`. Payload: `{ reason, question, options?, comparison? }`. Tells the frontend to render a prompt (chips + free-text) and POST the answer to the resume endpoint.
- `inconclusive` result variant — the existing `result` event carries the inconclusive payload (closest guesses + suggestions); no new event type needed, just a populated `message` + low-confidence candidates and empty/normal fields.

Frontend rendering map (per `conversation-state-spec`): user messages → right chat bubble; assistant text → left bubble; `detective_note` → notebook panel (append); `update_candidates` → candidate gallery (replace); `submit_identification` → final card; `awaiting_input` → chat bubble with quick-reply chips + free-text. (Notebook panel and candidate gallery are persistent UI; chat scroll is for turns. The *rendering* of these is the deferred next iteration; this iteration ensures the events flow.)

## 10. Prompt changes

- **Strengthen colloquial broadening** (`bird_agent.py:52`): treat folk names as shape-impressions, explicitly *widen* the candidate net, and treat modifiers as clues ("a duck with a hat" → think hooded merganser / crested waterbirds, not just Anatidae). Make the widening **visible** as a detective note (e.g., *"'Duck'? Maybe — but coots & grebes look the part too. Keeping options open."*).
- **Reframe regional data** away from abundance-by-count toward presence + bucketed frequency + rarity + season.
- **Document the three endings** and when to choose each.
- **Document the ask discipline** (when to interrupt vs. proceed).

## 11. Files

**Modify:**

| File | Changes |
|------|---------|
| `services/backend/app/helpers/bird_agent.py` | Restructure the loop into the LangGraph; add `get_species_frequency`, `get_regional_rarities`, `lookup_family` tool defs + dispatch; add `ask_user` / `inconclusive` terminal tools; raise data budget; prompt updates. |
| `services/backend/app/helpers/ebird_client.py` | Add `get_species_frequency` (bucketed), `get_regional_rarities`, `lookup_family`/taxonomy (cached), historic-date observations, region drill (`region/list`, `region/info`), `spplist`. Drop/relabel `observation_count`. |
| `services/backend/app/routes/identify.py` | Add resume endpoint / `session_id` handling; emit `session_id` + `awaiting_input` events; manage session store + TTL. |
| `services/backend/app/schemas/observation.py` | Add session/turn request schema, `awaiting_input` payload, comparison block (folded from old spec). |
| `frontend/src/api/client.ts`, `frontend/src/types/observation.ts` | `session_id` plumbing, resume call, `awaiting_input` event type. (Minimal — full chat/notebook UI is next iteration.) |
| `pyproject.toml` | Add `langgraph`. |
| `CLAUDE.md`, `docs/vision.md` | Update architecture: stateless single-shot → turn-based sessions; note in-memory session store; LangGraph addition. |

**Create:** possibly `services/backend/app/helpers/bird_graph.py` if the graph definition is large enough to warrant its own module (decide during planning; keep `bird_agent.py` focused).

## 12. Testing

- **Graph routing:** confident → `submit_id`; ambiguous → `ask_user`; stumped/out-of-rounds → `inconclusive`.
- **Guard enforcement:** gate bounces back when presence not checked; blocks HIGH confidence without frequency check; season-anchors when date present.
- **Interrupt/resume:** graph pauses at `ask_user`, resumes with a user message, budgets/`ask_rounds` carry over; ask-round cap forces `inconclusive`.
- **Input gaps:** unparseable location → hard ask; missing location → skippable ask → degraded ID; unparseable date → skippable ask; missing date → assume recent.
- **eBird tools:** frequency bucketing thresholds; rarities parse; family lookup; historic vs recent selection by date; graceful fallback on API error (never raises).
- **Session store:** TTL eviction; unknown/expired `session_id` → clean error guiding a fresh start.
- **Regression:** single-turn happy path still works (turn 1 that concludes without asking).
- Mock `AsyncAnthropic` and eBird httpx as today; extend trace/terminal-tool mocks.

## 13. Open questions (decide during planning)

- **Q1 — Graph module split:** one `bird_agent.py` or split graph into `bird_graph.py`? (Lean: split if it exceeds ~one screenful of node wiring.)
- **Q2 — Resume endpoint shape:** dedicated `/api/identify/resume` vs. overloading `/api/identify/stream` with an optional `session_id`. (Lean: dedicated, clearer contract.)
- **Q3 — "Season decisive" detection:** how does the agent decide a missing date is decisive enough to ask? Heuristic in the prompt (torn between species whose seasonal windows differ) vs. an explicit check. (Lean: prompt heuristic for v1.)
- **Q4 — Frequency cap value:** 400 is a guess; validate the bucket thresholds against a few regions/species during implementation.
- **Q5 — Region resolution fuzziness:** mapping "Brooklyn" → Kings County (US-NY-047) needs fuzzy matching against the `region/list` names. How much effort here vs. letting the LLM emit the county code directly? (Lean: LLM emits, validate against the list.)
