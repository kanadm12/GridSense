"""Bill comparison schemas."""

from datetime import date

from pydantic import BaseModel, Field


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
    provenance_status: str
    gst_treatment: str
    import_kwh: float
    export_kwh: float
    unresolved_reading_count: int
    excluded_quality_count: int = 0
    legacy_direction_unverified_count: int = 0
    duplicate_interval_count: int = 0
    unresolved_time_basis_count: int = 0
    expected_interval_count: int
    observed_interval_count: int
    missing_interval_count: int
    unpriced_interval_count: int
    unpriced_kwh: float = 0.0
    unpriced_days: int = 0
    coverage_fraction: float
    customer_estimate_available: bool
    full_bill_available: bool
    tariff_revision_ids: list[int] = Field(default_factory=list)
    gst_amount: float | None
    total_cost: float | None
    line_items: list[BillLineItem]
    limitations: list[str]


class PeriodComparison(BaseModel):
    """Comparison between two billing periods."""

    # Current period
    current_start: date
    current_end: date
    current_kwh: float
    current_cost: float | None
    current_days: int
    current_daily_avg_kwh: float | None

    # Previous period
    previous_start: date
    previous_end: date
    previous_kwh: float
    previous_cost: float | None
    previous_days: int
    previous_daily_avg_kwh: float | None

    # Changes
    kwh_change: float | None  # Absolute change
    kwh_change_percent: float | None
    cost_change: float | None
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
