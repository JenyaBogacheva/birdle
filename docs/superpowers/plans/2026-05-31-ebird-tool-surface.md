# eBird Tool Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `ebird_client.py` with the deeper eBird signals the new investigation graph needs — honest presence, bucketed abundance, regional rarities, taxonomy/family, historic-date observations, all-time species lists, and region drill-down — while dropping the phantom observation count.

**Architecture:** Pure additive changes to the existing `eBirdClient` class. Every method follows the established pattern: build the request, `raise_for_status()`, parse, log with `operation`/`latency_ms`/`status`, and **return a graceful fallback on any exception (never raise)**. This is plan 1 of 3; it ships independently (the methods are unit-testable and don't depend on LangGraph). Plan 2 wires a subset of these into agent-facing tools and the graph.

**Tech Stack:** Python 3.11, httpx.AsyncClient, pytest (asyncio_mode=auto — tests are plain `async def`, no decorator, matching `test_ebird_client.py`).

---

## File Structure

- **Modify:** `services/backend/app/helpers/ebird_client.py` — add methods + one bucket helper + a family cache; reframe `get_regional_birds`.
- **Modify:** `services/backend/tests/test_ebird_client.py` — add a test class per new method; update the existing `get_regional_birds` test for the dropped count.

All new methods are on the existing `eBirdClient` class and reuse `self._client`, `EBIRD_API_BASE`, and `settings.ebird_token`.

---

### Task 1: Reframe `get_regional_birds` — drop the phantom count

The `/data/obs/{region}/recent` endpoint returns one row per species, so the old `observation_count` was always ~1. Drop it; return a deduped presence list.

**Files:**
- Modify: `services/backend/app/helpers/ebird_client.py:33-106`
- Test: `services/backend/tests/test_ebird_client.py:8-46`

- [ ] **Step 1: Update the existing test to expect no count + dedupe**

Replace the body of `TestGetRegionalBirds.test_success` (`test_ebird_client.py:9-37`) with:

```python
    async def test_success_dedupes_without_count(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"comName": "Northern Cardinal", "sciName": "Cardinalis cardinalis", "speciesCode": "norcar"},
            {"comName": "Northern Cardinal", "sciName": "Cardinalis cardinalis", "speciesCode": "norcar"},
            {"comName": "Blue Jay", "sciName": "Cyanocitta cristata", "speciesCode": "blujay"},
        ]
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.get_regional_birds("US-NY", days=14)

        assert result["region"] == "US-NY"
        assert len(result["species_observed"]) == 2  # deduped
        first = result["species_observed"][0]
        assert first["common_name"] == "Northern Cardinal"
        assert first["species_code"] == "norcar"
        assert "observation_count" not in first  # phantom count removed
```

- [ ] **Step 2: Run it to verify it fails**

Run: `poetry run pytest services/backend/tests/test_ebird_client.py::TestGetRegionalBirds::test_success_dedupes_without_count -v`
Expected: FAIL — current code includes `observation_count`.

- [ ] **Step 3: Reframe the implementation**

In `ebird_client.py`, replace the species-aggregation block inside `get_regional_birds` (currently `ebird_client.py:58-80`) with first-seen dedupe (no counting):

```python
            # The /recent endpoint returns one row per species. Dedupe by
            # species, preserving eBird's order. We do NOT count rows — that
            # was always ~1 and is not a frequency signal.
            species_map: dict[str, dict[str, Any]] = {}
            for obs in data:
                code = obs.get("speciesCode", "")
                key = code or obs.get("comName", "Unknown")
                if key not in species_map:
                    species_map[key] = {
                        "common_name": obs.get("comName", "Unknown"),
                        "scientific_name": obs.get("sciName", ""),
                        "species_code": code,
                    }

            species = list(species_map.values())[:max_results]
            result = {
                "region": region,
                "days_searched": days,
                "species_observed": species,
            }
```

Also update the success log's `extra` to use `"species_count": len(species)` (drop any count references) and the fallback dict (`ebird_client.py:42-47`) to drop `total_observations`:

```python
        fallback: dict[str, Any] = {
            "region": region,
            "days_searched": days,
            "species_observed": [],
        }
```

- [ ] **Step 4: Run the regional-birds tests to verify they pass**

Run: `poetry run pytest services/backend/tests/test_ebird_client.py::TestGetRegionalBirds -v`
Expected: PASS (both the new test and `test_api_error_returns_fallback` — note that test asserts `species_observed == []`; remove its `assert result["total_observations"] == 0` line at `test_ebird_client.py:46`).

- [ ] **Step 5: Check downstream references didn't rely on the dropped fields**

Run: `grep -rn "observation_count\|total_observations" services/backend/app`
Expected: no matches in `app/`. If any appear, they're in `bird_agent._tool_result_summary` or `routes/identify.py` — update them to use `len(result["species_observed"])`. (`_tool_result_summary` at `bird_agent.py:336` already uses `species_observed` length, so it should be clean.)

- [ ] **Step 6: Commit**

```bash
git add services/backend/app/helpers/ebird_client.py services/backend/tests/test_ebird_client.py
git commit -m "refactor: drop phantom observation_count from get_regional_birds"
```

---

### Task 2: Bucketed abundance — `_abundance_bucket` + `get_species_frequency`

The real abundance signal: count recent reports of a specific species, capped, then bucket.

**Files:**
- Modify: `services/backend/app/helpers/ebird_client.py` (add module constant + helper + method)
- Test: `services/backend/tests/test_ebird_client.py` (add `TestAbundanceBucket`, `TestGetSpeciesFrequency`)

- [ ] **Step 1: Write the failing tests for the pure bucket helper**

Add to `test_ebird_client.py`:

```python
from services.backend.app.helpers.ebird_client import _abundance_bucket


class TestAbundanceBucket:
    def test_absent(self):
        assert _abundance_bucket(0) == "absent"

    def test_rare(self):
        assert _abundance_bucket(12) == "rare"
        assert _abundance_bucket(49) == "rare"

    def test_uncommon(self):
        assert _abundance_bucket(50) == "uncommon"
        assert _abundance_bucket(299) == "uncommon"

    def test_common(self):
        assert _abundance_bucket(300) == "common"
        assert _abundance_bucket(400) == "common"
```

- [ ] **Step 2: Run to verify it fails**

Run: `poetry run pytest services/backend/tests/test_ebird_client.py::TestAbundanceBucket -v`
Expected: FAIL — `cannot import name '_abundance_bucket'`.

- [ ] **Step 3: Implement the constant + helper**

In `ebird_client.py`, after the existing constants (`ebird_client.py:17-19`), add:

```python
FREQUENCY_FETCH_CAP = 400  # cap rows fetched per species; ">=cap" reads as "common"


def _abundance_bucket(report_count: int) -> str:
    """Bucket a recent-report count into a coarse abundance band."""
    if report_count <= 0:
        return "absent"
    if report_count < 50:
        return "rare"
    if report_count < 300:
        return "uncommon"
    return "common"
```

- [ ] **Step 4: Run to verify the helper passes**

Run: `poetry run pytest services/backend/tests/test_ebird_client.py::TestAbundanceBucket -v`
Expected: PASS.

- [ ] **Step 5: Write the failing tests for `get_species_frequency`**

Add to `test_ebird_client.py`:

```python
class TestGetSpeciesFrequency:
    async def test_success_buckets(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = [{"speciesCode": "norcar"}] * 125  # 125 reports
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.get_species_frequency("US-NY", "norcar", days=14)

        assert result["species_code"] == "norcar"
        assert result["report_count"] == 125
        assert result["abundance"] == "uncommon"
        assert result["capped"] is False

    async def test_capped_when_at_or_above_cap(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = [{"speciesCode": "norcar"}] * 400
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.get_species_frequency("US-NY", "norcar")

        assert result["abundance"] == "common"
        assert result["capped"] is True

    async def test_empty_code_returns_unknown(self):
        ebird = eBirdClient()
        result = await ebird.get_species_frequency("US-NY", "")
        assert result["abundance"] == "unknown"

    async def test_error_returns_unknown(self):
        ebird = eBirdClient()
        ebird._client.get = AsyncMock(side_effect=Exception("boom"))
        result = await ebird.get_species_frequency("US-NY", "norcar")
        assert result["abundance"] == "unknown"
        assert result["report_count"] == 0
```

- [ ] **Step 6: Run to verify they fail**

Run: `poetry run pytest services/backend/tests/test_ebird_client.py::TestGetSpeciesFrequency -v`
Expected: FAIL — `get_species_frequency` not defined.

- [ ] **Step 7: Implement `get_species_frequency`**

Add as a method on `eBirdClient` (after `get_regional_birds`):

```python
    async def get_species_frequency(
        self, region: str, species_code: str, days: int = 14
    ) -> dict[str, Any]:
        """
        How commonly a species has been reported in a region recently.

        Counts recent reports (capped) and buckets them. Returns an
        ``abundance`` of "unknown" on any error or empty code — never raises.
        """
        fallback: dict[str, Any] = {
            "region": region,
            "species_code": species_code,
            "days_searched": days,
            "report_count": 0,
            "capped": False,
            "abundance": "unknown",
        }
        if not species_code:
            return fallback

        start_time = time.time()
        try:
            url = f"{EBIRD_API_BASE}/data/obs/{region}/recent/{species_code}"
            headers = {"X-eBirdApiToken": settings.ebird_token}
            params = {"back": days, "maxResults": FREQUENCY_FETCH_CAP}

            resp = await self._client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()

            count = len(data)
            result = {
                "region": region,
                "species_code": species_code,
                "days_searched": days,
                "report_count": count,
                "capped": count >= FREQUENCY_FETCH_CAP,
                "abundance": _abundance_bucket(count),
            }
            logger.info(
                "eBird species frequency fetched",
                extra={
                    "operation": "get_species_frequency",
                    "region": region,
                    "species_code": species_code,
                    "abundance": result["abundance"],
                    "latency_ms": round((time.time() - start_time) * 1000, 2),
                    "status": "success",
                },
            )
            return result
        except Exception as e:
            logger.warning(
                f"eBird species frequency failed: {e}",
                extra={
                    "operation": "get_species_frequency",
                    "region": region,
                    "species_code": species_code,
                    "latency_ms": round((time.time() - start_time) * 1000, 2),
                    "status": "error",
                    "error_type": type(e).__name__,
                },
            )
            return fallback
```

- [ ] **Step 8: Run to verify they pass**

Run: `poetry run pytest services/backend/tests/test_ebird_client.py::TestGetSpeciesFrequency -v`
Expected: PASS (4 tests).

- [ ] **Step 9: Commit**

```bash
git add services/backend/app/helpers/ebird_client.py services/backend/tests/test_ebird_client.py
git commit -m "feat: add bucketed get_species_frequency to eBird client"
```

---

### Task 3: Regional rarities — `get_regional_rarities`

**Files:**
- Modify: `services/backend/app/helpers/ebird_client.py`
- Test: `services/backend/tests/test_ebird_client.py` (add `TestGetRegionalRarities`)

- [ ] **Step 1: Write the failing tests**

```python
class TestGetRegionalRarities:
    async def test_success_dedupes(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"speciesCode": "purgal2", "comName": "Purple Gallinule", "sciName": "Porphyrio martinica",
             "locName": "Central Park", "obsDt": "2026-05-30 08:00"},
            {"speciesCode": "purgal2", "comName": "Purple Gallinule", "sciName": "Porphyrio martinica",
             "locName": "Prospect Park", "obsDt": "2026-05-29 07:00"},
        ]
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.get_regional_rarities("US-NY", days=14)

        assert result["region"] == "US-NY"
        assert len(result["rarities"]) == 1  # deduped by species
        assert result["rarities"][0]["common_name"] == "Purple Gallinule"
        assert result["rarities"][0]["species_code"] == "purgal2"

    async def test_error_returns_empty(self):
        ebird = eBirdClient()
        ebird._client.get = AsyncMock(side_effect=Exception("boom"))
        result = await ebird.get_regional_rarities("US-NY")
        assert result["rarities"] == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `poetry run pytest services/backend/tests/test_ebird_client.py::TestGetRegionalRarities -v`
Expected: FAIL — method not defined.

- [ ] **Step 3: Implement `get_regional_rarities`**

```python
    async def get_regional_rarities(
        self, region: str, days: int = 14, max_results: int = 15
    ) -> dict[str, Any]:
        """
        Notable/rare species reported in a region recently (vagrant radar).

        Returns an empty ``rarities`` list on any error — never raises.
        """
        fallback: dict[str, Any] = {"region": region, "days_searched": days, "rarities": []}
        start_time = time.time()
        try:
            url = f"{EBIRD_API_BASE}/data/obs/{region}/recent/notable"
            headers = {"X-eBirdApiToken": settings.ebird_token}
            params = {"back": days, "maxResults": max_results, "detail": "simple"}

            resp = await self._client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()

            seen: dict[str, dict[str, Any]] = {}
            for obs in data:
                code = obs.get("speciesCode", "")
                if code and code not in seen:
                    seen[code] = {
                        "common_name": obs.get("comName", "Unknown"),
                        "scientific_name": obs.get("sciName", ""),
                        "species_code": code,
                        "location": obs.get("locName", ""),
                        "observed_on": obs.get("obsDt", ""),
                    }

            logger.info(
                "eBird rarities fetched",
                extra={
                    "operation": "get_regional_rarities",
                    "region": region,
                    "rarity_count": len(seen),
                    "latency_ms": round((time.time() - start_time) * 1000, 2),
                    "status": "success",
                },
            )
            return {"region": region, "days_searched": days, "rarities": list(seen.values())}
        except Exception as e:
            logger.warning(
                f"eBird rarities failed: {e}",
                extra={
                    "operation": "get_regional_rarities",
                    "region": region,
                    "latency_ms": round((time.time() - start_time) * 1000, 2),
                    "status": "error",
                    "error_type": type(e).__name__,
                },
            )
            return fallback
```

- [ ] **Step 4: Run to verify they pass**

Run: `poetry run pytest services/backend/tests/test_ebird_client.py::TestGetRegionalRarities -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/helpers/ebird_client.py services/backend/tests/test_ebird_client.py
git commit -m "feat: add get_regional_rarities (notable species) to eBird client"
```

---

### Task 4: Taxonomy/family lookup with in-process cache — `lookup_family`

**Files:**
- Modify: `services/backend/app/helpers/ebird_client.py` (`__init__` + method)
- Test: `services/backend/tests/test_ebird_client.py` (add `TestLookupFamily`)

- [ ] **Step 1: Write the failing tests**

```python
class TestLookupFamily:
    async def test_success(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"comName": "Northern Cardinal", "sciName": "Cardinalis cardinalis",
             "familyComName": "Cardinals and Allies", "order": "Passeriformes"}
        ]
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.lookup_family("norcar")

        assert result["family"] == "Cardinals and Allies"
        assert result["order"] == "Passeriformes"
        assert result["common_name"] == "Northern Cardinal"

    async def test_caches_second_call(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"comName": "Blue Jay", "sciName": "Cyanocitta cristata",
             "familyComName": "Crows, Jays, and Magpies", "order": "Passeriformes"}
        ]
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        await ebird.lookup_family("blujay")
        await ebird.lookup_family("blujay")

        ebird._client.get.assert_called_once()  # second call served from cache

    async def test_empty_code_returns_none(self):
        ebird = eBirdClient()
        assert await ebird.lookup_family("") is None

    async def test_error_returns_none(self):
        ebird = eBirdClient()
        ebird._client.get = AsyncMock(side_effect=Exception("boom"))
        assert await ebird.lookup_family("norcar") is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `poetry run pytest services/backend/tests/test_ebird_client.py::TestLookupFamily -v`
