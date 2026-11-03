"""Versioned evidence snapshots for deterministic recommendation outputs."""

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from app.models.meter import Meter
from app.models.reading import Reading
from app.schemas.recommendation import (
    CalculationEvidence,
    EvidenceCoverage,
    Recommendation,
    RecommendationStatus,
)
from app.schemas.usage import UsageSummary

if TYPE_CHECKING:
    from app.services.recommendation_engine import UsagePattern


RULE_VERSION = "1.0"
EVIDENCE_TTL = timedelta(hours=1)


class CalculationEvidenceService:
    """Build compact evidence references without copying raw reading datasets."""

    @staticmethod
    def build_usage_evidence(
        *,
        meter: Meter,
        recommendation: Recommendation,
        readings: list[Reading],
        summary: UsageSummary | None,
        pattern: "UsagePattern | None",
        tariff_revision_id: int | None,
        analysis_start_date: date | None,
        analysis_end_date: date | None,
        now: datetime | None = None,
    ) -> CalculationEvidence:
        evaluated_at = now or datetime.now(timezone.utc)
        if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
            raise ValueError("Evidence evaluation time must be timezone-aware.")
        evaluated_at = evaluated_at.astimezone(timezone.utc)

        serialized_readings = [
            {
                "id": reading.id,
                "timestamp": reading.timestamp.isoformat(),
                "interval_minutes": reading.interval_minutes,
                "value": reading.value,
                "source_value": reading.source_value,
                "source_unit": reading.source_unit,
                "direction": reading.direction,
                "quality": reading.quality,
                "provenance_kind": reading.provenance_kind,
                "source_time_basis": reading.source_time_basis,
            }
            for reading in sorted(readings, key=lambda item: item.id or 0)
        ]
        digest = hashlib.sha256(
            json.dumps(
                serialized_readings,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()

        provenance_counts: dict[str, int] = {}
        for reading in readings:
            provenance = reading.provenance_kind or "unknown"
            provenance_counts[provenance] = provenance_counts.get(provenance, 0) + 1

        coverage = EvidenceCoverage(
            expected_intervals=summary.expected_interval_count if summary else 0,
            eligible_intervals=summary.eligible_interval_count if summary else 0,
            missing_intervals=summary.missing_interval_count if summary else 0,
            excluded_quality_intervals=summary.excluded_quality_count if summary else 0,
            unresolved_direction_intervals=(
                summary.unresolved_direction_count if summary else 0
            ),
            legacy_direction_unverified_intervals=(
                summary.legacy_direction_unverified_count if summary else 0
            ),
            unresolved_time_basis_intervals=(
                summary.unresolved_time_basis_count if summary else 0
            ),
            duplicate_intervals=summary.duplicate_interval_count if summary else 0,
            invalid_intervals=(
                summary.invalid_interval_count + summary.invalid_unit_count
                if summary
                else 0
            ),
            coverage_fraction=summary.coverage_fraction if summary else 0,
            coverage_status=summary.coverage_status if summary else "unavailable",
            provenance_status=summary.provenance_status if summary else "unavailable",
        )

        if summary is None or summary.eligible_interval_count == 0:
            status = RecommendationStatus.UNAVAILABLE
        elif (
            summary.coverage_status != "complete"
            or summary.coverage_fraction < 1
            or summary.unresolved_direction_count > 0
            or summary.legacy_direction_unverified_count > 0
            or summary.unresolved_time_basis_count > 0
        ):
            status = RecommendationStatus.UNQUANTIFIED
        elif recommendation.id == "no_supported_action":
            status = RecommendationStatus.NO_SUPPORTED_ACTION
        elif (
            summary.provenance_status in {"synthetic", "mixed"}
            or provenance_counts.get("synthetic", 0) > 0
        ):
            status = RecommendationStatus.ILLUSTRATIVE
        elif summary.provenance_status == "measured":
            status = RecommendationStatus.VALIDATED
        else:
            status = RecommendationStatus.UNAVAILABLE

        calculated_values: dict[str, float] = {}
        value_units: dict[str, str] = {}
        if pattern is not None and status in {
            RecommendationStatus.VALIDATED,
            RecommendationStatus.ILLUSTRATIVE,
        }:
            calculated_values = {
                "eligible_import_kwh": round(pattern.total_kwh, 3),
                "evening_import_share": round(pattern.evening_ratio, 6),
                "overnight_import_share": round(pattern.night_ratio, 6),
                "daytime_import_share": round(pattern.daytime_ratio, 6),
                "weekday_weekend_average_ratio": round(
                    pattern.weekend_vs_weekday, 6
                ),
            }
            value_units = {
                "eligible_import_kwh": "kWh",
                "evening_import_share": "fraction",
                "overnight_import_share": "fraction",
                "daytime_import_share": "fraction",
                "weekday_weekend_average_ratio": "ratio",
            }

        limitations = [recommendation.uncertainty]
        if status == RecommendationStatus.ILLUSTRATIVE:
            limitations.append(
                "At least one input is synthetic; values describe an illustrative scenario only."
            )
        if recommendation.potential_savings_dollars is None:
            limitations.append(
                "No modeled appliance counterfactual or customer-specific "
                "financial impact is available."
            )

        return CalculationEvidence(
            recommendation_id=f"meter-{meter.id}:{recommendation.id}:v1",
            rule_id=recommendation.id,
            rule_version=RULE_VERSION,
            owner_user_id=meter.user_id,
            meter_id=meter.id,
            created_at=evaluated_at,
            expires_at=evaluated_at + EVIDENCE_TTL,
            status=status,
            analysis_start_date=analysis_start_date,
            analysis_end_date=analysis_end_date,
            input_references=[f"reading-set:sha256:{digest}"],
            input_record_count=len(readings),
            input_digest_sha256=digest,
            provenance_counts=provenance_counts,
            coverage=coverage,
            eligibility_checks={
                "complete_coverage": (
                    "pass" if summary and summary.coverage_status == "complete" else "fail"
                ),
                "classified_import_direction": (
                    "pass"
                    if summary
                    and summary.unresolved_direction_count == 0
                    and summary.legacy_direction_unverified_count == 0
                    else "fail"
                ),
                "verified_time_basis": (
                    "pass"
                    if summary and summary.unresolved_time_basis_count == 0
                    else "fail"
                ),
                "measured_or_illustrative_provenance": (
                    "pass"
                    if summary
                    and summary.provenance_status in {"measured", "synthetic", "mixed"}
                    else "fail"
                ),
            },
            tariff_revision_id=tariff_revision_id,
            baseline_scenario=(
                "Eligible quality-A imported interval observations over the complete "
                "local-date analysis window."
            ),
            proposed_scenario=(
                "Review-only action; no load change or customer savings is modeled."
            ),
            calculation_method_version="usage-pattern-observation-v1",
            calculated_values=calculated_values,
            value_units=value_units,
            energy_difference_kwh=None,
            financial_difference_aud=None,
            rounding_rule=(
                "Observed energy displayed to 0.001 kWh; shares stored to 0.000001 "
                "and rendered as whole percentages. No monetary rounding applies."
            ),
            assumptions=recommendation.assumptions,
            limitations=limitations,
            invalidation_conditions=[
                "Re-evaluate after any source reading is added, corrected, or deleted.",
                "Evidence expires one hour after evaluation.",
            ],
        )
