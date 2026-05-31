"""Tests for the eBird client."""

from unittest.mock import AsyncMock, MagicMock

from services.backend.app.helpers.ebird_client import eBirdClient, _abundance_bucket


class TestGetRegionalBirds:
    async def test_success_dedupes_without_count(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"comName": "Northern Cardinal", "sciName": "Cardinalis cardinalis", "speciesCode": "norcar"},
            {"comName": "Northern Cardinal", "sciName": "Cardinalis cardinalis", "speciesCode": "norcar"},
            {"comName": "Blue Jay", "sciName": "Cyanocitta cristata", "speciesCode": "blujay"},
        ]
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.get_regional_birds("US-NY", days=14)

        assert result["region"] == "US-NY"
        assert len(result["species_observed"]) == 2  # deduped
        first = result["species_observed"][0]
        assert first["common_name"] == "Northern Cardinal"
        assert first["species_code"] == "norcar"
        assert "observation_count" not in first  # phantom count removed

    async def test_api_error_returns_fallback(self):
        ebird = eBirdClient()
        ebird._client.get = AsyncMock(side_effect=Exception("API down"))

        result = await ebird.get_regional_birds("US-NY")

        assert result["species_observed"] == []
        assert "total_observations" not in result


class TestAbundanceBucket:
    def test_absent(self):
        assert _abundance_bucket(0) == "absent"

    def test_rare(self):
        assert _abundance_bucket(12) == "rare"
        assert _abundance_bucket(49) == "rare"

    def test_uncommon(self):
        assert _abundance_bucket(50) == "uncommon"
        assert _abundance_bucket(299) == "uncommon"

    def test_common(self):
        assert _abundance_bucket(300) == "common"
        assert _abundance_bucket(400) == "common"


class TestGetSpeciesFrequency:
    async def test_success_buckets(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = [{"speciesCode": "norcar"}] * 125  # 125 reports
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.get_species_frequency("US-NY", "norcar", days=14)

        assert result["species_code"] == "norcar"
        assert result["report_count"] == 125
        assert result["abundance"] == "uncommon"
        assert result["capped"] is False

    async def test_capped_when_at_or_above_cap(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = [{"speciesCode": "norcar"}] * 400
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.get_species_frequency("US-NY", "norcar")

        assert result["abundance"] == "common"
        assert result["capped"] is True

    async def test_empty_code_returns_unknown(self):
        ebird = eBirdClient()
        result = await ebird.get_species_frequency("US-NY", "")
        assert result["abundance"] == "unknown"

    async def test_error_returns_unknown(self):
        ebird = eBirdClient()
        ebird._client.get = AsyncMock(side_effect=Exception("boom"))
        result = await ebird.get_species_frequency("US-NY", "norcar")
        assert result["abundance"] == "unknown"
        assert result["report_count"] == 0


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
