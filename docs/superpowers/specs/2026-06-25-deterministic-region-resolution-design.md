# Deterministic Region Resolution + "Use My Location"

**Date:** 2026-06-25
**Status:** Approved (design) — ready for implementation planning
**Branch (planned):** `feat/region-resolution`

## Problem

`resolve_inputs` asks Haiku to *guess* the eBird region code from free-text
location. The prompt is Western-centric, so non-Western places fall back to the
whole-country code (e.g. "Dalat, Vietnam" → `VN`, 400+ species). The validator
(`get_region_info`) only re-asks when a code is *invalid*; a valid-but-coarse
code like `VN` is silently accepted. Root cause is region coarseness, not routing.

### Empirical findings (tested live, 2026-06-25)

The original idea assumed "eBird subnational codes *are* ISO-3166-2." **This is
false for the motivating case** and must not be relied on:

- Nominatim geocodes "Dalat, Vietnam" → `ISO3166-2-lvl4: VN-35` (Vietnam
  renumbered its provinces; this is the *current* ISO code).
- eBird's `region/info/VN-35` returns a **ghost**: HTTP 200, no bounds,
  lat/lng `0.0`, **0 recent observations**. So validation rubber-stamps it.
- eBird's *actual* Lâm Đồng code is **`VN-68`** ("Lam Dong, VN", real bounds,
  **115 species** recent) — eBird froze the old ISO code.

So a naive Nominatim-ISO→eBird pipeline resolves Dalat to `VN-35` → 0 birds,
**worse** than today's `VN` → 399. We must **name-match against eBird's own
authoritative region list**, never trust Nominatim's ISO string.

### Radius vs region precision (tested live)

Whether a lat/lng radius is "more precise" than a region code:

| Location | Region list | 50 km radius | Radius-only species | Region species missed by radius |
| --- | --- | --- | --- | --- |
| Dalat / `VN-68` (mid-size) | 115 | 112 | 0 | 3 |
| Yosemite / `US-CA` (large, diverse) | **483** | **201** | 0 | 282 |

