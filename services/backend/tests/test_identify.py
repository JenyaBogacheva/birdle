"""
Tests for bird identification endpoint.
"""

from fastapi.testclient import TestClient

from services.backend.app.main import app

client = TestClient(app)


def test_health_endpoint():
    """Test that health endpoint returns ok status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data
    assert data["app_name"] == "Bird-ID MVP"


def test_identify_endpoint_returns_stubbed_response():
    """Test that identify endpoint returns stubbed Northern Cardinal response."""
    payload = {
        "description": "Small red bird with black mask and crest",
        "location": "New York, NY",
        "observed_at": "Today morning",
    }
    response = client.post("/api/identify", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "message" in data
    assert "top_species" in data
    assert data["top_species"]["common_name"] == "Northern Cardinal"
    assert data["top_species"]["scientific_name"] == "Cardinalis cardinalis"
    assert data["clarification"] is None


def test_identify_endpoint_requires_description():
    """Test that identify endpoint requires description field."""
    payload = {}
    response = client.post("/api/identify", json=payload)
    assert response.status_code == 422  # Validation error


def test_identify_endpoint_accepts_minimal_payload():
    """Test that identify endpoint requires location."""
    payload = {"description": "A bird"}
    response = client.post("/api/identify", json=payload)
    # Location is now required, should return 400
    assert response.status_code == 400
    assert "Location is required" in response.json()["detail"]
