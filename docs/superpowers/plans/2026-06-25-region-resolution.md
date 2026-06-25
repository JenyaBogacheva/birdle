# Deterministic Region Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve eBird regions deterministically by geocoding the location (Nominatim) and name-matching eBird's authoritative subnational1 list, use a GPS radius for presence and the region code for abundance, and add a "Use my location" button.

**Architecture:** A new `geocoder.py` helper turns free text or coordinates into `{lat, lng, admin1_name, country_code}`. `resolve_region()` matches that admin name against eBird's own subnational1 list (renumbering-proof) to get a region code; the LLM stops guessing codes and only parses the date. The agent's presence tool (`get_regional_birds`) transparently serves a 50 km lat/lng radius when a specific point is known (via LangGraph `InjectedState`); frequency and rarities stay region-coded.

**Tech Stack:** FastAPI + Python 3.14 (uv), LangGraph, `httpx.AsyncClient`, Pydantic v2; React 18 + Vite + TypeScript (Vitest).

## Global Constraints

- Python ≥3.11,<4.0; managed with **uv** (`uv run …`).
- **No new Python dependency** — call Nominatim via the existing `httpx.AsyncClient`.
- All eBird/geocoder helpers **never raise** — return a graceful fallback / `None` on any error (matches existing `ebird_client` pattern).
- Nominatim policy: send `User-Agent: BirdleAI/1.0 (bird identification; https://github.com/birdle-ai)`; one geocode call per identification + in-process cache.
- TypeScript interfaces and Pydantic schemas must stay aligned.
- Lint/format/type gates must pass: `uv run ruff check services/`, `uv run black --check services/`, `uv run mypy services/backend/app --ignore-missing-imports`; frontend `npm run lint` (`--max-warnings 0`) + `npm run build`.
- Commit per task. Branch: `feat/region-resolution` (already created from `main`).
- Radius is fixed at **50 km / 30-day** window; region level is **subnational1** (no county/subnational2).

---

## File Structure

**Backend**
- Create `services/backend/app/helpers/geocoder.py` — Nominatim geocode/reverse + `GeoResult` + name-match + `resolve_region()`.
- Create `services/backend/tests/test_geocoder.py`.
- Modify `services/backend/app/helpers/ebird_client.py` — add `get_subnational1_list`, `get_nearby_birds`.
- Modify `services/backend/tests/test_ebird_client.py` — cover the two new methods.
- Modify `services/backend/app/graph/state.py` — add `lat`, `lng`.
- Modify `services/backend/app/graph/nodes.py` — rewrite `resolve_inputs`; slim `_parse_inputs` → `_parse_date`.
- Modify `services/backend/app/graph/tools.py` — `get_regional_birds` geo path via `InjectedState`.
- Modify `services/backend/app/graph/prompts.py` — slim `RESOLVE_PROMPT`, tweak region note.
- Modify `services/backend/app/schemas/observation.py` — optional `lat`/`lng`, relax `location`.
- Modify `services/backend/app/routes/identify.py` + `services/backend/app/graph/runner.py` — thread `lat`/`lng`.
- Modify graph node tests (`test_*` under `services/backend/tests/`).

**Frontend**
- Modify `frontend/src/types/observation.ts` — `lat?`, `lng?` on `ObservationInput`.
- Modify `frontend/src/api/client.ts` — pass coords through (already forwards the whole object; verify).
- Modify `frontend/src/hooks/useBirdleSession.ts` — coords state + `useMyLocation()` + observation wiring + `canStart`.
- Modify `frontend/src/components/birdle/DesktopBirdle.tsx` + `MobileBirdle.tsx` — the `📍 Use my location` button + status.

**Docs**
- Modify `docs/vision.md`, `docs/tasklist.md`.

---

## Task 1: eBird client — subnational1 list + nearby (geo) birds

**Files:**
- Modify: `services/backend/app/helpers/ebird_client.py`
- Test: `services/backend/tests/test_ebird_client.py`

**Interfaces:**
- Produces:
  - `eBirdClient.get_subnational1_list(country_code: str) -> list[dict[str, str]]` — items `{"code": "VN-68", "name": "Lam Dong"}`; `[]` on error; cached per uppercased country code.
  - `eBirdClient.get_nearby_birds(lat: float, lng: float, dist: int = 50, days: int = 14) -> dict[str, Any]` — **same shape** as `get_regional_birds`: `{"region", "days_searched", "total_species", "species_observed"[{common_name, scientific_name, species_code}]}`. Here `region` is the literal string `"geo"`.

- [ ] **Step 1: Write the failing tests**

Add to `services/backend/tests/test_ebird_client.py` (follow the existing httpx-mock style in that file — reuse its mock-response helper/fixtures; the snippet below shows intent):

```python
@pytest.mark.asyncio
async def test_get_subnational1_list_parses_and_caches(monkeypatch):
    calls = {"n": 0}
    async def fake_get(url, headers=None, params=None):
        calls["n"] += 1
        return _mock_response(200, [{"code": "VN-68", "name": "Lam Dong"},
                                    {"code": "VN-44", "name": "Hanoi"}])
    monkeypatch.setattr(ebird_client._client, "get", fake_get)
    out = await ebird_client.get_subnational1_list("vn")
    assert {"code": "VN-68", "name": "Lam Dong"} in out
    await ebird_client.get_subnational1_list("VN")   # cached -> no 2nd call
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_get_subnational1_list_error_returns_empty(monkeypatch):
    async def boom(*a, **k): raise httpx.ConnectError("down")
    monkeypatch.setattr(ebird_client._client, "get", boom)
    assert await ebird_client.get_subnational1_list("ZZ") == []


@pytest.mark.asyncio
async def test_get_nearby_birds_shape(monkeypatch):
    async def fake_get(url, headers=None, params=None):
        assert "/data/obs/geo/recent" in url
        assert params["lat"] == 11.9 and params["lng"] == 108.4 and params["dist"] == 50
        return _mock_response(200, [
            {"speciesCode": "x", "comName": "X", "sciName": "Xx"},
            {"speciesCode": "x", "comName": "X", "sciName": "Xx"},  # dup collapses
            {"speciesCode": "y", "comName": "Y", "sciName": "Yy"},
        ])
    monkeypatch.setattr(ebird_client._client, "get", fake_get)
    res = await ebird_client.get_nearby_birds(11.9, 108.4)
    assert res["total_species"] == 2
    assert res["region"] == "geo"
    assert {"common_name": "X", "scientific_name": "Xx", "species_code": "x"} in res["species_observed"]
```

