"""Insights and analytics schemas."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SeverityLevel(str, Enum):
    """Severity level for anomalies."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AnomalyType(str, Enum):
    """Types of energy usage anomalies."""
    DAILY_SPIKE = "daily_spike"
    OVERNIGHT_USAGE = "overnight_usage"
    UNUSUAL_PATTERN = "unusual_pattern"
    PEAK_HEAVY = "peak_heavy"
    APPLIANCE_LEFT_ON = "appliance_left_on"


class Anomaly(BaseModel):
    """A detected anomaly in energy usage."""
    type: AnomalyType
    date: str
    severity: SeverityLevel
    message: str
    suggestions: list[str] = []
    value_kwh: float | None = None
    expected_kwh: float | None = None
    extra_cost: float | None = None


class AnomalyReport(BaseModel):
    """Full anomaly detection report."""
    meter_id: int
    analysis_period_days: int
    total_anomalies: int
    high_severity_count: int
    medium_severity_count: int
    low_severity_count: int
    anomalies: list[Anomaly]


class BillForecast(BaseModel):
    """Bill forecast for current or future month."""
    meter_id: int
    month: str
    days_in_month: int
    days_elapsed: int
    days_remaining: int
    usage_so_far_kwh: float
    cost_so_far: float
    projected_total_kwh: float
    projected_total_cost: float
    projected_cost_low: float
    projected_cost_high: float
    daily_average_kwh: float
    confidence_level: float = 0.95


class BillTrendItem(BaseModel):
    """Historical bill data for a month."""
    month: str
    total_kwh: float
    total_cost: float
    days_with_data: int


class BillTrend(BaseModel):
    """Historical bill trend data."""
    meter_id: int
    months: list[BillTrendItem]


class InsightType(str, Enum):
    """Types of energy insights."""
    SAVINGS_OPPORTUNITY = "savings_opportunity"
    USAGE_PATTERN = "usage_pattern"
    COST_ALERT = "cost_alert"
    ACHIEVEMENT = "achievement"
    TIP = "tip"


class Insight(BaseModel):
    """A personalized energy insight."""
    type: InsightType
    title: str
    message: str
    impact_dollars: float | None = None
    action: str | None = None
    icon: str | None = None


class DailyBrief(BaseModel):
    """Daily energy brief for the user."""
    date: str
    greeting: str
    yesterday_usage_kwh: float
    yesterday_cost: float
    comparison_to_average: float  # Percentage, negative = below average
    insights: list[Insight]
    forecast_message: str | None = None
