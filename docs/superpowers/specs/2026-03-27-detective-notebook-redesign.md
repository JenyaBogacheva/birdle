# Birdle Detective Notebook Redesign

Full UI redesign transforming Birdle from a gradient form-based app into an immersive naturalist detective notebook experience. Full-bleed bird photography, frosted glass panels, hand-drawn rough.js annotations, and a phased investigation flow.

## Motivation

The current UI is functional but generic — gradient backgrounds, emoji-heavy copy, standard form layout. The redesign creates a distinctive identity: the AI investigates your bird sighting like a field detective, scribbling observations in a notebook while pinning candidate species to the board.

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Scope | Full app redesign | Consistent naturalist detective feel across all screens |
| Bird backgrounds | Contextual, from Macaulay Library | Same image source already used for species results |
| Landing bird | Single iconic species, hardcoded | Simple, no logic needed, changeable later |
| Input style | Free-text + location + time; pencil hints are decorative only | Keeps current backend contract, no confusing interactivity |
| Thinking phase | Notebook sketching with candidate elimination | Cohesive with notebook metaphor, responsive-friendly |
| Result | Winning bird takes over as full background | Clean, dramatic reveal moment |
| Color palette | Minimal/transparent — dark overlay, frosted glass, white pencil | Maximum photo immersion, bird IS the color |
| Responsive | Desktop-first, basic mobile fallback later | Ship the wow factor first |
| Branding | "Birdle" in Caveat handwriting font | Name confirmed, detective riddle connection |
| Tech approach | CSS animations + rough.js for hand-drawn SVGs | Organic look without Lottie/Canvas complexity |
| Candidate display | Explicit LLM tools, not thinking text parsing | Structured, reliable, clean separation |

## App Phases

The app has 4 phases, each a full-screen experience layered over a bird photo background.

### Phase 1 — Landing / Input

- Full-bleed iconic bird photo (single hardcoded species from Macaulay Library)
- Dark overlay (~35% opacity)
- Static pencil-sketch annotations scattered around ("What colors?", "How big?", "Where?") — decorative only, white Caveat font at varying opacities (0.4-0.7), slight CSS rotations (-3deg to +3deg)
- "Birdle" wordmark top-left in Caveat
- Frosted glass panel (bottom-center, ~500px wide on desktop) containing:
  - Description textarea
  - Location text input
  - Optional time input
  - "Investigate" submit button
- Subtle rough.js bird footprint doodles and dashed arrows as decoration

### Phase 2 — Thinking / Investigation

- Background stays on the landing bird photo (unchanged from Phase 1)
- Detective notes appear sequentially as SSE events arrive:
  - `detective_note` events → handwritten one-liners with typewriter character reveal in Caveat
  - Staggered positioning with slight rotation variation for organic feel
  - Canned notes for known events (tool calls, results)
- Candidate bird photos fade in from Macaulay Library:
  - Each framed with rough.js hand-drawn border (white stroke)
  - New candidates animate in with `stroke-dasharray` draw effect
  - Eliminated candidates get sketchy cross-out (two diagonal rough.js lines, ~0.5s) then fade to low opacity
- Raw thinking text from Claude is hidden entirely — detective notes + candidates ARE the thinking UI

### Phase 3 — Reveal

- All remaining candidates except the winner fade out
- Winning candidate photo crossfades to fill the background (CSS opacity transition ~0.8s)
- Short dramatic pause (~1s)
- Pencil annotations transform into result facts

### Phase 4 — Result

- Full-bleed photo of identified species as background
- Dark overlay (35%)
- Species name large (36-48px) in Caveat with rough.js wobbly underline
  - Underline stroke weight reflects confidence (thick = high, thin = low)
- Frosted glass panel containing:
  - Scientific name (italic)
  - Natural language summary from the LLM
  - Confidence indicator (rough.js line weight, not color badges)
  - Alternate species as small thumbnails with rough.js borders
  - eBird link
  - "Investigate another" button → resets to Phase 1

## Visual System

### Typography

- **Handwriting font:** Caveat (Google Fonts) — annotations, detective notes, species names, branding
- **Body font:** System UI / Inter — input fields, buttons, small utility text
- Annotations use varied sizes (14-24px) and slight CSS rotations for organic feel

### Color System

