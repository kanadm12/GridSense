"""Eligibility rules for fixed non-task scheduling baselines."""

from dataclasses import dataclass

from app.schemas.scheduling import (
    BaselineEligibilityStatus,
    BaselineSource,
    FixedBaselineProfileV1,
)


@dataclass(frozen=True)
class BaselineEligibility:
    """Eligibility outcome used before any numeric schedule evaluation."""

    status: BaselineEligibilityStatus
    source: BaselineSource
    eligible_for_costed_preview: bool
    explanation: str


def assess_scheduling_baseline(profile: FixedBaselineProfileV1) -> BaselineEligibility:
    """Reject measured profiles until server-verifiable separation evidence exists."""
    if profile.source == BaselineSource.SYNTHETIC:
        return BaselineEligibility(
            status=BaselineEligibilityStatus.ELIGIBLE_SYNTHETIC,
            source=profile.source,
            eligible_for_costed_preview=True,
            explanation=(
                "Synthetic non-task baseline is eligible for an illustrative scenario only; "
                "it is not measured household demand."
            ),
        )

    return BaselineEligibility(
        status=BaselineEligibilityStatus.UNAVAILABLE,
        source=profile.source,
        eligible_for_costed_preview=False,
        explanation=(
            "The supplied measurement method is a user declaration, not verified evidence. "
            "No server-validated separate submeter or synchronized disaggregation evidence "
            "is available for this meter, so a measured costed schedule is unavailable."
        ),
    )