- [ ] **Step 2: Run, verify they fail**

Run: `uv run pytest services/backend/tests/test_ebird_client.py -k "subnational1 or nearby" -v`
Expected: FAIL (AttributeError: no `get_subnational1_list` / `get_nearby_birds`).

- [ ] **Step 3: Implement**

In `ebird_client.py`, add a list cache to `__init__`:

```python
        self._subnat1_cache: dict[str, list[dict[str, str]]] = {}
```

Add the two methods to `eBirdClient` (near `get_region_info`):

```python
    async def get_subnational1_list(self, country_code: str) -> list[dict[str, str]]:
        """eBird's authoritative subnational1 (state/province) list for a country.

        Returns ``[{"code", "name"}]`` (empty on any error). Cached per country.
        """
        cc = (country_code or "").upper()
        if not cc:
            return []
        if cc in self._subnat1_cache:
            return self._subnat1_cache[cc]
        try:
            url = f"{EBIRD_API_BASE}/ref/region/list/subnational1/{cc}"
            resp = await self._client.get(url, headers={"X-eBirdApiToken": settings.ebird_token})
            resp.raise_for_status()
            out = [{"code": r.get("code", ""), "name": r.get("name", "")} for r in resp.json()]
            self._subnat1_cache[cc] = out
            return out
        except Exception as e:
            logger.warning(
                f"eBird subnational1 list failed: {e}",
                extra={"operation": "get_subnational1_list", "country": cc, "status": "error"},
            )
            return []

    async def get_nearby_birds(
        self, lat: float, lng: float, dist: int = 50, days: int = 14
    ) -> dict[str, Any]:
        """Recent species within ``dist`` km of a point (presence/recency).

        Same return shape as ``get_regional_birds`` (``region`` == "geo").
        """
        start_time = time.time()
        fallback: dict[str, Any] = {
            "region": "geo", "days_searched": days, "total_species": 0, "species_observed": []
        }
        try:
            url = f"{EBIRD_API_BASE}/data/obs/geo/recent"
            params = {"lat": lat, "lng": lng, "dist": dist, "back": days}
            resp = await self._client.get(
                url, headers={"X-eBirdApiToken": settings.ebird_token}, params=params
            )
            resp.raise_for_status()
            species_map: dict[str, dict[str, Any]] = {}
            for obs in resp.json():
                code = obs.get("speciesCode", "")
                key = code or obs.get("comName", "Unknown")
                if key not in species_map:
                    species_map[key] = {
                        "common_name": obs.get("comName", "Unknown"),
                        "scientific_name": obs.get("sciName", ""),
                        "species_code": code,
                    }
            species = list(species_map.values())
            logger.info(
                "eBird nearby observations fetched",
                extra={"operation": "get_nearby_birds", "dist_km": dist,
                       "species_count": len(species),
                       "latency_ms": round((time.time() - start_time) * 1000, 2),
                       "status": "success"},
            )
            return {"region": "geo", "days_searched": days,
                    "total_species": len(species), "species_observed": species}
        except Exception as e:
            logger.warning(
                f"eBird nearby observations failed: {e}",
                extra={"operation": "get_nearby_birds", "status": "error",
                       "error_type": type(e).__name__},
            )
            return fallback
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest services/backend/tests/test_ebird_client.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/helpers/ebird_client.py services/backend/tests/test_ebird_client.py
git commit -m "feat: eBird subnational1 list + geo (nearby) birds helpers"
```

---

## Task 2: Geocoder helper — geocode + reverse + GeoResult

**Files:**
- Create: `services/backend/app/helpers/geocoder.py`
- Test: `services/backend/tests/test_geocoder.py`

**Interfaces:**
- Produces:
  - `GeoResult` dataclass: `lat: float`, `lng: float`, `country_code: str` (upper), `admin1_name: Optional[str]`, `display_name: str`, `is_country: bool`.
  - `GeocoderClient.geocode(text: str) -> Optional[GeoResult]`
  - `GeocoderClient.reverse_geocode(lat: float, lng: float) -> Optional[GeoResult]`
  - module singleton `geocoder = GeocoderClient()`

- [ ] **Step 1: Write the failing tests**

Create `services/backend/tests/test_geocoder.py`:

```python
import httpx
import pytest

from services.backend.app.helpers import geocoder as geo_mod
from services.backend.app.helpers.geocoder import GeocoderClient


def _resp(status, payload):
    return httpx.Response(status, json=payload, request=httpx.Request("GET", "http://x"))


DALAT_SEARCH = [{
    "lat": "11.9082632", "lon": "108.4572089", "display_name": "Da Lat, Lam Dong, Vietnam",
    "addresstype": "historic",
    "address": {"state": "Tỉnh Lâm Đồng", "country_code": "vn"},
}]


@pytest.mark.asyncio
async def test_geocode_parses_specific_place(monkeypatch):
    c = GeocoderClient()
    async def fake_get(url, headers=None, params=None): return _resp(200, DALAT_SEARCH)
    monkeypatch.setattr(c._client, "get", fake_get)
    r = await c.geocode("Dalat, Vietnam")
    assert r is not None
    assert (round(r.lat, 3), round(r.lng, 3)) == (11.908, 108.457)
    assert r.country_code == "VN"
    assert r.admin1_name == "Tỉnh Lâm Đồng"
    assert r.is_country is False


@pytest.mark.asyncio
async def test_geocode_country_level_flagged(monkeypatch):
    c = GeocoderClient()
    payload = [{"lat": "16.0", "lon": "106.0", "display_name": "Vietnam",
                "addresstype": "country", "address": {"country_code": "vn"}}]
    async def fake_get(url, headers=None, params=None): return _resp(200, payload)
    monkeypatch.setattr(c._client, "get", fake_get)
    r = await c.geocode("Vietnam")
    assert r.is_country is True and r.admin1_name is None


@pytest.mark.asyncio
async def test_geocode_empty_returns_none(monkeypatch):
    c = GeocoderClient()
    async def fake_get(url, headers=None, params=None): return _resp(200, [])
    monkeypatch.setattr(c._client, "get", fake_get)
    assert await c.geocode("zzzz") is None


@pytest.mark.asyncio
async def test_geocode_error_returns_none(monkeypatch):
    c = GeocoderClient()
    async def boom(*a, **k): raise httpx.ConnectError("down")
    monkeypatch.setattr(c._client, "get", boom)
    assert await c.geocode("anything") is None


@pytest.mark.asyncio
async def test_reverse_geocode_parses(monkeypatch):
    c = GeocoderClient()
    payload = {"lat": "11.9", "lon": "108.4", "display_name": "Da Lat",
               "addresstype": "suburb", "address": {"state": "Tỉnh Lâm Đồng", "country_code": "vn"}}
    async def fake_get(url, headers=None, params=None):
        assert "/reverse" in url
        return _resp(200, payload)
    monkeypatch.setattr(c._client, "get", fake_get)
    r = await c.reverse_geocode(11.9, 108.4)
    assert r.admin1_name == "Tỉnh Lâm Đồng" and r.country_code == "VN"
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest services/backend/tests/test_geocoder.py -v`
Expected: FAIL (module/class not found).