- **Background:** Bird photography, full bleed, `object-fit: cover`
- **Overlay:** `rgba(0,0,0,0.35)`
- **Frosted glass:** `rgba(0,0,0,0.45)` + `backdrop-filter: blur(12px)` + `border: 1px solid rgba(255,255,255,0.1)`
- **Primary text:** `rgba(255,255,255,0.9)` — headings, species name, input text
- **Secondary text:** `rgba(255,255,255,0.6)` — annotations, hints, placeholders
- **Faded text:** `rgba(255,255,255,0.35)` — rejected candidates, background scribbles
- **No accent color** — bird photo provides all color. Confidence conveyed by line weight.

### rough.js Elements

All rendered in white stroke at varying opacities:

- Hand-drawn circles around candidate bird thumbnails
- Sketchy cross-outs (two diagonal lines) on rejected candidates
- Dashed arrows connecting thinking notes to candidates
- Wobbly underlines under species names
- Decorative bird footprint doodles (3-pronged Y shapes)
- Draw-in animation via `stroke-dasharray` + `stroke-dashoffset` CSS transitions

### Animations

- **Pencil draw-in:** `stroke-dasharray` + `stroke-dashoffset` on rough.js SVG paths
- **Typewriter reveal:** Character-by-character for detective notes, CSS `steps()` or JS interval
- **Photo transitions:** `opacity` + `transform: scale` for candidates appearing/fading
- **Cross-out:** Two rough.js lines drawn in sequence over ~0.5s
- **Phase transitions:** CSS opacity fade (~0.8s), background image crossfade
- **Frosted panel:** Slide-up + fade-in on appearance

### Frosted Glass Panel Variants

- **Input panel:** Larger, bottom-center, holds the form
- **Thinking notes:** Smaller, positioned as staggered margin notes
- **Result panel:** Medium, holds species info + alternates

## Component Architecture

### Page-level

- **`BirdleApp`** — top-level state machine managing the 4 phases. Holds current phase, bird photo URL, streaming data, candidates list.

### Background Layer

- **`BirdBackground`** — full-bleed bird photo with dark overlay. Handles crossfade between photos using two stacked `<img>` elements with CSS opacity transitions.
- **`PencilAnnotations`** — rough.js SVG overlay for decorative scribbles. Takes annotation configs (text, position, rotation, opacity) and renders with draw-in animations.

### Input Layer (Phase 1)

- **`FrostedPanel`** — reusable frosted glass container component. Used across all phases.
- **`BirdForm`** — refactored existing form component. Same fields (description, location, time), restyled for frosted glass aesthetic. Caveat labels. "Investigate" submit button.

### Thinking Layer (Phase 2)

- **`DetectiveNotes`** — renders detective_note SSE events as staggered handwritten entries with typewriter reveal. Includes canned notes for mapped events.
- **`CandidateBoard`** — displays candidate bird thumbnails from `candidates` SSE events. Manages appear/eliminate animations.
- **`CandidateCard`** — single bird photo + name. States: appearing, considering, eliminated. Loads Macaulay Library image.

### Result Layer (Phase 4)

- **`ResultOverlay`** — frosted glass panel with species name, confidence underline, summary, eBird link, "Investigate another" button.
- **`AlternateSpecies`** — row of small thumbnails with rough.js borders for alternate matches.

### Shared

- **`RoughElement`** — thin wrapper around rough.js for rendering circles, lines, cross-outs, arrows as animated SVGs.
- **`TypewriterText`** — character-by-character text reveal component.

## Backend Changes

### New Tools

Two new UI-only tools added to the bird agent:

```python
detective_note(message: str)
# Emits SSE: {"type": "detective_note", "message": "..."}
# Example: "Blue and orange... interesting."

update_candidates(candidates: list[{name: str, species_code: str, status: "considering"|"eliminated", reason: str?}])
# Backend resolves Macaulay image URLs for new species_codes before emitting
# Emits SSE: {"type": "candidates", "data": [{..., image_url: str}]}
```

These tools perform no external API calls — they relay data to the frontend via SSE events. Both return `{"acknowledged": true}` to the LLM as their tool result. This is necessary because every Anthropic tool call requires a `tool_result` content block in the conversation, but these tools have no meaningful return data.

### New SSE Event Types

