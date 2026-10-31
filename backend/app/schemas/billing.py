"""Bill comparison schemas."""

from datetime import date

from pydantic import BaseModel


class BillLineItem(BaseModel):
    """A rounded billing component; GST memorandum lines are not added to total."""

    label: str
    quantity_kwh: float | None = None
    rate_cents_kwh: float | None = None
    amount: float
    included_in_total: bool = True


class BillPeriodBreakdown(BaseModel):
    """Transparent estimate for one requested meter period."""

    start_date: date
    end_date: date
    estimate_type: str
    tariff_status: str
    data_status: str
    gst_treatment: str
    import_kwh: float
    export_kwh: float
    unresolved_reading_count: int
    expected_interval_count: int
    observed_interval_count: int
    missing_interval_count: int
    unpriced_interval_count: int
    gst_amount: float
    total_cost: float
    line_items: list[BillLineItem]
    limitations: list[str]


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
    kwh_change_percent: float | None
    cost_change: float
    cost_change_percent: float | None
    daily_avg_change_percent: float | None

    # Insights
    trend: str  # "up", "down", "stable", or "unavailable"
    insight: str  # Human-readable insight


class BillComparisonResponse(BaseModel):
    """Full bill comparison response."""

    meter_id: int
    meter_name: str | None
    comparison: PeriodComparison
    recommendations: list[str]
    current_breakdown: BillPeriodBreakdown
    previous_breakdown: BillPeriodBreakdown