- [ ] **Step 3: Implement `geocoder.py`**

```python
"""OpenStreetMap Nominatim geocoder (forward + reverse) for region resolution.

Returns a GeoResult or None on any error — never raises. Results are cached
in-process (Nominatim asks heavy users to cache + self-host); a descriptive
User-Agent is required by their usage policy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
NOMINATIM_UA = "BirdleAI/1.0 (bird identification; https://github.com/birdle-ai)"
TIMEOUT = 10.0


@dataclass(frozen=True)
class GeoResult:
    lat: float
    lng: float
    country_code: str          # uppercased ISO alpha-2 ("VN")
    admin1_name: Optional[str]  # e.g. "Tỉnh Lâm Đồng", or None
    display_name: str
    is_country: bool            # True when the match itself is a whole country


def _parse(obj: dict[str, Any]) -> Optional[GeoResult]:
    try:
        addr = obj.get("address") or {}
        cc = (addr.get("country_code") or "").upper()
        if not cc:
            return None
        return GeoResult(
            lat=float(obj["lat"]),
            lng=float(obj["lon"]),
            country_code=cc,
            admin1_name=addr.get("state") or addr.get("province") or None,
            display_name=obj.get("display_name", ""),
            is_country=(obj.get("addresstype") == "country"),
        )
    except (KeyError, TypeError, ValueError):
        return None


class GeocoderClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT))
        self._fwd_cache: dict[str, Optional[GeoResult]] = {}
        self._rev_cache: dict[str, Optional[GeoResult]] = {}

    async def close(self) -> None:
        await self._client.aclose()

    async def geocode(self, text: str) -> Optional[GeoResult]:
        key = (text or "").strip().lower()
        if not key:
            return None
        if key in self._fwd_cache:
            return self._fwd_cache[key]
        result: Optional[GeoResult] = None
        try:
            resp = await self._client.get(
                f"{NOMINATIM_BASE}/search",
                headers={"User-Agent": NOMINATIM_UA},
                params={"q": text, "format": "jsonv2", "addressdetails": 1, "limit": 1},
            )
            resp.raise_for_status()
            data = resp.json()
            result = _parse(data[0]) if data else None
        except Exception as e:
            logger.warning(
                f"Geocode failed: {e}",
                extra={"operation": "geocode", "status": "error", "error_type": type(e).__name__},
            )
        self._fwd_cache[key] = result
        return result

    async def reverse_geocode(self, lat: float, lng: float) -> Optional[GeoResult]:
        key = f"{round(lat, 4)},{round(lng, 4)}"
        if key in self._rev_cache:
            return self._rev_cache[key]
        result: Optional[GeoResult] = None
        try:
            resp = await self._client.get(
                f"{NOMINATIM_BASE}/reverse",
                headers={"User-Agent": NOMINATIM_UA},
                params={"lat": lat, "lon": lng, "format": "jsonv2",
                        "addressdetails": 1, "zoom": 8},
            )
            resp.raise_for_status()
            result = _parse(resp.json())
        except Exception as e:
            logger.warning(
                f"Reverse geocode failed: {e}",
                extra={"operation": "reverse_geocode", "status": "error",
                       "error_type": type(e).__name__},
            )
        self._rev_cache[key] = result
        return result


geocoder = GeocoderClient()
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest services/backend/tests/test_geocoder.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/helpers/geocoder.py services/backend/tests/test_geocoder.py
git commit -m "feat: Nominatim geocoder helper (forward + reverse)"
```

---

## Task 3: Name normalization + subnational1 matching (pure functions)

**Files:**
- Modify: `services/backend/app/helpers/geocoder.py`
- Test: `services/backend/tests/test_geocoder.py`

**Interfaces:**
- Produces (module-level functions in `geocoder.py`):
  - `normalize_region_name(name: str) -> str` — NFKD diacritic-strip, lowercase, drop admin words, collapse whitespace.
  - `match_subnational1(admin1_name: str, region_list: list[dict[str, str]]) -> Optional[str]` — returns the eBird `code` whose normalized name equals or token-subset-matches the normalized `admin1_name`; else `None`.

- [ ] **Step 1: Write the failing tests**

Add to `test_geocoder.py`:

```python
from services.backend.app.helpers.geocoder import normalize_region_name, match_subnational1

VN_LIST = [{"code": "VN-68", "name": "Lam Dong"}, {"code": "VN-44", "name": "Hanoi"}]
US_LIST = [{"code": "US-NY", "name": "New York"}, {"code": "US-NJ", "name": "New Jersey"}]


def test_normalize_strips_diacritics_and_admin_words():
    assert normalize_region_name("Tỉnh Lâm Đồng") == "lam dong"
    assert normalize_region_name("New York State") == "new york"
    assert normalize_region_name("Provincia de Buenos Aires") == "buenos aires"


def test_match_subnational1_diacritic_insensitive():
    assert match_subnational1("Tỉnh Lâm Đồng", VN_LIST) == "VN-68"


def test_match_subnational1_plain():
    assert match_subnational1("New York", US_LIST) == "US-NY"


def test_match_subnational1_no_match_returns_none():
    assert match_subnational1("Atlantis", VN_LIST) is None
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest services/backend/tests/test_geocoder.py -k "normalize or match" -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement**

Add to `geocoder.py` (near the top, after imports add `import re`, `import unicodedata`):

```python
# Admin-area words dropped before matching (lowercased, diacritic-free forms).
_ADMIN_WORDS = {
    "tinh", "thanh", "pho", "province", "provincia", "de", "del", "state",
    "city", "region", "prefecture", "district", "county", "oblast", "krai",
    "department", "governorate", "do", "si",
}