| Event | Payload | Frontend Action |
|---|---|---|
| `detective_note` | `{"type": "detective_note", "message": str}` | Append handwritten note with typewriter animation |
| `candidates` | `{"type": "candidates", "data": [{name, species_code, status, reason?}]}` | Show/update/cross-out candidate photos |

Existing events (`status`, `thinking`, `tool_call`, `tool_result`, `result`, `error`, `done`) remain unchanged. `thinking` events are received but not displayed in the UI.

### Two-Tier Tool Budget

| Tier | Tools | Limit | Rationale |
|---|---|---|---|
| Data tools | `get_regional_birds`, `web_search` | 8 calls | External APIs, cost and latency |
| UI tools | `detective_note`, `update_candidates` | 20 calls | SSE relay only, essentially free |

Tracked via two separate counters in the agent loop.

### System Prompt Addition

Instruct the bird agent to use the new tools:

> As you investigate, call `detective_note` with brief atmospheric observations — like a field naturalist's notebook. One sentence, max 10 words. Examples: "Blue and orange... interesting.", "Too small for a jay.", "That beak says kingfisher."
>
> Call `update_candidates` whenever your shortlist of possible species changes. Include species you're considering and ones you've eliminated.

### Canned Detective Notes

Canned notes are generated **in the frontend** by mapping existing SSE event types (`status`, `tool_call`, `tool_result`) to display text. This keeps the backend simple — it emits the same events as before, and the frontend's event handler maps them to notebook-style notes alongside the LLM-generated `detective_note` events.

For events not generated by the LLM:

| Event | Canned Note |
|---|---|
| Stream connected | "Let's find this bird..." |
| `get_regional_birds` called | "Checking the local records..." |
| `get_regional_birds` result | "N species in the area. Let's narrow it down." |
| `web_search` called | "Digging deeper..." |
| Error | "Hmm, hit a snag..." |

## Streaming Data Flow

1. User fills frosted glass form, hits "Investigate"
2. `POST /api/identify/stream` — no endpoint changes
3. SSE events drive the UI:
   - `status` → canned detective note + phase transition to Phase 2
   - `detective_note` → handwritten note with typewriter reveal
   - `candidates` → candidate photos fade in / get crossed out
   - `tool_call` → canned detective note
   - `tool_result` → canned detective note with data
   - `thinking` → hidden (not displayed)
   - `result` → trigger Phase 3 reveal → Phase 4 result
   - `error` → handwritten error note in notebook style
   - `done` → stream cleanup

4. On `result` event:
   - Preload identified species Macaulay photo
   - Crossfade background to species photo (Phase 3)
   - Pause ~1s
   - Show result overlay (Phase 4)

## Image Loading Strategy

- **Landing bird:** Hardcoded Macaulay URL, preloaded on page load via `<link rel="preload">`. Use the large asset URL pattern (`https://cdn.download.ams.birds.cornell.edu/api/v2/asset/{asset_id}/1800`) for full-bleed background quality.
- **Candidate birds during thinking:** The backend resolves Macaulay image URLs before emitting the `candidates` SSE event. When the agent calls `update_candidates`, the streaming route handler fetches image URLs for any new `species_code` values (via `ebird_client.get_species_image`) and includes them in the SSE payload as `image_url`. This mirrors the existing pattern where the route handler fetches images before emitting the `result` event. The frontend does not call Macaulay directly.
- **Result bird:** Already fetched by backend (existing behavior — streaming endpoint fetches images before sending `result` event). Use the large asset URL pattern for full-bleed background quality.
- **Background crossfade:** Two stacked `<img>` elements. Preload new image, then CSS opacity swap.
- **Image sizes:** Candidate thumbnails use the existing `previewUrl` (480px). Full-bleed backgrounds (landing + result) use the 1800px asset URL for high-resolution display.

## Dependencies

| Dependency | Size | Purpose |
|---|---|---|
| rough.js | ~9kb | Hand-drawn SVG rendering |
| Caveat (Google Fonts) | ~15kb | Handwriting typeface |

No other new dependencies. Existing stack (React 18 + Vite + Tailwind) unchanged.

## Out of Scope

- Mobile-optimized design (future iteration)
- New logo or brand identity beyond text wordmark
- Sound effects or haptic feedback
- User accounts or saved identifications
- Photo upload for bird identification
- Animated bird illustrations or Lottie assets
