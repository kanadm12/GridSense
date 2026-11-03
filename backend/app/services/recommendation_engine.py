"""Recommendation engine for personalized energy advice."""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.meter import Meter
from app.models.tariff import Tariff, TariffRevision
from app.schemas.recommendation import (
    Recommendation,
    RecommendationCategory,
    RecommendationConfidence,
    RecommendationEstimateStatus,
    RecommendationPriority,
    RecommendationsResponse,
    RecommendationStatus,
    RecommendationTariffStatus,
)
from app.services.calculation_evidence import CalculationEvidenceService
from app.services.tariff import applicable_tariff_revisions
from app.services.usage_analyzer import UsageAnalyzer


@dataclass
class UsagePattern:
    """Analyzed usage patterns for a meter."""

    avg_daily_kwh: float | None
    peak_hour: int | None
    peak_avg_kwh: float | None
    evening_ratio: float  # % of usage during peak hours (3pm-9pm)
    night_ratio: float  # % of usage during off-peak (10pm-7am)
    daytime_ratio: float  # % of usage between 9am and 3pm
    weekend_vs_weekday: float  # Ratio of weekend to weekday usage
    total_kwh: float
    days_analyzed: int


class RecommendationEngine:
    """Engine for generating personalized energy recommendations."""

    # These thresholds identify patterns to review; they are not savings targets.
    HIGH_EVENING_THRESHOLD = 0.35  # >35% usage in peak hours
    HIGH_NIGHT_THRESHOLD = 0.25  # >25% usage overnight
    HIGH_DAILY_USAGE = 20  # Internal review threshold, not a household benchmark
    SOLAR_BENEFIT_THRESHOLD = 0.30  # Daytime-use review threshold, not solar output

    def __init__(self, db: Session):
        self.db = db
        self.analyzer = UsageAnalyzer(db)
        self._latest_summary = None
        self._analysis_start_date: date | None = None
        self._analysis_end_date: date | None = None

    def _tariff_context(self, meter_id: int) -> RecommendationTariffStatus:
        meter = self.db.query(Meter).filter(Meter.id == meter_id).first()
        if meter is None:
            return RecommendationTariffStatus.MISSING

        tariff = (
            self.db.query(Tariff)
            .filter(
                Tariff.user_id == meter.user_id,
                Tariff.archived_at.is_(None),
            )
            .first()
        )
        if tariff is None:
            return RecommendationTariffStatus.MISSING
        today = date.today()
        revisions = (
            self.db.query(TariffRevision)
            .filter(TariffRevision.tariff_id == tariff.id)
            .order_by(TariffRevision.revision_number)
            .all()
        )
        applicable = applicable_tariff_revisions(revisions, today)
        if len(applicable) > 1:
            return RecommendationTariffStatus.MISSING
        if not applicable:
            if not revisions and tariff.is_preset:
                return RecommendationTariffStatus.ILLUSTRATIVE
            if revisions and revisions[-1].is_illustrative:
                return RecommendationTariffStatus.ILLUSTRATIVE
            if any(revision.effective_from is not None for revision in revisions):
                return RecommendationTariffStatus.OUTSIDE_EFFECTIVE_DATES
            return RecommendationTariffStatus.MISSING

        revision = applicable[0]
        if revision.tariff_type == "flat":
            if revision.flat_rate_cents_kwh is None:
                return RecommendationTariffStatus.MISSING_RATES
            return RecommendationTariffStatus.CONFIGURED

        if revision.periods:
            rates = [
                float(period["rate_cents_kwh"])
                for period in revision.periods
                if period.get("rate_cents_kwh") is not None
            ]
        elif revision.tariff_type in {"tou", "demand", "flexible"}:
            rates = [
                float(rate)
                for rate in (
                    revision.peak_rate_cents_kwh,
                    revision.shoulder_rate_cents_kwh,
                    revision.off_peak_rate_cents_kwh,
                )
                if rate is not None
            ]
        else:
            return RecommendationTariffStatus.MISSING_RATES

        if len(rates) < 2:
            return RecommendationTariffStatus.MISSING_RATES
        return RecommendationTariffStatus.CONFIGURED

    @staticmethod
    def summary_is_eligible_for_patterns(summary: object | None, days: int = 7) -> bool:
        """Require complete, classified, time-resolved actual days for pattern claims."""
        return bool(
            summary is not None
            and getattr(summary, "coverage_status", None) == "complete"
            and getattr(summary, "coverage_fraction", 0) == 1
            and getattr(summary, "days_count", 0) >= days
            and getattr(summary, "channel_classification_status", None) == "classified"
            and getattr(summary, "unresolved_direction_count", 0) == 0
            and getattr(summary, "legacy_direction_unverified_count", 0) == 0
            and getattr(summary, "unresolved_time_basis_count", 0) == 0
            and getattr(summary, "provenance_status", None)
            in {"measured", "synthetic", "mixed"}
        )

    def analyze_patterns(self, meter_id: int, days: int = 7) -> UsagePattern | None:
        """Analyze patterns only across fully covered, classifiable local days."""
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=days - 1)
        self._analysis_start_date = start_date
        self._analysis_end_date = end_date

        summary = self.analyzer.get_usage_summary(meter_id, start_date, end_date)
        self._latest_summary = summary
        if not self.summary_is_eligible_for_patterns(summary, days):
            return None

        hourly = self.analyzer.get_hourly_usage(meter_id, start_date, end_date)
        weekly = self.analyzer.get_weekly_usage(meter_id, start_date, end_date)

        if not hourly:
            return None

        # Calculate ratios
        total_hourly = sum(h.total_kwh for h in hourly)

        # Evening (peak) hours: 3pm-9pm
        evening_kwh = sum(h.total_kwh for h in hourly if 15 <= h.hour < 21)
        evening_ratio = evening_kwh / total_hourly if total_hourly > 0 else 0

        # Night (off-peak) hours: 10pm-7am
        night_kwh = sum(h.total_kwh for h in hourly if h.hour >= 22 or h.hour < 7)
        night_ratio = night_kwh / total_hourly if total_hourly > 0 else 0
        daytime_kwh = sum(h.total_kwh for h in hourly if 9 <= h.hour < 15)
        daytime_ratio = daytime_kwh / total_hourly if total_hourly > 0 else 0

        # Weekend vs weekday
        if weekly:
            weekday_avg = sum(w.avg_kwh for w in weekly if w.day_of_week < 5) / 5
            weekend_avg = sum(w.avg_kwh for w in weekly if w.day_of_week >= 5) / 2
            weekend_vs_weekday = weekend_avg / weekday_avg if weekday_avg > 0 else 1
        else:
            weekend_vs_weekday = 1.0

        return UsagePattern(
            avg_daily_kwh=summary.avg_daily_kwh,
            peak_hour=summary.peak_hour,
            peak_avg_kwh=summary.peak_avg_kwh,
            evening_ratio=evening_ratio,
            night_ratio=night_ratio,
            daytime_ratio=daytime_ratio,
            weekend_vs_weekday=weekend_vs_weekday,
            total_kwh=summary.total_kwh,
            days_analyzed=summary.days_count,
        )

    def _data_quality_recommendation(
        self, summary: object | None
    ) -> Recommendation:
        if summary is None:
            observed = "No eligible import summary is available for the latest seven local days."
            action = (
                "Upload at least seven complete days of interval data with verified "
                "direction and time basis."
            )
            requirements = [
                "Seven complete local days of eligible import intervals",
                "Confirmed import direction and supported source time basis",
            ]
            reason = "The required observation window cannot currently be evaluated."
        else:
            observed = (
                f"Coverage is {getattr(summary, 'coverage_fraction', 0) * 100:.1f}% "
                f"({getattr(summary, 'eligible_interval_count', 0)} eligible of "
                f"{getattr(summary, 'expected_interval_count', 0)} expected intervals); "
                f"status: {getattr(summary, 'coverage_status', 'unavailable')}."
            )
            reasons = []
            if getattr(summary, "unresolved_direction_count", 0) or getattr(
                summary, "legacy_direction_unverified_count", 0
            ):
                reasons.append("meter channel direction needs confirmation")
            if getattr(summary, "unresolved_time_basis_count", 0):
                reasons.append("source timestamp basis is unresolved")
            if getattr(summary, "coverage_status", None) != "complete":
                reasons.append("the seven-day interval window is incomplete")
            if not reasons:
                reasons.append("the available readings do not meet the pattern eligibility policy")
            reason = "Pattern analysis is withheld because " + ", ".join(reasons) + "."
            action = (
                "Confirm channel direction and source-time basis, then provide a fully "
                "covered seven-day interval window."
            )
            requirements = [
                "Complete 100% eligible coverage for seven local days",
                "No unresolved or legacy-unverified import direction",
                "Verified source time basis for every interval",
            ]

        return Recommendation(
            id="data_quality_action",
            title="Improve meter-data coverage",
            description="A data-quality action is needed before usage-pattern advice is supported.",
            category=RecommendationCategory.GENERAL,
            priority=RecommendationPriority.HIGH,
            potential_savings_kwh=None,
            potential_savings_dollars=None,
            action=action,
            reason=reason,
            observed_fact=observed,
            proposed_action=action,
            conditional_opportunity="No energy or financial impact is quantified.",
            estimate_status=RecommendationEstimateStatus.UNQUANTIFIED,
            baseline="No eligible seven-day pattern baseline is available.",
            assumptions=[],
            applicable_intervals="Latest seven complete local dates before today.",
            uncertainty=reason,
            confidence=RecommendationConfidence.LOW,
            data_requirements=requirements,
            status=RecommendationStatus.UNQUANTIFIED,
        )

    @staticmethod
    def _unquantified_recommendation(
        *,
        id: str,
        title: str,
        description: str,
        category: RecommendationCategory,
        priority: RecommendationPriority,
        observed_fact: str,
        action: str,
        reason: str,
        baseline: str,
        applicable_intervals: str,
        uncertainty: str,
    ) -> Recommendation:
        return Recommendation(
            id=id,
            title=title,
            description=description,
            category=category,
            priority=priority,
            potential_savings_kwh=None,
            potential_savings_dollars=None,
            action=action,
            reason=reason,
            observed_fact=observed_fact,
            proposed_action=action,
            conditional_opportunity=(
                "Not quantified. A user-declared appliance, its rated power or "
                "energy demand, a feasible available time window, and a verified "
                "current tariff are needed before estimating a monetary opportunity."
            ),
            estimate_status=RecommendationEstimateStatus.UNQUANTIFIED,
            baseline=baseline,
            assumptions=[
                (
                    "Interval-meter totals do not identify individual appliances "
                    "or explain why energy was used."
                ),
                "No appliance-specific load is assumed to be shiftable or reducible.",
            ],
            rate_difference_cents_kwh=None,
            applicable_intervals=applicable_intervals,
            uncertainty=uncertainty,
            confidence=RecommendationConfidence.LOW,
            data_requirements=[
                "User-declared appliance",
                "Appliance rated power or energy demand",
                "Feasible available operating window",
                "Verified tariff covering the proposed interval",
            ],
        )

    def _attach_evidence(
        self,
        meter_id: int,
        recommendations: list[Recommendation],
        *,
        pattern: UsagePattern | None,
        tariff_revision_id: int | None,
    ) -> None:
        meter = self.db.query(Meter).filter(Meter.id == meter_id).first()
        if meter is None:
            return
        start_date = self._analysis_start_date or (date.today() - timedelta(days=7))
        end_date = self._analysis_end_date or (date.today() - timedelta(days=1))
        readings = self.analyzer._readings_for_window(
            meter_id, meter.state, start_date, end_date
        )
        for recommendation in recommendations:
            evidence = CalculationEvidenceService.build_usage_evidence(
                meter=meter,
                recommendation=recommendation,
                readings=readings,
                summary=self._latest_summary,
                pattern=pattern,
                tariff_revision_id=tariff_revision_id,
                analysis_start_date=self._analysis_start_date,
                analysis_end_date=self._analysis_end_date,
            )
            recommendation.calculation_evidence = evidence
            recommendation.status = evidence.status

    def generate_recommendations(self, meter_id: int) -> RecommendationsResponse:
        """Generate personalized recommendations based on usage patterns."""
        self._latest_summary = None
        self._analysis_start_date = None
        self._analysis_end_date = None
        tariff_status = self._tariff_context(meter_id)
        patterns = self.analyze_patterns(meter_id)

        if not patterns:
            recommendation = self._data_quality_recommendation(self._latest_summary)
            self._attach_evidence(
                meter_id,
                [recommendation],
                pattern=None,
                tariff_revision_id=None,
            )
            return RecommendationsResponse(
                recommendations=[recommendation],
                total_potential_savings=None,
                tariff_status=tariff_status,
            )

        recommendations = []

        # Rule 1: High evening/peak usage
        if patterns.evening_ratio > self.HIGH_EVENING_THRESHOLD:
            recommendations.append(
                self._unquantified_recommendation(
                    id="shift_evening_load",
                    title="Shift load from peak hours",
                    description=(
                        "Review whether discretionary activity can be moved out "
                        "of this observed interval."
                    ),
                    category=RecommendationCategory.LOAD_SHIFTING,
                    priority=RecommendationPriority.HIGH,
                    observed_fact=(
                        f"{patterns.evening_ratio * 100:.0f}% of classifiable "
                        "import energy occurred during 15:00-21:00."
                    ),
                    action=(
                        "Review whether any user-identified flexible loads can "
                        "safely run at another time."
                    ),
                    reason=(
                        "This is an observed timing pattern, not evidence that "
                        "a specific appliance ran or can be shifted."
                    ),
                    baseline=(
                        f"{patterns.total_kwh:.1f} kWh across "
                        f"{patterns.days_analyzed} analyzed day(s); "
                        f"{patterns.evening_ratio * 100:.0f}% fell in the evening."
                    ),
                    applicable_intervals=(
                        "Observed: 15:00-21:00 local time. Any alternative "
                        "depends on the appliance and tariff."
                    ),
                    uncertainty=(
                        "Aggregate readings cannot attribute evening use to an "
                        "appliance or show what portion is flexible."
                    ),
                )
            )

        # Rule 2: High overnight usage is a timing observation, not an appliance diagnosis.
        if patterns.night_ratio > self.HIGH_NIGHT_THRESHOLD:
            recommendations.append(
                self._unquantified_recommendation(
                    id="overnight_load_review",
                    title="Review overnight energy use",
                    description=(
                        "The meter shows overnight imports; it cannot determine "
                        "whether these were standby loads."
                    ),
                    category=RecommendationCategory.STANDBY_REDUCTION,
                    priority=RecommendationPriority.MEDIUM,
                    observed_fact=(
                        f"{patterns.night_ratio * 100:.0f}% of classifiable "
                        "import energy occurred during 22:00-07:00."
                    ),
                    action=(
                        "Review overnight meter intervals alongside devices "
                        "you know were operating."
                    ),
                    reason=(
                        "Overnight consumption is observed, but standby use or "
                        "an appliance being left on is not established by meter totals."
                    ),
                    baseline=(
                        f"{patterns.total_kwh:.1f} kWh across "
                        f"{patterns.days_analyzed} analyzed day(s); "
                        f"{patterns.night_ratio * 100:.0f}% fell overnight."
                    ),
                    applicable_intervals="22:00-07:00 local time",
                    uncertainty=(
                        "No appliance disaggregation or device-state data is "
                        "available; no reducible fraction is assumed."
                    ),
                )
            )

        # Rule 3: Daytime imports alone do not prove solar availability or export.
        if patterns.daytime_ratio < self.SOLAR_BENEFIT_THRESHOLD:
            recommendations.append(
                self._unquantified_recommendation(
                    id="use_solar_hours",
                    title="Review daytime energy use",
                    description=(
                        "The interval data shows a limited share of imports "
                        "during daytime hours; it does not measure solar generation."
                    ),
                    category=RecommendationCategory.SOLAR_OPTIMIZATION,
                    priority=RecommendationPriority.MEDIUM,
                    observed_fact=(
                        f"{patterns.daytime_ratio * 100:.0f}% of classifiable "
                        "import energy occurred during 09:00-15:00."
                    ),
                    action=(
                        "If you have solar and a flexible appliance, compare "
                        "its operating window with measured solar output."
                    ),
                    reason=(
                        "Daytime imports alone do not establish solar "
                        "availability, self-consumption, or a shift opportunity."
                    ),
                    baseline=(
                        f"{patterns.total_kwh:.1f} kWh across "
                        f"{patterns.days_analyzed} analyzed day(s); "
                        f"{patterns.daytime_ratio * 100:.0f}% fell in 09:00-15:00."
                    ),
                    applicable_intervals=(
                        "09:00-15:00 local time; solar output is not available "
                        "in these meter data."
                    ),
                    uncertainty=(
                        "No PV generation, export, appliance, or device-state "
                        "profile is available."
                    ),
                )
            )

        # Rule 4: This fixed review threshold is not a claim about a typical household.
        if (
            patterns.avg_daily_kwh is not None
            and patterns.avg_daily_kwh > self.HIGH_DAILY_USAGE
        ):
            recommendations.append(
                self._unquantified_recommendation(
                    id="energy_audit",
                    title="Consider an energy audit",
                    description=(
                        f"Your analyzed average was {patterns.avg_daily_kwh:.1f} "
                        "kWh/day, above GridSense's internal 20 kWh/day review threshold."
                    ),
                    category=RecommendationCategory.GENERAL,
                    priority=RecommendationPriority.LOW,
                    observed_fact=(
                        f"Average import was {patterns.avg_daily_kwh:.1f} "
                        f"kWh/day over {patterns.days_analyzed} analyzed day(s)."
                    ),
                    action=(
                        "Review the household's own history and investigate "
                        "changes before considering an energy audit."
                    ),
                    reason=(
                        "The threshold only flags a pattern for review; it is "
                        "not a Victorian benchmark or proof of inefficiency."
                    ),
                    baseline=(
                        f"{patterns.total_kwh:.1f} kWh across "
                        f"{patterns.days_analyzed} analyzed day(s)."
                    ),
                    applicable_intervals="Daily total; no specific time window",
                    uncertainty=(
                        "Household size, heating, cooling, solar, occupancy, "
                        "and appliance mix are not represented."
                    ),
                )
            )

        # Rule 5: Weekend difference is descriptive and not causal.
        if patterns.weekend_vs_weekday > 1.3:
            recommendations.append(
                self._unquantified_recommendation(
                    id="weekend_awareness",
                    title="High weekend energy use",
                    description=(
                        f"Average weekend imports were "
                        f"{(patterns.weekend_vs_weekday - 1) * 100:.0f}% "
                        "higher than the weekday average."
                    ),
                    category=RecommendationCategory.GENERAL,
                    priority=RecommendationPriority.LOW,
                    observed_fact=(
                        f"Weekend average was {patterns.weekend_vs_weekday:.2f} "
                        "times the weekday average."
                    ),
                    action=(
                        "Compare the weekend pattern with your own schedule "
                        "and known appliance use."
                    ),
                    reason=(
                        "This is a calendar-based difference and does not "
                        "identify a cause or controllable load."
                    ),
                    baseline="Weekend and weekday average imports from the analyzed sample.",
                    applicable_intervals="Saturday and Sunday versus Monday-Friday",
                    uncertainty="Occupancy and device-level measurements are unavailable.",
                )
            )

        # Rule 6: A tariff check does not imply a cheaper plan or bill.
        if patterns.evening_ratio > 0.30:
            recommendations.append(
                self._unquantified_recommendation(
                    id="tou_tariff_check",
                    title="Review your electricity tariff",
                    description=(
                        "Compare observed usage timing with current retailer "
                        "offers and their actual terms."
                    ),
                    category=RecommendationCategory.TARIFF_OPTIMIZATION,
                    priority=RecommendationPriority.MEDIUM,
                    observed_fact=(
                        f"{patterns.evening_ratio * 100:.0f}% of classifiable "
                        "import energy occurred during 15:00-21:00."
                    ),
                    action=(
                        "Compare current offers using your interval history and "
                        "the retailer's complete tariff terms."
                    ),
                    reason=(
                        "A usage pattern and rate spread alone cannot establish "
                        "that switching would reduce a bill."
                    ),
                    baseline=(
                        f"{patterns.total_kwh:.1f} kWh across "
                        f"{patterns.days_analyzed} analyzed day(s)."
                    ),
                    applicable_intervals="Observed peak window: 15:00-21:00 local time.",
                    uncertainty=(
                        "This comparison excludes retailer eligibility, "
                        "controlled loads, demand windows, discounts, and other terms."
                    ),
                )
            )

        # Sort by priority
        priority_order = {
            RecommendationPriority.HIGH: 0,
            RecommendationPriority.MEDIUM: 1,
            RecommendationPriority.LOW: 2,
        }
        recommendations.sort(key=lambda r: priority_order[r.priority])

        if not recommendations:
            recommendations.append(
                Recommendation(
                    id="no_supported_action",
                    title="No action supported by current evidence",
                    description=(
                        "Eligible meter observations were reviewed, but no "
                        "actionable pattern crossed the current review rules."
                    ),
                    category=RecommendationCategory.GENERAL,
                    priority=RecommendationPriority.LOW,
                    potential_savings_kwh=None,
                    potential_savings_dollars=None,
                    action="Continue reviewing complete interval data and confirmed tariff terms.",
                    reason=(
                        "No supported action was identified; this is not a finding "
                        "that usage is efficient."
                    ),
                    observed_fact=(
                        f"{patterns.total_kwh:.3f} kWh of eligible import across "
                        f"{patterns.days_analyzed} fully covered local days."
                    ),
                    proposed_action="No change is recommended from this observation alone.",
                    conditional_opportunity="No energy or financial impact is quantified.",
                    estimate_status=RecommendationEstimateStatus.UNQUANTIFIED,
                    baseline=(
                        "Complete, quality-eligible imported intervals for the "
                        "analysis window."
                    ),
                    assumptions=[],
                    applicable_intervals="Latest seven complete local dates before today.",
                    uncertainty="No tested rule identified a supported action.",
                    confidence=RecommendationConfidence.MEDIUM,
                    data_requirements=[],
                    status=RecommendationStatus.NO_SUPPORTED_ACTION,
                )
            )

        self._attach_evidence(
            meter_id,
            recommendations,
            pattern=patterns,
            tariff_revision_id=None,
        )
        return RecommendationsResponse(
            recommendations=recommendations,
            total_potential_savings=None,
            tariff_status=tariff_status,
        )
