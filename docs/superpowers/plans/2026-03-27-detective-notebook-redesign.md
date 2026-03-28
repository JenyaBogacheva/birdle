# Detective Notebook Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform Birdle from a gradient form-based app into an immersive naturalist detective notebook with full-bleed bird photography, frosted glass panels, rough.js hand-drawn annotations, and a phased investigation flow.

**Architecture:** Backend adds two UI-only tools (`detective_note`, `update_candidates`) to the bird agent with a two-tier tool budget. Frontend is a full UI rewrite — new phase-based state machine, rough.js SVG overlays, CSS animations, and Caveat handwriting font. Streaming client reuses existing SSE parsing, extended with new event types.

**Tech Stack:** React 18, Vite, Tailwind CSS, rough.js (~9kb), Caveat (Google Fonts), FastAPI, Anthropic Claude Sonnet

**Spec:** `docs/superpowers/specs/2026-03-27-detective-notebook-redesign.md`

---

## File Structure

### Backend (modify)

| File | Changes |
|---|---|
| `services/backend/app/helpers/bird_agent.py` | Add `detective_note` + `update_candidates` tool definitions, two-tier budget counters, system prompt update, tool execution routing |
| `services/backend/app/routes/identify.py` | Intercept `candidates` events to resolve Macaulay image URLs before emitting SSE |
| `services/backend/app/schemas/observation.py` | Add `CandidateUpdate` Pydantic model |
| `services/backend/tests/test_bird_agent.py` | Tests for new tools, budget enforcement, tool result format |
| `services/backend/tests/test_identify.py` | Tests for candidates SSE event with image resolution |

### Frontend (create)

| File | Purpose |
|---|---|
| `frontend/src/pages/BirdleApp.tsx` | Top-level phase state machine (replaces Home.tsx) |
| `frontend/src/components/BirdBackground.tsx` | Full-bleed bird photo with dark overlay + crossfade |
| `frontend/src/components/PencilAnnotations.tsx` | rough.js SVG decorative scribbles |
| `frontend/src/components/FrostedPanel.tsx` | Reusable frosted glass container |
| `frontend/src/components/DetectiveNotes.tsx` | Streaming detective notes with typewriter reveal |
| `frontend/src/components/TypewriterText.tsx` | Character-by-character text reveal |
| `frontend/src/components/CandidateBoard.tsx` | Candidate bird grid with appear/eliminate animations |
| `frontend/src/components/CandidateCard.tsx` | Single candidate with rough.js border + cross-out |
| `frontend/src/components/RoughElement.tsx` | Thin wrapper around rough.js for animated SVG shapes |
| `frontend/src/components/ResultOverlay.tsx` | Final result frosted panel with species info |
| `frontend/src/components/AlternateSpecies.tsx` | Row of alternate species thumbnails |
| `frontend/src/hooks/useRough.ts` | React hook for rough.js canvas/SVG initialization |

### Frontend (modify)

| File | Changes |
|---|---|
| `frontend/src/components/BirdForm.tsx` | Restyle for frosted glass, Caveat labels, "Investigate" button |
| `frontend/src/api/client.ts` | Add `detective_note` and `candidates` to SSE event handling |
| `frontend/src/types/observation.ts` | Add `CandidateUpdate`, `DetectiveNoteEvent`, `CandidatesEvent` types |
| `frontend/src/index.css` | Replace current styles with new animations (typewriter, fade, cross-out, draw-in) |
| `frontend/tailwind.config.js` | Add Caveat font family, custom animation utilities |
| `frontend/package.json` | Add rough.js dependency |
| `frontend/index.html` | Add Google Fonts preconnect + Caveat stylesheet link |

### Frontend (delete)

| File | Reason |
|---|---|
| `frontend/src/pages/Home.tsx` | Replaced by BirdleApp.tsx |
| `frontend/src/components/ResultPanel.tsx` | Replaced by ResultOverlay.tsx |
| `frontend/src/components/SpeciesCard.tsx` | Replaced by CandidateCard.tsx + ResultOverlay.tsx |

---

## Task 1: Backend — Add Pydantic models for new tools

**Files:**
- Modify: `services/backend/app/schemas/observation.py`

- [ ] **Step 1: Write failing test for CandidateUpdate model**

```python
# In services/backend/tests/test_schemas.py (create)
from services.backend.app.schemas.observation import CandidateUpdate


def test_candidate_update_considering():
    c = CandidateUpdate(
        name="Common Kingfisher",
        species_code="comkin1",
        status="considering",
    )
    assert c.name == "Common Kingfisher"
    assert c.species_code == "comkin1"
    assert c.status == "considering"
    assert c.reason is None


def test_candidate_update_eliminated_with_reason():
    c = CandidateUpdate(
        name="Blue Jay",
        species_code="blujay",
        status="eliminated",
        reason="Too large",
    )
    assert c.status == "eliminated"
    assert c.reason == "Too large"


def test_candidate_update_invalid_status():
    import pytest
    with pytest.raises(Exception):
        CandidateUpdate(
            name="Test",
            species_code="test1",
            status="invalid",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest services/backend/tests/test_schemas.py -v`
Expected: FAIL — `CandidateUpdate` not defined

- [ ] **Step 3: Add CandidateUpdate model**

Add to `services/backend/app/schemas/observation.py`:

```python
from enum import Enum

class CandidateStatus(str, Enum):
    considering = "considering"
    eliminated = "eliminated"

class CandidateUpdate(BaseModel):
    name: str
    species_code: str
    status: CandidateStatus
    reason: Optional[str] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest services/backend/tests/test_schemas.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/schemas/observation.py services/backend/tests/test_schemas.py
git commit -m "feat: add CandidateUpdate Pydantic model for UI tools"
```

---

## Task 2: Backend — Add detective_note and update_candidates tools to agent

**Files:**
- Modify: `services/backend/app/helpers/bird_agent.py`

- [ ] **Step 1: Write failing test for new tool definitions**

Add to `services/backend/tests/test_bird_agent.py`:

```python
class TestUITools:
    """Tests for detective_note and update_candidates UI-only tools."""

    def test_detective_note_tool_in_definitions(self):
        """detective_note tool should be in TOOLS list."""
        from services.backend.app.helpers.bird_agent import TOOLS
        tool_names = [t["name"] for t in TOOLS]
        assert "detective_note" in tool_names

    def test_update_candidates_tool_in_definitions(self):
        """update_candidates tool should be in TOOLS list."""
        from services.backend.app.helpers.bird_agent import TOOLS
        tool_names = [t["name"] for t in TOOLS]
        assert "update_candidates" in tool_names

    @pytest.mark.asyncio
    async def test_execute_detective_note(self):
        """detective_note should return acknowledgment, not call external APIs."""
        from services.backend.app.helpers.bird_agent import _execute_tool
        result = await _execute_tool("detective_note", {"message": "Blue and orange..."})
        assert result == {"acknowledged": True}

    @pytest.mark.asyncio
    async def test_execute_update_candidates(self):
        """update_candidates should return acknowledgment, not call external APIs."""
        from services.backend.app.helpers.bird_agent import _execute_tool
        result = await _execute_tool("update_candidates", {
            "candidates": [
                {"name": "Kingfisher", "species_code": "comkin1", "status": "considering"}
            ]
        })
        assert result == {"acknowledged": True}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest services/backend/tests/test_bird_agent.py::TestUITools -v`
Expected: FAIL — tools not found

- [ ] **Step 3: Add tool definitions and execution routing**

In `bird_agent.py`, add tool definitions after existing `TOOLS` list (after line 152):

```python
UI_TOOLS = [
    {
        "name": "detective_note",
        "description": "Record a brief atmospheric observation about the investigation. Use this to share your thinking process as short, evocative notes — like a field naturalist's notebook. One sentence, max 10 words.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "A brief atmospheric observation, e.g. 'Blue and orange... interesting.' or 'That beak says kingfisher.'"
                }
            },
            "required": ["message"]
        }
    },
    {
        "name": "update_candidates",
        "description": "Update your shortlist of candidate species. Call this whenever you add or eliminate species from consideration.",
        "input_schema": {
            "type": "object",
            "properties": {
                "candidates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Common name of the species"},
                            "species_code": {"type": "string", "description": "eBird species code"},
                            "status": {"type": "string", "enum": ["considering", "eliminated"]},
                            "reason": {"type": "string", "description": "Brief reason for status"}
                        },
                        "required": ["name", "species_code", "status"]
                    }
                }
            },
            "required": ["candidates"]
        }
    }
]

ALL_TOOLS = TOOLS + UI_TOOLS
UI_TOOL_NAMES = {t["name"] for t in UI_TOOLS}
```

Add to the module-level `_execute_tool` function (at the top, before existing routing):

```python
if name in UI_TOOL_NAMES:
    return {"acknowledged": True}
```

Update the `messages.stream()` / `messages.create()` calls to use `ALL_TOOLS` instead of `TOOLS`.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest services/backend/tests/test_bird_agent.py::TestUITools -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/helpers/bird_agent.py services/backend/tests/test_bird_agent.py
git commit -m "feat: add detective_note and update_candidates UI tools to agent"
```

---

## Task 3: Backend — Two-tier tool budget

**Files:**
- Modify: `services/backend/app/helpers/bird_agent.py`

- [ ] **Step 1: Write failing test for budget enforcement**

Add to `services/backend/tests/test_bird_agent.py`:

```python
class TestToolBudget:
    """Tests for two-tier tool budget (data vs UI tools)."""

    def test_ui_tools_not_counted_against_data_budget(self):
        """UI tool calls should not count toward MAX_ITERATIONS."""
        from services.backend.app.helpers.bird_agent import UI_TOOL_NAMES, MAX_DATA_TOOL_CALLS, MAX_UI_TOOL_CALLS
        assert MAX_DATA_TOOL_CALLS == 8
        assert MAX_UI_TOOL_CALLS == 20
        assert "detective_note" in UI_TOOL_NAMES
        assert "update_candidates" in UI_TOOL_NAMES
        assert "get_regional_birds" not in UI_TOOL_NAMES
        assert "web_search" not in UI_TOOL_NAMES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest services/backend/tests/test_bird_agent.py::TestToolBudget -v`
Expected: FAIL — constants not defined

- [ ] **Step 3: Add budget constants and tracking**

In `bird_agent.py`, add constants:

```python
MAX_DATA_TOOL_CALLS = 8
MAX_UI_TOOL_CALLS = 20
```

In the `identify_stream` method, replace the single iteration counter with two counters:

```python
data_tool_calls = 0
ui_tool_calls = 0
```

When processing tool use blocks, increment the appropriate counter:

```python
for tool_block in tool_blocks:
    if tool_block.name in UI_TOOL_NAMES:
        ui_tool_calls += 1
        if ui_tool_calls > MAX_UI_TOOL_CALLS:
            break
    else:
        data_tool_calls += 1
        if data_tool_calls > MAX_DATA_TOOL_CALLS:
            break
```

The outer loop condition changes from `iteration < MAX_ITERATIONS` to checking whether data tool budget is exhausted. UI tool calls should not consume an iteration.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest services/backend/tests/test_bird_agent.py::TestToolBudget -v`
Expected: PASS

- [ ] **Step 5: Run all existing agent tests to verify no regressions**

Run: `poetry run pytest services/backend/tests/test_bird_agent.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add services/backend/app/helpers/bird_agent.py services/backend/tests/test_bird_agent.py
git commit -m "feat: two-tier tool budget (8 data / 20 UI)"
```

---

## Task 4: Backend — Emit new SSE events and resolve candidate images

**Files:**
- Modify: `services/backend/app/helpers/bird_agent.py` (yield new event types)
- Modify: `services/backend/app/routes/identify.py` (intercept candidates, resolve images)

- [ ] **Step 1: Write failing test for detective_note SSE event**

Add to `services/backend/tests/test_identify.py`:

```python
@pytest.mark.asyncio
async def test_stream_emits_detective_note(client, mock_bird_agent_stream):
    """detective_note events should pass through to SSE stream."""
    async def mock_stream(*args, **kwargs):
        yield {"type": "detective_note", "message": "Blue and orange... interesting."}
        yield {"type": "result", "data": sample_agent_result}

    mock_bird_agent_stream.side_effect = mock_stream
    response = client.post("/api/identify/stream", json={"description": "blue bird", "location": "US-NY"})
    events = parse_sse_events(response.text)
    detective_notes = [e for e in events if e.get("type") == "detective_note"]
    assert len(detective_notes) == 1
    assert detective_notes[0]["message"] == "Blue and orange... interesting."
```

