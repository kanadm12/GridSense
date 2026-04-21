"""Recommendation engine for personalized energy advice."""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.schemas.recommendation import (
    Recommendation,
    RecommendationCategory,
    RecommendationPriority,
    RecommendationsResponse,
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
    weekend_vs_weekday: float  # Ratio of weekend to weekday usage
    total_kwh: float
    days_analyzed: int


class RecommendationEngine:
    """Engine for generating personalized energy recommendations."""

    # Thresholds for recommendations
    HIGH_EVENING_THRESHOLD = 0.35  # >35% usage in peak hours
    HIGH_NIGHT_THRESHOLD = 0.25  # >25% usage overnight (standby concern)
    HIGH_DAILY_USAGE = 20  # >20 kWh/day is high for a household
    SOLAR_BENEFIT_THRESHOLD = 0.30  # <30% usage during solar hours

    def __init__(self, db: Session):
        self.db = db
        self.analyzer = UsageAnalyzer(db)

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
            weekend_vs_weekday=weekend_vs_weekday,
            total_kwh=summary.total_kwh,
            days_analyzed=summary.days_count,
        )

    def generate_recommendations(self, meter_id: int) -> RecommendationsResponse:
        """Generate personalized recommendations based on usage patterns."""
        patterns = self.analyze_patterns(meter_id)

        if not patterns:
            return RecommendationsResponse(
                recommendations=[
                    Recommendation(
                        id="no_data",
                        title="Upload more data",
                        description="We need more usage data to provide personalized recommendations.",
                        category=RecommendationCategory.GENERAL,
                        priority=RecommendationPriority.HIGH,
                        action="Upload at least 7 days of smart meter data",
                        reason="Insufficient data for analysis",
                    )
                ],
                total_potential_savings=None,
            )

        recommendations = []
        total_savings = 0.0

        # Rule 1: High evening/peak usage
        if patterns.evening_ratio > self.HIGH_EVENING_THRESHOLD:
            potential_shift = patterns.evening_ratio - 0.25  # Target 25%
            potential_savings = potential_shift * patterns.total_kwh * 0.10  # 10c/kWh difference

            recommendations.append(
                Recommendation(
                    id="shift_evening_load",
                    title="Shift load from peak hours",
                    description=f"{patterns.evening_ratio * 100:.0f}% of your energy is used during expensive peak hours (3pm-9pm).",
                    category=RecommendationCategory.LOAD_SHIFTING,
                    priority=RecommendationPriority.HIGH,
                    potential_savings_kwh=round(potential_shift * patterns.total_kwh, 1),
                    potential_savings_dollars=round(potential_savings, 2),
                    action="Run dishwasher, washing machine, and dryer before 3pm or after 9pm",
                    reason=f"Your peak hour usage is {(patterns.evening_ratio - 0.25) * 100:.0f}% higher than optimal",
                )
            )
            total_savings += potential_savings

        # Rule 2: High overnight usage (possible standby drain)
        if patterns.night_ratio > self.HIGH_NIGHT_THRESHOLD:
            potential_savings = patterns.night_ratio * patterns.total_kwh * 0.3 * 0.25  # 30% reducible

            recommendations.append(
                Recommendation(
                    id="reduce_standby",
                    title="Check standby power usage",
                    description=f"{patterns.night_ratio * 100:.0f}% of energy used overnight suggests standby drain.",
                    category=RecommendationCategory.STANDBY_REDUCTION,
                    priority=RecommendationPriority.MEDIUM,
                    potential_savings_kwh=round(patterns.night_ratio * patterns.total_kwh * 0.3, 1),
                    potential_savings_dollars=round(potential_savings, 2),
                    action="Use power boards with switches for entertainment units and home office equipment",
                    reason="High overnight usage often indicates appliances using power while idle",
                )
            )
            total_savings += potential_savings

        # Rule 3: Low solar hour usage (missing solar opportunity)
        solar_ratio = 1 - patterns.evening_ratio - patterns.night_ratio
        if solar_ratio < self.SOLAR_BENEFIT_THRESHOLD:
            recommendations.append(
                Recommendation(
                    id="use_solar_hours",
                    title="Use more energy during solar hours",
                    description=f"Only {solar_ratio * 100:.0f}% of usage is during solar generation hours (9am-3pm).",
                    category=RecommendationCategory.SOLAR_OPTIMIZATION,
                    priority=RecommendationPriority.MEDIUM,
                    potential_savings_kwh=None,
                    potential_savings_dollars=None,
                    action="Schedule high-energy tasks like laundry and dishwashing for late morning",
                    reason="Solar energy is cheapest when the sun is highest (10am-2pm)",
                )
            )

        # Rule 4: High overall consumption
        if patterns.avg_daily_kwh > self.HIGH_DAILY_USAGE:
            recommendations.append(
                Recommendation(
                    id="energy_audit",
                    title="Consider an energy audit",
                    description=f"Your average daily usage of {patterns.avg_daily_kwh:.1f} kWh is higher than typical households.",
                    category=RecommendationCategory.GENERAL,
                    priority=RecommendationPriority.LOW,
                    potential_savings_kwh=None,
                    potential_savings_dollars=None,
                    action="Check insulation, heating/cooling efficiency, and appliance energy ratings",
                    reason="Average Victorian household uses 12-16 kWh per day",
                )
            )

        # Rule 5: Weekend spike
        if patterns.weekend_vs_weekday > 1.3:
            recommendations.append(
                Recommendation(
                    id="weekend_awareness",
                    title="High weekend energy use",
                    description=f"Your weekend usage is {(patterns.weekend_vs_weekday - 1) * 100:.0f}% higher than weekdays.",
                    category=RecommendationCategory.GENERAL,
                    priority=RecommendationPriority.LOW,
                    potential_savings_kwh=None,
                    potential_savings_dollars=None,
                    action="Review weekend habits - heating/cooling, entertainment systems, cooking",
                    reason="Weekend usage often increases from more time at home",
                )
            )

        # Rule 6: TOU tariff recommendation
        if patterns.evening_ratio > 0.30:
            recommendations.append(
                Recommendation(
                    id="tou_tariff_check",
                    title="Review your electricity tariff",
                    description="Your usage pattern may not be optimal for Time-of-Use tariffs.",
                    category=RecommendationCategory.TARIFF_OPTIMIZATION,
                    priority=RecommendationPriority.MEDIUM,
                    potential_savings_kwh=None,
                    potential_savings_dollars=None,
                    action="Compare flat-rate vs TOU tariffs using Victorian Energy Compare",
                    reason="High peak usage can make TOU tariffs more expensive",
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
            total_potential_savings=round(total_savings, 2) if total_savings > 0 else None,
        )