def normalize_region_name(name: str) -> str:
    """Lowercase, strip diacritics, drop admin words, collapse whitespace."""
    decomposed = unicodedata.normalize("NFKD", name or "")
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    ascii_only = re.sub(r"[^a-zA-Z\s]", " ", ascii_only).lower()
    tokens = [t for t in ascii_only.split() if t and t not in _ADMIN_WORDS]
    return " ".join(tokens)


def match_subnational1(
    admin1_name: str, region_list: list[dict[str, str]]
) -> Optional[str]:
    """eBird code whose normalized name == or token-subset-matches admin1_name."""
    target = normalize_region_name(admin1_name)
    if not target:
        return None
    target_tokens = set(target.split())
    best: Optional[str] = None
    for r in region_list:
        cand = normalize_region_name(r.get("name", ""))
        if not cand:
            continue
        if cand == target:
            return r.get("code")  # exact wins immediately
        cand_tokens = set(cand.split())
        # token-subset both directions ("lam dong" vs "lam dong city")
        if cand_tokens and (cand_tokens <= target_tokens or target_tokens <= cand_tokens):
            best = best or r.get("code")
    return best
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest services/backend/tests/test_geocoder.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/helpers/geocoder.py services/backend/tests/test_geocoder.py
git commit -m "feat: region-name normalization + eBird subnational1 matching"
```

---

## Task 4: `resolve_region()` orchestration

**Files:**
- Modify: `services/backend/app/helpers/geocoder.py`
- Test: `services/backend/tests/test_geocoder.py`

**Interfaces:**
- Consumes: `geocoder.geocode` / `reverse_geocode` (Task 2), `match_subnational1` (Task 3), `ebird_client.get_subnational1_list` (Task 1).
- Produces (module function in `geocoder.py`):
  - `resolve_region(text: Optional[str] = None, lat: Optional[float] = None, lng: Optional[float] = None) -> dict` returning
    `{"region_code": Optional[str], "lat": Optional[float], "lng": Optional[float], "precision": "point"|"country"|"none", "display_name": Optional[str]}`.
  - Rules: coordinates win (reverse-geocode); else forward-geocode `text`. From the `GeoResult`: `region_code` = `match_subnational1(admin1_name, get_subnational1_list(country_code))` else the country code; `precision = "country"` if `is_country` (region presence), else `"point"`; lat/lng passed through **only** when `precision == "point"`. Geocode `None` → all-None / `precision="none"`.

- [ ] **Step 1: Write the failing tests**

Add to `test_geocoder.py`:

```python
import services.backend.app.helpers.geocoder as gmod


@pytest.mark.asyncio
async def test_resolve_region_text_namematches_subnational1(monkeypatch):
    async def fake_geocode(text):
        return gmod.GeoResult(11.9, 108.4, "VN", "Tỉnh Lâm Đồng", "Da Lat, VN", False)
    async def fake_list(cc): return [{"code": "VN-68", "name": "Lam Dong"}]
    monkeypatch.setattr(gmod.geocoder, "geocode", fake_geocode)
    monkeypatch.setattr(gmod.ebird_client, "get_subnational1_list", fake_list)
    out = await gmod.resolve_region(text="Dalat, Vietnam")
    assert out["region_code"] == "VN-68"
    assert out["precision"] == "point"
    assert (round(out["lat"], 1), round(out["lng"], 1)) == (11.9, 108.4)


@pytest.mark.asyncio
async def test_resolve_region_falls_back_to_country_when_no_match(monkeypatch):
    async def fake_geocode(text):
        return gmod.GeoResult(11.9, 108.4, "VN", "Some Unknown Area", "x", False)
    async def fake_list(cc): return [{"code": "VN-68", "name": "Lam Dong"}]
    monkeypatch.setattr(gmod.geocoder, "geocode", fake_geocode)
    monkeypatch.setattr(gmod.ebird_client, "get_subnational1_list", fake_list)
    out = await gmod.resolve_region(text="someplace, vietnam")
    assert out["region_code"] == "VN"          # country fallback
    assert out["precision"] == "point"          # still a specific point -> radius


@pytest.mark.asyncio
async def test_resolve_region_country_level_uses_region_presence(monkeypatch):
    async def fake_geocode(text):
        return gmod.GeoResult(16.0, 106.0, "VN", None, "Vietnam", True)
    monkeypatch.setattr(gmod.geocoder, "geocode", fake_geocode)
    out = await gmod.resolve_region(text="Vietnam")
    assert out["region_code"] == "VN"
    assert out["precision"] == "country"
    assert out["lat"] is None and out["lng"] is None


@pytest.mark.asyncio
async def test_resolve_region_coordinates_win(monkeypatch):
    called = {"reverse": False}
    async def fake_reverse(lat, lng):
        called["reverse"] = True
        return gmod.GeoResult(lat, lng, "VN", "Tỉnh Lâm Đồng", "Da Lat", False)
    async def fake_list(cc): return [{"code": "VN-68", "name": "Lam Dong"}]
    monkeypatch.setattr(gmod.geocoder, "reverse_geocode", fake_reverse)
    monkeypatch.setattr(gmod.ebird_client, "get_subnational1_list", fake_list)
    out = await gmod.resolve_region(text="ignored", lat=11.9, lng=108.4)
    assert called["reverse"] and out["region_code"] == "VN-68" and out["precision"] == "point"


