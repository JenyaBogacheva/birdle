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


class eBirdClient:  # noqa: N801 - eBird is a proper brand name
    """Direct eBird API client with graceful error handling."""

    def __init__(self) -> None:
        self._timeout = httpx.Timeout(TIMEOUT)
        self._client = httpx.AsyncClient(timeout=self._timeout)

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
