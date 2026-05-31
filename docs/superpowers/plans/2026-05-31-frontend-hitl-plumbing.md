# Frontend HITL Plumbing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the React frontend to the new turn-based LangGraph backend — capture the `session_id`, render the `awaiting_input` prompt (quick-reply chips + free text), and POST the user's answer to `/api/identify/resume`, streaming the continued events into the existing UI.

**Architecture:** The backend already emits a complete SSE protocol over `/api/identify/stream` (turn 1) and `/api/identify/resume` (turn 2+). This plan adds the minimal client + UI plumbing to consume the two new event types (`session_id`, `awaiting_input`) and to drive a resume turn. The streaming/SSE-reader logic is refactored into shared helpers so the resume call reuses it (DRY). A small presentational `AwaitingInputPrompt` component renders the question; `Home.tsx` holds the session-id ref + awaiting state and wires the resume call. The full chat/notebook redesign is explicitly deferred (spec §3) — `detective_note` / `candidates` events stay unrendered for now.

**Tech Stack:** React 18 + Vite 5 + TypeScript + Tailwind. New dev-only test stack: Vitest 2 + jsdom + React Testing Library + jest-dom.

---

## Backend contract (already shipped — do NOT change)

The frontend must match what the backend **actually emits today** (verified in `services/backend/app/graph/runner.py` and `services/backend/app/routes/identify.py`):

