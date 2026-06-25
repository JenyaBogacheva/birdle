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
    country_code: str  # uppercased ISO alpha-2 ("VN")
    admin1_name: Optional[str]  # e.g. "Tỉnh Lâm Đồng", or None
    display_name: str
    is_country: bool  # True when the match itself is a whole country


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
                params={"lat": lat, "lon": lng, "format": "jsonv2", "addressdetails": 1, "zoom": 8},
            )
            resp.raise_for_status()
            result = _parse(resp.json())
        except Exception as e:
            logger.warning(
                f"Reverse geocode failed: {e}",
                extra={
                    "operation": "reverse_geocode",
                    "status": "error",
                    "error_type": type(e).__name__,
                },
            )
        self._rev_cache[key] = result
        return result


geocoder = GeocoderClient()
