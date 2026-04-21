"""Recommendation schemas."""

from enum import Enum

from pydantic import BaseModel


class RecommendationPriority(str, Enum):
    """Priority level for recommendations."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RecommendationCategory(str, Enum):
    """Category of recommendation."""

    LOAD_SHIFTING = "load_shifting"
    STANDBY_REDUCTION = "standby_reduction"
    SOLAR_OPTIMIZATION = "solar_optimization"
    TARIFF_OPTIMIZATION = "tariff_optimization"
    GENERAL = "general"


class Recommendation(BaseModel):
    """A single energy recommendation."""

    id: str
    title: str
    description: str
    category: RecommendationCategory
    priority: RecommendationPriority
    potential_savings_kwh: float | None = None
    potential_savings_dollars: float | None = None
    action: str  # What the user should do
    reason: str  # Why this recommendation was made


class RecommendationsResponse(BaseModel):
    """Response containing all recommendations for a user."""

    recommendations: list[Recommendation]
    total_potential_savings: float | None = None
