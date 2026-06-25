import httpx
import pytest

from services.backend.app.helpers.geocoder import GeocoderClient


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
