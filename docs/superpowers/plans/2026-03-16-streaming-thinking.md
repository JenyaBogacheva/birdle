# Streaming Thinking Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream real-time status updates and Claude's thinking to the frontend via SSE, replacing the fake loading stages.

**Architecture:** New `POST /api/identify/stream` SSE endpoint wraps a new `BirdAgent.identify_stream()` async generator. Frontend reads the stream with `fetch` + readable stream, updating status text and a collapsible thinking block in real-time. Result appears all at once when streaming completes. Existing non-streaming endpoint is preserved as fallback.

**Tech Stack:** FastAPI StreamingResponse, Anthropic SDK streaming (`client.messages.stream()`), React useState/useRef, SSE over POST with hand-rolled parser.

**Spec:** `docs/superpowers/specs/2026-03-16-streaming-thinking-design.md`

---

## Chunk 1: Backend — Streaming Agent Method

### Task 1: Add `_tool_result_summary` helper

**Files:**
- Modify: `services/backend/app/helpers/bird_agent.py`
- Test: `services/backend/tests/test_bird_agent.py`

- [ ] **Step 1: Write the failing test**

Add to `services/backend/tests/test_bird_agent.py`:

```python
from services.backend.app.helpers.bird_agent import _tool_result_summary


class TestToolResultSummary:
    def test_regional_birds_summary(self):
        result = {"species_observed": [{"common_name": "Robin"}, {"common_name": "Sparrow"}]}
        assert _tool_result_summary("get_regional_birds", {"region": "US-NY"}, result) == "Found 2 species in US-NY"

    def test_regional_birds_empty(self):
        result = {"species_observed": []}
        assert _tool_result_summary("get_regional_birds", {"region": "AU-NSW"}, result) == "Found 0 species in AU-NSW"

    def test_web_search_summary(self):
        result = [{"title": "a"}, {"title": "b"}, {"title": "c"}]
        assert _tool_result_summary("web_search", {"query": "red bird NY"}, result) == "Found 3 results for 'red bird NY'"

    def test_web_search_empty(self):
        result = []
        assert _tool_result_summary("web_search", {"query": "rare bird"}, result) == "Found 0 results for 'rare bird'"

    def test_unknown_tool_summary(self):
        summary = _tool_result_summary("unknown_tool", {}, {})
        assert "unknown_tool" in summary.lower() or "completed" in summary.lower()

    def test_error_result_summary(self):
        result = {"error": "timeout"}
        summary = _tool_result_summary("get_regional_birds", {"region": "XX"}, result)
        assert "error" in summary.lower() or "failed" in summary.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/eugenia_bogacheva/PersonalProjects/birdle && poetry run pytest services/backend/tests/test_bird_agent.py::TestToolResultSummary -v`
Expected: FAIL — `_tool_result_summary` not defined.

- [ ] **Step 3: Write minimal implementation**

Add to `services/backend/app/helpers/bird_agent.py` (after `_execute_tool`, before `_parse_response`):

```python
def _tool_result_summary(tool_name: str, input_data: dict[str, Any], result: Any) -> str:
    """Generate a human-readable summary of a tool call result."""
    if isinstance(result, dict) and "error" in result:
        return f"Tool {tool_name} failed: {result['error']}"

    if tool_name == "get_regional_birds":
        species = result.get("species_observed", []) if isinstance(result, dict) else []
        region = input_data.get("region", "unknown region")
        return f"Found {len(species)} species in {region}"

    if tool_name == "web_search":
        count = len(result) if isinstance(result, list) else 0
        query = input_data.get("query", "")
        return f"Found {count} results for '{query}'"

    return f"Tool {tool_name} completed"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/eugenia_bogacheva/PersonalProjects/birdle && poetry run pytest services/backend/tests/test_bird_agent.py::TestToolResultSummary -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/helpers/bird_agent.py services/backend/tests/test_bird_agent.py
git commit -m "feat: add _tool_result_summary helper for streaming status messages"
```

---

### Task 2: Add `BirdAgent.identify_stream()` async generator

**Files:**
- Modify: `services/backend/app/helpers/bird_agent.py`
- Test: `services/backend/tests/test_bird_agent.py`

This is the core backend change. The method uses `client.messages.stream()` and yields event dicts.

- [ ] **Step 1: Write the failing tests**

Add to `services/backend/tests/test_bird_agent.py`:

