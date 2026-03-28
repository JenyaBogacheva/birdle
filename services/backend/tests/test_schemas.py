from services.backend.app.schemas.observation import CandidateUpdate


def test_candidate_update_considering():
    c = CandidateUpdate(
        name="Common Kingfisher",
        species_code="comkin1",
        status="considering",
    )
    assert c.name == "Common Kingfisher"
    assert c.species_code == "comkin1"
    assert c.status == "considering"
    assert c.reason is None


def test_candidate_update_eliminated_with_reason():
    c = CandidateUpdate(
        name="Blue Jay",
        species_code="blujay",
        status="eliminated",
        reason="Too large",
    )
    assert c.status == "eliminated"
    assert c.reason == "Too large"


def test_candidate_update_invalid_status():
    import pytest
    with pytest.raises(Exception):
        CandidateUpdate(
            name="Test",
            species_code="test1",
            status="invalid",
        )
