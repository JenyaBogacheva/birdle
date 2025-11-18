"""
Pydantic schemas for bird observation data.
"""
from typing import Optional
from pydantic import BaseModel, Field


class ObservationInput(BaseModel):
    """User's bird observation input."""

    description: str = Field(..., min_length=1, description="Description of the observed bird")
    location: Optional[str] = Field(None, description="Location where bird was observed")
    observed_at: Optional[str] = Field(None, description="When the bird was observed")


class SpeciesInfo(BaseModel):
    """Information about a bird species."""

    scientific_name: str
    common_name: str
    range_link: str


class RecommendationResponse(BaseModel):
    """Response containing bird identification recommendation."""

    message: str = Field(..., description="Summary message about the identification")
    top_species: Optional[SpeciesInfo] = Field(
        None, description="Top matching species information"
    )
    clarification: Optional[str] = Field(
        None, description="Follow-up question if more info needed"
    )