Expected: FAIL — method not defined.

- [ ] **Step 3: Add the cache to `__init__` and implement `lookup_family`**

In `__init__` (`ebird_client.py:25-27`), add after `self._client = ...`:

```python
        self._family_cache: dict[str, dict[str, Any]] = {}
```

Then add the method:

```python
    async def lookup_family(self, species_code: str) -> Optional[dict[str, Any]]:
        """
        Family + order for a species code (for family-level reasoning and
        "duck-like → grebes/coots" broadening). Cached in-process. Returns
        None on empty code or any error.
        """
        if not species_code:
            return None
        if species_code in self._family_cache:
            return self._family_cache[species_code]

        try:
            url = f"{EBIRD_API_BASE}/ref/taxonomy/ebird"
            headers = {"X-eBirdApiToken": settings.ebird_token}
            params: dict[str, str] = {"fmt": "json", "species": species_code}

            resp = await self._client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            if not data:
                return None

            item = data[0]
            info = {
                "species_code": species_code,
                "common_name": item.get("comName", ""),
                "scientific_name": item.get("sciName", ""),
                "family": item.get("familyComName", ""),
                "order": item.get("order", ""),
            }
            self._family_cache[species_code] = info
            return info
        except Exception as e:
            logger.warning(
                f"eBird taxonomy lookup failed: {e}",
                extra={
                    "operation": "lookup_family",
                    "species_code": species_code,
                    "status": "error",
                    "error_type": type(e).__name__,
                },
            )
            return None
```

