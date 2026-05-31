"""
Direct eBird API client replacing the MCP server+client layer.

Uses httpx.AsyncClient for eBird observations and Macaulay Library image lookups.
"""

import logging
import time
from typing import Any, Optional

import httpx

from ..settings import settings

logger = logging.getLogger(__name__)

EBIRD_API_BASE = "https://api.ebird.org/v2"
MACAULAY_API_BASE = "https://search.macaulaylibrary.org/api/v1"
TIMEOUT = 10.0

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


class eBirdClient:  # noqa: N801 - eBird is a proper brand name
    """Direct eBird API client with graceful error handling."""

    def __init__(self) -> None:
        self._timeout = httpx.Timeout(TIMEOUT)
        self._client = httpx.AsyncClient(timeout=self._timeout)
        self._family_cache: dict[str, dict[str, Any]] = {}

    async def close(self) -> None:
        """Close the shared HTTP client."""
        await self._client.aclose()

    async def get_regional_birds(
        self, region: str = "US", days: int = 14, max_results: int = 50
    ) -> dict[str, Any]:
        """
        Fetch recent bird observations for a region from eBird.

        Returns empty fallback on any error — never raises.
        """
        start_time = time.time()
        fallback: dict[str, Any] = {
            "region": region,
            "days_searched": days,
            "species_observed": [],
        }

        try:
            url = f"{EBIRD_API_BASE}/data/obs/{region}/recent"
            headers = {"X-eBirdApiToken": settings.ebird_token}
            params = {"back": days}

            resp = await self._client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()

            # /recent can return multiple rows for the same species; dedupe to a
            # presence list. We do NOT count rows — counts here are not a reliable
            # frequency signal (use get_species_frequency for abundance).
            species_map: dict[str, dict[str, Any]] = {}
            for obs in data:
                code = obs.get("speciesCode", "")
                # eBird effectively always provides speciesCode; comName fallback
                # is purely defensive so dedupe never collapses distinct species.
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
            latency_ms = (time.time() - start_time) * 1000
            logger.info(
                "eBird regional observations fetched",
                extra={
                    "operation": "get_regional_birds",
                    "region": region,
                    "species_count": len(species),
                    "latency_ms": round(latency_ms, 2),
                    "status": "success",
                },
            )
            return result

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.warning(
                f"eBird regional observations failed: {e}",
                extra={
                    "operation": "get_regional_birds",
                    "region": region,
                    "latency_ms": round(latency_ms, 2),
                    "status": "error",
                    "error_type": type(e).__name__,
                },
            )
            return fallback

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

    async def get_species_image(self, species_code: str) -> Optional[dict[str, str]]:
        """
        Fetch the top-rated photo for a species from Macaulay Library.

        Returns None on any error — image is optional.
        """
        if not species_code:
            return None

        start_time = time.time()

        try:
            params: dict[str, str | int] = {
                "taxonCode": species_code,
                "mediaType": "photo",
                "sort": "rating_rank_desc",
                "count": 1,
            }

            resp = await self._client.get(f"{MACAULAY_API_BASE}/search", params=params)
            resp.raise_for_status()
            data = resp.json()

            results_content = data.get("results", {}).get("content", [])
            if not results_content:
                logger.info(
                    "No image found for species",
                    extra={
                        "operation": "get_species_image",
                        "species_code": species_code,
                        "status": "not_found",
                    },
                )
                return None

            item = results_content[0]
            latency_ms = (time.time() - start_time) * 1000
            logger.info(
                "Species image fetched",
                extra={
                    "operation": "get_species_image",
                    "species_code": species_code,
                    "latency_ms": round(latency_ms, 2),
                    "status": "success",
                },
            )
            return {
                "image_url": item.get("previewUrl", ""),
                "photographer": item.get("userDisplayName", "Unknown"),
            }

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.warning(
                f"Species image fetch failed: {e}",
                extra={
                    "operation": "get_species_image",
                    "species_code": species_code,
                    "latency_ms": round(latency_ms, 2),
                    "status": "error",
                    "error_type": type(e).__name__,
                },
            )
            return None


# Module-level singleton
ebird_client = eBirdClient()