```python
import json
from unittest.mock import AsyncMock, MagicMock, patch

from services.backend.app.helpers.bird_agent import BirdAgent


class TestIdentifyStream:
    """Tests for the streaming identify method."""

    @pytest.fixture
    def agent(self):
        with patch("services.backend.app.helpers.bird_agent.settings") as mock_settings:
            mock_settings.anthropic_api_key = "test-key"
            return BirdAgent()

    async def _collect_events(self, agent, **kwargs):
        """Collect all events from identify_stream into a list."""
        events = []
        async for event in agent.identify_stream(**kwargs):
            events.append(event)
        return events

    @pytest.mark.asyncio
    async def test_non_bird_query_yields_result_immediately(self, agent):
        """Non-bird queries should yield a status, then result, no thinking."""
        agent._is_bird_related = AsyncMock(return_value=False)

        events = await self._collect_events(
            agent, description="how do I cook pasta", location="Italy"
        )

        types = [e["type"] for e in events]
        assert "status" in types
        assert "result" in types
        # Should NOT have thinking events
        assert "thinking" not in types
        # Result should be the not-bird response
        result_event = next(e for e in events if e["type"] == "result")
        assert "bird identification" in result_event["data"]["message"].lower() or "only help with" in result_event["data"]["message"].lower()

    @pytest.mark.asyncio
    async def test_stream_yields_status_events(self, agent):
        """Should yield status events at key pipeline stages."""
        agent._is_bird_related = AsyncMock(return_value=True)

        # Mock the streaming API — simulate a simple end_turn response (no tool calls)
        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=False)
        mock_stream.get_final_message = MagicMock(return_value=MagicMock(
            stop_reason="end_turn",
            content=[MagicMock(type="text", text='{"message":"hi","top_species":null,"alternate_species":[],"clarification":null}')],
            usage=MagicMock(input_tokens=100, output_tokens=50),
        ))

        # No events from the stream itself (no thinking, no tool_use)
        async def empty_stream():
            return
            yield  # make it an async generator

        mock_stream.__aiter__ = lambda self: empty_stream()

        agent._client.messages.stream = MagicMock(return_value=mock_stream)

        events = await self._collect_events(
            agent, description="red bird", location="New York"
        )

        types = [e["type"] for e in events]
        assert types[0] == "status"  # First event is always a status
        assert "result" in types  # Must end with a result

    @pytest.mark.asyncio
    async def test_stream_error_yields_error_event(self, agent):
        """Exceptions should yield an error event, not raise."""
        agent._is_bird_related = AsyncMock(return_value=True)
        agent._client.messages.stream = MagicMock(side_effect=Exception("API down"))

        events = await self._collect_events(
            agent, description="red bird", location="New York"
        )

        types = [e["type"] for e in events]
        assert "error" in types
        error_event = next(e for e in events if e["type"] == "error")
        assert "unexpected error" in error_event["message"].lower()
```