@pytest.mark.asyncio
async def test_resolve_region_geocode_none(monkeypatch):
    async def fake_geocode(text): return None
    monkeypatch.setattr(gmod.geocoder, "geocode", fake_geocode)
    out = await gmod.resolve_region(text="zzz")
    assert out == {"region_code": None, "lat": None, "lng": None,
                   "precision": "none", "display_name": None}
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest services/backend/tests/test_geocoder.py -k resolve_region -v`
Expected: FAIL (`resolve_region` undefined).

- [ ] **Step 3: Implement**

Add the eBird import at the top of `geocoder.py`:

```python
from .ebird_client import ebird_client
```

Add the function:

```python
async def resolve_region(
    text: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
) -> dict[str, Any]:
    """Deterministically resolve a location to an eBird region + point.

    Coordinates win (reverse-geocode); otherwise forward-geocode ``text``.
    Region code comes from name-matching eBird's subnational1 list, falling
    back to the country code. lat/lng are returned only for a specific point.
    """
    none_result = {"region_code": None, "lat": None, "lng": None,
                   "precision": "none", "display_name": None}

    if lat is not None and lng is not None:
        geo = await geocoder.reverse_geocode(lat, lng)
    elif text and text.strip():
        geo = await geocoder.geocode(text)
    else:
        return none_result

    if geo is None:
        return none_result

    region_code = geo.country_code
    if not geo.is_country and geo.admin1_name:
        region_list = await ebird_client.get_subnational1_list(geo.country_code)
        matched = match_subnational1(geo.admin1_name, region_list)
        if matched:
            region_code = matched

    precision = "country" if geo.is_country else "point"
    return {
        "region_code": region_code,
        "lat": None if precision == "country" else geo.lat,
        "lng": None if precision == "country" else geo.lng,
        "precision": precision,
        "display_name": geo.display_name,
    }
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest services/backend/tests/test_geocoder.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/helpers/geocoder.py services/backend/tests/test_geocoder.py
git commit -m "feat: resolve_region() — geocode + name-match orchestration"
```

---

## Task 5: State + request schema + runner/route plumbing for lat/lng

**Files:**
- Modify: `services/backend/app/graph/state.py`
- Modify: `services/backend/app/schemas/observation.py`
- Modify: `services/backend/app/graph/runner.py`
- Modify: `services/backend/app/routes/identify.py`
- Test: `services/backend/tests/test_identify.py` (schema validation)

**Interfaces:**
- Produces: `BirdState` gains `lat: Optional[float]`, `lng: Optional[float]`. `ObservationInput` gains optional `lat`, `lng`; `location` relaxed to optional. `runner.run_stream(..., lat=None, lng=None)`.
- Consumes: nothing yet (Task 6 reads `lat`/`lng` from state).

- [ ] **Step 1: Write the failing test**

Add to `services/backend/tests/test_identify.py`:

```python
def test_observation_input_accepts_coordinates_without_location():
    from services.backend.app.schemas.observation import ObservationInput
    obs = ObservationInput(description="small brown bird", lat=11.9, lng=108.4)
    assert obs.lat == 11.9 and obs.lng == 108.4 and (obs.location or "") == ""


def test_observation_input_still_accepts_text_location():
    from services.backend.app.schemas.observation import ObservationInput
    obs = ObservationInput(description="x", location="Dalat")
    assert obs.location == "Dalat" and obs.lat is None
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest services/backend/tests/test_identify.py -k coordinates -v`
Expected: FAIL (ValidationError — `location` required / `lat` unknown).

- [ ] **Step 3: Implement**

`schemas/observation.py` — relax `location`, add coords:

```python
    location: Optional[str] = Field(
        "", description="Location where bird was observed (optional if coordinates given)"
    )
    observed_at: Optional[str] = Field(None, description="When the bird was observed")
    lat: Optional[float] = Field(None, description="Latitude from the 'use my location' button")
    lng: Optional[float] = Field(None, description="Longitude from the 'use my location' button")
```

`state.py` — add to `BirdState` (after `location` / near the resolved block):

```python
    lat: Optional[float]
    lng: Optional[float]