- [ ] **Step 4: Run to verify they pass**

Run: `poetry run pytest services/backend/tests/test_ebird_client.py::TestLookupFamily -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/helpers/ebird_client.py services/backend/tests/test_ebird_client.py
git commit -m "feat: add cached lookup_family (taxonomy) to eBird client"
```

---

### Task 5: Historic-date observations — `get_historic_birds`

For season-anchoring to a past `observed_at`.

**Files:**
- Modify: `services/backend/app/helpers/ebird_client.py`
- Test: `services/backend/tests/test_ebird_client.py` (add `TestGetHistoricBirds`)

- [ ] **Step 1: Write the failing tests**

```python
class TestGetHistoricBirds:
    async def test_success_dedupes(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"comName": "Dark-eyed Junco", "sciName": "Junco hyemalis", "speciesCode": "daejun"},
            {"comName": "Dark-eyed Junco", "sciName": "Junco hyemalis", "speciesCode": "daejun"},
        ]
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.get_historic_birds("US-NY", 2026, 1, 15)

        assert result["region"] == "US-NY"
        assert result["date"] == "2026-01-15"
        assert len(result["species_observed"]) == 1
        assert result["species_observed"][0]["species_code"] == "daejun"

    async def test_error_returns_empty(self):
        ebird = eBirdClient()
        ebird._client.get = AsyncMock(side_effect=Exception("boom"))
        result = await ebird.get_historic_birds("US-NY", 2026, 1, 15)
        assert result["species_observed"] == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `poetry run pytest services/backend/tests/test_ebird_client.py::TestGetHistoricBirds -v`
Expected: FAIL — method not defined.

- [ ] **Step 3: Implement `get_historic_birds`**

```python
    async def get_historic_birds(
        self, region: str, year: int, month: int, day: int, max_results: int = 200
    ) -> dict[str, Any]:
        """
        Species reported in a region on a specific past date (season anchor).

        Returns an empty ``species_observed`` list on any error — never raises.
        """
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        fallback: dict[str, Any] = {
            "region": region,
            "date": date_str,
            "species_observed": [],
        }
        start_time = time.time()
        try:
            url = f"{EBIRD_API_BASE}/data/obs/{region}/historic/{year}/{month}/{day}"
            headers = {"X-eBirdApiToken": settings.ebird_token}
            params = {"maxResults": max_results}

            resp = await self._client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()

            species_map: dict[str, dict[str, Any]] = {}
            for obs in data:
                code = obs.get("speciesCode", "")
                key = code or obs.get("comName", "Unknown")
                if key not in species_map:
                    species_map[key] = {
                        "common_name": obs.get("comName", "Unknown"),
                        "scientific_name": obs.get("sciName", ""),
                        "species_code": code,
                    }

            logger.info(
                "eBird historic observations fetched",
                extra={
                    "operation": "get_historic_birds",
                    "region": region,
                    "date": date_str,
                    "species_count": len(species_map),
                    "latency_ms": round((time.time() - start_time) * 1000, 2),
                    "status": "success",
                },
            )
            return {
                "region": region,
                "date": date_str,
                "species_observed": list(species_map.values()),
            }
        except Exception as e:
            logger.warning(
                f"eBird historic observations failed: {e}",
                extra={
                    "operation": "get_historic_birds",
                    "region": region,
                    "date": date_str,
                    "latency_ms": round((time.time() - start_time) * 1000, 2),
                    "status": "error",
                    "error_type": type(e).__name__,
                },
            )
            return fallback