Add `import pytest` at the top of the test file if not already there.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/eugenia_bogacheva/PersonalProjects/birdle && poetry run pytest services/backend/tests/test_bird_agent.py::TestIdentifyStream -v`
Expected: FAIL — `identify_stream` not defined.

- [ ] **Step 3: Write the implementation**

Add to `services/backend/app/helpers/bird_agent.py`. Add this import at the top:

```python
from collections.abc import AsyncIterator
```

Add this method to the `BirdAgent` class (after the existing `identify` method):

```python
    async def identify_stream(
        self,
        description: str,
        location: str,
        observed_at: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Run bird identification with streaming events.

        Yields event dicts with a 'type' field:
        - status: {"type": "status", "message": str}
        - thinking: {"type": "thinking", "content": str}
        - tool_call: {"type": "tool_call", "tool": str, "input": dict}
        - tool_result: {"type": "tool_result", "tool": str, "summary": str}
        - result: {"type": "result", "data": dict}
        - error: {"type": "error", "message": str}
        """
        start_time = time.time()

        try:
            # Step 1: Guardrail
            yield {"type": "status", "message": "Checking your description..."}

            if not await self._is_bird_related(description):
                logger.info(
                    "Non-bird query rejected by guardrail (streaming)",
                    extra={"operation": "bird_agent_stream", "status": "rejected"},
                )
                yield {"type": "result", "data": dict(NOT_BIRD_RESPONSE)}
                return

            # Step 2: Build user message
            yield {"type": "status", "message": "Looking up birds in your area..."}

            user_message = (
                f"I observed a bird...\n\n"
                f"Description: {description}\n"
                f"Location: {location}"
            )
            if observed_at:
                user_message += f"\nObserved at: {observed_at}"

            messages: list[MessageParam] = [
                {"role": "user", "content": user_message},
            ]

            # Step 3: Agent loop with streaming
            final_message = None
            iterations = 0

            for iteration in range(MAX_ITERATIONS):
                iterations = iteration + 1

                async with self._client.messages.stream(
                    model=AGENT_MODEL,
                    max_tokens=16000,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                    thinking={"type": "adaptive"},
                    messages=messages,
                ) as stream:
                    # Process streaming events
                    async for event in stream:
                        if hasattr(event, "type") and event.type == "content_block_delta":
                            delta = event.delta
                            if delta.type == "thinking_delta":
                                yield {"type": "thinking", "content": delta.thinking}
                            # Text deltas are part of the final JSON — don't stream

                    final_message = stream.get_final_message()

                # Check if done
                if final_message.stop_reason == "end_turn":
                    break

                # Extract tool use blocks
                tool_use_blocks = [
                    b for b in final_message.content if isinstance(b, ToolUseBlock)
                ]
                if not tool_use_blocks:
                    break

                # Append assistant response to conversation
                messages.append(
                    {"role": "assistant", "content": cast(Any, final_message.content)},
                )

                # Execute tools and yield events
                tool_results: list[dict[str, Any]] = []
                for tool_block in tool_use_blocks:
                    yield {
                        "type": "tool_call",
                        "tool": tool_block.name,
                        "input": tool_block.input,
                    }

                    result = await _execute_tool(tool_block.name, tool_block.input)

                    summary = _tool_result_summary(
                        tool_block.name, tool_block.input, result
                    )
                    yield {
                        "type": "tool_result",
                        "tool": tool_block.name,
                        "summary": summary,
                    }

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_block.id,
                            "content": (
                                json.dumps(result)
                                if isinstance(result, (dict, list))
                                else str(result)
                            ),
                        }
                    )

                messages.append({"role": "user", "content": cast(Any, tool_results)})

                if iteration < MAX_ITERATIONS - 1:
                    yield {"type": "status", "message": "Narrowing it down..."}

            latency_ms = (time.time() - start_time) * 1000
            usage = final_message.usage if final_message else None
            logger.info(
                "Bird agent stream completed",
                extra={
                    "operation": "bird_agent_stream",
                    "total_latency_ms": round(latency_ms, 2),
                    "iterations": iterations,
                    "input_tokens": usage.input_tokens if usage else 0,
                    "output_tokens": usage.output_tokens if usage else 0,
                    "status": "success",
                },
            )

            if final_message is None:
                yield {"type": "result", "data": dict(FALLBACK_RESPONSE)}
                return

            parsed = _parse_response(final_message)

            # Yield parsed result — images are fetched by the route handler
            # before constructing the final RecommendationResponse
            yield {"type": "result", "data": parsed}

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(
                f"Bird agent stream failed: {e}",
                extra={
                    "operation": "bird_agent_stream",
                    "total_latency_ms": round(latency_ms, 2),
                    "status": "error",
                    "error_type": type(e).__name__,
                },
            )
            yield {"type": "error", "message": "An unexpected error occurred. Please try again."}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/eugenia_bogacheva/PersonalProjects/birdle && poetry run pytest services/backend/tests/test_bird_agent.py -v`
Expected: All tests PASS (existing + new).

- [ ] **Step 5: Run linting**

Run: `cd /Users/eugenia_bogacheva/PersonalProjects/birdle && poetry run ruff check services/backend/app/helpers/bird_agent.py && poetry run black --check services/backend/app/helpers/bird_agent.py`
Expected: Clean.

- [ ] **Step 6: Commit**

```bash
git add services/backend/app/helpers/bird_agent.py services/backend/tests/test_bird_agent.py
git commit -m "feat: add BirdAgent.identify_stream() async generator with SSE events"
```

---

## Chunk 2: Backend — Streaming Endpoint

### Task 3: Add `POST /api/identify/stream` endpoint

**Files:**
- Modify: `services/backend/app/routes/identify.py`
- Test: `services/backend/tests/test_identify.py`

- [ ] **Step 1: Write the failing tests**

Add to `services/backend/tests/test_identify.py`:

```python
import json


class TestStreamEndpoint:
    def _parse_sse_events(self, response_text: str) -> list[dict]:
        """Parse SSE response text into event dicts."""
        events = []
        for part in response_text.split("\n\n"):
            line = part.strip()
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
        return events

    def test_stream_success(self, client, mock_bird_agent_stream):
        """Streaming endpoint returns SSE events ending with result and done."""
        async def fake_stream(**kwargs):
            yield {"type": "status", "message": "Checking your description..."}
            yield {"type": "status", "message": "Looking up birds..."}
            yield {"type": "result", "data": {"message": "Found it!", "top_species": None, "alternate_species": [], "clarification": None}}

        mock_bird_agent_stream.side_effect = fake_stream

        response = client.post(
            "/api/identify/stream",
            json={"description": "red bird", "location": "New York"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

        events = self._parse_sse_events(response.text)
        types = [e["type"] for e in events]
        assert "status" in types
        assert "result" in types
        assert types[-1] == "done"
        # Result should have been enriched with RecommendationResponse fields
        result_event = next(e for e in events if e["type"] == "result")
        assert "message" in result_event["data"]

    def test_stream_result_has_images(self, client, mock_bird_agent_stream, monkeypatch):
        """Streaming result should include image data from _build_species_info."""
        async def fake_stream(**kwargs):
            yield {"type": "result", "data": {
                "message": "Found it!",
                "top_species": {"common_name": "Cardinal", "scientific_name": "Cardinalis cardinalis", "species_code": "norcar", "confidence": "high", "reasoning": "test"},
                "alternate_species": [],
                "clarification": None,
            }}

        mock_bird_agent_stream.side_effect = fake_stream

        # Mock ebird_client.get_species_image to return test data
        mock_image = AsyncMock(return_value={"image_url": "https://example.com/img.jpg", "photographer": "Test"})
        monkeypatch.setattr(
            "services.backend.app.routes.identify.ebird_client.get_species_image",
            mock_image,
        )

        response = client.post(
            "/api/identify/stream",
            json={"description": "red bird", "location": "New York"},
        )
        events = self._parse_sse_events(response.text)
        result_event = next(e for e in events if e["type"] == "result")
        assert result_event["data"]["top_species"]["image_url"] == "https://example.com/img.jpg"
        assert result_event["data"]["top_species"]["range_link"]  # should be populated

    def test_stream_missing_description(self, client):
        response = client.post(
            "/api/identify/stream",
            json={"location": "New York"},
        )
        assert response.status_code == 422

    def test_stream_missing_location(self, client):
        response = client.post(
            "/api/identify/stream",
            json={"description": "red bird"},
        )
        assert response.status_code == 422

    def test_stream_error_yields_error_and_done(self, client, mock_bird_agent_stream):
        """When the agent generator raises, the endpoint yields error + done."""
        async def failing_stream(**kwargs):
            yield {"type": "status", "message": "Starting..."}
            raise Exception("boom")

        mock_bird_agent_stream.side_effect = failing_stream

        response = client.post(
            "/api/identify/stream",
            json={"description": "red bird", "location": "New York"},
        )
        assert response.status_code == 200  # SSE always returns 200

        events = self._parse_sse_events(response.text)
        types = [e["type"] for e in events]
        assert "error" in types
        assert types[-1] == "done"
        error_event = next(e for e in events if e["type"] == "error")
        assert "unexpected error" in error_event["message"].lower()

    def test_stream_timeout(self, client, mock_bird_agent_stream):
        """When the stream exceeds the timeout, an error event is emitted."""
        import services.backend.app.routes.identify as route_mod

        async def slow_stream(**kwargs):
            yield {"type": "status", "message": "Starting..."}
            import asyncio
            await asyncio.sleep(5)
            yield {"type": "result", "data": {"message": "too late"}}

        mock_bird_agent_stream.side_effect = slow_stream

        original_timeout = route_mod.IDENTIFY_TIMEOUT
        route_mod.IDENTIFY_TIMEOUT = 0.1  # Very short for test
        try:
            response = client.post(
                "/api/identify/stream",
                json={"description": "red bird", "location": "New York"},
            )
            events = self._parse_sse_events(response.text)
            types = [e["type"] for e in events]
            assert "error" in types
            assert types[-1] == "done"
        finally:
            route_mod.IDENTIFY_TIMEOUT = original_timeout
```

Add a new fixture to `services/backend/tests/conftest.py`:

```python
@pytest.fixture
def mock_bird_agent_stream(monkeypatch):
    """Mock the bird_agent.identify_stream method."""
    mock = AsyncMock()
    monkeypatch.setattr(
        "services.backend.app.routes.identify.bird_agent.identify_stream",
        mock,
    )
    return mock
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/eugenia_bogacheva/PersonalProjects/birdle && poetry run pytest services/backend/tests/test_identify.py::TestStreamEndpoint -v`
Expected: FAIL — endpoint not found (404).

- [ ] **Step 3: Write the implementation**

Add to `services/backend/app/routes/identify.py`. Add `json` import and `StreamingResponse` import at the top (note: `asyncio` is already imported):

```python
import json

from fastapi.responses import StreamingResponse
```

Add the new endpoint after the existing `identify_bird` function:

```python
@router.post("/identify/stream")
async def identify_bird_stream(observation: ObservationInput):
    """Stream bird identification progress via SSE."""
    request_start = time.time()

    logger.info(
        "Streaming identification request started",
        extra={
            "operation": "identify_bird_stream",
            "description_length": len(observation.description),
            "location": observation.location,
        },
    )

    async def event_generator():
        start_time = time.time()
        try:
            async for event in bird_agent.identify_stream(
                description=observation.description,
                location=observation.location,
                observed_at=observation.observed_at,
            ):
                if time.time() - start_time > IDENTIFY_TIMEOUT:
                    logger.error(
                        "Streaming request timeout",
                        extra={
                            "operation": "identify_bird_stream",
                            "total_latency_ms": round((time.time() - request_start) * 1000, 2),
                            "status": "timeout",
                        },
                    )
                    yield f'data: {json.dumps({"type": "error", "message": "Request timed out. Please try again."})}\n\n'
                    yield f'data: {json.dumps({"type": "done"})}\n\n'
                    return

                # Intercept result events to fetch images and build RecommendationResponse
                if event.get("type") == "result":
                    agent_data = event["data"]

                    yield f'data: {json.dumps({"type": "status", "message": "Fetching photos..."})}\n\n'

                    # Build species info with images (same as non-streaming path)
                    top_species = None
                    image_tasks = []
                    if agent_data.get("top_species"):
                        image_tasks.append(_build_species_info(agent_data["top_species"]))
                    for alt in agent_data.get("alternate_species", []):
                        image_tasks.append(_build_species_info(alt))

                    built = await asyncio.gather(*image_tasks) if image_tasks else []

                    if agent_data.get("top_species") and built:
                        top_species = built[0]
                        alternate_species = list(built[1:])
                    else:
                        alternate_species = list(built)

                    response = RecommendationResponse(
                        message=agent_data.get("message", ""),
                        top_species=top_species,
                        alternate_species=alternate_species,
                        clarification=agent_data.get("clarification"),
                    )

                    yield f"data: {json.dumps({'type': 'result', 'data': response.model_dump()})}\n\n"
                else:
                    yield f"data: {json.dumps(event)}\n\n"

            total_latency_ms = (time.time() - request_start) * 1000
            logger.info(
                "Streaming identification completed",
                extra={
                    "operation": "identify_bird_stream",
                    "total_latency_ms": round(total_latency_ms, 2),
                    "status": "success",
                },
            )
            yield f'data: {json.dumps({"type": "done"})}\n\n'

        except Exception as e:
            logger.error(
                f"Streaming identification failed: {e}",
                exc_info=True,
                extra={
                    "operation": "identify_bird_stream",
                    "total_latency_ms": round((time.time() - request_start) * 1000, 2),
                    "status": "error",
                },
            )
            yield f'data: {json.dumps({"type": "error", "message": "An unexpected error occurred. Please try again."})}\n\n'
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/eugenia_bogacheva/PersonalProjects/birdle && poetry run pytest services/backend/tests/test_identify.py -v`
Expected: All tests PASS (existing + new).

- [ ] **Step 5: Run full backend test suite**

Run: `cd /Users/eugenia_bogacheva/PersonalProjects/birdle && poetry run pytest services/backend/tests/ -v`
Expected: All tests PASS.

- [ ] **Step 6: Run linting**

Run: `cd /Users/eugenia_bogacheva/PersonalProjects/birdle && poetry run ruff check services/backend/ && poetry run black --check services/backend/`
Expected: Clean.

- [ ] **Step 7: Commit**

```bash
git add services/backend/app/routes/identify.py services/backend/tests/test_identify.py services/backend/tests/conftest.py
git commit -m "feat: add POST /api/identify/stream SSE endpoint"
```

---

## Chunk 3: Frontend — Types and API Client

### Task 4: Add `StreamEvent` type

**Files:**
- Modify: `frontend/src/types/observation.ts`

- [ ] **Step 1: Add the type**

Append to `frontend/src/types/observation.ts`:

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

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd /Users/eugenia_bogacheva/PersonalProjects/birdle/frontend && npx tsc --noEmit`
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/observation.ts
git commit -m "feat: add StreamEvent type for SSE protocol"
```

---

### Task 5: Add `identifyBirdStream()` API function

**Files:**
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add the function**

Add to `frontend/src/api/client.ts` (add `StreamEvent` to the import, then add the function after `identifyBird`):

```typescript
import type { ObservationInput, RecommendationResponse, StreamEvent } from '../types/observation';
```

```typescript
export async function identifyBirdStream(
  observation: ObservationInput,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const controller = new AbortController();
  const connectionTimeout = setTimeout(() => controller.abort(), 5_000);

  // Link external signal to our controller
  const onAbort = () => controller.abort();
  signal?.addEventListener('abort', onAbort);

  try {
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
    let receivedDone = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const parts = buffer.split('\n\n');
      buffer = parts.pop() || '';
      for (const part of parts) {
        const line = part.trim();
        if (line.startsWith('data: ')) {
          const event = JSON.parse(line.slice(6)) as StreamEvent;
          onEvent(event);
          if (event.type === 'done') receivedDone = true;
        }
      }
    }

    if (!receivedDone) {
      throw new Error('Stream ended unexpectedly');
    }
  } catch (error) {
    clearTimeout(connectionTimeout);
    if (error instanceof DOMException && error.name === 'AbortError') {
      // If it was our connection timeout, throw a specific message
      if (!signal?.aborted) {
        throw new Error('Could not connect to streaming endpoint');
      }
      // If it was the caller's abort, just return silently
      return;
    }
    throw error;
  } finally {
    signal?.removeEventListener('abort', onAbort);
  }
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd /Users/eugenia_bogacheva/PersonalProjects/birdle/frontend && npx tsc --noEmit`
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: add identifyBirdStream() SSE client function"
```

---

## Chunk 4: Frontend — Home.tsx Streaming UI

### Task 6: Update Home.tsx to use streaming with thinking block

**Files:**
- Modify: `frontend/src/pages/Home.tsx`

This task replaces the fake loading stages with real streaming events and adds the collapsible thinking block.

- [ ] **Step 1: Rewrite Home.tsx**

Replace the contents of `frontend/src/pages/Home.tsx` with:

```typescript
/**
 * Home page with bird identification form and results.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { BirdForm } from '../components/BirdForm';
import { ResultPanel } from '../components/ResultPanel';
import { identifyBird, identifyBirdStream } from '../api/client';
import type { ObservationInput, RecommendationResponse, StreamEvent } from '../types/observation';

export function Home() {
  const [result, setResult] = useState<RecommendationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');
  const [thinkingText, setThinkingText] = useState('');
  const [showThinking, setShowThinking] = useState(false);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [canRetry, setCanRetry] = useState(false);
  const timerRef = useRef<number | null>(null);
  const lastObservationRef = useRef<ObservationInput | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Timer effect for elapsed time during loading
  useEffect(() => {
    if (isLoading) {
      const startTime = Date.now();
      timerRef.current = window.setInterval(() => {
        setElapsedTime(Math.floor((Date.now() - startTime) / 1000));
      }, 1000);
    } else {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      setElapsedTime(0);
    }

    return () => {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
      }
    };
  }, [isLoading]);

  const handleStreamEvent = useCallback((event: StreamEvent) => {
    switch (event.type) {
      case 'status':
        setStatusMessage(event.message);
        break;
      case 'thinking':
        setThinkingText((prev) => prev + event.content);
        break;
      case 'result':
        setResult(event.data);
        break;
      case 'error':
        setError(event.message);
        setCanRetry(true);
        break;
      case 'tool_call':
        setStatusMessage(`Calling ${event.tool}...`);
        break;
      case 'tool_result':
        setStatusMessage(event.summary);
        break;
      case 'done':
        break;
    }
  }, []);

  const handleSubmit = async (observation: ObservationInput) => {
    // Abort any in-flight stream
    abortRef.current?.abort();
    const abortController = new AbortController();
    abortRef.current = abortController;

    lastObservationRef.current = observation;
    setIsLoading(true);
    setError(null);
    setResult(null);
    setCanRetry(false);
    setStatusMessage('');
    setThinkingText('');
    setShowThinking(false);

    try {
      // Try streaming first
      await identifyBirdStream(observation, handleStreamEvent, abortController.signal);
    } catch {
      // Fallback to non-streaming if stream fails
      if (abortController.signal.aborted) return; // User cancelled
      try {
        setStatusMessage('Identifying your bird...');
        const response = await identifyBird(observation);
        setResult(response);
      } catch (err) {
        const errorMessage =
          err instanceof Error
            ? err.message
            : 'An unexpected error occurred. Please try again.';
        setError(errorMessage);
        setCanRetry(
          errorMessage.includes('timeout') ||
            errorMessage.includes('network') ||
            errorMessage.includes('try again')
        );
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleRetry = () => {
    if (lastObservationRef.current) {
      handleSubmit(lastObservationRef.current);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-pink-100 via-orange-50 to-yellow-100 relative overflow-hidden">
      {/* Decorative bird emojis - hidden on mobile, visible on tablet+ */}
      {/* Top corners */}
      <div className="hidden sm:block fixed top-[8%] left-[6%] text-6xl opacity-25 animate-bounce-slow pointer-events-none">
        🦆
      </div>
      <div className="hidden sm:block fixed top-[8%] right-[6%] text-6xl opacity-25 animate-bounce-slow pointer-events-none" style={{ animationDelay: '1s' }}>
        🦢
      </div>

      {/* Middle sides */}
      <div className="hidden sm:block fixed top-[40%] left-[3%] text-5xl opacity-[0.15] animate-bounce-slow pointer-events-none" style={{ animationDelay: '0.5s' }}>
        🪶
      </div>
      <div className="hidden sm:block fixed top-[40%] right-[3%] text-5xl opacity-[0.15] animate-bounce-slow pointer-events-none" style={{ animationDelay: '1.5s' }}>
        🐓
      </div>

      {/* Bottom corners */}
      <div className="hidden sm:block fixed bottom-[10%] left-[8%] text-6xl opacity-25 animate-bounce-slow pointer-events-none" style={{ animationDelay: '0.8s' }}>
        🦚
      </div>
      <div className="hidden sm:block fixed bottom-[10%] right-[8%] text-6xl opacity-25 animate-bounce-slow pointer-events-none" style={{ animationDelay: '2s' }}>
        🦤
      </div>

      <div className="container mx-auto px-4 py-12 relative z-10">
        <div className="max-w-3xl mx-auto">
          {/* Header */}
          <div className="text-center mb-12">
            <div className="flex items-center justify-center gap-2 sm:gap-3 mb-3">
              <span className="text-4xl sm:text-5xl">🦜</span>
              <h1 className="text-4xl sm:text-5xl font-bold text-gray-900">
                birdle-ai ✨
              </h1>
              <span className="text-4xl sm:text-5xl">🦩</span>
            </div>
            <p className="text-lg sm:text-xl text-gray-700">
              spotted a bird? let's figure out what it is!
            </p>
          </div>

          {/* Main Content */}
          <div className="bg-white rounded-xl shadow-lg p-8 mb-8">
            <BirdForm onSubmit={handleSubmit} isLoading={isLoading} />
          </div>

          {/* Loading Indicator with Streaming Status */}
          {isLoading && (
            <div className="bg-white rounded-xl shadow-lg p-8 mb-8">
              <div className="flex flex-col items-center justify-center space-y-4">
                {/* Spinner */}
                <div className="relative">
                  <div className="w-16 h-16 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin"></div>
                </div>

                {/* Status Message */}
                <div className="text-center">
                  <p className="text-lg font-medium text-gray-900">
                    {statusMessage || 'Starting...'}
                  </p>
                  <p className="text-sm text-gray-500 mt-2">
                    {elapsedTime > 0 && `${elapsedTime}s elapsed`}
                  </p>
                </div>
              </div>

              {/* Thinking Block (collapsible) */}
              {thinkingText && (
                <div className="mt-6 border-t pt-4">
                  <button
                    onClick={() => setShowThinking(!showThinking)}
                    className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1"
                  >
                    <span className="text-xs">{showThinking ? '▼' : '▶'}</span>
                    {showThinking ? 'Hide thinking' : 'Show thinking'}
                  </button>
                  {showThinking && (
                    <div className="mt-2 p-3 bg-gray-50 rounded-lg text-sm text-gray-700 whitespace-pre-wrap max-h-64 overflow-y-auto">
                      {thinkingText}
                      <span className="inline-block w-2 h-4 bg-gray-400 animate-pulse ml-0.5" />
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Thinking Block (persists after result) */}
          {!isLoading && thinkingText && (result || error) && (
            <div className="bg-white rounded-xl shadow-lg p-4 mb-4">
              <button
                onClick={() => setShowThinking(!showThinking)}
                className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1"
              >
                <span className="text-xs">{showThinking ? '▼' : '▶'}</span>
                {showThinking ? 'Hide thinking' : 'Show thinking'}
              </button>
              {showThinking && (
                <div className="mt-2 p-3 bg-gray-50 rounded-lg text-sm text-gray-700 whitespace-pre-wrap max-h-64 overflow-y-auto">
                  {thinkingText}
                </div>
              )}
            </div>
          )}

          {/* Results */}
          {(result || error) && (
            <div className="animate-fade-in">
              <ResultPanel
                result={result}
                error={error}
                canRetry={canRetry}
                onRetry={handleRetry}
              />
            </div>
          )}

          {/* Footer */}
          <div className="text-center mt-12 text-gray-600 text-sm">
            <p>
              powered by fastapi, react, claude, and vibes ⚡✨
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd /Users/eugenia_bogacheva/PersonalProjects/birdle/frontend && npx tsc --noEmit`
Expected: No errors.

- [ ] **Step 3: Verify dev server starts**

Run: `cd /Users/eugenia_bogacheva/PersonalProjects/birdle/frontend && npx vite build`
Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Home.tsx
git commit -m "feat: replace fake loading stages with streaming status + thinking block"
```

---

## Chunk 5: Integration Testing and Cleanup

### Task 7: Manual E2E verification

**Files:** None (verification only)

- [ ] **Step 1: Start the backend**

Run: `cd /Users/eugenia_bogacheva/PersonalProjects/birdle && poetry run uvicorn services.backend.app.main:app --reload --port 8000`

- [ ] **Step 2: Start the frontend**

Run: `cd /Users/eugenia_bogacheva/PersonalProjects/birdle/frontend && npm run dev`

- [ ] **Step 3: Test streaming flow**

Open `http://localhost:5173`. Submit a bird identification request (e.g., "bright red bird with a crest" in "New York"). Verify:
- Status messages update in real-time (not fake timers)
- "Show thinking" toggle appears (if Claude uses thinking)
- Expanding thinking shows streaming text with blinking cursor
- Result appears all at once when done
- Thinking block persists above result after completion

- [ ] **Step 4: Test fallback**

Stop the backend, submit a request. Verify:
- Frontend shows error or falls back gracefully
- Retry button works

- [ ] **Step 5: Test non-bird query**

Submit "how do I cook pasta" with location "Italy". Verify:
- Quick response (guardrail rejection)
- No thinking block shown
- "I can only help with identifying birds" message

### Task 8: Run full test suite and lint

- [ ] **Step 1: Run all backend tests**

Run: `cd /Users/eugenia_bogacheva/PersonalProjects/birdle && poetry run pytest services/backend/tests/ -v`
Expected: All tests PASS.

- [ ] **Step 2: Run linting and type checking**

Run: `cd /Users/eugenia_bogacheva/PersonalProjects/birdle && poetry run ruff check services/ && poetry run black --check services/ && poetry run mypy services/backend/app/`
Expected: Clean.

- [ ] **Step 3: Run frontend build**

Run: `cd /Users/eugenia_bogacheva/PersonalProjects/birdle/frontend && npx tsc --noEmit && npx vite build`
Expected: Clean build.

- [ ] **Step 4: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: address issues found during integration testing"
```
