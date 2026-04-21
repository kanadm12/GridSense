"""Bill comparison schemas."""

from datetime import date
from pydantic import BaseModel


class PeriodComparison(BaseModel):
    """Comparison between two billing periods."""

    # Current period
    current_start: date
    current_end: date
    current_kwh: float
    current_cost: float
    current_days: int
    current_daily_avg_kwh: float

    # Previous period
    previous_start: date
    previous_end: date
    previous_kwh: float
    previous_cost: float
    previous_days: int
    previous_daily_avg_kwh: float

    # Changes
    kwh_change: float  # Absolute change
    kwh_change_percent: float
    cost_change: float
    cost_change_percent: float
    daily_avg_change_percent: float

    # Insights
    trend: str  # "up", "down", "stable"
    insight: str  # Human-readable insight


class BillComparisonResponse(BaseModel):
    """Full bill comparison response."""

    meter_id: int
    meter_name: str | None
    comparison: PeriodComparison
    recommendations: list[str]