```

- [ ] **Step 4: Run to verify they pass**

Run: `poetry run pytest services/backend/tests/test_ebird_client.py::TestGetHistoricBirds -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/helpers/ebird_client.py services/backend/tests/test_ebird_client.py
git commit -m "feat: add get_historic_birds (date-anchored observations) to eBird client"
```

---

### Task 6: All-time species list — `get_region_species_list`

Plausibility backstop ("ever recorded here?").

**Files:**
- Modify: `services/backend/app/helpers/ebird_client.py`
- Test: `services/backend/tests/test_ebird_client.py` (add `TestGetRegionSpeciesList`)

- [ ] **Step 1: Write the failing tests**

```python
class TestGetRegionSpeciesList:
    async def test_success(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = ["norcar", "blujay", "amerob"]
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.get_region_species_list("US-NY")

        assert "norcar" in result
        assert len(result) == 3

    async def test_error_returns_empty(self):
        ebird = eBirdClient()
        ebird._client.get = AsyncMock(side_effect=Exception("boom"))
        result = await ebird.get_region_species_list("US-NY")
        assert result == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `poetry run pytest services/backend/tests/test_ebird_client.py::TestGetRegionSpeciesList -v`
Expected: FAIL — method not defined.

- [ ] **Step 3: Implement `get_region_species_list`**

```python
    async def get_region_species_list(self, region: str) -> list[str]:
        """
        All species codes ever recorded in a region (plausibility backstop).

        Returns an empty list on any error — never raises.
        """
        try:
            url = f"{EBIRD_API_BASE}/product/spplist/{region}"
            headers = {"X-eBirdApiToken": settings.ebird_token}
            resp = await self._client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(
                f"eBird species list failed: {e}",
                extra={
                    "operation": "get_region_species_list",
                    "region": region,
                    "status": "error",
                    "error_type": type(e).__name__,
                },
            )
            return []
```

- [ ] **Step 4: Run to verify they pass**

Run: `poetry run pytest services/backend/tests/test_ebird_client.py::TestGetRegionSpeciesList -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add services/backend/app/helpers/ebird_client.py services/backend/tests/test_ebird_client.py
git commit -m "feat: add get_region_species_list (spplist) to eBird client"
```

---

### Task 7: Region drill-down — `get_subregions` + `get_region_info`

For resolving a named place to a precise (county-level) region code.

**Files:**
- Modify: `services/backend/app/helpers/ebird_client.py`
- Test: `services/backend/tests/test_ebird_client.py` (add `TestRegionResolution`)

- [ ] **Step 1: Write the failing tests**

```python
class TestRegionResolution:
    async def test_get_subregions_success(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"code": "US-NY-047", "name": "Kings"},
            {"code": "US-NY-061", "name": "New York"},
        ]
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.get_subregions("US-NY")

        assert {"code": "US-NY-047", "name": "Kings"} in result

    async def test_get_subregions_error_returns_empty(self):
        ebird = eBirdClient()
        ebird._client.get = AsyncMock(side_effect=Exception("boom"))
        assert await ebird.get_subregions("US-NY") == []

    async def test_get_region_info_success(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": "US-NY-047", "result": "Kings, New York, US"}
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.get_region_info("US-NY-047")

        assert result["code"] == "US-NY-047"

    async def test_get_region_info_error_returns_none(self):
        ebird = eBirdClient()
        ebird._client.get = AsyncMock(side_effect=Exception("boom"))
        assert await ebird.get_region_info("US-NY-047") is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `poetry run pytest services/backend/tests/test_ebird_client.py::TestRegionResolution -v`
Expected: FAIL — methods not defined.

- [ ] **Step 3: Implement both methods**

```python
    async def get_subregions(
        self, parent_region: str, region_type: str = "subnational2"
    ) -> list[dict[str, str]]:
        """
        Sub-regions of a parent (e.g. counties of a US state) as {code, name}.

        Returns an empty list on any error — never raises.
        """
        try:
            url = f"{EBIRD_API_BASE}/ref/region/list/{region_type}/{parent_region}"
            headers = {"X-eBirdApiToken": settings.ebird_token}
            resp = await self._client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(
                f"eBird subregion list failed: {e}",
                extra={
                    "operation": "get_subregions",
                    "region": parent_region,
                    "status": "error",
                    "error_type": type(e).__name__,
                },
            )
            return []

    async def get_region_info(self, region: str) -> Optional[dict[str, Any]]:
        """
        Metadata (name, bounds, parent) for a region code.

        Returns None on any error — never raises.
        """
        try:
            url = f"{EBIRD_API_BASE}/ref/region/info/{region}"
            headers = {"X-eBirdApiToken": settings.ebird_token}
            resp = await self._client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(
                f"eBird region info failed: {e}",
                extra={
                    "operation": "get_region_info",
                    "region": region,
                    "status": "error",
                    "error_type": type(e).__name__,
                },
            )
            return None
```

- [ ] **Step 4: Run to verify they pass**

Run: `poetry run pytest services/backend/tests/test_ebird_client.py::TestRegionResolution -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the full eBird suite + lint/type checks**

Run:
```bash
poetry run pytest services/backend/tests/test_ebird_client.py -v
poetry run ruff check services/backend/app/helpers/ebird_client.py
poetry run black --check services/backend/app/helpers/ebird_client.py
poetry run mypy services/backend/app/helpers/ebird_client.py --ignore-missing-imports
```
Expected: all pass. (If black reports formatting, run `poetry run black services/backend/app/helpers/ebird_client.py services/backend/tests/test_ebird_client.py` and re-commit.)

- [ ] **Step 6: Commit**

```bash
git add services/backend/app/helpers/ebird_client.py services/backend/tests/test_ebird_client.py
git commit -m "feat: add region drill-down (subregions + region info) to eBird client"
```

---

## Self-Review

**Spec coverage (against §7 of the design spec):**
- `get_regional_birds` reframed (drop phantom count) → Task 1 ✅
- `get_species_frequency` bucketed abundance → Task 2 ✅
- `get_regional_rarities` (notable) → Task 3 ✅
- `lookup_family` (taxonomy, cached) → Task 4 ✅
- Historic/season-anchor endpoint → Task 5 ✅
- `spplist` plausibility backstop → Task 6 ✅
- Region drill (`region/list` + `region/info`) → Task 7 ✅
- Geo lat/lng → intentionally **out of scope** (spec §3 future enhancement) ✅
- Images (`get_species_image`) → unchanged, already exists ✅

**Placeholder scan:** No TBD/TODO; every code step has complete, runnable code and exact commands. ✅

**Type consistency:** `_abundance_bucket` returns the same band strings used in `get_species_frequency`. New methods reuse existing `EBIRD_API_BASE`, `settings.ebird_token`, `self._client`, `logger`, and the `Any`/`Optional` imports already present (`ebird_client.py:9`). `_family_cache` is initialized in `__init__` (Task 4 Step 3) before use. Return-shape keys (`species_observed`, `abundance`, `rarities`, `report_count`, `capped`) are consistent across tasks and match what Plan 2 will consume. ✅

**Note for Plan 2:** which of these become agent-facing tools (`get_species_frequency`, `get_regional_rarities`, `lookup_family`) vs. internal-only (`get_historic_birds`, `get_region_species_list`, region drill) is decided in Plan 2, along with raising `MAX_DATA_TOOL_CALLS` from 8 to ~12.
