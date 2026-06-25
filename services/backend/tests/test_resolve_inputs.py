import pytest

from services.backend.app.graph import nodes


@pytest.mark.asyncio
async def test_resolve_inputs_uses_geocoder_not_llm(monkeypatch):
    async def fake_resolve(text=None, lat=None, lng=None):
        return {
            "region_code": "VN-68",
            "lat": 11.9,
            "lng": 108.4,
            "precision": "point",
            "display_name": "Da Lat, VN",
        }

    async def fake_date(observed_at):
        return "recent"

    monkeypatch.setattr(nodes, "resolve_region", fake_resolve)
    monkeypatch.setattr(nodes, "_parse_date", fake_date)
    out = await nodes.resolve_inputs(
        {"location": "Dalat, Vietnam", "observed_at": None, "ask_rounds": 0}
    )
    assert out["region"] == "VN-68"
    assert out["lat"] == 11.9 and out["lng"] == 108.4


@pytest.mark.asyncio
async def test_resolve_inputs_country_precision_drops_latlng(monkeypatch):
    async def fake_resolve(text=None, lat=None, lng=None):
        return {
            "region_code": "VN",
            "lat": None,
            "lng": None,
            "precision": "country",
            "display_name": "Vietnam",
        }

    async def fake_date(observed_at):
        return "recent"

    monkeypatch.setattr(nodes, "resolve_region", fake_resolve)
    monkeypatch.setattr(nodes, "_parse_date", fake_date)
    out = await nodes.resolve_inputs({"location": "Vietnam", "observed_at": None, "ask_rounds": 0})
    assert out["region"] == "VN" and out["lat"] is None and out["lng"] is None


@pytest.mark.asyncio
async def test_resolve_inputs_coordinates_take_precedence(monkeypatch):
    seen = {}

    async def fake_resolve(text=None, lat=None, lng=None):
        seen["lat"], seen["lng"] = lat, lng
        return {
            "region_code": "VN-68",
            "lat": lat,
            "lng": lng,
            "precision": "point",
            "display_name": "Da Lat",
        }

    async def fake_date(observed_at):
        return "recent"

    monkeypatch.setattr(nodes, "resolve_region", fake_resolve)
    monkeypatch.setattr(nodes, "_parse_date", fake_date)
    out = await nodes.resolve_inputs(
        {"location": "", "observed_at": None, "ask_rounds": 0, "lat": 11.9, "lng": 108.4}
    )
    assert seen == {"lat": 11.9, "lng": 108.4} and out["region"] == "VN-68"
