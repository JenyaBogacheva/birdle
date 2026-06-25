import pytest

from services.backend.app.graph import tools
from services.backend.app.helpers.ebird_client import ebird_client


@pytest.mark.asyncio
async def test_get_regional_birds_uses_geo_when_point(monkeypatch):
    async def fake_nearby(lat, lng, dist=50, days=14):
        return {
            "region": "geo",
            "days_searched": days,
            "total_species": 2,
            "species_observed": [
                {"common_name": "X", "scientific_name": "Xx", "species_code": "x"}
            ],
        }

    async def fake_region(*a, **k):
        raise AssertionError("region path should not run")

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