Conclusions:
- The radius list is **always a subset** of the region list (it never finds a
  species the region doesn't — 0 radius-only in every test).
- For a **large/diverse** region the radius is **far more precise**: a Yosemite
  pin drops ~282 California species (coastal/desert birds) that cannot occur
  there — i.e. it strips *false candidates*. The benefit grows with region size.
- The radius's only risk is **under-sampling** (a tight radius misses real local
  species); 50 km (eBird's max) + a 30-day window mitigates this.

## Decision

Make resolution **deterministic** via geocoding, and **use region code and
lat/lng radius for what each is best at**:

- **Candidate / presence list → GPS radius** (50 km) when a specific point is
  known. Habitat-relevant; strips false candidates from large regions.
- **Frequency / abundance bucket → region code.** Abundance is region-native
  (tuned to region report denominators); no clean geo equivalent.
- **Rarities → region code.**
- The LLM (Haiku) keeps **only the date parse**; it never picks a region code.

Plus a lightweight **"Use my location"** button: the browser hands us exact
coordinates, which we reverse-geocode to the region — the most reliable input.

## Architecture

```
location text ─┐
               ├─► geocode/reverse-geocode (Nominatim) ─► {lat,lng, admin1 name, country_code}
GPS pin ───────┘                                              │
                                                              ▼
                              match admin1 name vs eBird subnational1 list  ─► region code
                                                              │
                              store {region, lat, lng, precision} in state
                                                              ▼
  agent calls get_regional_birds(region)
     └─ specific point?  yes → obs/geo(lat,lng,50km)  "what's around HERE" (presence)
                          no → region recent obs        (coarse fallback)
  agent calls get_species_frequency(region, code) → region abundance bucket
  agent calls get_regional_rarities(region)       → region rarities
```

**Resolution precedence:** explicit GPS coordinates win (reverse-geocode →
region; lat/lng used directly). Otherwise forward-geocode the text. When neither
yields a specific point, fall back to the country code and region-based presence.

## Components

### New: `helpers/geocoder.py`
- `geocode(text) -> GeoResult | None` — Nominatim `/search`, `limit=1`.
- `reverse_geocode(lat, lng) -> GeoResult | None` — Nominatim `/reverse`, `zoom=8`.
- `GeoResult = {lat, lng, country_code, admin1_name, display_name}`.
- In-process cache keyed by normalized input (mirrors the image cache in
  `ebird_client`). Descriptive `User-Agent` (required by Nominatim policy).
  Returns `None` on any error/empty (graceful, never raises).

### `helpers/ebird_client.py` (additions)
- `get_subnational1_list(country_code) -> list[{code, name}]` —
  `/ref/region/list/subnational1/{CC}`, cached per country.
- `get_nearby_birds(lat, lng, dist=50, days=14) -> dict` —
  `/data/obs/geo/recent`, **same return shape as `get_regional_birds`** so the
  presence tool can return either transparently.

### Resolution logic (`resolve_region`)
Lives with the geocoder (or a small `graph/resolve.py`). Given text **or**
coordinates:
1. geocode / reverse-geocode → `GeoResult` (or `None`).
2. `country_code` present → fetch eBird subnational1 list → **normalize-match**
   `admin1_name` → subnational1 code.
3. No confident match → fall back to the **country code** (uppercased alpha-2).
4. Geocode failed → region `None` (caller drives the clarify interrupt).

Returns `{region_code, lat, lng, precision, display_name}` where `precision ∈
{point, country, none}` decides whether geo radius is used for presence:
- `point` — geocode resolved a *specific* place (a city/town/pin, i.e. Nominatim
  `addresstype` is not `country` and an `admin1_name` was present). Use the
  50 km radius for presence. `region_code` is the matched subnational1, or the
  country code if the name-match failed (frequency still works at country level).
- `country` — only a country-level result (country-centroid lat/lng is not
  meaningful for a radius). Use region recent obs for presence.
- `none` — geocode failed; caller drives the clarify interrupt.

**Name normalization (match step):** NFKD diacritic-strip + lowercase + drop
admin words ("Tỉnh", "Province", "State", "Thành phố", "City", "Region", …),
then exact-normalized or token-subset match against the (normalized) eBird list
names. Example: `"Tỉnh Lâm Đồng"` + `VN` → `VN-68`; `"New York"` → `US-NY`.

### `graph/state.py`
Add `lat: Optional[float]`, `lng: Optional[float]` (`region` already exists).

### `graph/nodes.py` — `resolve_inputs`
- Replace Haiku region-guessing with `resolve_region`.
- Haiku slims to a **date-only** parse (`observed_window`).
- Coordinate precedence: use provided GPS lat/lng (reverse-geocode) when present.
- Store `region`, `lat`, `lng`, `observed_window`.
- Keep the existing `interrupt()` clarify flow: location given but unresolved →
  hard clarify; missing → soft (skippable) clarify; re-resolve on the reply.
- Stream the resolved `display_name` so the UI can confirm what was understood.

### `graph/tools.py` — `get_regional_birds`
- Pull `lat`/`lng` from state via `InjectedState` (model-facing signature
  unchanged — the model still calls `get_regional_birds(region, days)`).
- If `precision == point` (specific lat/lng): return `get_nearby_birds(50 km)`;
  the SSE summary states the source ("201 species within 50 km of your
  location"). Else: region recent obs ("115 species in Lam Dong").
- `get_species_frequency`, `get_regional_rarities` unchanged (region-based).

### `graph/prompts.py`
- Slim `RESOLVE_PROMPT` to the date parse only.
- Update the region note: presence is point-scoped when a location is known.

### Frontend — "Use my location"
- A `📍 Use my location` button beside the location field.
- Click → `navigator.geolocation.getCurrentPosition` → `{lat, lng}` sent in the
  identify request. A confirmation chip shows the reverse-geocoded place name
  with a clear/undo to revert to typing.
- Permission denied / unavailable → silent fall back to the text field.
- No new frontend libraries.

### Schemas
- Add optional `lat`, `lng` to the identify request (Pydantic) and the matching
  TypeScript interface. `location` text stays optional. Keep TS/Pydantic aligned.

## Error handling / graceful degradation

- Geocode fails/empty → region `None` → existing clarify interrupt (location
  given) or proceed description-only (missing).
- eBird subnational1 list fails, or no name match → country code (lower
  precision; presence falls back to region recency).
- lat/lng absent → no geo radius; region recency for presence.
- Reuses the one-retry / `None`-on-error pattern already in the httpx clients.

## Testing

- **Unit — geocoder:** parse a known Nominatim payload → `GeoResult`; `None` on
  error/empty; reverse-geocode parse.
- **Unit — name match:** `"Tỉnh Lâm Đồng"` + `VN` → `VN-68`; diacritic-insensitive;
  `"Brooklyn, NY"` (state "New York") → `US-NY`; no match → country code.
- **Unit — eBird:** `get_subnational1_list`, `get_nearby_birds` (mock httpx).
- **Unit — presence tool:** `precision == point` → geo path; coarse → region path
  (mock both `ebird_client` methods).
- **Integration — `resolve_inputs`:** stubbed geocoder + eBird; coordinate
  precedence; clarify interrupt on unresolved text.
- **Schema:** identify request accepts/validates optional lat/lng.
- **Frontend:** denied geolocation degrades to text input.
- Update existing resolve tests (no more LLM region guessing).

## Scope (YAGNI)

- **Standardize on subnational1 (state/province); do NOT resolve county /
  subnational2** (`Brooklyn → US-NY`, not `US-NY-047`). This is a *correctness*
  decision, not a tolerated loss, given the "use both" split:
  - Presence now comes from the **GPS radius (50 km)**, which ignores admin
    boundaries — so county granularity buys presence nothing.
  - `get_species_frequency` is **count-based** with fixed thresholds
    (`<50 rare`, `<300 uncommon`, `≥300 common`) calibrated to region report
    volume. County counts are far smaller, so the same species drops buckets
    (tested: American Robin `US-NY` 400=common vs `US-NY-061` 129=uncommon;
    Wood Thrush 400=common vs 16=rare — and Manhattan is among the most birded
    counties on Earth). Mixing county and state codes makes abundance
    inconsistent and pessimistic. Subnational1 keeps buckets comparable.
- **No global rate limiter** — cache + one geocode per identification stays under
  Nominatim's 1 req/s. Revisit if volume grows.
- **Radius is fixed at 50 km / 30-day window** (eBird's max, best coverage) — no
  agent knob.
- **Interactive map pin** is a separate future iteration; this ships the
  one-tap geolocation button only.
- lat/lng is internal plumbing + the geolocation button; not a free-form input.

## Dependency / vision note

Adds **OpenStreetMap Nominatim** as an external geocoding service, called via the
existing `httpx.AsyncClient` (no new Python library). Per CLAUDE.md (MVP/KISS, no
new services without vision approval) this is recorded in `docs/vision.md`, and a
`docs/tasklist.md` iteration row is added. Nominatim usage policy: descriptive
`User-Agent`, attribution, 1 req/s — satisfied by caching + a single call per
identification. A keyed/self-hosted geocoder is a later option if volume grows.
