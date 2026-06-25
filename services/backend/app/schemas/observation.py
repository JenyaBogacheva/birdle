"""
Pydantic schemas for bird observation data.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ObservationInput(BaseModel):
    """User's bird observation input."""

    description: str = Field(..., min_length=1, description="Description of the observed bird")
    location: Optional[str] = Field(
        "", description="Location where bird was observed (optional if coordinates given)"
    )
    observed_at: Optional[str] = Field(None, description="When the bird was observed")
    lat: Optional[float] = Field(None, description="Latitude from the 'use my location' button")
    lng: Optional[float] = Field(None, description="Longitude from the 'use my location' button")


class ReverseGeocodeResponse(BaseModel):
    """A concise place label for a coordinate (for the 'use my location' field)."""

    label: str = Field("", description="Short human-readable place name, or '' if unknown")


class ResumeInput(BaseModel):
    """Turn 2+ payload: resume a paused identification session with a reply."""

    session_id: str = Field(..., min_length=1, description="Session id from turn 1")
    user_message: str = Field(
        ..., min_length=1, description="The user's answer to the pending question"
    )


class ImageFocus(BaseModel):
    """Hero-photo focal point as a CSS background-position percentage (0–100)."""

    x: int = Field(..., ge=0, le=100, description="Horizontal focal point (0=left, 100=right)")
    y: int = Field(..., ge=0, le=100, description="Vertical focal point (0=top, 100=bottom)")


class SpeciesInfo(BaseModel):
    """Information about a bird species."""

    scientific_name: str
    common_name: str
    species_code: Optional[str] = Field(None, description="eBird species code, when known")
    range_link: str
    confidence: Optional[str] = Field(None, description="Confidence level: high, medium, or low")
    reasoning: Optional[str] = Field(None, description="Reasoning for the identification")
    image_url: Optional[str] = Field(None, description="URL to species image from Wikimedia")
    image_credit: Optional[str] = Field(None, description="Photographer credit")
    image_focus: Optional[ImageFocus] = Field(
        None, description="Hero-photo focal point; None falls back to a static crop position"
    )


class CandidateStatus(str, Enum):
    considering = "considering"
    eliminated = "eliminated"


class CandidateUpdate(BaseModel):
    name: str
    species_code: str
    status: CandidateStatus
    reason: Optional[str] = None


class RecommendationResponse(BaseModel):
    """Response containing bird identification recommendation."""

    message: str = Field(..., description="Summary message about the identification")
    top_species: Optional[SpeciesInfo] = Field(None, description="Top matching species information")
    alternate_species: list[SpeciesInfo] = Field(
        default_factory=list, description="Alternative possible species (up to 2)"
    )
    clarification: Optional[str] = Field(None, description="Follow-up question if more info needed")
