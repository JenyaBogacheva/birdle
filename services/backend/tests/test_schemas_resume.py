import pytest
from pydantic import ValidationError

from services.backend.app.schemas.observation import ResumeInput


def test_resume_input_valid():
    r = ResumeInput(session_id="abc123", user_message="It had a crest")
    assert r.session_id == "abc123"
    assert r.user_message == "It had a crest"


def test_resume_input_requires_fields():
    with pytest.raises(ValidationError):
        ResumeInput(session_id="abc123")  # missing user_message
