"""Route-level tests for the graph-backed identify endpoints."""

import json
from unittest.mock import AsyncMock, patch

ROUTE = "services.backend.app.routes.identify"


async def _aevents(items):
    for it in items:
        yield it


def _parse_sse(text: str) -> list[dict]:
    return [
        json.loads(line[len("data: ") :]) for line in text.splitlines() if line.startswith("data: ")
    ]


class TestHealthEndpoint:
    def test_health_check(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_root_endpoint(self, client):
        resp = client.get("/")
        assert resp.status_code == 200


class TestIdentifyEndpoint:
    def test_identify_success(self, client):
        result = {
            "message": "It's a Northern Cardinal!",
            "top_species": {
                "scientific_name": "Cardinalis cardinalis",
                "common_name": "Northern Cardinal",
                "species_code": "norcar",
                "confidence": "high",
                "reasoning": "red + crest",
            },
            "alternate_species": [],
            "clarification": None,
        }
        with patch(f"{ROUTE}.bird_runner") as runner, patch(f"{ROUTE}.ebird_client") as eb:
            runner.run_stream = lambda **kw: _aevents([{"type": "result", "data": result}])
            eb.get_species_image = AsyncMock(
                return_value={"image_url": "http://img/c.jpg", "photographer": "JD"}
            )
            resp = client.post(
                "/api/identify", json={"description": "red crested bird", "location": "NY"}
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["top_species"]["common_name"] == "Northern Cardinal"
        assert data["top_species"]["image_url"] == "http://img/c.jpg"
        # With a species code we link to the eBird species page (range map).
        assert data["top_species"]["range_link"] == "https://ebird.org/species/norcar"

    def test_identify_no_match(self, client):
        result = {
            "message": "Not sure",
            "top_species": None,
            "alternate_species": [],
            "clarification": "More detail?",
        }
        with patch(f"{ROUTE}.bird_runner") as runner:
            runner.run_stream = lambda **kw: _aevents([{"type": "result", "data": result}])
            resp = client.post("/api/identify", json={"description": "a bird", "location": "NY"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["top_species"] is None
        assert data["clarification"] == "More detail?"

    def test_identify_missing_description(self, client):
        resp = client.post("/api/identify", json={"location": "NY"})
        assert resp.status_code == 422

    def test_identify_location_is_now_optional(self, client):
        # location is optional since Task 5 (lat/lng can substitute); omitting
        # it is no longer a 422 — the request reaches the graph.
        with patch(f"{ROUTE}.bird_runner") as runner:
            runner.run_stream = lambda **kw: _aevents(
                [
                    {
                        "type": "result",
                        "data": {"message": "ok", "top_species": None, "alternate_species": []},
                    }
                ]
            )
            resp = client.post("/api/identify", json={"description": "red bird"})
        assert resp.status_code == 200

    def test_identify_awaiting_degrades_to_clarification(self, client):
        with patch(f"{ROUTE}.bird_runner") as runner:
            runner.run_stream = lambda **kw: _aevents(
                [{"type": "awaiting_input", "reason": "disambiguate_species", "question": "Crest?"}]
            )
            resp = client.post("/api/identify", json={"description": "bird", "location": "NY"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["top_species"] is None
        assert data["clarification"] == "Crest?"


class TestStreamEndpoint:
    def test_stream_emits_session_and_result_with_images(self, client):
        result = {
            "message": "It's a cardinal",
            "top_species": {
                "scientific_name": "Cardinalis cardinalis",
                "common_name": "Northern Cardinal",
                "species_code": "norcar",
                "confidence": "high",
                "reasoning": "r",
            },
            "alternate_species": [],
            "clarification": None,
        }
        scripted = [
            {"type": "session_id", "session_id": "s1"},
            {"type": "detective_note", "message": "Red and crested..."},
            {"type": "result", "data": result},
        ]
        with patch(f"{ROUTE}.bird_runner") as runner, patch(f"{ROUTE}.ebird_client") as eb:
            runner.run_stream = lambda **kw: _aevents(scripted)
            eb.get_species_image = AsyncMock(
                return_value={"image_url": "http://img/c.jpg", "photographer": "JD"}
            )
            resp = client.post(
                "/api/identify/stream", json={"description": "red bird", "location": "NY"}
            )
        events = _parse_sse(resp.text)
        types = [e["type"] for e in events]
        assert "session_id" in types
        assert "detective_note" in types
        assert "result" in types
        assert types[-1] == "done"
        result_event = next(e for e in events if e["type"] == "result")
        assert result_event["data"]["top_species"]["image_url"] == "http://img/c.jpg"

    def test_stream_resolves_candidate_images(self, client):
        scripted = [
            {
                "type": "candidates",
                "data": [
                    {
                        "name": "Common Kingfisher",
                        "species_code": "comkin1",
                        "status": "considering",
                    }
                ],
            },
            {
                "type": "result",
                "data": {"message": "done", "top_species": None, "alternate_species": []},
            },
        ]
        with patch(f"{ROUTE}.bird_runner") as runner, patch(f"{ROUTE}.ebird_client") as eb:
            runner.run_stream = lambda **kw: _aevents(scripted)
            eb.get_species_image = AsyncMock(
                return_value={"image_url": "http://img/k.jpg", "photographer": "AB"}
            )
            resp = client.post(
                "/api/identify/stream", json={"description": "blue bird", "location": "NY"}
            )
        events = _parse_sse(resp.text)
        cand = next(e for e in events if e["type"] == "candidates")
        assert cand["data"][0]["image_url"] == "http://img/k.jpg"

    def test_stream_passes_through_awaiting_input(self, client):
        scripted = [
            {"type": "session_id", "session_id": "s1"},
            {"type": "awaiting_input", "reason": "disambiguate_species", "question": "Crest?"},
        ]
        with patch(f"{ROUTE}.bird_runner") as runner:
            runner.run_stream = lambda **kw: _aevents(scripted)
            resp = client.post(
                "/api/identify/stream", json={"description": "red bird", "location": "NY"}
            )
        events = _parse_sse(resp.text)
        types = [e["type"] for e in events]
        assert "awaiting_input" in types
        assert types[-1] == "done"

    def test_stream_error_yields_error_and_done(self, client):
        async def boom(**kw):
            raise Exception("kaboom")
            yield  # pragma: no cover

        with patch(f"{ROUTE}.bird_runner") as runner:
            runner.run_stream = boom
            resp = client.post(
                "/api/identify/stream", json={"description": "red bird", "location": "NY"}
            )
        events = _parse_sse(resp.text)
        types = [e["type"] for e in events]
        assert "error" in types
        assert types[-1] == "done"

    def test_stream_missing_description(self, client):
        resp = client.post("/api/identify/stream", json={"location": "NY"})
        assert resp.status_code == 422


class TestObservationInputSchema:
    def test_observation_input_accepts_coordinates_without_location(self):
        from services.backend.app.schemas.observation import ObservationInput

        obs = ObservationInput(description="small brown bird", lat=11.9, lng=108.4)
        assert obs.lat == 11.9 and obs.lng == 108.4 and (obs.location or "") == ""

    def test_observation_input_still_accepts_text_location(self):
        from services.backend.app.schemas.observation import ObservationInput

        obs = ObservationInput(description="x", location="Dalat")
        assert obs.location == "Dalat" and obs.lat is None


class TestResumeEndpoint:
    def test_resume_streams_events(self, client):
        scripted = [
            {"type": "session_id", "session_id": "s1"},
            {
                "type": "result",
                "data": {
                    "message": "It's a cardinal",
                    "top_species": None,
                    "alternate_species": [],
                },
            },
        ]
        with patch(f"{ROUTE}.bird_runner") as runner:
            runner.resume_stream = lambda **kw: _aevents(scripted)
            resp = client.post(
                "/api/identify/resume", json={"session_id": "s1", "user_message": "it had a crest"}
            )
        events = _parse_sse(resp.text)
        types = [e["type"] for e in events]
        assert "result" in types
        assert types[-1] == "done"

    def test_resume_requires_fields(self, client):
        resp = client.post("/api/identify/resume", json={"session_id": "s1"})
        assert resp.status_code == 422
