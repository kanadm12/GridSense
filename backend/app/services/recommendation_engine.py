"""Recommendation engine for personalized energy advice."""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.meter import Meter
from app.models.tariff import Tariff
from app.schemas.recommendation import (
    Recommendation,
    RecommendationCategory,
    RecommendationConfidence,
    RecommendationEstimateStatus,
    RecommendationPriority,
    RecommendationsResponse,
    RecommendationTariffStatus,
)
from app.services.usage_analyzer import UsageAnalyzer


@dataclass
class UsagePattern:
    """Analyzed usage patterns for a meter."""

    avg_daily_kwh: float
    peak_hour: int
    peak_avg_kwh: float
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

    def _tariff_context(
        self, meter_id: int
    ) -> tuple[RecommendationTariffStatus, float | None]:
        meter = self.db.query(Meter).filter(Meter.id == meter_id).first()
        if meter is None:
            return RecommendationTariffStatus.MISSING, None

        tariff = self.db.query(Tariff).filter(Tariff.user_id == meter.user_id).first()
        if tariff is None:
            return RecommendationTariffStatus.MISSING, None
        if tariff.is_preset:
            return RecommendationTariffStatus.ILLUSTRATIVE, None

        today = date.today()
        if (
            (tariff.effective_from is not None and today < tariff.effective_from)
            or (tariff.effective_to is not None and today > tariff.effective_to)
        ):
            return RecommendationTariffStatus.OUTSIDE_EFFECTIVE_DATES, None

        if tariff.tariff_type == "flat":
            if tariff.flat_rate_cents_kwh is None:
                return RecommendationTariffStatus.MISSING_RATES, None
            return RecommendationTariffStatus.CONFIGURED, 0.0

        if tariff.periods:
            rates = [
                float(period["rate_cents_kwh"])
                for period in tariff.periods
                if period.get("rate_cents_kwh") is not None
            ]
        elif tariff.tariff_type in {"tou", "demand", "flexible"}:
            rates = [
                float(rate)
                for rate in (
                    tariff.peak_rate_cents_kwh,
                    tariff.shoulder_rate_cents_kwh,
                    tariff.off_peak_rate_cents_kwh,
                )
                if rate is not None
            ]
        else:
            return RecommendationTariffStatus.MISSING_RATES, None

        if len(rates) < 2:
            return RecommendationTariffStatus.MISSING_RATES, None
        return (
            RecommendationTariffStatus.CONFIGURED,
            round(max(rates) - min(rates), 2),
        )

    def analyze_patterns(self, meter_id: int, days: int = 30) -> UsagePattern | None:
        """Analyze usage patterns for a meter."""
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        summary = self.analyzer.get_usage_summary(meter_id, start_date, end_date)
        if not summary:
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
        rate_difference_cents_kwh: float | None = None,
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
            rate_difference_cents_kwh=rate_difference_cents_kwh,
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

    def generate_recommendations(self, meter_id: int) -> RecommendationsResponse:
        """Generate personalized recommendations based on usage patterns."""
        tariff_status, rate_difference = self._tariff_context(meter_id)
        patterns = self.analyze_patterns(meter_id)

        if not patterns:
            return RecommendationsResponse(
                recommendations=[
                    Recommendation(
                        id="no_data",
                        title="Upload more data",
                        description=(
                            "We need more usage data to provide "
                            "personalized recommendations."
                        ),
                        category=RecommendationCategory.GENERAL,
                        priority=RecommendationPriority.HIGH,
                        action="Upload at least 7 days of smart meter data",
                        reason="Insufficient data for analysis",
                        observed_fact=(
                            "There is not enough classifiable import data for a "
                            "usage-pattern analysis."
                        ),
                        proposed_action=(
                            "Upload a valid interval-data file with classifiable "
                            "import readings."
                        ),
                        conditional_opportunity=(
                            "Not available until sufficient import data and "
                            "opportunity inputs are supplied."
                        ),
                        estimate_status=RecommendationEstimateStatus.UNQUANTIFIED,
                        baseline="No classifiable import baseline is available.",
                        assumptions=[],
                        applicable_intervals="Not available",
                        uncertainty=(
                            "The source data does not currently support a "
                            "usage-pattern finding."
                        ),
                        confidence=RecommendationConfidence.LOW,
                        data_requirements=["At least 7 days of classifiable import readings"],
                    )
                ],
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
                    rate_difference_cents_kwh=(
                        rate_difference
                        if tariff_status == RecommendationTariffStatus.CONFIGURED
                        else None
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
        if patterns.avg_daily_kwh > self.HIGH_DAILY_USAGE:
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
                    rate_difference_cents_kwh=(
                        rate_difference
                        if tariff_status == RecommendationTariffStatus.CONFIGURED
                        else None
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

        return RecommendationsResponse(
            recommendations=recommendations,
            total_potential_savings=None,
            tariff_status=tariff_status,
        )