- Transport: `text/event-stream`, each event on a line `data: <json>\n\n`.
- The stream **always** ends with `{"type": "done"}` — including when the graph interrupts at `ask_user` (the route appends `done` after the runner's generator returns). The client's existing "Stream ended unexpectedly" guard therefore still holds for resume turns.
- Event types the client may receive:
  - `{"type": "session_id", "session_id": "<uuid>"}` — emitted once near the start of every turn (turn 1 **and** resume).
  - `{"type": "status", "message": "..."}`
  - `{"type": "thinking", "content": "..."}`
  - `{"type": "tool_call", "tool": "...", "input": {...}}`
  - `{"type": "tool_result", "tool": "...", "summary": "..."}`
  - `{"type": "detective_note", "message": "..."}` (rendering deferred)
  - `{"type": "candidates", "data": [...]}` (rendering deferred)
  - `{"type": "awaiting_input", "reason": "<tag>", "question": "...", "options"?: ["label", ...]}` — emitted when the graph pauses at `ask_user`. `options` is a list of **plain strings** (quick-reply labels). There is **no** `comparison` field (the spec mentioned one aspirationally; the backend never sends it — do not add it).
  - `{"type": "result", "data": RecommendationResponse}`
  - `{"type": "error", "message": "..."}`
  - `{"type": "done"}`
- Resume endpoint: `POST /api/identify/resume` with JSON body `{"session_id": "<uuid>", "user_message": "<text>"}` (`ResumeInput`). Returns the same SSE stream. A chip's label becomes the `user_message`; free text wins (spec §6).

---

## File structure

**Create:**

| File | Responsibility |
|------|----------------|
| `frontend/vitest.config.ts` *(folded into `vite.config.ts`)* | Test runner config (jsdom env, setup file). Implemented by editing `vite.config.ts`, not a separate file. |
| `frontend/src/test/setup.ts` | Global test setup: jest-dom matchers + RTL cleanup. |
| `frontend/src/test/smoke.test.ts` | Harness sanity check (jsdom + jest-dom wired). |
| `frontend/src/components/AwaitingInputPrompt.tsx` | Presentational prompt: question + chip buttons + free-text form. Calls `onAnswer(message)`. |
| `frontend/src/components/AwaitingInputPrompt.test.tsx` | RTL tests for the prompt. |
| `frontend/src/api/client.test.ts` | Tests for the SSE client functions. |
| `frontend/src/pages/Home.test.tsx` | Integration test: stream → prompt → resume → result. |

**Modify:**

| File | Changes |
|------|---------|
| `frontend/package.json` | Add dev deps + `test` script. |
| `frontend/.eslintrc.cjs` | Allow `_`-prefixed unused args (needed by test mock signatures). |
| `frontend/vite.config.ts` | Import `defineConfig` from `vitest/config`; add `test` block. |
| `frontend/src/types/observation.ts` | Add `AwaitingInput`, `ResumeInput`; add `session_id` + `awaiting_input` to `StreamEvent`. |
| `frontend/src/api/client.ts` | Extract `consumeSSEStream` + `streamSSE` helpers; `identifyBirdStream` delegates; add `resumeIdentificationStream`. |
| `frontend/src/pages/Home.tsx` | Capture `session_id`; track `awaiting` state; render `AwaitingInputPrompt`; add `handleAnswer` resume flow. |
| `.github/workflows/ci.yml` | Add a `Run tests` step to the frontend job. |

**All commands below run from `frontend/`** unless shown otherwise.

---

### Task 1: Test infrastructure (Vitest + RTL + jsdom)

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/.eslintrc.cjs`
- Modify: `.github/workflows/ci.yml`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/test/smoke.test.ts`

- [ ] **Step 1: Install the test dev-dependencies**

Run (from `frontend/`):
```bash
npm install -D vitest@^2.1 jsdom@^25 @testing-library/react@^16.1 @testing-library/dom@^10 @testing-library/jest-dom@^6.6 @testing-library/user-event@^14.5
```
Expected: `package.json` `devDependencies` gains those six packages; `package-lock.json` updates. (`@testing-library/dom` is a required peer of `@testing-library/react@16`.)

- [ ] **Step 2: Add the `test` script to `package.json`**

In `frontend/package.json`, the `scripts` block currently is:
```json
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "lint": "eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0",
    "preview": "vite preview"
  },
```
Change it to:
```json
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "lint": "eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0",
    "preview": "vite preview",
    "test": "vitest run"
  },
```

- [ ] **Step 3: Configure Vitest inside `vite.config.ts`**

Replace the entire contents of `frontend/vite.config.ts` with:
```ts
/// <reference types="vitest/config" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
  },
  test: {
    globals: false,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: false,
  },
})
```
Note: `globals: false` — every test imports `describe`/`it`/`expect`/`vi` from `vitest` explicitly. This keeps ESLint happy without an env override.

- [ ] **Step 4: Create the test setup file**

Create `frontend/src/test/setup.ts`:
```ts
import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

// Unmount React trees and reset jsdom between tests.
afterEach(() => {
  cleanup();
});
```

- [ ] **Step 5: Allow underscore-prefixed unused args in ESLint**

Test mock signatures need a leading positional arg they don't use (e.g. `(_observation, onEvent) => ...`). `tsc`'s `noUnusedParameters` already ignores `_`-prefixed args; make ESLint match.

In `frontend/.eslintrc.cjs`, the `rules` block currently is:
```js
  rules: {
    'react-refresh/only-export-components': [
      'warn',
      { allowConstantExport: true },
    ],
  },
```
Change it to:
```js
  rules: {
    'react-refresh/only-export-components': [
      'warn',
      { allowConstantExport: true },
    ],
    '@typescript-eslint/no-unused-vars': [
      'warn',
      { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
    ],
  },
```

- [ ] **Step 6: Add a smoke test proving the harness works**

Create `frontend/src/test/smoke.test.ts`:
```ts
import { describe, it, expect } from 'vitest';

describe('test harness', () => {
  it('runs basic assertions', () => {
    expect(1 + 1).toBe(2);
  });

  it('has a jsdom document with jest-dom matchers', () => {
    document.body.innerHTML = '<button>hi</button>';
    expect(document.querySelector('button')).toBeInTheDocument();
  });
});
```

- [ ] **Step 7: Run the smoke test (it should pass)**

Run:
```bash
npm test
```
Expected: PASS — 2 tests in `src/test/smoke.test.ts`. If `toBeInTheDocument` is a type error during `npm run build` later, the jest-dom import in `setup.ts` (Step 4) is what registers it; confirm `src/test/setup.ts` is under `src/` so `tsconfig.json` (`include: ["src"]`) picks it up.

- [ ] **Step 8: Add the test step to CI**

In `.github/workflows/ci.yml`, the frontend job currently ends with:
```yaml
      - name: Run ESLint
        working-directory: frontend
        run: npm run lint
```
Append a new step after it:
```yaml
      - name: Run ESLint
        working-directory: frontend
        run: npm run lint

      - name: Run tests
        working-directory: frontend
        run: npm test
```

- [ ] **Step 9: Verify the full frontend check suite still passes**

Run (from `frontend/`):
```bash
npm run build && npm run lint && npm test
```
Expected: `tsc` compiles cleanly (it now also typechecks `src/test/*`), ESLint reports 0 warnings, Vitest passes 2 tests.

- [ ] **Step 10: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/.eslintrc.cjs frontend/src/test/setup.ts frontend/src/test/smoke.test.ts .github/workflows/ci.yml
git commit -m "feat: add vitest + RTL frontend test harness"
```

---

### Task 2: Frontend types for sessions + awaiting_input

**Files:**
- Modify: `frontend/src/types/observation.ts`

- [ ] **Step 1: Add the new interfaces and StreamEvent variants**

In `frontend/src/types/observation.ts`, the file currently ends with this block:
```ts
export type StreamEvent =
  | { type: 'status'; message: string }
  | { type: 'thinking'; content: string }
  | { type: 'tool_call'; tool: string; input: Record<string, unknown> }
  | { type: 'tool_result'; tool: string; summary: string }
  | { type: 'detective_note'; message: string }
  | { type: 'candidates'; data: CandidateInfo[] }
  | { type: 'result'; data: RecommendationResponse }
  | { type: 'error'; message: string }
  | { type: 'done' };
```
Replace that block with (adds `AwaitingInput`, `ResumeInput`, and two new union members):
```ts
/** Payload the backend sends when the graph pauses to ask the user a question. */
export interface AwaitingInput {
  reason: string;
  question: string;
  options?: string[];
}

/** Body for POST /api/identify/resume — continues a paused session. */
export interface ResumeInput {
  session_id: string;
  user_message: string;
}

export type StreamEvent =
  | { type: 'session_id'; session_id: string }
  | { type: 'status'; message: string }
  | { type: 'thinking'; content: string }
  | { type: 'tool_call'; tool: string; input: Record<string, unknown> }
  | { type: 'tool_result'; tool: string; summary: string }
  | { type: 'detective_note'; message: string }
  | { type: 'candidates'; data: CandidateInfo[] }
  | { type: 'awaiting_input'; reason: string; question: string; options?: string[] }
  | { type: 'result'; data: RecommendationResponse }
  | { type: 'error'; message: string }
  | { type: 'done' };
```

- [ ] **Step 2: Verify types compile**

Run (from `frontend/`):
```bash
npm run build
```
Expected: `tsc` compiles with no errors. (No runtime test — type-only change; it is exercised by Tasks 3–6.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/observation.ts
git commit -m "feat: add session_id + awaiting_input frontend types"
```

---

### Task 3: Refactor the SSE client into shared helpers

This is an internal refactor: extract the SSE-reader loop (`consumeSSEStream`) and the POST-and-stream wrapper (`streamSSE`) so the upcoming resume function reuses them. `identifyBirdStream`'s observable behavior must not change.

**Files:**
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/api/client.test.ts`

- [ ] **Step 1: Write failing tests for the refactored stream client**

Create `frontend/src/api/client.test.ts`:
```ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { identifyBirdStream } from './client';
import type { StreamEvent } from '../types/observation';

/** Build a fake fetch Response whose body streams the given SSE text chunks. */
function sseResponse(chunks: string[], ok = true, status = 200): Response {
  let i = 0;
  const reader = {
    read() {
      if (i < chunks.length) {
        const value = new TextEncoder().encode(chunks[i++]);
        return Promise.resolve({ done: false, value });
      }
      return Promise.resolve({ done: true, value: undefined });
    },
  };
  return { ok, status, body: { getReader: () => reader } } as unknown as Response;
}

function dataLine(event: object): string {
  return `data: ${JSON.stringify(event)}\n\n`;
}

describe('identifyBirdStream', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('POSTs to the stream endpoint and delivers each parsed event', async () => {
    vi.mocked(fetch).mockResolvedValue(
      sseResponse([
        dataLine({ type: 'session_id', session_id: 's-1' }),
        dataLine({ type: 'status', message: 'Checking...' }),
        dataLine({ type: 'done' }),
      ]),
    );

    const events: StreamEvent[] = [];
    await identifyBirdStream({ description: 'red bird', location: 'NY' }, (e) =>
      events.push(e),
    );

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/identify/stream'),
      expect.objectContaining({ method: 'POST' }),
    );
    expect(events.map((e) => e.type)).toEqual(['session_id', 'status', 'done']);
  });

  it('handles events split across read() chunks', async () => {
    vi.mocked(fetch).mockResolvedValue(
      sseResponse([
        'data: {"type":"sta',
        'tus","message":"hi"}\n\n' + dataLine({ type: 'done' }),
      ]),
    );

    const events: StreamEvent[] = [];
    await identifyBirdStream({ description: 'x', location: 'y' }, (e) => events.push(e));

    expect(events).toEqual([
      { type: 'status', message: 'hi' },
      { type: 'done' },
    ]);
  });

  it('throws when the stream ends without a done event', async () => {
    vi.mocked(fetch).mockResolvedValue(
      sseResponse([dataLine({ type: 'status', message: 'hi' })]),
    );

    await expect(
      identifyBirdStream({ description: 'x', location: 'y' }, () => {}),
    ).rejects.toThrow('Stream ended unexpectedly');
  });

  it('throws on a non-ok response', async () => {
    vi.mocked(fetch).mockResolvedValue(sseResponse([], false, 500));

    await expect(
      identifyBirdStream({ description: 'x', location: 'y' }, () => {}),
    ).rejects.toThrow('Stream request failed: 500');
  });
});
```

- [ ] **Step 2: Run the tests to confirm they pass against the current implementation**

Run:
```bash
npm test -- client
```
Expected: PASS (the current `identifyBirdStream` already satisfies these). This locks in behavior **before** the refactor so the refactor can't silently change it.

- [ ] **Step 3: Refactor `client.ts` to extract the helpers**

Replace the entire contents of `frontend/src/api/client.ts` with:
```ts
/**
 * API client for backend communication.
 */
