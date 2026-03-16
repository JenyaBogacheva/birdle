"""Tests for identify endpoint resilience."""

import asyncio


class TestTimeout:
    def test_agent_timeout(self, client, mock_bird_agent):
        async def slow_identify(**kwargs):
            await asyncio.sleep(120)

        mock_bird_agent.side_effect = slow_identify

        # Reduce the timeout so the test finishes quickly
        import services.backend.app.routes.identify as route_mod

        original_timeout = route_mod.IDENTIFY_TIMEOUT
        route_mod.IDENTIFY_TIMEOUT = 0.5
        try:
            response = client.post(
                "/api/identify",
                json={"description": "some bird", "location": "London"},
            )
            assert response.status_code == 504
        finally:
            route_mod.IDENTIFY_TIMEOUT = original_timeout

    def test_agent_returns_fallback_on_error(self, client, mock_bird_agent):
        mock_bird_agent.return_value = {
            "message": "I wasn't able to identify the bird.",
            "top_species": None,
            "alternate_species": [],
            "clarification": "Please provide more details.",
        }
        response = client.post(
            "/api/identify",
            json={"description": "bird", "location": "London"},
        )
        assert response.status_code == 200
        assert response.json()["top_species"] is None
