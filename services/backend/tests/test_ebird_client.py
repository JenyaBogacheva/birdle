"""Tests for the eBird client."""

from unittest.mock import AsyncMock, MagicMock

from services.backend.app.helpers.ebird_client import _abundance_bucket, eBirdClient


class TestGetRegionalBirds:
    async def test_success_dedupes_without_count(self):
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
    async def test_success_uses_thumbnail_verbatim(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "title": "Northern cardinal",
            "thumbnail": {"source": "https://upload.wikimedia.org/a/b/file.jpg/330px-file.jpg"},
        }
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.get_species_image("Cardinalis cardinalis")

        # The thumbnail URL is used as-is (Wikimedia only serves fixed widths).
        assert result["image_url"] == "https://upload.wikimedia.org/a/b/file.jpg/330px-file.jpg"
        assert result["photographer"] == "Wikimedia Commons"

    async def test_falls_back_to_originalimage(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "originalimage": {"source": "https://upload.wikimedia.org/a/b/full.jpg"},
        }
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.get_species_image("Ardea cinerea")

        assert result["image_url"] == "https://upload.wikimedia.org/a/b/full.jpg"

    async def test_no_image(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = {"title": "Some page", "extract": "no image"}
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.get_species_image("Nonexistent species")

        assert result is None

    async def test_empty_query(self):
        ebird = eBirdClient()
        assert await ebird.get_species_image("") is None
        assert await ebird.get_species_image("   ") is None

    async def test_error_returns_none(self):
        ebird = eBirdClient()
        ebird._client.get = AsyncMock(side_effect=Exception("network error"))

        result = await ebird.get_species_image("Cardinalis cardinalis")

        assert result is None


class TestGetRegionalRarities:
    async def test_success_dedupes(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "speciesCode": "purgal2",
                "comName": "Purple Gallinule",
                "sciName": "Porphyrio martinica",
                "locName": "Central Park",
                "obsDt": "2026-05-30 08:00",
            },
            {
                "speciesCode": "purgal2",
                "comName": "Purple Gallinule",
                "sciName": "Porphyrio martinica",
                "locName": "Prospect Park",
                "obsDt": "2026-05-29 07:00",
            },
        ]
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.get_regional_rarities("US-NY", days=14)

        assert result["region"] == "US-NY"
        assert len(result["rarities"]) == 1  # deduped by species
        assert result["rarities"][0]["common_name"] == "Purple Gallinule"
        assert result["rarities"][0]["species_code"] == "purgal2"

    async def test_error_returns_empty(self):
        ebird = eBirdClient()
        ebird._client.get = AsyncMock(side_effect=Exception("boom"))
        result = await ebird.get_regional_rarities("US-NY")
        assert result["rarities"] == []


class TestLookupFamily:
    async def test_success(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "comName": "Northern Cardinal",
                "sciName": "Cardinalis cardinalis",
                "familyComName": "Cardinals and Allies",
                "order": "Passeriformes",
            }
        ]
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.lookup_family("norcar")

        assert result["family"] == "Cardinals and Allies"
        assert result["order"] == "Passeriformes"
        assert result["common_name"] == "Northern Cardinal"

    async def test_caches_second_call(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "comName": "Blue Jay",
                "sciName": "Cyanocitta cristata",
                "familyComName": "Crows, Jays, and Magpies",
                "order": "Passeriformes",
            }
        ]
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        await ebird.lookup_family("blujay")
        await ebird.lookup_family("blujay")

        ebird._client.get.assert_called_once()  # second call served from cache

    async def test_empty_code_returns_none(self):
        ebird = eBirdClient()
        assert await ebird.lookup_family("") is None

    async def test_error_returns_none(self):
        ebird = eBirdClient()
        ebird._client.get = AsyncMock(side_effect=Exception("boom"))
        assert await ebird.lookup_family("norcar") is None


class TestGetHistoricBirds:
    async def test_success_dedupes(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"comName": "Dark-eyed Junco", "sciName": "Junco hyemalis", "speciesCode": "daejun"},
            {"comName": "Dark-eyed Junco", "sciName": "Junco hyemalis", "speciesCode": "daejun"},
        ]
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.get_historic_birds("US-NY", 2026, 1, 15)

        assert result["region"] == "US-NY"
        assert result["date"] == "2026-01-15"
        assert len(result["species_observed"]) == 1
        assert result["species_observed"][0]["species_code"] == "daejun"

    async def test_error_returns_empty(self):
        ebird = eBirdClient()
        ebird._client.get = AsyncMock(side_effect=Exception("boom"))
        result = await ebird.get_historic_birds("US-NY", 2026, 1, 15)
        assert result["species_observed"] == []


class TestGetRegionSpeciesList:
    async def test_success(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = ["norcar", "blujay", "amerob"]
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.get_region_species_list("US-NY")

        assert "norcar" in result
        assert len(result) == 3

    async def test_error_returns_empty(self):
        ebird = eBirdClient()
        ebird._client.get = AsyncMock(side_effect=Exception("boom"))
        result = await ebird.get_region_species_list("US-NY")
        assert result == []


class TestRegionResolution:
    async def test_get_subregions_success(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"code": "US-NY-047", "name": "Kings"},
            {"code": "US-NY-061", "name": "New York"},
        ]
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.get_subregions("US-NY")

        assert {"code": "US-NY-047", "name": "Kings"} in result

    async def test_get_subregions_error_returns_empty(self):
        ebird = eBirdClient()
        ebird._client.get = AsyncMock(side_effect=Exception("boom"))
        assert await ebird.get_subregions("US-NY") == []

    async def test_get_region_info_success(self):
        ebird = eBirdClient()
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": "US-NY-047", "result": "Kings, New York, US"}
        mock_response.raise_for_status = MagicMock()
        ebird._client.get = AsyncMock(return_value=mock_response)

        result = await ebird.get_region_info("US-NY-047")

        assert result["code"] == "US-NY-047"

    async def test_get_region_info_error_returns_none(self):
        ebird = eBirdClient()
        ebird._client.get = AsyncMock(side_effect=Exception("boom"))
        assert await ebird.get_region_info("US-NY-047") is None