```

`runner.py` — extend `run_stream` and the graph input (pass through; resolve_inputs will use them):

```python
    async def run_stream(
        self, session_id: str, description: str, location: str,
        observed_at: Optional[str] = None,
        lat: Optional[float] = None, lng: Optional[float] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        ...
        graph_input = {
            "description": description,
            "location": location,
            "observed_at": observed_at,
            "lat": lat,
            "lng": lng,
            "messages": [SystemMessage(content=prompts.SYSTEM_PROMPT), HumanMessage(content=user)],
            "ask_rounds": 0,
            "final": None,
        }
```

`routes/identify.py` — pass coords in both `identify_bird` and `identify_bird_stream` runner calls:

```python
            location=observation.location or "",
            observed_at=observation.observed_at,
            lat=observation.lat,
            lng=observation.lng,
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest services/backend/tests/test_identify.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/graph/state.py services/backend/app/schemas/observation.py services/backend/app/graph/runner.py services/backend/app/routes/identify.py services/backend/tests/test_identify.py
git commit -m "feat: thread optional lat/lng through schema, state, runner, routes"
```

---

## Task 6: `resolve_inputs` node — deterministic region + date-only LLM

**Files:**
- Modify: `services/backend/app/graph/nodes.py`
- Modify: `services/backend/app/graph/prompts.py`
- Test: `services/backend/tests/test_resolve_inputs.py` (create if absent; else add to the existing graph-node test file)

**Interfaces:**
- Consumes: `geocoder.resolve_region` (Task 4); state `lat`/`lng` (Task 5).
- Produces: `resolve_inputs` returns `{"region", "lat", "lng", "observed_window", "ask_rounds", "messages"}`. `_parse_date(observed_at) -> str` (replaces `_parse_inputs`, region dropped from the LLM).

- [ ] **Step 1: Write the failing test**

Create `services/backend/tests/test_resolve_inputs.py`:

```python
import pytest
from services.backend.app.graph import nodes


@pytest.mark.asyncio
async def test_resolve_inputs_uses_geocoder_not_llm(monkeypatch):
    async def fake_resolve(text=None, lat=None, lng=None):
        return {"region_code": "VN-68", "lat": 11.9, "lng": 108.4,
                "precision": "point", "display_name": "Da Lat, VN"}
    async def fake_date(observed_at): return "recent"
    monkeypatch.setattr(nodes, "resolve_region", fake_resolve)
    monkeypatch.setattr(nodes, "_parse_date", fake_date)
    out = await nodes.resolve_inputs({"location": "Dalat, Vietnam", "observed_at": None, "ask_rounds": 0})
    assert out["region"] == "VN-68"
    assert out["lat"] == 11.9 and out["lng"] == 108.4


@pytest.mark.asyncio
async def test_resolve_inputs_country_precision_drops_latlng(monkeypatch):
    async def fake_resolve(text=None, lat=None, lng=None):
        return {"region_code": "VN", "lat": None, "lng": None,
                "precision": "country", "display_name": "Vietnam"}
    async def fake_date(observed_at): return "recent"
    monkeypatch.setattr(nodes, "resolve_region", fake_resolve)
    monkeypatch.setattr(nodes, "_parse_date", fake_date)
    out = await nodes.resolve_inputs({"location": "Vietnam", "observed_at": None, "ask_rounds": 0})
    assert out["region"] == "VN" and out["lat"] is None and out["lng"] is None


@pytest.mark.asyncio
async def test_resolve_inputs_coordinates_take_precedence(monkeypatch):
    seen = {}
    async def fake_resolve(text=None, lat=None, lng=None):
        seen["lat"], seen["lng"] = lat, lng
        return {"region_code": "VN-68", "lat": lat, "lng": lng,
                "precision": "point", "display_name": "Da Lat"}
    async def fake_date(observed_at): return "recent"
    monkeypatch.setattr(nodes, "resolve_region", fake_resolve)
    monkeypatch.setattr(nodes, "_parse_date", fake_date)
    out = await nodes.resolve_inputs(
        {"location": "", "observed_at": None, "ask_rounds": 0, "lat": 11.9, "lng": 108.4}
    )
    assert seen == {"lat": 11.9, "lng": 108.4} and out["region"] == "VN-68"
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest services/backend/tests/test_resolve_inputs.py -v`
Expected: FAIL (`resolve_region`/`_parse_date` not in `nodes`).

- [ ] **Step 3: Implement**

In `nodes.py`: add import `from ..helpers.geocoder import resolve_region`. Replace `_parse_inputs` with a date-only `_parse_date`:

```python
async def _parse_date(observed_at: Optional[str]) -> str:
    """Haiku parse: free-text time -> 'recent' | 'YYYY-MM-DD' | 'unparseable'."""
    if not observed_at or not observed_at.strip():
        return "recent"
    try:
        resp = await _raw_anthropic.messages.create(
            model=prompts.RESOLVE_MODEL,
            max_tokens=40,
            system=prompts.RESOLVE_PROMPT,
            messages=[{"role": "user", "content": f"time={observed_at!r}"}],
        )
        window = _first_text(resp).strip().strip('"')
        return window or "recent"
    except Exception as e:
        logger.warning(f"Date parse failed: {e}",
                       extra={"operation": "resolve_inputs", "status": "error"})
        return "recent"
```

Rewrite `resolve_inputs`:

```python
async def resolve_inputs(state: BirdState) -> dict[str, Any]:
    """Deterministically resolve region (+point) via geocoding; clarify via interrupt."""
    location = state.get("location", "") or ""
    observed_at = state.get("observed_at")
    ask_rounds = state.get("ask_rounds", 0)
    lat_in, lng_in = state.get("lat"), state.get("lng")

    resolved = await resolve_region(text=location, lat=lat_in, lng=lng_in)
    window = await _parse_date(observed_at)
    if window == "unparseable":
        window = "recent"

    region = resolved["region_code"]
    lat, lng = resolved["lat"], resolved["lng"]
    display = resolved.get("display_name")

    if display:
        _emit({"type": "status", "message": f"Looking around {display}…"})

    answer: Optional[str] = None
    if region is None and ask_rounds < prompts.MAX_ASK_ROUNDS:
        if location.strip():
            payload: dict[str, Any] = {
                "reason": "clarify_location",
                "question": (
                    f"I couldn't pin down “{location}” to a birding region. "
                    "Which country/state (or nearest city) was it?"
                ),
            }
        else:
            payload = {
                "reason": "clarify_location",
                "question": "Where did you see it? A location helps a lot — or skip and I'll do my best.",
                "options": ["Skip — no location"],
            }
        answer = interrupt(payload)
        ask_rounds += 1
        if answer and answer.strip().lower() not in {"skip", "skip — no location", "not sure"}:
            reparsed = await resolve_region(text=answer)
            region, lat, lng = reparsed["region_code"], reparsed["lat"], reparsed["lng"]

    context = HumanMessage(
        content=(
            f"Resolved region: {region or 'UNKNOWN (proceed description-only, lower confidence)'}. "
            f"Observation window: {window}. "
            + (
                "Use get_regional_birds for what's present near the sighting."
                if window == "recent"
                else f"The sighting was on {window}; prefer date-anchored evidence and reason about seasonality."
            )
        )
    )
    return {
        "region": region,
        "lat": lat,
        "lng": lng,
        "observed_window": window,
        "ask_rounds": ask_rounds,
        "messages": [context],
    }
```

In `prompts.py`, replace `RESOLVE_PROMPT` with a date-only parser:

```python
RESOLVE_PROMPT = """\
You convert a user's free-text observation time into a single token. Output ONLY
the token, no prose, no JSON:
- "recent" — no date, or within ~14 days, or words meaning "lately".
- "YYYY-MM-DD" — a specific past date is given or clearly inferable.
- "unparseable" — a date was attempted but is genuinely ambiguous (e.g. "summer?").
"""
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest services/backend/tests/test_resolve_inputs.py -v`
Expected: PASS. Then run the full graph-node suite to catch regressions: `uv run pytest services/backend/tests/ -k "resolve or node" -v`.

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/graph/nodes.py services/backend/app/graph/prompts.py services/backend/tests/test_resolve_inputs.py
git commit -m "feat: deterministic resolve_inputs (geocoder) + date-only LLM parse"
```

---

## Task 7: `get_regional_birds` — transparent geo presence via InjectedState

**Files:**
- Modify: `services/backend/app/graph/tools.py`
- Test: `services/backend/tests/test_tools.py` (create if absent; else add to existing tool test file)

**Interfaces:**
- Consumes: state `lat`/`lng` (Task 5/6); `ebird_client.get_nearby_birds` (Task 1).
- Produces: `get_regional_birds(region, days=14, state=<injected>)` — when state has `lat`/`lng`, returns `get_nearby_birds(lat, lng, 50, max(days, 30))`; if that yields 0 species, falls back to region recency; else region recency. SSE summary names the source.

- [ ] **Step 1: Write the failing test**

Create `services/backend/tests/test_tools.py`:

```python
import pytest
from services.backend.app.graph import tools
from services.backend.app.helpers.ebird_client import ebird_client


@pytest.mark.asyncio
async def test_get_regional_birds_uses_geo_when_point(monkeypatch):
    async def fake_nearby(lat, lng, dist=50, days=14):
        return {"region": "geo", "days_searched": days, "total_species": 2,
                "species_observed": [{"common_name": "X", "scientific_name": "Xx", "species_code": "x"}]}
    async def fake_region(*a, **k): raise AssertionError("region path should not run")
    monkeypatch.setattr(ebird_client, "get_nearby_birds", fake_nearby)
    monkeypatch.setattr(ebird_client, "get_regional_birds", fake_region)
    res = await tools.get_regional_birds.ainvoke(
        {"region": "VN-68", "days": 14, "state": {"lat": 11.9, "lng": 108.4}}
    )
    assert res["total_species"] == 2 and res["region"] == "geo"


@pytest.mark.asyncio
async def test_get_regional_birds_uses_region_when_no_point(monkeypatch):
    async def fake_region(region, days=14):
        return {"region": region, "days_searched": days, "total_species": 5, "species_observed": []}
    monkeypatch.setattr(ebird_client, "get_regional_birds", fake_region)
    res = await tools.get_regional_birds.ainvoke({"region": "VN", "days": 14, "state": {}})
    assert res["region"] == "VN" and res["total_species"] == 5


@pytest.mark.asyncio
async def test_get_regional_birds_geo_empty_falls_back_to_region(monkeypatch):
    async def empty_nearby(lat, lng, dist=50, days=14):
        return {"region": "geo", "days_searched": days, "total_species": 0, "species_observed": []}
    async def fake_region(region, days=14):
        return {"region": region, "days_searched": days, "total_species": 7, "species_observed": []}
    monkeypatch.setattr(ebird_client, "get_nearby_birds", empty_nearby)
    monkeypatch.setattr(ebird_client, "get_regional_birds", fake_region)
    res = await tools.get_regional_birds.ainvoke(
        {"region": "VN-68", "days": 14, "state": {"lat": 11.9, "lng": 108.4}}
    )
    assert res["region"] == "VN-68" and res["total_species"] == 7
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest services/backend/tests/test_tools.py -v`
Expected: FAIL (`state` not accepted / geo path missing).

- [ ] **Step 3: Implement**

In `tools.py` add the import:

```python
from typing import Annotated, Any
from langgraph.prebuilt import InjectedState
```

Rewrite `get_regional_birds`:

```python
@tool
async def get_regional_birds(
    region: str,
    days: int = 14,
    state: Annotated[dict, InjectedState] = None,  # injected; hidden from the model
) -> dict[str, Any]:
    """Recently observed bird species near the sighting (presence/recency, not abundance)."""
    lat = (state or {}).get("lat")
    lng = (state or {}).get("lng")

    if lat is not None and lng is not None:
        _emit({"type": "tool_call", "tool": "get_regional_birds",
               "input": {"lat": lat, "lng": lng, "dist_km": 50}})
        result = await ebird_client.get_nearby_birds(lat, lng, dist=50, days=max(days, 30))
        if isinstance(result, dict) and result.get("total_species", 0) > 0:
            shown = len(result.get("species_observed", []))
            _emit({"type": "tool_result", "tool": "get_regional_birds",
                   "summary": f"{result['total_species']} species within 50 km (reviewing {shown})"})
            return result
        # geo desert -> fall back to the region's recency list

    _emit({"type": "tool_call", "tool": "get_regional_birds",
           "input": {"region": region, "days": days}})
    result = await ebird_client.get_regional_birds(region=region, days=days)
    shown = len(result.get("species_observed", [])) if isinstance(result, dict) else 0
    total = result.get("total_species", shown) if isinstance(result, dict) else 0
    summary = f"{total} species recently in {region}" + (
        f" (reviewing top {shown})" if total > shown else ""
    )
    _emit({"type": "tool_result", "tool": "get_regional_birds", "summary": summary})
    return result
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest services/backend/tests/test_tools.py -v`
Expected: PASS. Then `uv run pytest services/backend/tests/ -v` (full suite green).

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/graph/tools.py services/backend/tests/test_tools.py
git commit -m "feat: get_regional_birds serves GPS-radius presence when a point is known"
```

---

## Task 8: Backend gates — lint, format, types, full suite

**Files:** none (verification + any fixups).

- [ ] **Step 1: Run the gates**

```bash
uv run ruff check services/
uv run black --check services/
uv run mypy services/backend/app --ignore-missing-imports
uv run pytest services/backend/tests/ -v
```
Expected: all clean/green. Fix any issues (e.g. run `uv run black services/` to format; add return-type/`Optional` annotations mypy flags — note `state: Annotated[dict, InjectedState] = None` may need `Optional[dict]`).

- [ ] **Step 2: Commit any fixups**

```bash
git add -A && git commit -m "chore: lint/format/type fixups for region resolution"
```

---

## Task 9: Frontend — coordinates in the request type + client

**Files:**
- Modify: `frontend/src/types/observation.ts`
- Test: `frontend/src/api/client.test.ts`

**Interfaces:**
- Produces: `ObservationInput` gains `lat?: number`, `lng?: number`; `location?` optional. The existing `identifyBirdStream`/`identifyBird` send the whole object as JSON, so no client change is needed beyond the type (verify the body is `JSON.stringify(observation)`).

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/api/client.test.ts` (match the file's existing fetch-mock style):

```ts
it('sends lat/lng in the identify request body when present', async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response('data: {"type":"done"}\n\n', { status: 200 }),
  );
  vi.stubGlobal('fetch', fetchMock);
  await identifyBirdStream(
    { description: 'small brown bird', lat: 11.9, lng: 108.4 },
    () => {},
    new AbortController().signal,
  );
  const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
  expect(body.lat).toBe(11.9);
  expect(body.lng).toBe(108.4);
});
```

- [ ] **Step 2: Run, verify fail**

Run (from `frontend/`): `npm run test -- client.test.ts`
Expected: FAIL (type error on `lat`/`lng`, or body lacks them).

- [ ] **Step 3: Implement**

`frontend/src/types/observation.ts` — update `ObservationInput`:

```ts
export interface ObservationInput {
  description: string;
  location?: string;
  observed_at?: string;
  lat?: number;
  lng?: number;
}
```

If `client.ts` builds the body field-by-field rather than `JSON.stringify(observation)`, add `lat`/`lng` there; otherwise no change.

- [ ] **Step 4: Run, verify pass**

Run: `npm run test -- client.test.ts` then `npm run build`
Expected: PASS + clean build.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/observation.ts frontend/src/api/client.ts frontend/src/api/client.test.ts
git commit -m "feat(fe): optional lat/lng on the identify request"
```

---

## Task 10: Frontend — "Use my location" button + geolocation wiring

**Files:**
- Modify: `frontend/src/hooks/useBirdleSession.ts`
- Modify: `frontend/src/components/birdle/DesktopBirdle.tsx`
- Modify: `frontend/src/components/birdle/MobileBirdle.tsx`

**Interfaces:**
- Consumes: `ObservationInput.lat/lng` (Task 9).
- Produces on the session object `s`: `coords: {lat: number, lng: number} | null`, `geoStatus: 'idle'|'locating'|'on'|'error'`, `useMyLocation(): void`, `clearCoords(): void`. `canStart` becomes true when `desc` is set AND (`loc` text OR `coords`). `start()` includes `coords` in the observation.

- [ ] **Step 1: Add state + handlers in the hook**

In `useBirdleSession.ts`, near the other `useState`s:

```ts
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [geoStatus, setGeoStatus] = useState<'idle' | 'locating' | 'on' | 'error'>('idle');

  const useMyLocation = useCallback(() => {
    if (!('geolocation' in navigator)) { setGeoStatus('error'); return; }
    setGeoStatus('locating');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setGeoStatus('on');
      },
      () => setGeoStatus('error'),
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 },
    );
  }, []);

  const clearCoords = useCallback(() => { setCoords(null); setGeoStatus('idle'); }, []);
