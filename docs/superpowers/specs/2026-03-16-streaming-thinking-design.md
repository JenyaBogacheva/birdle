# Streaming Responses — Show Agent Thinking in Real-Time

**Date:** 2026-03-16
**Issue:** #11
**Status:** Draft

## Problem

The identification flow takes 10-50 seconds. During this time the frontend shows a spinner with fake hardcoded stage messages ("reading the vibes...", "checking what's around...") on client-side timers. Users have no visibility into what's actually happening.

## Solution

Stream real progress events from the backend to the frontend via Server-Sent Events (SSE). Show a real-time status line and a collapsible "Show thinking" block that reveals Claude's reasoning as it streams in (Claude.ai-style).

## Decisions

- **SSE over WebSockets** — this is request-scoped, one-direction streaming. WebSockets add complexity we don't need. Can revisit for multi-turn refinement (issue #10).
- **Additive endpoint** — new `POST /api/identify/stream` alongside existing `POST /api/identify`. No breaking changes.
- **Result appears all at once** — no progressive reveal of species cards. Thinking block + status line handle the wait; result renders complete when streaming finishes.
- **Thinking block stays after result** — collapses above the result card so users can review reasoning after the fact.
- **Fallback** — if SSE connection fails, frontend falls back to the existing non-streaming endpoint automatically.

## SSE Event Protocol

Each SSE message is a JSON object with a `type` field:

```
data: {"type": "status", "message": "Checking birds in AU-NSW..."}

data: {"type": "thinking", "content": "The description mentions bright red plumage..."}

data: {"type": "tool_call", "tool": "get_regional_birds", "input": {"region": "AU-NSW"}}

data: {"type": "tool_result", "tool": "get_regional_birds", "summary": "Found 38 species"}

data: {"type": "result", "data": { ...RecommendationResponse JSON... }}

data: {"type": "error", "message": "Request timed out after 90 seconds."}

data: {"type": "done"}
```

| Event type | When emitted | Payload |
|---|---|---|
| `status` | Pipeline stage transitions | `{"message": string}` |
| `thinking` | Claude's reasoning streams in | `{"content": string}` — text delta, append to build full text |
| `tool_call` | Agent requests a tool | `{"tool": string, "input": object}` |
| `tool_result` | Tool returns | `{"tool": string, "summary": string}` |
| `result` | Identification complete | `{"data": RecommendationResponse}` |
| `error` | Failure | `{"message": string}` |
| `done` | Stream complete | No payload — sent after `result` or `error` as explicit completion signal |

The `thinking` events are incremental text deltas. All other events are complete payloads.

**Terminal events:** `done` is always the last event. If the frontend's readable stream ends without receiving `done`, it should treat this as a stream interruption and either show an error or fall back to the non-streaming endpoint.

## Backend Design

### New endpoint: `POST /api/identify/stream`

**File:** `services/backend/app/routes/identify.py`

Returns `StreamingResponse` with `content-type: text/event-stream`. Consumes an async generator from the bird agent.

```python
@router.post("/identify/stream")
async def identify_bird_stream(observation: ObservationInput):
    async def event_generator():
        start_time = time.time()
        try:
            async for event in bird_agent.identify_stream(
                description=observation.description,
                location=observation.location,
                observed_at=observation.observed_at,
            ):
                if time.time() - start_time > IDENTIFY_TIMEOUT:
                    yield f'data: {json.dumps({"type": "error", "message": "Request timed out after 90 seconds."})}\n\n'
                    yield f'data: {json.dumps({"type": "done"})}\n\n'
                    return
                yield f"data: {json.dumps(event)}\n\n"
            yield f'data: {json.dumps({"type": "done"})}\n\n'
        except Exception as e:
            yield f'data: {json.dumps({"type": "error", "message": str(e)})}\n\n'
            yield f'data: {json.dumps({"type": "done"})}\n\n'

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
```

