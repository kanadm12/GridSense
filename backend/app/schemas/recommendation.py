"""Recommendation schemas."""

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


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
    """Compatibility status for whether an opportunity can be quantified."""

    UNQUANTIFIED = "unquantified"
    CONDITIONAL_ESTIMATE = "conditional_estimate"


class RecommendationStatus(str, Enum):
    """Evidence-derived lifecycle status for a recommendation."""

    VALIDATED = "validated"
    ESTIMATED = "estimated"
    ILLUSTRATIVE = "illustrative"
    UNQUANTIFIED = "unquantified"
    UNAVAILABLE = "unavailable"
    EXPIRED = "expired"
    NO_SUPPORTED_ACTION = "no_supported_action"


class EvidenceCoverage(BaseModel):
    expected_intervals: int = 0
    eligible_intervals: int = 0
    missing_intervals: int = 0
    excluded_quality_intervals: int = 0
    unresolved_direction_intervals: int = 0
    legacy_direction_unverified_intervals: int = 0
    unresolved_time_basis_intervals: int = 0
    duplicate_intervals: int = 0
    invalid_intervals: int = 0
    coverage_fraction: float = Field(default=0, ge=0, le=1)
    coverage_status: str = "unavailable"
    provenance_status: str = "unavailable"


class CalculationEvidence(BaseModel):
    """Compact, reproducible provenance for a recommendation response."""

    schema_version: Literal["1.0"] = "1.0"
    recommendation_id: str
    rule_id: str
    rule_version: str
    owner_user_id: int
    meter_id: int
    created_at: datetime
    expires_at: datetime
    status: RecommendationStatus
    analysis_start_date: date | None = None
    analysis_end_date: date | None = None
    input_references: list[str] = Field(default_factory=list)
    input_record_count: int = 0
    input_digest_sha256: str | None = None
    provenance_counts: dict[str, int] = Field(default_factory=dict)
    coverage: EvidenceCoverage
    eligibility_checks: dict[str, str] = Field(default_factory=dict)
    tariff_revision_id: int | None = None
    baseline_scenario: str
    proposed_scenario: str
    calculation_method_version: str
    calculated_values: dict[str, float] = Field(default_factory=dict)
    value_units: dict[str, str] = Field(default_factory=dict)
    energy_difference_kwh: float | None = None
    financial_difference_aud: float | None = None
    rounding_rule: str
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)


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
    status: RecommendationStatus = RecommendationStatus.UNQUANTIFIED
    calculation_evidence: CalculationEvidence | None = None


class RecommendationsResponse(BaseModel):
    """Response containing all recommendations for a user."""

    recommendations: list[Recommendation]
    total_potential_savings: float | None = None
    tariff_status: RecommendationTariffStatus = RecommendationTariffStatus.MISSING