```

Update `start()`'s guard, observation, and deps:

```ts
    const description = desc.trim();
    const location = loc.trim();
    if (!description || (!location && !coords)) return;
    const observation: ObservationInput = {
      description,
      ...(location && { location }),
      ...(coords && { lat: coords.lat, lng: coords.lng }),
      ...(time.trim() && { observed_at: time.trim() }),
    };
```
```ts
  }, [desc, loc, time, coords, beginTurn, handleStreamEvent]);
```

Update `canStart` and the returned object:

```ts
    canStart: !!desc.trim() && (!!loc.trim() || !!coords),
```
```ts
    coords, geoStatus, useMyLocation, clearCoords,
```

Add these to the hook's return-type interface (the block around lines 57–81 that declares `loc`, `setLoc`, etc.):

```ts
  coords: { lat: number; lng: number } | null;
  geoStatus: 'idle' | 'locating' | 'on' | 'error';
  useMyLocation: () => void;
  clearCoords: () => void;
```

- [ ] **Step 2: Add the button to both layouts**

In `DesktopBirdle.tsx` and `MobileBirdle.tsx`, inside the `FieldShell icon="pin" label="Where"` block, beside the `TextInput`, add (use the existing `Chip`/button primitive; plain button shown for clarity):

```tsx
                <TextInput value={s.loc} onChange={s.setLoc} ariaLabel="Where" placeholder="City or area" />
                {s.geoStatus === 'on' ? (
                  <button type="button" onClick={s.clearCoords} className="bd-geo-chip" aria-label="Clear my location">
                    📍 Using your location ✕
                  </button>
                ) : (
                  <button type="button" onClick={s.useMyLocation} className="bd-geo-chip"
                          disabled={s.geoStatus === 'locating'} aria-label="Use my location">
                    {s.geoStatus === 'locating' ? '📍 Locating…' : '📍 Use my location'}
                  </button>
                )}
                {s.geoStatus === 'error' && (
                  <span className="bd-geo-err">Couldn’t get your location — type it instead.</span>
                )}