- [ ] **Step 2: Write failing test for candidates SSE event with image URLs**

```python
@pytest.mark.asyncio
async def test_stream_resolves_candidate_images(client, mock_bird_agent_stream):
    """candidates events should have image_url resolved by backend."""
    async def mock_stream(*args, **kwargs):
        yield {
            "type": "candidates",
            "data": [
                {"name": "Common Kingfisher", "species_code": "comkin1", "status": "considering"}
            ]
        }
        yield {"type": "result", "data": sample_agent_result}

    mock_bird_agent_stream.side_effect = mock_stream
    with patch("services.backend.app.routes.identify.ebird_client") as mock_ebird:
        mock_ebird.get_species_image = AsyncMock(return_value={
            "image_url": "https://example.com/kingfisher.jpg",
            "photographer": "Test Photographer"
        })
        response = client.post("/api/identify/stream", json={"description": "blue bird", "location": "US-NY"})

    events = parse_sse_events(response.text)
    candidate_events = [e for e in events if e.get("type") == "candidates"]
    assert len(candidate_events) == 1
    assert candidate_events[0]["data"][0]["image_url"] == "https://example.com/kingfisher.jpg"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `poetry run pytest services/backend/tests/test_identify.py -k "detective_note or candidate_images" -v`
Expected: FAIL

- [ ] **Step 4: Update agent to yield new event types**

In `bird_agent.py` `identify_stream` method, when processing tool use blocks, yield events for UI tools before returning the acknowledgment:

```python
if tool_block.name == "detective_note":
    yield {"type": "detective_note", "message": tool_block.input["message"]}
elif tool_block.name == "update_candidates":
    yield {"type": "candidates", "data": tool_block.input["candidates"]}
```

- [ ] **Step 5: Update route to intercept candidates and resolve images**

In `identify.py` `event_generator`, add handling for `candidates` events (similar to how `result` events are intercepted):

```python
elif event.get("type") == "candidates":
    candidates = event["data"]
    # Resolve image URLs for new "considering" candidates
    async def resolve_image(candidate):
        if candidate.get("status") == "considering" and candidate.get("species_code"):
            img = await ebird_client.get_species_image(candidate["species_code"])
            if img:
                candidate["image_url"] = img["image_url"]
                candidate["image_credit"] = img.get("photographer")
        return candidate

    resolved = await asyncio.gather(*[resolve_image(c) for c in candidates])
    event["data"] = resolved
    yield f"data: {json.dumps(event)}\n\n"
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `poetry run pytest services/backend/tests/test_identify.py -k "detective_note or candidate_images" -v`
Expected: PASS

- [ ] **Step 7: Run all backend tests**

Run: `poetry run pytest services/backend/tests/ -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add services/backend/app/helpers/bird_agent.py services/backend/app/routes/identify.py services/backend/tests/test_identify.py
git commit -m "feat: emit detective_note and candidates SSE events with image resolution"
```

---

## Task 5: Backend — Update system prompt for detective style

**Files:**
- Modify: `services/backend/app/helpers/bird_agent.py`

- [ ] **Step 1: Add detective note instructions to SYSTEM_PROMPT**

Append to the existing system prompt (after the current instructions, before the JSON output format section):

```python
## Investigation Style

As you investigate, call `detective_note` with brief atmospheric observations — like a field naturalist's notebook. One sentence, max 10 words. Examples:
- "Blue and orange... interesting."
- "Too small for a jay."
- "That beak says kingfisher."
- "Common in this region. Good sign."

Call `update_candidates` whenever your shortlist of possible species changes. Include species you're considering and ones you've eliminated with brief reasons.

Start with a detective_note before your first tool call. Update candidates after reviewing regional data. Eliminate candidates as evidence rules them out.
```

- [ ] **Step 2: Run all backend tests to verify no regressions**

Run: `poetry run pytest services/backend/tests/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add services/backend/app/helpers/bird_agent.py
git commit -m "feat: update system prompt for detective-style investigation notes"
```

---

## Task 6: Frontend — Install dependencies and configure Tailwind

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/tailwind.config.js`
- Modify: `frontend/index.html`
- Modify: `frontend/src/index.css`

- [ ] **Step 1: Install rough.js**

Run: `cd frontend && npm install roughjs`

- [ ] **Step 2: Add Caveat font to index.html**

Add to `<head>` in `frontend/index.html`:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Caveat:wght@400;500;600;700&display=swap" rel="stylesheet">
```

- [ ] **Step 3: Update Tailwind config**

Replace `frontend/tailwind.config.js`:

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        hand: ['Caveat', 'cursive'],
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-in',
        'slide-up': 'slideUp 0.5s ease-out',
        'draw-in': 'drawIn 1s ease-out forwards',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        drawIn: {
          '0%': { strokeDashoffset: '1000' },
          '100%': { strokeDashoffset: '0' },
        },
      },
    },
  },
  plugins: [],
}
```

- [ ] **Step 4: Replace index.css with new animations**

Replace `frontend/src/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  body {
    @apply bg-black text-white overflow-hidden;
    font-family: system-ui, -apple-system, sans-serif;
  }
}

@layer utilities {
  .glass {
    background: rgba(0, 0, 0, 0.45);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.1);
  }

  .text-primary {
    color: rgba(255, 255, 255, 0.9);
  }

  .text-secondary {
    color: rgba(255, 255, 255, 0.6);
  }

  .text-faded {
    color: rgba(255, 255, 255, 0.35);
  }

  .overlay {
    background: rgba(0, 0, 0, 0.35);
  }
}

@keyframes typewriter {
  from { width: 0; }
  to { width: 100%; }
}

@keyframes crossOut {
  0% { stroke-dashoffset: 200; }
  100% { stroke-dashoffset: 0; }
}
```

- [ ] **Step 5: Verify build succeeds**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/tailwind.config.js frontend/index.html frontend/src/index.css
git commit -m "feat: add rough.js, Caveat font, detective notebook styles"
```

