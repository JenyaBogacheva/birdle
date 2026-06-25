"""OpenStreetMap Nominatim geocoder (forward + reverse) for region resolution.

Returns a GeoResult or None on any error — never raises. Results are cached
in-process (Nominatim asks heavy users to cache + self-host); a descriptive
User-Agent is required by their usage policy.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from .ebird_client import ebird_client

logger = logging.getLogger(__name__)

# Admin-area words dropped before matching (lowercased, diacritic-free forms).
_ADMIN_WORDS = {
    "tinh",
    "thanh",
    "pho",
    "province",
    "provincia",
    "de",
    "del",
    "state",
    "city",
    "region",
    "prefecture",
    "district",
    "county",
    "oblast",
    "krai",
    "department",
    "governorate",
    "do",
    "si",
}


# Latin letters NFKD does not decompose — map to ASCII bases for matching.
_TRANSLIT = str.maketrans(
    {
        "Đ": "D",
        "đ": "d",
        "Ð": "D",
        "ð": "d",
        "Ł": "L",
        "ł": "l",
        "Ŀ": "L",
        "ŀ": "l",
        "Ø": "O",
        "ø": "o",
        "İ": "I",
        "ı": "i",
        "Ħ": "H",
        "ħ": "h",
        "Ŧ": "T",
        "ŧ": "t",
        "Þ": "Th",
        "þ": "th",
        "Æ": "Ae",
        "æ": "ae",
        "Œ": "Oe",
        "œ": "oe",
    }
)


def normalize_region_name(name: str) -> str:
    """Lowercase, strip diacritics, drop admin words, collapse whitespace."""
    transliterated = (name or "").translate(_TRANSLIT)
    decomposed = unicodedata.normalize("NFKD", transliterated)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    ascii_only = re.sub(r"[^a-zA-Z\s]", " ", ascii_only).lower()
    tokens = [t for t in ascii_only.split() if t and t not in _ADMIN_WORDS]
    return " ".join(tokens)


def match_subnational1(admin1_name: str, region_list: list[dict[str, str]]) -> Optional[str]:
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


NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
NOMINATIM_UA = "BirdleAI/1.0 (bird identification; https://github.com/birdle-ai)"
TIMEOUT = 10.0


# Address keys, most-specific first, for a concise human-readable place label.
_LOCALITY_KEYS = ("city", "town", "village", "municipality", "suburb", "county")

# Leading admin-type words to drop from a region name for display (longest first),
# so "Tỉnh Lâm Đồng" reads as "Lâm Đồng". Case/diacritics of the rest are kept.
_DISPLAY_ADMIN_PREFIXES = (
    "thành phố",
    "province of",
    "state of",
    "provincia de",
    "provincia di",
    "tỉnh",
    "province",
    "provincia",
    "state",
    "region",
    "prefecture",
    "governorate",
    "oblast",
    "okrug",
    "krai",
)


def _clean_admin_for_display(name: str) -> str:
    low = name.lower()
    for p in _DISPLAY_ADMIN_PREFIXES:
        if low.startswith(p + " "):
            return name[len(p) :].strip()
    return name


@dataclass(frozen=True)
class GeoResult:
    lat: float
    lng: float
    country_code: str  # uppercased ISO alpha-2 ("VN")
    admin1_name: Optional[str]  # e.g. "Tỉnh Lâm Đồng", or None
    display_name: str
    is_country: bool  # True when the match itself is a whole country
    locality: Optional[str] = None  # city/town/area, when known

    @property
    def short_label(self) -> str:
        """A concise place name to show in a location field (e.g. "Đà Lạt, Lâm Đồng")."""
        admin = _clean_admin_for_display(self.admin1_name) if self.admin1_name else None
        if self.locality and admin and self.locality != admin:
            return f"{self.locality}, {admin}"
        return (
            self.locality
            or admin
            or (self.display_name.split(",")[0].strip() if self.display_name else "")
        )


def _parse(obj: dict[str, Any]) -> Optional[GeoResult]:
    try:
        addr = obj.get("address") or {}
        cc = (addr.get("country_code") or "").upper()
        if not cc:
            return None
        locality = next((addr[k] for k in _LOCALITY_KEYS if addr.get(k)), None)
        return GeoResult(
            lat=float(obj["lat"]),
            lng=float(obj["lon"]),
            country_code=cc,
            admin1_name=addr.get("state") or addr.get("province") or None,
            display_name=obj.get("display_name", ""),
            is_country=(obj.get("addresstype") == "country"),
            locality=locality,
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
    none_result = {
        "region_code": None,
        "lat": None,
        "lng": None,
        "precision": "none",
        "display_name": None,
    }

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
