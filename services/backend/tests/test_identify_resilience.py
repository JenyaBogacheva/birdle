"""Tests for identify endpoint resilience (graph-runner-backed)."""

import asyncio
from unittest.mock import patch

ROUTE = "services.backend.app.routes.identify"


async def _aevents(items):
    for it in items:
        yield it


class TestTimeout:
    def test_agent_timeout(self, client):
        async def slow_stream(**kwargs):
            await asyncio.sleep(120)
            yield  # pragma: no cover

        import services.backend.app.routes.identify as route_mod

        original_timeout = route_mod.IDENTIFY_TIMEOUT
        route_mod.IDENTIFY_TIMEOUT = 0.5
        try:
            with patch(f"{ROUTE}.bird_runner") as runner:
                runner.run_stream = slow_stream
                response = client.post(
                    "/api/identify",
                    json={"description": "some bird", "location": "London"},
                )
            assert response.status_code == 504
        finally:
            route_mod.IDENTIFY_TIMEOUT = original_timeout

    def test_agent_returns_no_match(self, client):
        result = {
            "message": "I wasn't able to identify the bird.",
            "top_species": None,
            "alternate_species": [],
            "clarification": "Please provide more details.",
        }
        with patch(f"{ROUTE}.bird_runner") as runner:
            runner.run_stream = lambda **kw: _aevents([{"type": "result", "data": result}])
            response = client.post(
                "/api/identify",
                json={"description": "bird", "location": "London"},
            )
        assert response.status_code == 200
        assert response.json()["top_species"] is None
