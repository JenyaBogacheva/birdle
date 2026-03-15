"""Tests for the eBird client."""

from unittest.mock import AsyncMock, MagicMock

from services.backend.app.helpers.ebird_client import eBirdClient


class TestGetRegionalBirds:
    async def test_success(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "comName": "Northern Cardinal",
                "sciName": "Cardinalis cardinalis",
                "speciesCode": "norcar",
            },
            {
                "comName": "Northern Cardinal",
                "sciName": "Cardinalis cardinalis",
                "speciesCode": "norcar",
            },
            {
                "comName": "Blue Jay",
                "sciName": "Cyanocitta cristata",
                "speciesCode": "blujay",
            },
        ]
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.get_regional_birds("US-NY", days=14)

        assert result["region"] == "US-NY"
        assert len(result["species_observed"]) == 2
        assert result["species_observed"][0]["common_name"] == "Northern Cardinal"
        assert result["species_observed"][0]["observation_count"] == 2

    async def test_api_error_returns_fallback(self):
        ebird = eBirdClient()
        ebird._client.get = AsyncMock(side_effect=Exception("API down"))

        result = await ebird.get_regional_birds("US-NY")

        assert result["species_observed"] == []
        assert result["total_observations"] == 0


class TestGetSpeciesImage:
    async def test_success(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": {
                "content": [
                    {
                        "previewUrl": "https://img.example.com/bird.jpg",
                        "userDisplayName": "Jane Doe",
                    }
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.get_species_image("norcar")

        assert result["image_url"] == "https://img.example.com/bird.jpg"
        assert result["photographer"] == "Jane Doe"

    async def test_no_results(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": {"content": []}}
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.get_species_image("norcar")

        assert result is None

    async def test_empty_code(self):
        ebird = eBirdClient()
        result = await ebird.get_species_image("")
        assert result is None

    async def test_error_returns_none(self):
        ebird = eBirdClient()
        ebird._client.get = AsyncMock(side_effect=Exception("network error"))

        result = await ebird.get_species_image("norcar")

        assert result is None