### New method: `BirdAgent.identify_stream()`

**File:** `services/backend/app/helpers/bird_agent.py`

Async generator that yields event dicts. Uses Anthropic's `client.messages.stream()` for native streaming support.

**Multi-stream loop:** Each agent iteration (max 4) opens a separate `client.messages.stream()` context. When a response's `stop_reason` is `tool_use`, the stream ends for that iteration. The backend executes the tool, appends results to the conversation, and opens a new stream for the next iteration. Thinking deltas from all iterations are yielded sequentially — the frontend appends them all into one continuous thinking block. Between iterations (during tool execution), the backend yields `tool_call`, `tool_result`, and `status` events so the frontend knows work is happening.

**Flow:**

1. Yield `status: "Checking your description..."`
2. Run Haiku guardrail. If rejected, yield `result` with not-bird response and return.
3. Yield `status: "Looking up birds in your area..."`
4. Agent loop (up to 4 iterations, one `client.messages.stream()` per iteration):
   - As `thinking` content blocks stream in, yield `thinking` deltas
   - When a `tool_use` block completes, yield `tool_call` event
   - Execute the tool
   - Yield `tool_result` with a human-readable summary
   - Yield `status` with contextual message (e.g., "Narrowing it down...")
   - If `stop_reason == "end_turn"`, break out of loop
   - Otherwise, open next stream with updated conversation
5. Parse final response JSON
6. Yield `status: "Fetching photos..."`
7. Fetch images in parallel (same as current `_build_species_info`)
8. Yield `result` with complete `RecommendationResponse`

**Error handling:** Wrap entire generator in try/except. On any exception, yield `error` event. The `done` event is emitted by the route handler, not the generator itself.

**Existing `identify()` method stays unchanged** — used by the non-streaming endpoint.

### Tool result summaries

To produce friendly `tool_result` summaries:

- `get_regional_birds` → "Found {n} species in {region}"
- `web_search` → "Found {n} results for '{query}'"

## Frontend Design

### New API function: `identifyBirdStream()`

**File:** `frontend/src/api/client.ts`

Uses `fetch` with response body readable stream to consume SSE. Calls an `onEvent` callback for each parsed event.

Accepts an `AbortSignal` for cancellation (e.g., when the user submits a new request or navigates away). Uses a 5-second timeout on the initial connection — if the streaming endpoint doesn't respond within 5 seconds, throw immediately so the caller can fall back to the non-streaming endpoint without a long wait.

SSE parsing: split the buffer on `\n\n` boundaries, strip the `data: ` prefix, and `JSON.parse` each message. This is simple enough to hand-roll since all payloads are single-line JSON (no multi-line `data:` fields).

```typescript
export async function identifyBirdStream(
  observation: ObservationInput,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const controller = new AbortController();
  const connectionTimeout = setTimeout(() => controller.abort(), 5_000);

  // Link external signal to our controller
  signal?.addEventListener('abort', () => controller.abort());

  const response = await fetch(`${API_BASE_URL}/api/identify/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(observation),
    signal: controller.signal,
  });
  clearTimeout(connectionTimeout);

  if (!response.ok) {
    throw new Error(`Stream request failed: ${response.status}`);
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Parse complete SSE messages (split on double newline)
    const parts = buffer.split('\n\n');
    buffer = parts.pop() || '';
    for (const part of parts) {
      const line = part.trim();
      if (line.startsWith('data: ')) {
        const event = JSON.parse(line.slice(6)) as StreamEvent;
        onEvent(event);
      }
    }
  }
}
```

### New types

**File:** `frontend/src/types/observation.ts`

```typescript
export type StreamEvent =
  | { type: 'status'; message: string }
  | { type: 'thinking'; content: string }
  | { type: 'tool_call'; tool: string; input: Record<string, unknown> }
  | { type: 'tool_result'; tool: string; summary: string }
  | { type: 'result'; data: RecommendationResponse }
  | { type: 'error'; message: string }
  | { type: 'done' };
