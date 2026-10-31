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


class RecommendationEstimateStatus(str, Enum):
    """Whether an opportunity is supported by enough inputs to quantify."""

    UNQUANTIFIED = "unquantified"
    CONDITIONAL_ESTIMATE = "conditional_estimate"


class RecommendationConfidence(str, Enum):
    """Confidence in the interpretation, not a probability of savings."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecommendationTariffStatus(str, Enum):
    """Availability and provenance of the meter owner's configured tariff."""

    MISSING = "missing"
    ILLUSTRATIVE = "illustrative"
    OUTSIDE_EFFECTIVE_DATES = "outside_effective_dates"
    MISSING_RATES = "missing_rates"
    CONFIGURED = "configured"


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
    observed_fact: str
    proposed_action: str
    conditional_opportunity: str
    estimate_status: RecommendationEstimateStatus
    baseline: str
    assumptions: list[str]
    rate_difference_cents_kwh: float | None = None
    applicable_intervals: str
    uncertainty: str
    confidence: RecommendationConfidence
    data_requirements: list[str]


class RecommendationsResponse(BaseModel):
    """Response containing all recommendations for a user."""

    recommendations: list[Recommendation]
    total_potential_savings: float | None = None
    tariff_status: RecommendationTariffStatus = RecommendationTariffStatus.MISSING