```

Style `.bd-geo-chip` / `.bd-geo-err` in `frontend/src/index.css` consistent with existing chips (small, accent border, rounded). Keep it minimal.

- [ ] **Step 3: Verify build + lint + manual smoke**

Run (from `frontend/`):
```bash
npm run lint
npm run build
```
Expected: clean (no warnings — `--max-warnings 0`).
Manual: `npm run dev`, click **📍 Use my location**, allow permission → chip shows "Using your location"; deny → error hint + text still works.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/useBirdleSession.ts frontend/src/components/birdle/DesktopBirdle.tsx frontend/src/components/birdle/MobileBirdle.tsx frontend/src/index.css
git commit -m "feat(fe): 'Use my location' button (browser geolocation)"
```

---

## Task 11: Docs — vision + tasklist

**Files:**
- Modify: `docs/vision.md`
- Modify: `docs/tasklist.md`

- [ ] **Step 1: Update `vision.md`**

Under the technologies/architecture section, record the new dependency and resolution path:
- Add OpenStreetMap **Nominatim** geocoding (forward + reverse) as an external data source, called via `httpx` (no new library).
- Note: region resolution is deterministic (geocode → name-match eBird subnational1 list); the LLM only parses the date. Presence uses a 50 km GPS radius when a specific point is known; frequency/rarities use the region code. Standardized on subnational1.

- [ ] **Step 2: Update `tasklist.md`**

Add a row to the Progress Report table and a backlog entry:
```
| 7 | Deterministic region resolution + "Use my location" | Complete | ✅ | Geocode→name-match eBird; GPS radius presence |
```
Backlog section: goal/test bullets mirroring this plan; note county precision intentionally dropped; future: interactive map pin, keyed geocoder if volume grows.

- [ ] **Step 3: Commit**

```bash
git add docs/vision.md docs/tasklist.md
git commit -m "docs: record geocoder dependency + region-resolution iteration"
```

---

## Task 12: End-to-end verification + PR

**Files:** none (verification).

- [ ] **Step 1: Full backend + frontend gates**

```bash
uv run pre-commit run --all-files
uv run pytest services/backend/tests/ -v
cd frontend && npm run lint && npm run build && npm run test
```
Expected: all green.

- [ ] **Step 2: Manual end-to-end (the motivating case)**

Start backend + frontend; submit description + "Dalat, Vietnam" (no coords). Confirm via logs/SSE the resolved region is `VN-68` (not `VN`/`VN-35`) and presence comes from the 50 km radius. Then repeat using **📍 Use my location**.

- [ ] **Step 3: Open the PR**

```bash
git push -u origin feat/region-resolution
gh pr create --title "feat: deterministic region resolution + 'use my location'" \
  --body "$(cat <<'EOF'
Deterministic eBird region resolution: geocode (Nominatim) → name-match eBird's
authoritative subnational1 list, replacing LLM code-guessing. GPS radius for
presence, region code for frequency/rarities. Adds a "Use my location" button.

Spec: docs/superpowers/specs/2026-06-25-deterministic-region-resolution-design.md
Plan: docs/superpowers/plans/2026-06-25-region-resolution.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review notes (addressed)

- **Spec coverage:** geocoder (T2), reverse (T2), name-match vs eBird list (T1+T3), resolve_region precedence (T4), state/schema/route plumbing (T5), resolve_inputs + date-only LLM (T6), radius-presence via InjectedState + geo-empty fallback (T7), frontend coords + button (T9–T10), vision/tasklist + dependency note (T11), county-drop honored (subnational1 only, no subnational2 task). ✅
- **InjectedState risk:** if `langgraph.prebuilt.InjectedState` import path differs in the installed version, Task 7 falls back to reading lat/lng from a module-level contextvar set in `resolve_inputs`; verify the import in Task 7 Step 3 before implementing.
- **Type consistency:** `get_nearby_birds` returns the same keys as `get_regional_birds`; `resolve_region` dict keys (`region_code/lat/lng/precision/display_name`) are consumed verbatim in T6; `coords/geoStatus/useMyLocation/clearCoords` names match between hook and components.
