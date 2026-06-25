import httpx
import pytest

import services.backend.app.helpers.geocoder as gmod
from services.backend.app.helpers.geocoder import (
    GeocoderClient,
    match_subnational1,
    normalize_region_name,
)


def _resp(status, payload):
    return httpx.Response(status, json=payload, request=httpx.Request("GET", "http://x"))


DALAT_SEARCH = [
    {
        "lat": "11.9082632",
        "lon": "108.4572089",
        "display_name": "Da Lat, Lam Dong, Vietnam",
        "addresstype": "historic",
        "address": {"state": "Tỉnh Lâm Đồng", "country_code": "vn"},
    }
]


@pytest.mark.asyncio
async def test_geocode_parses_specific_place(monkeypatch):
    c = GeocoderClient()

    async def fake_get(url, headers=None, params=None):
        return _resp(200, DALAT_SEARCH)

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
    payload = [
        {
            "lat": "16.0",
            "lon": "106.0",
            "display_name": "Vietnam",
            "addresstype": "country",
            "address": {"country_code": "vn"},
        }
    ]

    async def fake_get(url, headers=None, params=None):
        return _resp(200, payload)

    monkeypatch.setattr(c._client, "get", fake_get)
    r = await c.geocode("Vietnam")
    assert r.is_country is True and r.admin1_name is None


@pytest.mark.asyncio
async def test_geocode_empty_returns_none(monkeypatch):
    c = GeocoderClient()

    async def fake_get(url, headers=None, params=None):
        return _resp(200, [])

    monkeypatch.setattr(c._client, "get", fake_get)
    assert await c.geocode("zzzz") is None


@pytest.mark.asyncio
async def test_geocode_error_returns_none(monkeypatch):
    c = GeocoderClient()

    async def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(c._client, "get", boom)
    assert await c.geocode("anything") is None


@pytest.mark.asyncio
async def test_reverse_geocode_parses(monkeypatch):
    c = GeocoderClient()
    payload = {
        "lat": "11.9",
        "lon": "108.4",
        "display_name": "Da Lat",
        "addresstype": "suburb",
        "address": {"state": "Tỉnh Lâm Đồng", "country_code": "vn"},
    }

    async def fake_get(url, headers=None, params=None):
        assert "/reverse" in url
        return _resp(200, payload)

    monkeypatch.setattr(c._client, "get", fake_get)
    r = await c.reverse_geocode(11.9, 108.4)
    assert r.admin1_name == "Tỉnh Lâm Đồng" and r.country_code == "VN"


# ---------------------------------------------------------------------------
# normalize_region_name + match_subnational1
# ---------------------------------------------------------------------------

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


def test_normalize_handles_non_decomposing_latin():
    assert normalize_region_name("Đồng") == "dong"  # U+0111
    assert normalize_region_name("Diyarbakır") == "diyarbakir"  # U+0131 dotless i
    assert normalize_region_name("Trøndelag") == "trondelag"  # U+00F8


# ---------------------------------------------------------------------------
# resolve_region
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_region_text_namematches_subnational1(monkeypatch):
    async def fake_geocode(text):
        return gmod.GeoResult(11.9, 108.4, "VN", "Tỉnh Lâm Đồng", "Da Lat, VN", False)

    async def fake_list(cc):
        return [{"code": "VN-68", "name": "Lam Dong"}]

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

    async def fake_list(cc):
        return [{"code": "VN-68", "name": "Lam Dong"}]

    monkeypatch.setattr(gmod.geocoder, "geocode", fake_geocode)
    monkeypatch.setattr(gmod.ebird_client, "get_subnational1_list", fake_list)
    out = await gmod.resolve_region(text="someplace, vietnam")
    assert out["region_code"] == "VN"  # country fallback
    assert out["precision"] == "point"  # still a specific point -> radius


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

    async def fake_list(cc):
        return [{"code": "VN-68", "name": "Lam Dong"}]

    monkeypatch.setattr(gmod.geocoder, "reverse_geocode", fake_reverse)
    monkeypatch.setattr(gmod.ebird_client, "get_subnational1_list", fake_list)
    out = await gmod.resolve_region(text="ignored", lat=11.9, lng=108.4)
    assert called["reverse"] and out["region_code"] == "VN-68" and out["precision"] == "point"


@pytest.mark.asyncio
async def test_resolve_region_geocode_none(monkeypatch):
    async def fake_geocode(text):
        return None

    monkeypatch.setattr(gmod.geocoder, "geocode", fake_geocode)
    out = await gmod.resolve_region(text="zzz")
    assert out == {
        "region_code": None,
        "lat": None,
        "lng": None,
        "precision": "none",
        "display_name": None,
    }