---

## Task 7: Frontend — Add new TypeScript types for SSE events

**Files:**
- Modify: `frontend/src/types/observation.ts`

- [ ] **Step 1: Add new types**

Add to `frontend/src/types/observation.ts`:

```typescript
export interface CandidateInfo {
  name: string;
  species_code: string;
  status: 'considering' | 'eliminated';
  reason?: string;
  image_url?: string;
  image_credit?: string;
}

export type AppPhase = 'landing' | 'thinking' | 'reveal' | 'result';
```

Update the `StreamEvent` union to include new event types:

```typescript
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

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/observation.ts
git commit -m "feat: add CandidateInfo, AppPhase types and new SSE event types"
```

---

## Task 8: Frontend — Shared components (FrostedPanel, TypewriterText, RoughElement)

**Files:**
- Create: `frontend/src/components/FrostedPanel.tsx`
- Create: `frontend/src/components/TypewriterText.tsx`
- Create: `frontend/src/components/RoughElement.tsx`
- Create: `frontend/src/hooks/useRough.ts`

- [ ] **Step 1: Create FrostedPanel**

```typescript
// frontend/src/components/FrostedPanel.tsx
import { ReactNode } from 'react';

interface FrostedPanelProps {
  children: ReactNode;
  className?: string;
}

export default function FrostedPanel({ children, className = '' }: FrostedPanelProps) {
  return (
    <div className={`glass rounded-xl p-6 ${className}`}>
      {children}
    </div>
  );
}
```

- [ ] **Step 2: Create TypewriterText**

```typescript
// frontend/src/components/TypewriterText.tsx
import { useState, useEffect } from 'react';

interface TypewriterTextProps {
  text: string;
  speed?: number; // ms per character
  className?: string;
  onComplete?: () => void;
}

export default function TypewriterText({ text, speed = 40, className = '', onComplete }: TypewriterTextProps) {
  const [displayed, setDisplayed] = useState('');

  useEffect(() => {
    setDisplayed('');
    let i = 0;
    const interval = setInterval(() => {
      i++;
      setDisplayed(text.slice(0, i));
      if (i >= text.length) {
        clearInterval(interval);
        onComplete?.();
      }
    }, speed);
    return () => clearInterval(interval);
  }, [text, speed, onComplete]);

  return (
    <span className={`font-hand ${className}`}>
      {displayed}
      {displayed.length < text.length && (
        <span className="animate-pulse">|</span>
      )}
    </span>
  );
}
```

- [ ] **Step 3: Create useRough hook**

```typescript
// frontend/src/hooks/useRough.ts
import { useRef, useEffect, useState } from 'react';
import rough from 'roughjs';
import type { RoughSVG } from 'roughjs/bin/svg';

export function useRough() {
  const svgRef = useRef<SVGSVGElement>(null);
  const [rc, setRc] = useState<RoughSVG | null>(null);

  useEffect(() => {
    if (svgRef.current) {
      setRc(rough.svg(svgRef.current));
    }
  }, []);

  return { svgRef, rc };
}
```

- [ ] **Step 4: Create RoughElement**

```typescript
// frontend/src/components/RoughElement.tsx
import { useEffect, useRef } from 'react';
import { useRough } from '../hooks/useRough';

interface RoughElementProps {
  type: 'circle' | 'line' | 'rectangle';
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  x2?: number;
  y2?: number;
  options?: Record<string, unknown>;
  className?: string;
  animate?: boolean;
}

export default function RoughElement({
  type, x = 0, y = 0, width = 100, height = 100,
  x2 = 100, y2 = 100, options = {}, className = '', animate = true,
}: RoughElementProps) {
  const { svgRef, rc } = useRough();
  const drawnRef = useRef(false);

  const defaultOptions = {
    stroke: 'rgba(255,255,255,0.7)',
    strokeWidth: 1.5,
    roughness: 1.5,
    ...options,
  };

  useEffect(() => {
    if (!rc || !svgRef.current || drawnRef.current) return;
    drawnRef.current = true;

    let node: SVGGElement;
    switch (type) {
      case 'circle':
        node = rc.circle(x + width / 2, y + height / 2, width, defaultOptions);
        break;
      case 'rectangle':
        node = rc.rectangle(x, y, width, height, defaultOptions);
        break;
      case 'line':
        node = rc.line(x, y, x2, y2, defaultOptions);
        break;
    }

    if (animate) {
      const paths = node.querySelectorAll('path');
      paths.forEach((path) => {
        const length = path.getTotalLength();
        path.style.strokeDasharray = `${length}`;
        path.style.strokeDashoffset = `${length}`;
        path.style.animation = `drawIn 0.8s ease-out forwards`;
      });
    }

    svgRef.current.appendChild(node);
  }, [rc, type, x, y, width, height, x2, y2, animate]);

  return (
    <svg
      ref={svgRef}
      className={`absolute inset-0 pointer-events-none ${className}`}
      width="100%"
      height="100%"
    />
  );
}
```

- [ ] **Step 5: Verify build**

Run: `cd frontend && npm run build`
Expected: PASS (components not yet used, but should compile)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/FrostedPanel.tsx frontend/src/components/TypewriterText.tsx frontend/src/components/RoughElement.tsx frontend/src/hooks/useRough.ts
git commit -m "feat: add shared components — FrostedPanel, TypewriterText, RoughElement"
```

---

## Task 9: Frontend — BirdBackground component

**Files:**
- Create: `frontend/src/components/BirdBackground.tsx`

- [ ] **Step 1: Create BirdBackground with crossfade**

```typescript
// frontend/src/components/BirdBackground.tsx
import { useState, useEffect } from 'react';

interface BirdBackgroundProps {
  src: string;
  className?: string;
}

