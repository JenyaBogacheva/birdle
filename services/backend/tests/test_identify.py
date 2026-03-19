"""Tests for the identify endpoint."""

import json
from unittest.mock import AsyncMock


class TestHealthEndpoint:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_root_endpoint(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"


class TestIdentifyEndpoint:
    def test_identify_success(self, client, mock_bird_agent, sample_agent_result):
        mock_bird_agent.return_value = sample_agent_result
        response = client.post(
            "/api/identify",
            json={"description": "bright red bird", "location": "New York"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"]
        assert data["top_species"]["common_name"] == "Northern Cardinal"
        mock_bird_agent.assert_called_once_with(
            description="bright red bird",
            location="New York",
            observed_at=None,
        )

    def test_identify_missing_description(self, client):
        response = client.post(
            "/api/identify",
            json={"location": "New York"},
        )
        assert response.status_code == 422

    def test_identify_missing_location(self, client):
        response = client.post(
            "/api/identify",
            json={"description": "red bird"},
        )
        assert response.status_code == 422  # location is now required

    def test_identify_with_observed_at(self, client, mock_bird_agent, sample_agent_result):
        mock_bird_agent.return_value = sample_agent_result
        response = client.post(
            "/api/identify",
            json={
                "description": "red bird",
                "location": "New York",
                "observed_at": "morning",
            },
        )
        assert response.status_code == 200
        mock_bird_agent.assert_called_once_with(
            description="red bird",
            location="New York",
            observed_at="morning",
        )

    def test_identify_agent_error(self, client, mock_bird_agent):
        mock_bird_agent.side_effect = Exception("Agent crashed")
        response = client.post(
            "/api/identify",
            json={"description": "red bird", "location": "New York"},
        )
        assert response.status_code == 500

    def test_identify_no_match(self, client, mock_bird_agent):
        mock_bird_agent.return_value = {
            "message": "I couldn't identify this bird.",
            "top_species": None,
            "alternate_species": [],
            "clarification": "Can you describe the size?",
        }
        response = client.post(
            "/api/identify",
            json={"description": "something flew by", "location": "London"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["top_species"] is None
        assert data["clarification"]

    def test_identify_multiple_alternates(self, client, mock_bird_agent, sample_agent_result):
        sample_agent_result["alternate_species"].append(
            {
                "scientific_name": "Piranga olivacea",
                "common_name": "Scarlet Tanager",
                "confidence": "low",
                "reasoning": "Possible but unlikely at feeders.",
            }
        )
        mock_bird_agent.return_value = sample_agent_result
        response = client.post(
            "/api/identify",
            json={"description": "red bird", "location": "New York"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["alternate_species"]) == 2

    def test_identify_range_link_generated(self, client, mock_bird_agent, sample_agent_result):
        mock_bird_agent.return_value = sample_agent_result
        response = client.post(
            "/api/identify",
            json={"description": "red bird", "location": "New York"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "ebird.org/explore" in data["top_species"]["range_link"]


class TestStreamEndpoint:
    def _parse_sse_events(self, response_text: str) -> list[dict]:
        """Parse SSE response text into event dicts."""
        events = []
        for part in response_text.split("\n\n"):
            line = part.strip()
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
        return events

    def test_stream_success(self, client, mock_bird_agent_stream):
        """Streaming endpoint returns SSE events ending with result and done."""

        async def fake_stream(**kwargs):
            yield {"type": "status", "message": "Checking your description..."}
            yield {"type": "status", "message": "Looking up birds..."}
            yield {
                "type": "result",
                "data": {
                    "message": "Found it!",
                    "top_species": None,
                    "alternate_species": [],
                    "clarification": None,
                },
            }

        mock_bird_agent_stream.side_effect = fake_stream

        response = client.post(
            "/api/identify/stream",
            json={"description": "red bird", "location": "New York"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

        events = self._parse_sse_events(response.text)
        types = [e["type"] for e in events]
        assert "status" in types
        assert "result" in types
        assert types[-1] == "done"
        result_event = next(e for e in events if e["type"] == "result")
        assert "message" in result_event["data"]

    def test_stream_result_has_images(self, client, mock_bird_agent_stream, monkeypatch):
        """Streaming result should include image data from _build_species_info."""

        async def fake_stream(**kwargs):
            yield {
                "type": "result",
                "data": {
                    "message": "Found it!",
                    "top_species": {
                        "common_name": "Cardinal",
                        "scientific_name": "Cardinalis cardinalis",
                        "species_code": "norcar",
                        "confidence": "high",
                        "reasoning": "test",
                    },
                    "alternate_species": [],
                    "clarification": None,
                },
            }

        mock_bird_agent_stream.side_effect = fake_stream

        mock_image = AsyncMock(
            return_value={
                "image_url": "https://example.com/img.jpg",
                "photographer": "Test",
            }
        )
        monkeypatch.setattr(
            "services.backend.app.routes.identify.ebird_client.get_species_image",
            mock_image,
        )

        response = client.post(
            "/api/identify/stream",
            json={"description": "red bird", "location": "New York"},
        )
        events = self._parse_sse_events(response.text)
        result_event = next(e for e in events if e["type"] == "result")
        assert result_event["data"]["top_species"]["image_url"] == "https://example.com/img.jpg"
        assert result_event["data"]["top_species"]["range_link"]

    def test_stream_missing_description(self, client):
        response = client.post(
            "/api/identify/stream",
            json={"location": "New York"},
        )
        assert response.status_code == 422

    def test_stream_missing_location(self, client):
        response = client.post(
            "/api/identify/stream",
            json={"description": "red bird"},
        )
        assert response.status_code == 422

    def test_stream_error_yields_error_and_done(self, client, mock_bird_agent_stream):
        """When the agent generator raises, the endpoint yields error + done."""

        async def failing_stream(**kwargs):
            yield {"type": "status", "message": "Starting..."}
            raise Exception("boom")

        mock_bird_agent_stream.side_effect = failing_stream

        response = client.post(
            "/api/identify/stream",
            json={"description": "red bird", "location": "New York"},
        )
        assert response.status_code == 200

        events = self._parse_sse_events(response.text)
        types = [e["type"] for e in events]
        assert "error" in types
        assert types[-1] == "done"
        error_event = next(e for e in events if e["type"] == "error")
        assert "unexpected error" in error_event["message"].lower()

    def test_stream_timeout(self, client, mock_bird_agent_stream):
        """When the stream exceeds the timeout, an error event is emitted."""
        import services.backend.app.routes.identify as route_mod

        async def slow_stream(**kwargs):
            yield {"type": "status", "message": "Starting..."}
            import asyncio

            await asyncio.sleep(5)
            yield {"type": "result", "data": {"message": "too late"}}

        mock_bird_agent_stream.side_effect = slow_stream

        original_timeout = route_mod.IDENTIFY_TIMEOUT
        route_mod.IDENTIFY_TIMEOUT = 0.1
        try:
            response = client.post(
                "/api/identify/stream",
                json={"description": "red bird", "location": "New York"},
            )
            events = self._parse_sse_events(response.text)
            types = [e["type"] for e in events]
            assert "error" in types
            assert types[-1] == "done"
        finally:
            route_mod.IDENTIFY_TIMEOUT = original_timeout