```

### State changes in `Home.tsx`

**Remove:**
- `loadingStage` state and the fake timer `useEffect`
- The hardcoded stage messages ("reading the vibes...", etc.)
- Progress dots

**Add:**
- `statusMessage: string` — current status text from backend
- `thinkingText: string` — accumulated thinking content (append each delta)
- `showThinking: boolean` — toggle for collapsible section

**Keep:**
- `isLoading`, `elapsedTime`, `result`, `error`, `canRetry`

### Loading UI

Replace the current loading block (spinner + fake stages + progress dots) with:

```
┌─────────────────────────────────────────┐
│         [spinner]                        │
│   Checking birds in AU-NSW... 🔍        │
│   12s elapsed                            │
│                                          │
│   ▶ Show thinking                        │
│   ┌─────────────────────────────────┐    │
│   │ The description mentions a      │    │
│   │ bright red bird with a crest... │    │
│   │ █ (blinking cursor)             │    │
│   └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

- Spinner stays (same CSS animation)
- Status message updates in real-time from `status` events
- Elapsed time counter stays
- "Show thinking" toggle — collapsed by default
- When expanded, shows streaming reasoning text with a blinking cursor at the end
- Progress dots removed (replaced by real status)

### After result arrives

```
┌─────────────────────────────────────────┐
│   ▶ Show thinking                        │
│   (collapsed, expandable)                │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│   [Result card — same as today]          │
│   Top species, alternates, etc.          │
└─────────────────────────────────────────┘
```

- Loading block disappears
- Thinking block persists above result, collapsed
- If no thinking was produced, toggle doesn't appear
- Result card renders with same fade-in animation

### Fallback behavior

If `identifyBirdStream()` throws on initial connection (within 5-second timeout) or returns a non-200 response, `Home.tsx` catches it and falls back to calling `identifyBird()` (existing non-streaming function). In fallback mode, the UI shows a spinner with "Identifying your bird..." and the elapsed time counter — no fake stage messages (those are removed). This is acceptable degradation.

If the stream connects but drops mid-way (reader loop exits without receiving a `done` event), the frontend shows an error with a retry button, preserving any thinking text already received.

**Cancellation:** `Home.tsx` passes an `AbortController` signal to `identifyBirdStream()`. If the user submits a new request while streaming is in progress, the previous stream is aborted.

## Error Handling

| Scenario | Behavior |
|---|---|
| SSE connection fails | Fall back to non-streaming endpoint |
| Stream interrupted mid-way | Show error with retry button, preserve any thinking text received |
| Guardrail rejects query | Stream emits `result` immediately with not-bird response, no thinking block |
| 90s timeout | Stream emits `error` event, frontend shows timeout message |
| Empty thinking | "Show thinking" toggle doesn't appear |
| Tool call fails | Agent handles internally (existing fallback logic), `tool_result` shows error summary |

## Files Changed

| File | Change |
|---|---|
| `services/backend/app/helpers/bird_agent.py` | Add `identify_stream()` async generator method |
| `services/backend/app/routes/identify.py` | Add `POST /api/identify/stream` endpoint |
| `frontend/src/api/client.ts` | Add `identifyBirdStream()` function |
| `frontend/src/types/observation.ts` | Add `StreamEvent` type |
| `frontend/src/pages/Home.tsx` | Replace fake loading with streamed status + thinking block |

## Files NOT Changed

- `services/backend/app/schemas/observation.py` — response schema unchanged
- `frontend/src/components/ResultPanel.tsx` — result rendering unchanged
- `frontend/src/components/SpeciesCard.tsx` — species cards unchanged
- `frontend/src/components/BirdForm.tsx` — form unchanged

## Out of Scope

- Progressive result reveal (result appears all at once)
- WebSocket support (SSE is sufficient for this use case)
- Persisting thinking text across sessions
- Streaming the image fetch progress
