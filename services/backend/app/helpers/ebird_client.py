"""
Direct eBird API client replacing the MCP server+client layer.

Uses httpx.AsyncClient for eBird observations; species photos come from the
public Wikimedia REST API (Macaulay's API was retired / is auth-gated).
"""

import base64
import logging
import re
import time
from typing import Any, Optional
from urllib.parse import quote

import httpx

from ..settings import settings

logger = logging.getLogger(__name__)

EBIRD_API_BASE = "https://api.ebird.org/v2"
# Wikimedia REST page-summary endpoint — returns a lead image per page title.
WIKIPEDIA_SUMMARY_BASE = "https://en.wikipedia.org/api/rest_v1/page/summary"
# Wikimedia asks all clients to send a descriptive User-Agent.
WIKIPEDIA_UA = "BirdleAI/1.0 (bird identification; https://github.com/birdle-ai)"
TIMEOUT = 10.0

FREQUENCY_FETCH_CAP = 400  # cap rows fetched per species; ">=cap" reads as "common"

# Target width for species photos. The page-summary API hands back a ~320px
# lead thumbnail, which looks pixelated stretched across a card banner / poster.
IMAGE_TARGET_WIDTH = 1280


def _upscale_wikimedia_thumb(url: str, target_width: int = IMAGE_TARGET_WIDTH) -> str:
    """Bump a Wikimedia thumbnail URL to a larger on-demand render.

    Commons thumb URLs end in ``/<width>px-<file>``; Wikimedia renders any
    requested width on demand, so raising it yields a much sharper image than
    the ~320px lead thumbnail the page-summary API returns by default. URLs that
    don't match the thumb pattern (e.g. a full original) are returned unchanged.
    """
    m = re.search(r"/(\d+)px-([^/]+)$", url)
    if not m or int(m.group(1)) >= target_width:
        return url
    return f"{url[: m.start(1)]}{target_width}{url[m.end(1) :]}"


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
        # Photo lookups repeat across turns (same-species follow-ups, recurring
        # alternates); cache by normalized query. ``None`` is cached too, to
        # avoid re-hitting Wikimedia for a title that has no image.
        self._image_cache: dict[str, Optional[dict[str, str]]] = {}
        self._subnat1_cache: dict[str, list[dict[str, str]]] = {}

    async def close(self) -> None:
        """Close the shared HTTP client."""
        await self._client.aclose()

    async def get_regional_birds(
        self, region: str = "US", days: int = 14, max_results: int = 200
    ) -> dict[str, Any]:
        """
        Fetch recent bird observations for a region from eBird.

        Returns empty fallback on any error — never raises.
        """
        start_time = time.time()
        fallback: dict[str, Any] = {
            "region": region,
            "days_searched": days,
            "total_species": 0,
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

            all_species = list(species_map.values())
            result = {
                "region": region,
                "days_searched": days,
                # True distinct-species count; species_observed is capped below.
                "total_species": len(all_species),
                "species_observed": all_species[:max_results],
            }
            latency_ms = (time.time() - start_time) * 1000
            logger.info(
                "eBird regional observations fetched",
                extra={
                    "operation": "get_regional_birds",
                    "region": region,
                    "species_count": len(all_species),
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
            "common_name": "",
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
                # eBird's observation rows carry the common name; surface it so
                # the UI/agent can name the species instead of the bare code.
                "common_name": data[0].get("comName", "") if data else "",
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
            params: dict[str, str | int] = {
                "back": days,
                "maxResults": max_results,
                "detail": "simple",
            }

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
            data: dict[str, Any] = resp.json()
            return data
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

    async def get_subnational1_list(self, country_code: str) -> list[dict[str, str]]:
        """eBird's authoritative subnational1 (state/province) list for a country.

        Returns ``[{"code", "name"}]`` (empty on any error). Cached per country.
        """
        cc = (country_code or "").upper()
        if not cc:
            return []
        if cc in self._subnat1_cache:
            return list(self._subnat1_cache[cc])
        try:
            url = f"{EBIRD_API_BASE}/ref/region/list/subnational1/{cc}"
            resp = await self._client.get(url, headers={"X-eBirdApiToken": settings.ebird_token})
            resp.raise_for_status()
            out = [{"code": r.get("code", ""), "name": r.get("name", "")} for r in resp.json()]
            self._subnat1_cache[cc] = out
            return list(out)
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
            "region": "geo",
            "days_searched": days,
            "total_species": 0,
            "species_observed": [],
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
                extra={
                    "operation": "get_nearby_birds",
                    "dist_km": dist,
                    "species_count": len(species),
                    "latency_ms": round((time.time() - start_time) * 1000, 2),
                    "status": "success",
                },
            )
            return {
                "region": "geo",
                "days_searched": days,
                "total_species": len(species),
                "species_observed": species,
            }
        except Exception as e:
            logger.warning(
                f"eBird nearby observations failed: {e}",
                extra={
                    "operation": "get_nearby_birds",
                    "status": "error",
                    "error_type": type(e).__name__,
                },
            )
            return fallback

    async def get_species_image(self, query: str) -> Optional[dict[str, str]]:
        """
        Fetch a species lead photo from the public Wikimedia REST API.

        ``query`` should be a page title — the scientific name is most reliable
        (e.g. "Anastomus oscitans"); a common name also works. Wikimedia follows
        redirects to the canonical species page. Returns ``{image_url,
        photographer}`` or None on any error / missing image — image is optional.
        """
        if not query or not query.strip():
            return None

        cache_key = query.strip().lower()
        if cache_key in self._image_cache:
            return self._image_cache[cache_key]

        start_time = time.time()

        try:
            title = quote(query.strip().replace(" ", "_"), safe="")
            resp = await self._client.get(
                f"{WIKIPEDIA_SUMMARY_BASE}/{title}",
                headers={"User-Agent": WIKIPEDIA_UA, "Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

            # The page-summary thumbnail is a small (~320px) cached render that
            # looks pixelated stretched across the card banner. Get a sharper
            # image without risking a 400: Wikimedia refuses to render a raster
            # thumb WIDER than its source, so only upscale when the source file
            # is genuinely larger than our target; otherwise the original file
            # itself is the sharpest render that's guaranteed valid.
            orig = data.get("originalimage") or {}
            orig_src, orig_w = orig.get("source"), orig.get("width")
            thumb = (data.get("thumbnail") or {}).get("source")
            image_url: Optional[str]
            if thumb and isinstance(orig_w, int) and orig_w > IMAGE_TARGET_WIDTH:
                image_url = _upscale_wikimedia_thumb(thumb)
            else:
                image_url = orig_src or thumb
            if not image_url:
                logger.info(
                    "No image found for species",
                    extra={
                        "operation": "get_species_image",
                        "query": query,
                        "status": "not_found",
                    },
                )
                self._image_cache[cache_key] = None
                return None

            latency_ms = (time.time() - start_time) * 1000
            logger.info(
                "Species image fetched",
                extra={
                    "operation": "get_species_image",
                    "query": query,
                    "latency_ms": round(latency_ms, 2),
                    "status": "success",
                },
            )
            result = {"image_url": image_url, "photographer": "Wikimedia Commons"}
            self._image_cache[cache_key] = result
            return result

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.warning(
                f"Species image fetch failed: {e}",
                extra={
                    "operation": "get_species_image",
                    "query": query,
                    "latency_ms": round(latency_ms, 2),
                    "status": "error",
                    "error_type": type(e).__name__,
                },
            )
            return None

    async def fetch_image_b64(self, url: str) -> Optional[tuple[str, str]]:
        """Download an image and return ``(base64_data, media_type)``, or None.

        Anthropic's server-side URL image fetcher is refused by Wikimedia's
        hotlink / User-Agent policy, so for vision calls we download the bytes
        ourselves (sending the descriptive UA Wikimedia asks for) and inline them
        as base64. Returns None on any error or unsupported media type.
        """
        if not url:
            return None
        supported = {"image/jpeg", "image/png", "image/gif", "image/webp"}
        try:
            resp = await self._client.get(url, headers={"User-Agent": WIKIPEDIA_UA})
            resp.raise_for_status()
            media_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            if media_type not in supported:
                return None
            return base64.standard_b64encode(resp.content).decode("ascii"), media_type
        except Exception as e:
            logger.warning(
                f"Image byte fetch failed: {e}",
                extra={
                    "operation": "fetch_image_b64",
                    "status": "error",
                    "error_type": type(e).__name__,
                },
            )
            return None


# Module-level singleton
ebird_client = eBirdClient()