import type {
  ObservationInput,
  RecommendationResponse,
  ResumeInput,
  StreamEvent,
} from '../types/observation';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export async function identifyBird(
  observation: ObservationInput
): Promise<RecommendationResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 95_000);

  try {
    const response = await fetch(`${API_BASE_URL}/api/identify`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(observation),
      signal: controller.signal,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const errorMessage = errorData.detail || response.statusText || 'API request failed';
      throw new Error(errorMessage);
    }

    return response.json();
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('Request timed out after 45 seconds. Please try again.');
    }
    if (error instanceof TypeError && error.message.includes('fetch')) {
      throw new Error('Cannot connect to server. Please ensure the backend is running at ' + API_BASE_URL);
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

/** Read an SSE response body, dispatching each `data:` event to onEvent. */
async function consumeSSEStream(
  response: Response,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let receivedDone = false;

  let reading = true;
  while (reading) {
    const { done, value } = await reader.read();
    if (done) {
      reading = false;
      break;
    }
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
}

/** POST a JSON body to an SSE endpoint and stream the events. */
async function streamSSE(
  path: string,
  body: unknown,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const controller = new AbortController();
  const connectionTimeout = setTimeout(() => controller.abort(), 5_000);

  // Link external signal to our controller
  const onAbort = () => controller.abort();
  signal?.addEventListener('abort', onAbort);

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    clearTimeout(connectionTimeout);

    if (!response.ok) {
      throw new Error(`Stream request failed: ${response.status}`);
    }

    await consumeSSEStream(response, onEvent);
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

export function identifyBirdStream(
  observation: ObservationInput,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamSSE('/api/identify/stream', observation, onEvent, signal);
}

export function resumeIdentificationStream(
  payload: ResumeInput,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamSSE('/api/identify/resume', payload, onEvent, signal);
}
```
Note: `resumeIdentificationStream` is added here too (it's a one-liner over `streamSSE`); Task 4 adds its dedicated test.

- [ ] **Step 4: Run the existing tests — behavior must be unchanged**

Run:
```bash
npm test -- client
```
Expected: PASS — the same 4 tests still pass against the refactored code.

- [ ] **Step 5: Verify build + lint**

Run:
```bash
npm run build && npm run lint
```
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/api/client.test.ts
git commit -m "refactor: extract shared SSE helpers + add resume client fn"
```

---

### Task 4: Test the resume client function

`resumeIdentificationStream` already exists (added in Task 3). This task adds its dedicated test.

**Files:**
- Modify: `frontend/src/api/client.test.ts`

- [ ] **Step 1: Add failing tests for `resumeIdentificationStream`**

In `frontend/src/api/client.test.ts`, update the import line:
```ts
import { identifyBirdStream } from './client';
```
to:
```ts
import { identifyBirdStream, resumeIdentificationStream } from './client';
```
Then append this new `describe` block to the end of the file:
```ts
describe('resumeIdentificationStream', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('POSTs the session_id + user_message to the resume endpoint', async () => {
    vi.mocked(fetch).mockResolvedValue(
      sseResponse([
        dataLine({ type: 'session_id', session_id: 's-9' }),
        dataLine({ type: 'done' }),
      ]),
    );

    await resumeIdentificationStream(
      { session_id: 's-9', user_message: 'It had a crest' },
      () => {},
    );

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/identify/resume'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ session_id: 's-9', user_message: 'It had a crest' }),
      }),
    );
  });

  it('delivers resumed events through onEvent', async () => {
    vi.mocked(fetch).mockResolvedValue(
      sseResponse([
        dataLine({ type: 'session_id', session_id: 's-9' }),
        dataLine({
          type: 'result',
          data: { message: 'Northern Cardinal.', alternate_species: [] },
        }),
        dataLine({ type: 'done' }),
      ]),
    );

    const types: string[] = [];
    await resumeIdentificationStream(
      { session_id: 's-9', user_message: 'crest' },
      (e) => types.push(e.type),
    );

    expect(types).toEqual(['session_id', 'result', 'done']);
  });

  it('returns silently when the caller aborts', async () => {
    const controller = new AbortController();
    vi.mocked(fetch).mockImplementation(() => {
      controller.abort();
      return Promise.reject(
        new DOMException('Aborted', 'AbortError'),
      );
    });

    await expect(
      resumeIdentificationStream(
        { session_id: 's-9', user_message: 'crest' },
        () => {},
        controller.signal,
      ),
    ).resolves.toBeUndefined();
  });
});
```

- [ ] **Step 2: Run the tests**

Run:
```bash
npm test -- client
```
Expected: PASS — all 7 tests (4 from Task 3 + 3 new).

- [ ] **Step 3: Verify build + lint**

Run:
```bash
npm run build && npm run lint
```
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.test.ts
git commit -m "test: cover resumeIdentificationStream"
```

---

### Task 5: AwaitingInputPrompt component

A presentational prompt: shows the question, renders one chip button per option, and a free-text form. Both a chip click and a free-text submit call `onAnswer(message)`. No network, no session knowledge — that lives in `Home`.

**Files:**
- Create: `frontend/src/components/AwaitingInputPrompt.tsx`
- Create: `frontend/src/components/AwaitingInputPrompt.test.tsx`

- [ ] **Step 1: Write the failing component tests**

Create `frontend/src/components/AwaitingInputPrompt.test.tsx`:
```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AwaitingInputPrompt } from './AwaitingInputPrompt';

describe('AwaitingInputPrompt', () => {
  it('renders the question', () => {
    render(
      <AwaitingInputPrompt question="Crest or no crest?" onAnswer={() => {}} />,
    );
    expect(screen.getByText('Crest or no crest?')).toBeInTheDocument();
  });

  it('renders a chip button per option and answers with its label', async () => {
    const onAnswer = vi.fn();
    render(
      <AwaitingInputPrompt
        question="Which one?"
        options={['Crest', 'No crest']}
        onAnswer={onAnswer}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Crest' }));
    expect(onAnswer).toHaveBeenCalledWith('Crest');
  });

  it('answers with trimmed free text on submit', async () => {
    const onAnswer = vi.fn();
    render(<AwaitingInputPrompt question="Tell me more" onAnswer={onAnswer} />);

    await userEvent.type(
      screen.getByPlaceholderText(/type your answer/i),
      '  it was tiny  ',
    );
    await userEvent.click(screen.getByRole('button', { name: /send/i }));

    expect(onAnswer).toHaveBeenCalledWith('it was tiny');
  });

  it('does not answer on empty free-text submit', async () => {
    const onAnswer = vi.fn();
    render(<AwaitingInputPrompt question="Tell me more" onAnswer={onAnswer} />);

    // Send button is disabled while the field is empty.
    expect(screen.getByRole('button', { name: /send/i })).toBeDisabled();
    expect(onAnswer).not.toHaveBeenCalled();
  });

  it('renders no chips when options is empty or omitted', () => {
    render(<AwaitingInputPrompt question="No options" onAnswer={() => {}} />);
    // Only the submit ("send") button should be present.
    expect(screen.getAllByRole('button')).toHaveLength(1);
  });

  it('disables interaction when disabled', () => {
    render(
      <AwaitingInputPrompt
        question="Busy"
        options={['A']}
        disabled
        onAnswer={() => {}}
      />,
    );
    expect(screen.getByRole('button', { name: 'A' })).toBeDisabled();
    expect(screen.getByPlaceholderText(/type your answer/i)).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
npm test -- AwaitingInputPrompt
```
Expected: FAIL — `Failed to resolve import "./AwaitingInputPrompt"` (component does not exist yet).

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/AwaitingInputPrompt.tsx`:
```tsx
/**
 * Prompt shown when the agent pauses to ask the user a question
 * (the `awaiting_input` SSE event). Offers quick-reply chips and a
 * free-text field; both resume the conversation via onAnswer.
 */
import { useState } from 'react';

interface AwaitingInputPromptProps {
  question: string;
  options?: string[];
  disabled?: boolean;
  onAnswer: (message: string) => void;
}

export function AwaitingInputPrompt({
  question,
  options,
  disabled = false,
  onAnswer,
}: AwaitingInputPromptProps) {
  const [text, setText] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) return;
    onAnswer(trimmed);
    setText('');
  };

  return (
    <div className="bg-blue-50 border-2 border-blue-300 rounded-lg p-5 shadow-sm space-y-4">
      <div className="flex items-start gap-3">
        <span className="text-2xl">🐦</span>
        <p className="text-base font-medium text-blue-900 leading-relaxed">
          {question}
        </p>
      </div>

      {options && options.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {options.map((opt) => (
            <button
              key={opt}
              type="button"
              disabled={disabled}
              onClick={() => onAnswer(opt)}
              className="px-4 py-2 bg-white border border-blue-400 text-blue-700 text-sm font-medium rounded-full hover:bg-blue-100 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {opt}
            </button>
          ))}
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="type your answer... ✍️"
          disabled={disabled}
          className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={disabled || !text.trim()}
          className="px-5 py-2 bg-blue-500 text-white text-sm font-medium rounded-lg hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          send 📨
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
npm test -- AwaitingInputPrompt
```
Expected: PASS — all 6 tests.

- [ ] **Step 5: Verify build + lint**

Run:
```bash
npm run build && npm run lint
```
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/AwaitingInputPrompt.tsx frontend/src/components/AwaitingInputPrompt.test.tsx
git commit -m "feat: add AwaitingInputPrompt component"
```

---

### Task 6: Wire session capture + resume flow into Home

`Home.tsx` captures the `session_id`, tracks an `awaiting` payload, renders `AwaitingInputPrompt` when the graph pauses, and resumes via `resumeIdentificationStream` when the user answers.

**Files:**
- Modify: `frontend/src/pages/Home.tsx`
- Create: `frontend/src/pages/Home.test.tsx`

- [ ] **Step 1: Write the failing integration test**

Create `frontend/src/pages/Home.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Home } from './Home';
import type { StreamEvent } from '../types/observation';

vi.mock('../api/client', () => ({
  identifyBird: vi.fn(),
  identifyBirdStream: vi.fn(),
  resumeIdentificationStream: vi.fn(),
}));

import {
  identifyBirdStream,
  resumeIdentificationStream,
} from '../api/client';

async function fillAndSubmit() {
  await userEvent.type(
    screen.getByLabelText(/what did you see/i),
    'small red bird with a crest',
  );
  await userEvent.type(screen.getByLabelText(/where are you/i), 'New York');
  await userEvent.click(screen.getByRole('button', { name: /let's go/i }));
}

describe('Home — HITL resume flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the awaiting prompt when the stream pauses', async () => {
    vi.mocked(identifyBirdStream).mockImplementation(
      async (_observation, onEvent: (e: StreamEvent) => void) => {
        onEvent({ type: 'session_id', session_id: 's-1' });
        onEvent({
          type: 'awaiting_input',
          reason: 'disambiguate_species',
          question: 'Crest or no crest?',
          options: ['Crest', 'No crest'],
        });
      },
    );

    render(<Home />);
    await fillAndSubmit();

    expect(await screen.findByText('Crest or no crest?')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Crest' })).toBeInTheDocument();
  });

  it('resumes with the captured session_id when a chip is clicked', async () => {
    vi.mocked(identifyBirdStream).mockImplementation(
      async (_observation, onEvent: (e: StreamEvent) => void) => {
        onEvent({ type: 'session_id', session_id: 's-42' });
        onEvent({
          type: 'awaiting_input',
          reason: 'disambiguate_species',
          question: 'Crest or no crest?',
          options: ['Crest'],
        });
      },
    );
    vi.mocked(resumeIdentificationStream).mockImplementation(
      async (_payload, onEvent: (e: StreamEvent) => void) => {
        onEvent({
          type: 'result',
          data: {
            message: 'It is a Northern Cardinal.',
            alternate_species: [],
          },
        });
      },
    );

    render(<Home />);
    await fillAndSubmit();
    await screen.findByText('Crest or no crest?');

    await userEvent.click(screen.getByRole('button', { name: 'Crest' }));

    expect(resumeIdentificationStream).toHaveBeenCalledWith(
      { session_id: 's-42', user_message: 'Crest' },
      expect.any(Function),
      expect.any(Object),
    );
    expect(
      await screen.findByText('It is a Northern Cardinal.'),
    ).toBeInTheDocument();
  });

  it('shows an error if answered after the session was lost', async () => {
    // Stream pauses but never emits a session_id.
    vi.mocked(identifyBirdStream).mockImplementation(
      async (_observation, onEvent: (e: StreamEvent) => void) => {
        onEvent({
          type: 'awaiting_input',
          reason: 'clarify_location',
          question: 'Where did you see it?',
          options: ['Skip — no location'],
        });
      },
    );

    render(<Home />);
    await fillAndSubmit();
    await screen.findByText('Where did you see it?');

    await userEvent.click(
      screen.getByRole('button', { name: 'Skip — no location' }),
    );

    expect(
      await screen.findByText(/start a new identification/i),
    ).toBeInTheDocument();
    expect(resumeIdentificationStream).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
npm test -- Home
```
Expected: FAIL — `Home` does not yet capture `session_id`, render the prompt, or call `resumeIdentificationStream`.

- [ ] **Step 3: Update the imports in `Home.tsx`**

In `frontend/src/pages/Home.tsx`, the top imports currently are:
```tsx
import { useState, useEffect, useRef, useCallback } from 'react';
import { BirdForm } from '../components/BirdForm';
import { ResultPanel } from '../components/ResultPanel';
import { identifyBird, identifyBirdStream } from '../api/client';
import type { ObservationInput, RecommendationResponse, StreamEvent } from '../types/observation';
```
Replace them with:
```tsx
import { useState, useEffect, useRef, useCallback } from 'react';
import { BirdForm } from '../components/BirdForm';
import { ResultPanel } from '../components/ResultPanel';
import { AwaitingInputPrompt } from '../components/AwaitingInputPrompt';
import {
  identifyBird,
  identifyBirdStream,
  resumeIdentificationStream,
} from '../api/client';
import type {
  AwaitingInput,
  ObservationInput,
  RecommendationResponse,
  StreamEvent,
} from '../types/observation';
```

- [ ] **Step 4: Add the session + awaiting state**

In `frontend/src/pages/Home.tsx`, find the state declarations block that currently ends with:
```tsx
  const timerRef = useRef<number | null>(null);
  const lastObservationRef = useRef<ObservationInput | null>(null);
  const abortRef = useRef<AbortController | null>(null);
```
Replace that three-line block with:
```tsx
  const [awaiting, setAwaiting] = useState<AwaitingInput | null>(null);
  const timerRef = useRef<number | null>(null);
  const lastObservationRef = useRef<ObservationInput | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const sessionIdRef = useRef<string | null>(null);
```

- [ ] **Step 5: Handle the new events in `handleStreamEvent`**

In `frontend/src/pages/Home.tsx`, the `handleStreamEvent` callback currently is:
```tsx
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
```
Replace it with (adds `session_id` + `awaiting_input`; clears `awaiting` on terminal events; `detective_note` / `candidates` intentionally unhandled — rendering deferred per spec §3):
```tsx
  const handleStreamEvent = useCallback((event: StreamEvent) => {
    switch (event.type) {
      case 'session_id':
        sessionIdRef.current = event.session_id;
        break;
      case 'status':
        setStatusMessage(event.message);
        break;
      case 'thinking':
        setThinkingText((prev) => prev + event.content);
        break;
      case 'awaiting_input':
        setAwaiting({
          reason: event.reason,
          question: event.question,
          options: event.options,
        });
        break;
      case 'result':
        setResult(event.data);
        setAwaiting(null);
        break;
      case 'error':
        setError(event.message);
        setCanRetry(true);
        setAwaiting(null);
        break;
      case 'tool_call':
        setStatusMessage(`Calling ${event.tool}...`);
        break;
      case 'tool_result':
        setStatusMessage(event.summary);
        break;
      case 'detective_note':
      case 'candidates':
        // Notebook panel + candidate gallery are the next iteration (spec §3).
        break;
      case 'done':
        break;
    }
  }, []);
```

- [ ] **Step 6: Reset session + awaiting state on a fresh submit**

In `frontend/src/pages/Home.tsx`, `handleSubmit` currently begins:
```tsx
    lastObservationRef.current = observation;
    setIsLoading(true);
    setError(null);
    setResult(null);
    setCanRetry(false);
    setStatusMessage('');
    setThinkingText('');
    setShowThinking(false);
```
Replace that block with (adds the two resets):
```tsx
    lastObservationRef.current = observation;
    sessionIdRef.current = null;
    setIsLoading(true);
    setError(null);
    setResult(null);
    setAwaiting(null);
    setCanRetry(false);
    setStatusMessage('');
    setThinkingText('');
    setShowThinking(false);
```

- [ ] **Step 7: Add the `handleAnswer` resume handler**

In `frontend/src/pages/Home.tsx`, the `handleRetry` function currently is:
```tsx
  const handleRetry = () => {
    if (lastObservationRef.current) {
      handleSubmit(lastObservationRef.current);
    }
  };
```
Insert this new function immediately **before** `handleRetry`:
```tsx
  const handleAnswer = async (message: string) => {
    const sessionId = sessionIdRef.current;
    if (!sessionId) {
      setError('Lost the session. Please start a new identification.');
      setAwaiting(null);
      return;
    }

    // Abort any in-flight stream
    abortRef.current?.abort();
    const abortController = new AbortController();
    abortRef.current = abortController;

    setAwaiting(null);
    setIsLoading(true);
    setError(null);
    setCanRetry(false);
    setStatusMessage('');
    setThinkingText('');

    try {
      await resumeIdentificationStream(
        { session_id: sessionId, user_message: message },
        handleStreamEvent,
        abortController.signal,
      );
    } catch (err) {
      if (abortController.signal.aborted) return; // User cancelled
      const errorMessage =
        err instanceof Error
          ? err.message
          : 'An unexpected error occurred. Please try again.';
      setError(errorMessage);
      setCanRetry(true);
    } finally {
      setIsLoading(false);
    }
  };

```

- [ ] **Step 8: Render the prompt**

In `frontend/src/pages/Home.tsx`, find the results block:
```tsx
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
```
Insert this block immediately **before** it:
```tsx
          {/* Awaiting user input (HITL pause) */}
          {awaiting && !isLoading && (
            <div className="animate-fade-in mb-8">
              <AwaitingInputPrompt
                question={awaiting.question}
                options={awaiting.options}
                onAnswer={handleAnswer}
              />
            </div>
          )}

```

- [ ] **Step 9: Run the integration test**

Run:
```bash
npm test -- Home
```
Expected: PASS — all 3 tests.

- [ ] **Step 10: Verify the whole frontend suite + build + lint**

Run (from `frontend/`):
```bash
npm run build && npm run lint && npm test
```
Expected: `tsc` clean, ESLint 0 warnings, all tests pass (smoke + client + AwaitingInputPrompt + Home).

- [ ] **Step 11: Commit**

```bash
git add frontend/src/pages/Home.tsx frontend/src/pages/Home.test.tsx
git commit -m "feat: wire session capture + HITL resume flow into Home"
```

---

### Task 7: Final verification

**Files:** none (verification only).

- [ ] **Step 1: Run the complete frontend check suite exactly as CI does**

Run (from `frontend/`):
```bash
npm ci && npm run build && npm run lint && npm test
```
Expected: all four steps succeed. `npm ci` proves `package-lock.json` is consistent; `build` proves types are sound; `lint` proves 0 warnings; `test` proves all suites green.

- [ ] **Step 2: Confirm no stray uncommitted changes**

Run (from repo root):
```bash
git status --short
```
Expected: clean working tree (every change from Tasks 1–6 is committed). If `package-lock.json` shows as modified after `npm ci`, commit it:
```bash
git add frontend/package-lock.json && git commit -m "chore: sync frontend lockfile"
```

---

## Self-Review

**1. Spec coverage** (against `docs/superpowers/specs/2026-05-31-langgraph-hitl-bird-id-design.md` §8, §9, §11 — the frontend slice):

| Spec requirement | Task |
|------------------|------|
| `session_id` plumbing (capture, send back each turn) | Task 2 (type), Task 6 (capture in `sessionIdRef`, send in `handleAnswer`) |
| Resume call → `POST /api/identify/resume {session_id, user_message}` | Task 3 (`resumeIdentificationStream`), Task 4 (test), Task 6 (wire) |
| `awaiting_input` event type | Task 2 |
| Render `awaiting_input` as a prompt (quick-reply chips + free text) | Task 5 (component), Task 6 (render) |
| Chip label becomes the user message; free text wins (spec §6) | Task 5 (`onAnswer(opt)` for chips, trimmed text on submit) |
| `inconclusive` result variant needs no new handling (existing `result`) | Confirmed — `ResultPanel` already renders `message` + optional species; no change needed |
| Notebook / candidate-gallery rendering deferred (spec §3) | `detective_note` / `candidates` left unhandled with an explicit comment (Task 6, Step 5) |
| "Minimal — full chat/notebook UI is next iteration" (spec §11) | No chat scroll, no theme change, no notebook panel — only the resume plumbing |

No gaps in the frontend slice. Backend slice (§4–§7, §10) was delivered by the LangGraph backend plan (`2026-05-31-langgraph-hitl-backend.md`) and is out of scope here.

**2. Placeholder scan:** No "TBD"/"TODO"/"handle edge cases" — every code step shows complete code; every command shows expected output. The one "decision" (vitest config as a separate file vs folded into `vite.config.ts`) is resolved explicitly: folded in.

**3. Type consistency:**
- `AwaitingInput { reason; question; options? }` (Task 2) — matches the `awaiting_input` event fields used in `handleStreamEvent` (Task 6, Step 5) and the `AwaitingInputPrompt` props consuming `question`/`options` (Task 5).
- `ResumeInput { session_id; user_message }` (Task 2) — matches the body passed in `handleAnswer` (Task 6, Step 7) and asserted in the client test (Task 4) and the `resumeIdentificationStream` signature (Task 3).
- `resumeIdentificationStream(payload, onEvent, signal?)` — same signature used in Task 4 tests, Task 6 wiring, and Task 6 test (`expect.any(Function)`, `expect.any(Object)` for the signal).
- `options` is `string[]` everywhere (backend emits plain-string labels — verified in `tools.py:169` / `nodes.py:216`); no `comparison` field anywhere.
- Event union members added in Task 2 (`session_id`, `awaiting_input`) are exactly the `case` labels added in Task 6.

Consistent throughout. Plan is ready for execution.
