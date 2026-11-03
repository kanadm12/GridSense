"""Usage data schemas for analytics endpoints."""

from datetime import date, datetime

from pydantic import BaseModel


class DailyUsage(BaseModel):
    """Daily usage aggregation."""

    date: date
    observed_eligible_kwh: float
    total_kwh: float
    peak_kwh: float  # 3pm-9pm
    off_peak_kwh: float  # 10pm-7am
    shoulder_kwh: float  # 7am-3pm, 9pm-10pm
    max_interval_kwh: float
    estimated_cost: float | None = None
    expected_interval_count: int
    observed_interval_count: int
    eligible_interval_count: int
    missing_interval_count: int
    excluded_quality_count: int
    unresolved_direction_count: int
    legacy_direction_unverified_count: int
    duplicate_interval_count: int
    invalid_interval_count: int
    invalid_unit_count: int
    coverage_fraction: float
    coverage_status: str
    provenance_status: str
    observed_interval_average_demand_kw: float | None = None
    observed_interval_peak_demand_kw: float | None = None
    full_period_average_demand_kw: float | None = None


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
    complete_day_count: int = 0
    coverage_status: str = "unavailable"


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
    avg_daily_kwh: float | None
    max_daily_kwh: float | None
    min_daily_kwh: float | None

    # Peak analysis
    peak_hour: int | None  # Hour of day with highest average eligible interval energy
    peak_avg_kwh: float | None
    off_peak_percentage: float | None

    estimated_total_cost: float | None = None
    estimated_daily_cost: float | None = None
    eligible_import_kwh: float
    eligible_export_kwh: float
    net_grid_kwh: float | None
    expected_interval_count: int
    observed_interval_count: int
    eligible_interval_count: int
    missing_interval_count: int
    excluded_quality_count: int
    unresolved_direction_count: int
    legacy_direction_unverified_count: int
    duplicate_interval_count: int
    invalid_interval_count: int
    invalid_unit_count: int
    unresolved_time_basis_count: int
    coverage_fraction: float
    coverage_status: str
    provenance_status: str
    channel_classification_status: str
    explanation: str | None = None
    observed_interval_average_demand_kw: float | None = None
    observed_interval_peak_demand_kw: float | None = None
    full_period_average_demand_kw: float | None = None


class UsageChartData(BaseModel):
    """Data formatted for chart display."""

    labels: list[str]
    values: list[float]
    unit: str = "kWh"