export default function BirdBackground({ src, className = '' }: BirdBackgroundProps) {
  const [currentSrc, setCurrentSrc] = useState(src);
  const [nextSrc, setNextSrc] = useState<string | null>(null);
  const [showNext, setShowNext] = useState(false);

  useEffect(() => {
    if (src !== currentSrc) {
      // Preload new image, then crossfade
      const img = new Image();
      img.onload = () => {
        setNextSrc(src);
        // Small delay to ensure the element renders before transition
        requestAnimationFrame(() => {
          setShowNext(true);
        });
      };
      img.src = src;
    }
  }, [src, currentSrc]);

  const handleTransitionEnd = () => {
    if (showNext && nextSrc) {
      setCurrentSrc(nextSrc);
      setNextSrc(null);
      setShowNext(false);
    }
  };

  return (
    <div className={`fixed inset-0 ${className}`}>
      {/* Current image */}
      <img
        src={currentSrc}
        alt=""
        className="absolute inset-0 w-full h-full object-cover"
      />
      {/* Next image (crossfade) */}
      {nextSrc && (
        <img
          src={nextSrc}
          alt=""
          className="absolute inset-0 w-full h-full object-cover transition-opacity duration-700"
          style={{ opacity: showNext ? 1 : 0 }}
          onTransitionEnd={handleTransitionEnd}
        />
      )}
      {/* Dark overlay */}
      <div className="absolute inset-0 overlay" />
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/BirdBackground.tsx
git commit -m "feat: add BirdBackground component with crossfade transitions"
```

---

## Task 10: Frontend — PencilAnnotations component

**Files:**
- Create: `frontend/src/components/PencilAnnotations.tsx`

- [ ] **Step 1: Create PencilAnnotations**

```typescript
// frontend/src/components/PencilAnnotations.tsx
interface Annotation {
  text: string;
  x: string;      // CSS position (e.g., '10%')
  y: string;
  rotation: number; // degrees
  opacity: number;
  size: string;    // Tailwind text size class
}

const LANDING_ANNOTATIONS: Annotation[] = [
  { text: 'What colors did you see?', x: '5%', y: '12%', rotation: -3, opacity: 0.5, size: 'text-2xl' },
  { text: 'How big was it?', x: '65%', y: '8%', rotation: 2, opacity: 0.45, size: 'text-xl' },
  { text: 'Where did you see it?', x: '70%', y: '25%', rotation: -1, opacity: 0.55, size: 'text-lg' },
  { text: 'What was it doing?', x: '8%', y: '55%', rotation: 1, opacity: 0.4, size: 'text-xl' },
  { text: 'Remember the colors?', x: '72%', y: '50%', rotation: -2, opacity: 0.35, size: 'text-lg' },
  { text: '- - - →', x: '25%', y: '40%', rotation: 0, opacity: 0.3, size: 'text-2xl' },
  { text: '↗', x: '60%', y: '35%', rotation: 15, opacity: 0.3, size: 'text-3xl' },
];

interface PencilAnnotationsProps {
  annotations?: Annotation[];
  show?: boolean;
}

export default function PencilAnnotations({ annotations = LANDING_ANNOTATIONS, show = true }: PencilAnnotationsProps) {
  if (!show) return null;

  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden">
      {annotations.map((ann, i) => (
        <span
          key={i}
          className={`absolute font-hand text-white animate-fade-in ${ann.size}`}
          style={{
            left: ann.x,
            top: ann.y,
            transform: `rotate(${ann.rotation}deg)`,
            opacity: ann.opacity,
            animationDelay: `${i * 0.15}s`,
            animationFillMode: 'backwards',
          }}
        >
          {ann.text}
        </span>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/PencilAnnotations.tsx
git commit -m "feat: add PencilAnnotations decorative overlay component"
```

---

## Task 11: Frontend — DetectiveNotes component

**Files:**
- Create: `frontend/src/components/DetectiveNotes.tsx`

- [ ] **Step 1: Create DetectiveNotes**

```typescript
// frontend/src/components/DetectiveNotes.tsx
import TypewriterText from './TypewriterText';

interface DetectiveNote {
  id: string;
  message: string;
}

// Canned note mappings for non-LLM events
const CANNED_NOTES: Record<string, string> = {
  'stream_start': "Let's find this bird...",
  'get_regional_birds': 'Checking the local records...',
  'web_search': 'Digging deeper...',
  'error': 'Hmm, hit a snag...',
};

export function cannedNoteForEvent(
  eventType: string,
  toolName?: string,
  toolSummary?: string,
): string | null {
  if (eventType === 'status' && toolName === undefined) return CANNED_NOTES['stream_start'];
  if (eventType === 'tool_call' && toolName) return CANNED_NOTES[toolName] ?? null;
  if (eventType === 'tool_result' && toolSummary) {
    const match = toolSummary.match(/Found (\d+) species/);
    if (match) return `${match[1]} species in the area. Let's narrow it down.`;
    return null;
  }
  if (eventType === 'error') return CANNED_NOTES['error'];
  return null;
}

// Stagger positions for organic notebook feel
const POSITIONS = [
  { x: '5%', y: '0', rotation: -2 },
  { x: '15%', y: '0', rotation: 1 },
  { x: '3%', y: '0', rotation: -1 },
  { x: '20%', y: '0', rotation: 2 },
  { x: '8%', y: '0', rotation: -3 },
  { x: '12%', y: '0', rotation: 0 },
];

interface DetectiveNotesProps {
  notes: DetectiveNote[];
}

export default function DetectiveNotes({ notes }: DetectiveNotesProps) {
  return (
    <div className="absolute inset-0 pointer-events-none overflow-y-auto p-8">
      <div className="flex flex-col gap-6 max-w-lg">
        {notes.map((note, i) => {
          const pos = POSITIONS[i % POSITIONS.length];
          return (
            <div
              key={note.id}
              className="animate-fade-in"
              style={{
                marginLeft: pos.x,
                transform: `rotate(${pos.rotation}deg)`,
                animationDelay: '0.1s',
                animationFillMode: 'backwards',
              }}
            >
              <TypewriterText
                text={note.message}
                speed={35}
                className="text-xl text-secondary"
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/DetectiveNotes.tsx
git commit -m "feat: add DetectiveNotes component with typewriter reveal and canned notes"
```

---

## Task 12: Frontend — CandidateCard and CandidateBoard components

**Files:**
- Create: `frontend/src/components/CandidateCard.tsx`
- Create: `frontend/src/components/CandidateBoard.tsx`

- [ ] **Step 1: Create CandidateCard**

```typescript
// frontend/src/components/CandidateCard.tsx
import { useEffect, useRef } from 'react';
import rough from 'roughjs';
import type { CandidateInfo } from '../types/observation';

interface CandidateCardProps {
  candidate: CandidateInfo;
}

export default function CandidateCard({ candidate }: CandidateCardProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const prevStatusRef = useRef(candidate.status);
  const isEliminated = candidate.status === 'eliminated';

  useEffect(() => {
    if (!svgRef.current) return;
    // Only redraw when status changes (or on first mount)
    if (prevStatusRef.current === candidate.status && svgRef.current.childElementCount > 0) return;
    prevStatusRef.current = candidate.status;

    const rc = rough.svg(svgRef.current);
    const w = svgRef.current.clientWidth || 160;
    const h = svgRef.current.clientHeight || 200;

    // Hand-drawn border
    const rect = rc.rectangle(2, 2, w - 4, h - 4, {
      stroke: 'rgba(255,255,255,0.6)',
      strokeWidth: 1.5,
      roughness: 2,
      fill: 'none',
    });
    svgRef.current.appendChild(rect);

    // Cross-out for eliminated candidates
    if (isEliminated) {
      const line1 = rc.line(4, 4, w - 4, h - 4, {
        stroke: 'rgba(255,255,255,0.5)',
        strokeWidth: 2,
        roughness: 1.5,
      });
      const line2 = rc.line(w - 4, 4, 4, h - 4, {
        stroke: 'rgba(255,255,255,0.5)',
        strokeWidth: 2,
        roughness: 1.5,
      });

      // Animate cross-out
      [line1, line2].forEach((node, idx) => {
        node.querySelectorAll('path').forEach((path) => {
          const len = path.getTotalLength();
          path.style.strokeDasharray = `${len}`;
          path.style.strokeDashoffset = `${len}`;
          path.style.animation = `drawIn 0.5s ease-out ${idx * 0.3}s forwards`;
        });
      });

      svgRef.current.appendChild(line1);
      svgRef.current.appendChild(line2);
    }
  }, [isEliminated]);

  return (
    <div
      className={`relative w-40 transition-opacity duration-500 ${
        isEliminated ? 'opacity-30' : 'opacity-100'
      }`}
    >
      <div className="relative overflow-hidden rounded-lg">
        {candidate.image_url ? (
          <img
            src={candidate.image_url}
            alt={candidate.name}
            className="w-40 h-48 object-cover"
          />
        ) : (
          <div className="w-40 h-48 bg-white/5 flex items-center justify-center">
            <span className="font-hand text-secondary text-lg">?</span>
          </div>
        )}
        <svg
          ref={svgRef}
          className="absolute inset-0 pointer-events-none"
          width="100%"
          height="100%"
        />
      </div>
      <p className={`font-hand text-center mt-2 ${isEliminated ? 'text-faded line-through' : 'text-secondary'}`}>
        {candidate.name}
      </p>
    </div>
  );
}
```

- [ ] **Step 2: Create CandidateBoard**

```typescript
// frontend/src/components/CandidateBoard.tsx
import type { CandidateInfo } from '../types/observation';
import CandidateCard from './CandidateCard';

interface CandidateBoardProps {
  candidates: CandidateInfo[];
}

export default function CandidateBoard({ candidates }: CandidateBoardProps) {
  if (candidates.length === 0) return null;

  return (
    <div className="absolute bottom-32 right-8 flex gap-4 flex-wrap justify-end max-w-md">
      {candidates.map((c) => (
        <div key={c.species_code} className="animate-fade-in">
          <CandidateCard candidate={c} />
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/CandidateCard.tsx frontend/src/components/CandidateBoard.tsx
git commit -m "feat: add CandidateCard and CandidateBoard with rough.js borders and cross-out"
```

---

## Task 13: Frontend — ResultOverlay and AlternateSpecies components

**Files:**
- Create: `frontend/src/components/ResultOverlay.tsx`
- Create: `frontend/src/components/AlternateSpecies.tsx`

- [ ] **Step 1: Create AlternateSpecies**

```typescript
// frontend/src/components/AlternateSpecies.tsx
import type { SpeciesInfo } from '../types/observation';

interface AlternateSpeciesProps {
  species: SpeciesInfo[];
}

export default function AlternateSpecies({ species }: AlternateSpeciesProps) {
  if (species.length === 0) return null;

  return (
    <div>
      <p className="font-hand text-secondary text-lg mb-3">Also considered:</p>
      <div className="flex gap-3">
        {species.map((s) => (
          <div key={s.common_name} className="text-center">
            {s.image_url ? (
              <img
                src={s.image_url}
                alt={s.common_name}
                className="w-16 h-16 object-cover rounded-lg border border-white/10"
              />
            ) : (
              <div className="w-16 h-16 bg-white/5 rounded-lg flex items-center justify-center">
                <span className="font-hand text-faded">?</span>
              </div>
            )}
            <p className="font-hand text-faded text-sm mt-1">{s.common_name}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create ResultOverlay**

```typescript
// frontend/src/components/ResultOverlay.tsx
import { useEffect, useRef } from 'react';
import rough from 'roughjs';
import FrostedPanel from './FrostedPanel';
import AlternateSpecies from './AlternateSpecies';
import type { RecommendationResponse } from '../types/observation';

interface ResultOverlayProps {
  result: RecommendationResponse;
  onReset: () => void;
}

export default function ResultOverlay({ result, onReset }: ResultOverlayProps) {
  const underlineRef = useRef<SVGSVGElement>(null);

  const species = result.top_species;
  const confidence = species?.confidence ?? 'medium';

  // Rough.js underline with weight based on confidence
  useEffect(() => {
    if (!underlineRef.current || !species) return;
    const rc = rough.svg(underlineRef.current);
    const strokeWidth = confidence === 'high' ? 3 : confidence === 'medium' ? 2 : 1;
    const line = rc.line(0, 10, 300, 10, {
      stroke: 'rgba(255,255,255,0.7)',
      strokeWidth,
      roughness: 1.5,
    });
    line.querySelectorAll('path').forEach((path) => {
      const len = path.getTotalLength();
      path.style.strokeDasharray = `${len}`;
      path.style.strokeDashoffset = `${len}`;
      path.style.animation = 'drawIn 1s ease-out 0.3s forwards';
    });
    underlineRef.current.appendChild(line);
  }, [species, confidence]);

  if (!species) return null;

  return (
    <div className="absolute inset-0 flex items-center justify-center p-8 animate-fade-in">
      {/* Species name with rough underline */}
      <div className="absolute top-16 left-8 right-8 text-center">
        <h1 className="font-hand text-5xl text-primary font-bold">
          {species.common_name}
        </h1>
        <svg ref={underlineRef} className="mx-auto mt-1" width="300" height="20" />
      </div>

      {/* Info panel */}
      <FrostedPanel className="max-w-lg w-full mt-24 animate-slide-up">
        <p className="font-hand text-secondary text-lg italic mb-4">
          {species.scientific_name}
        </p>

        <p className="text-primary leading-relaxed mb-6">
          {result.message}
        </p>

        {species.reasoning && (
          <p className="font-hand text-secondary text-lg mb-6">
            {species.reasoning}
          </p>
        )}

        {result.clarification && (
          <div className="glass rounded-lg p-4 mb-6">
            <p className="font-hand text-secondary">{result.clarification}</p>
          </div>
        )}

        <AlternateSpecies species={result.alternate_species ?? []} />

        <div className="flex items-center justify-between mt-6 pt-4 border-t border-white/10">
          <a
            href={species.range_link}
            target="_blank"
            rel="noopener noreferrer"
            className="font-hand text-secondary hover:text-primary transition-colors"
          >
            View on eBird →
          </a>
          <button
            onClick={onReset}
            className="glass rounded-lg px-6 py-2 font-hand text-lg text-primary hover:bg-white/10 transition-colors"
          >
            Investigate another
          </button>
        </div>
      </FrostedPanel>
    </div>
  );
}
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ResultOverlay.tsx frontend/src/components/AlternateSpecies.tsx
git commit -m "feat: add ResultOverlay and AlternateSpecies with rough.js confidence underline"
```

---

## Task 14: Frontend — Restyle BirdForm for frosted glass

**Files:**
- Modify: `frontend/src/components/BirdForm.tsx`

- [ ] **Step 1: Restyle BirdForm**

Rewrite `BirdForm.tsx` to use frosted glass styling, Caveat font labels, and "Investigate" button:

```typescript
// frontend/src/components/BirdForm.tsx
import { useState, FormEvent } from 'react';
import FrostedPanel from './FrostedPanel';
import type { ObservationInput } from '../types/observation';

interface BirdFormProps {
  onSubmit: (observation: ObservationInput) => void;
  isLoading: boolean;
}

export default function BirdForm({ onSubmit, isLoading }: BirdFormProps) {
  const [description, setDescription] = useState('');
  const [location, setLocation] = useState('');
  const [observedAt, setObservedAt] = useState('');

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!description.trim() || !location.trim()) return;
    onSubmit({
      description: description.trim(),
      location: location.trim(),
      observed_at: observedAt.trim() || undefined,
    });
  };

  return (
    <FrostedPanel className="w-full max-w-lg animate-slide-up">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="font-hand text-secondary text-lg block mb-1">
            Tell me what you saw...
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            disabled={isLoading}
            className="w-full bg-white/5 border border-dashed border-white/20 rounded-lg p-3 text-primary placeholder-white/30 focus:outline-none focus:border-white/40 resize-none disabled:opacity-50"
            placeholder="A small bird with bright blue feathers..."
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="font-hand text-secondary block mb-1">
              Where?
            </label>
            <input
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              disabled={isLoading}
              className="w-full bg-white/5 border border-dashed border-white/20 rounded-lg p-3 text-primary placeholder-white/30 focus:outline-none focus:border-white/40 disabled:opacity-50"
              placeholder="Central Park, NY"
            />
          </div>
          <div>
            <label className="font-hand text-secondary block mb-1">
              When?
            </label>
            <input
              type="text"
              value={observedAt}
              onChange={(e) => setObservedAt(e.target.value)}
              disabled={isLoading}
              className="w-full bg-white/5 border border-dashed border-white/20 rounded-lg p-3 text-primary placeholder-white/30 focus:outline-none focus:border-white/40 disabled:opacity-50"
              placeholder="This morning"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={!description.trim() || !location.trim() || isLoading}
          className="w-full glass rounded-lg py-3 font-hand text-xl text-primary hover:bg-white/10 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          {isLoading ? 'Investigating...' : 'Investigate →'}
        </button>
      </form>
    </FrostedPanel>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/BirdForm.tsx
git commit -m "feat: restyle BirdForm with frosted glass, Caveat font, Investigate button"
```

---

## Task 15: Frontend — BirdleApp main page (phase state machine)

**Files:**
- Create: `frontend/src/pages/BirdleApp.tsx`
- Modify: `frontend/src/main.tsx` (update import)

- [ ] **Step 1: Create BirdleApp**

```typescript
// frontend/src/pages/BirdleApp.tsx
import { useState, useCallback, useRef, useEffect } from 'react';
import BirdBackground from '../components/BirdBackground';
import PencilAnnotations from '../components/PencilAnnotations';
import BirdForm from '../components/BirdForm';
import DetectiveNotes, { cannedNoteForEvent } from '../components/DetectiveNotes';
import CandidateBoard from '../components/CandidateBoard';
import ResultOverlay from '../components/ResultOverlay';
import { identifyBirdStream } from '../api/client';
import type {
  ObservationInput,
  RecommendationResponse,
  CandidateInfo,
  AppPhase,
  StreamEvent,
} from '../types/observation';

// Hardcoded landing bird — Common Kingfisher from Macaulay Library
const LANDING_BIRD_URL = 'https://cdn.download.ams.birds.cornell.edu/api/v2/asset/303899551/1800';

let noteIdCounter = 0;

interface DetectiveNote {
  id: string;
  message: string;
}

export default function BirdleApp() {
  const [phase, setPhase] = useState<AppPhase>('landing');
  const [backgroundSrc, setBackgroundSrc] = useState(LANDING_BIRD_URL);
  const [isLoading, setIsLoading] = useState(false);
  const [notes, setNotes] = useState<DetectiveNote[]>([]);
  const [candidates, setCandidates] = useState<CandidateInfo[]>([]);
  const [result, setResult] = useState<RecommendationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const phaseRef = useRef<AppPhase>(phase);
  // Keep ref in sync so the stream callback always sees current phase
  useEffect(() => { phaseRef.current = phase; }, [phase]);

  const addNote = useCallback((message: string) => {
    noteIdCounter++;
    setNotes((prev) => [...prev, { id: `note-${noteIdCounter}`, message }]);
  }, []);

  const handleStreamEvent = useCallback((event: StreamEvent) => {
    switch (event.type) {
      case 'status': {
        const canned = cannedNoteForEvent('status');
        if (canned && phaseRef.current !== 'thinking') addNote(canned);
        break;
      }
      case 'detective_note':
        addNote(event.message);
        break;
      case 'candidates':
        setCandidates(event.data);
        break;
      case 'tool_call': {
        const canned = cannedNoteForEvent('tool_call', event.tool);
        if (canned) addNote(canned);
        break;
      }
      case 'tool_result': {
        const canned = cannedNoteForEvent('tool_result', undefined, event.summary);
        if (canned) addNote(canned);
        break;
      }
      case 'result':
        // Phase 3: Reveal — crossfade to winner
        if (event.data.top_species?.image_url) {
          setBackgroundSrc(event.data.top_species.image_url);
        }
        setPhase('reveal');
        // Phase 4: Result — after dramatic pause
        setTimeout(() => {
          setResult(event.data);
          setPhase('result');
        }, 1500);
        break;
      case 'error': {
        const canned = cannedNoteForEvent('error');
        if (canned) addNote(canned);
        setError(event.message);
        break;
      }
      case 'done':
        setIsLoading(false);
        break;
    }
  }, [addNote]);

  const handleSubmit = async (observation: ObservationInput) => {
    // Reset state
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setPhase('thinking');
    setIsLoading(true);
    setNotes([]);
    setCandidates([]);
    setResult(null);
    setError(null);

    try {
      await identifyBirdStream(observation, handleStreamEvent, controller.signal);
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err.message : 'Something went wrong');
      addNote('Hmm, hit a snag...');
      setIsLoading(false);
    }
  };

  const handleReset = () => {
    setPhase('landing');
    setBackgroundSrc(LANDING_BIRD_URL);
    setNotes([]);
    setCandidates([]);
    setResult(null);
    setError(null);
    setIsLoading(false);
  };

  return (
    <div className="relative w-screen h-screen overflow-hidden">
      <BirdBackground src={backgroundSrc} />

      {/* Branding */}
      <h1 className="absolute top-6 left-8 font-hand text-3xl text-primary z-10">
        Birdle
      </h1>

      {/* Phase 1: Landing */}
      {phase === 'landing' && (
        <>
          <PencilAnnotations />
          <div className="absolute inset-0 flex items-end justify-center pb-16">
            <BirdForm onSubmit={handleSubmit} isLoading={isLoading} />
          </div>
        </>
      )}

      {/* Phase 2: Thinking */}
      {(phase === 'thinking' || phase === 'reveal') && (
        <>
          <DetectiveNotes notes={notes} />
          <CandidateBoard candidates={candidates} />
          {error && (
            <div className="absolute bottom-8 left-8 right-8">
              <div className="glass rounded-lg p-4 max-w-md">
                <p className="font-hand text-secondary">{error}</p>
                <button
                  onClick={handleReset}
                  className="font-hand text-primary mt-2 hover:underline"
                >
                  Try again
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Phase 4: Result */}
      {phase === 'result' && result && (
        <ResultOverlay result={result} onReset={handleReset} />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Update main.tsx to use BirdleApp**

The entry point is `frontend/src/main.tsx` (there is no `App.tsx`). Find the import of `Home` and replace:

```typescript
import BirdleApp from './pages/BirdleApp';
// In the JSX, replace <Home /> with <BirdleApp />
```

- [ ] **Step 3: Delete old components**

Delete:
- `frontend/src/pages/Home.tsx`
- `frontend/src/components/ResultPanel.tsx`
- `frontend/src/components/SpeciesCard.tsx`

- [ ] **Step 4: Verify build**

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 5: Run lint**

Run: `cd frontend && npm run lint`
Expected: PASS (or fix any issues)

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: add BirdleApp phase state machine, wire up all components, remove old UI"
```

---

## Task 16: Backend — Run all tests and lint

**Files:** None (verification only)

- [ ] **Step 1: Run all backend tests**

Run: `poetry run pytest services/backend/tests/ -v`
Expected: All PASS

- [ ] **Step 2: Run ruff lint**

Run: `poetry run ruff check services/`
Expected: PASS (or fix issues)

- [ ] **Step 3: Run black format check**

Run: `poetry run black --check services/`
Expected: PASS (or fix formatting)

- [ ] **Step 4: Run mypy type check**

Run: `poetry run mypy services/backend/app --ignore-missing-imports`
Expected: PASS (or fix type issues)

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -m "fix: lint and type check fixes"
```

---

## Task 17: Frontend — Full build and smoke test

**Files:** None (verification only)

- [ ] **Step 1: Run frontend build**

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 2: Run frontend lint**

Run: `cd frontend && npm run lint`
Expected: PASS

- [ ] **Step 3: Start backend and frontend for manual smoke test**

Run (two terminals):
```bash
# Terminal 1
poetry run uvicorn services.backend.app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2
cd frontend && npm run dev
```

Verify:
- Landing page shows full-bleed bird photo with dark overlay
- Pencil annotations visible as white handwriting text
- Frosted glass form panel at bottom
- "Birdle" wordmark top-left in Caveat font
- Submit triggers thinking phase with detective notes appearing
- Candidates appear with rough.js borders
- Result shows full-bleed species photo with frosted glass info panel

- [ ] **Step 4: Commit any smoke test fixes**

```bash
git add -A
git commit -m "fix: smoke test adjustments"
```

---

## Task 18: Run pre-commit hooks

- [ ] **Step 1: Run all pre-commit hooks**

Run: `poetry run pre-commit run --all-files`
Expected: All PASS

- [ ] **Step 2: Fix any issues and commit**

```bash
git add -A
git commit -m "fix: pre-commit hook fixes"
```
