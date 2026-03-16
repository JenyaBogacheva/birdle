"""Tests for the identify endpoint."""


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
