"""Usage data schemas for analytics endpoints."""

from datetime import date, datetime

from pydantic import BaseModel


class DailyUsage(BaseModel):
    """Daily usage aggregation."""

    date: date
    total_kwh: float
    peak_kwh: float  # 3pm-9pm
    off_peak_kwh: float  # 10pm-7am
    shoulder_kwh: float  # 7am-3pm, 9pm-10pm
    max_interval_kwh: float
    estimated_cost: float | None = None


class HourlyUsage(BaseModel):
    """Hourly usage aggregation."""

    hour: int  # 0-23
    avg_kwh: float
    total_kwh: float
    reading_count: int


class WeeklyUsage(BaseModel):
    """Weekly usage pattern."""

    day_of_week: int  # 0=Monday, 6=Sunday
    day_name: str
    avg_kwh: float
    total_kwh: float


class UsageSummary(BaseModel):
    """Overall usage summary."""

    meter_id: int
    meter_name: str | None
    nmi: str

    # Time range
    start_date: datetime
    end_date: datetime
    days_count: int

    # Consumption totals
    total_kwh: float
    avg_daily_kwh: float
    max_daily_kwh: float
    min_daily_kwh: float

    # Peak analysis
    peak_hour: int  # Hour of day with highest average usage
    peak_avg_kwh: float
    off_peak_percentage: float

    # Cost estimates (using flat rate)
    estimated_total_cost: float
    estimated_daily_cost: float


class UsageChartData(BaseModel):
    """Data formatted for chart display."""

    labels: list[str]
    values: list[float]
    unit: str = "kWh"
