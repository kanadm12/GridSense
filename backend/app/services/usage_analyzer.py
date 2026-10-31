"""Usage analyzer service for calculating consumption metrics."""

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.meter import Meter
from app.models.reading import Reading, consumption_reading_filter
from app.schemas.usage import DailyUsage, HourlyUsage, UsageSummary, WeeklyUsage
from app.services.tariff import (
    OFF_PEAK_END_HOUR,
    OFF_PEAK_START_HOUR,
    PEAK_END_HOUR,
    PEAK_START_HOUR,
    TouPeriod,
    classify_interval_tou_period,
    local_interval_end_date,
    market_bounds_for_local_dates,
    market_interval_start_to_local,
    split_readings_by_period,
)


def _ensure_date(value: date | str) -> date:
    """Convert string to date if needed (SQLite returns strings)."""
    if isinstance(value, str):
        return date.fromisoformat(value)
    return value


class UsageAnalyzer:
    """Service for analyzing energy usage data."""

    # Victorian TOU period boundaries, sourced from the shared tariff module so the
    # analyzer never diverges from billing/forecasting.
    PEAK_START = PEAK_START_HOUR  # 3pm
    PEAK_END = PEAK_END_HOUR  # 9pm
    OFF_PEAK_START = OFF_PEAK_START_HOUR  # 10pm
    OFF_PEAK_END = OFF_PEAK_END_HOUR  # 7am

    def __init__(self, db: Session):
        self.db = db

    def get_daily_usage(
        self,
        meter_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 30,
    ) -> list[DailyUsage]:
        """Get daily usage aggregations for a meter.

        Args:
            meter_id: The meter ID
            start_date: Start date (defaults to 30 days ago)
            end_date: End date (defaults to today)
            limit: Maximum number of days to return

        Returns:
            List of daily usage data
        """
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=limit)

        meter = self.db.query(Meter).filter(Meter.id == meter_id).first()
        if meter is None:
            return []

        market_start, market_end = market_bounds_for_local_dates(
            start_date, end_date, meter.state
        )
        readings = (
            self.db.query(Reading)
            .filter(
                Reading.meter_id == meter_id,
                consumption_reading_filter(),
                Reading.timestamp > market_start,
                Reading.timestamp <= market_end,
            )
            .all()
        )
        daily: dict[date, dict[str, float]] = defaultdict(
            lambda: {
                "total": 0.0,
                "max": 0.0,
                "peak": 0.0,
                "off_peak": 0.0,
                "shoulder": 0.0,
            }
        )
        for reading in readings:
            if reading.timestamp is None:
                continue
            day_data = daily[local_interval_end_date(reading.timestamp, meter.state)]
            day_data["total"] += reading.value
            day_data["max"] = max(day_data["max"], reading.value)
            period = classify_interval_tou_period(
                reading.timestamp, reading.interval_minutes, meter.state
            )
            day_data[period.value] += reading.value

        return [
            DailyUsage(
                date=day,
                total_kwh=round(data["total"], 3),
                peak_kwh=round(data["peak"], 3),
                off_peak_kwh=round(data["off_peak"], 3),
                shoulder_kwh=round(data["shoulder"], 3),
                max_interval_kwh=round(data["max"], 3),
                estimated_cost=None,
            )
            for day, data in sorted(daily.items(), reverse=True)[:limit]
        ]

    def _batch_tou_breakdown(
        self, readings: list[Reading], state: str = "VIC"
    ) -> dict[date, dict[str, float]]:
        """Bucket interval energy by local end date and local-start tariff period."""
        result: dict[date, dict[str, float]] = defaultdict(
            lambda: {"peak": 0.0, "off_peak": 0.0, "shoulder": 0.0}
        )
        for reading in readings:
            if reading.timestamp is None:
                continue
            day = local_interval_end_date(reading.timestamp, state)
            period = classify_interval_tou_period(
                reading.timestamp, reading.interval_minutes, state
            )
            result[day][period.value] += reading.value
        return dict(result)

    def _get_tou_breakdown(self, meter_id: int, day: date | str) -> dict[str, float]:
        """Get weekday-aware Time-of-Use breakdown for a specific day."""
        day = _ensure_date(day)
        meter = self.db.query(Meter).filter(Meter.id == meter_id).first()
        if meter is None:
            return {"peak": 0.0, "off_peak": 0.0, "shoulder": 0.0}
        start, end = market_bounds_for_local_dates(day, day, meter.state)

        readings = (
            self.db.query(Reading)
            .filter(
                Reading.meter_id == meter_id,
                consumption_reading_filter(),
                Reading.timestamp > start,
                Reading.timestamp <= end,
            )
            .all()
        )

        buckets = split_readings_by_period(readings, meter.state)
        return {
            "peak": buckets[TouPeriod.PEAK],
            "off_peak": buckets[TouPeriod.OFF_PEAK],
            "shoulder": buckets[TouPeriod.SHOULDER],
        }

    def get_hourly_usage(
        self,
        meter_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[HourlyUsage]:
        """Get average hourly usage pattern.

        Returns the average consumption for each hour of the day (0-23).
        """
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=30)

        meter = self.db.query(Meter).filter(Meter.id == meter_id).first()
        if meter is None:
            return []
        market_start, market_end = market_bounds_for_local_dates(
            start_date, end_date, meter.state
        )
        readings = (
            self.db.query(Reading)
            .filter(
                Reading.meter_id == meter_id,
                consumption_reading_filter(),
                Reading.timestamp > market_start,
                Reading.timestamp <= market_end,
            )
            .all()
        )
        hourly: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for reading in readings:
            hour = market_interval_start_to_local(
                reading.timestamp, reading.interval_minutes, meter.state
            ).hour
            hourly[hour][0] += reading.value
            hourly[hour][1] += 1
        return [
            HourlyUsage(
                hour=hour,
                avg_kwh=round(total / count, 4),
                total_kwh=round(total, 3),
                reading_count=int(count),
            )
            for hour, (total, count) in sorted(hourly.items())
        ]

    def get_weekly_usage(
        self,
        meter_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[WeeklyUsage]:
        """Get average usage by day of week."""
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=90)  # 3 months for better pattern

        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        meter = self.db.query(Meter).filter(Meter.id == meter_id).first()
        if meter is None:
            return []
        market_start, market_end = market_bounds_for_local_dates(
            start_date, end_date, meter.state
        )
        readings = (
            self.db.query(Reading)
            .filter(
                Reading.meter_id == meter_id,
                consumption_reading_filter(),
                Reading.timestamp > market_start,
                Reading.timestamp <= market_end,
            )
            .all()
        )
        weekly: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for reading in readings:
            weekday = market_interval_start_to_local(
                reading.timestamp, reading.interval_minutes, meter.state
            ).weekday()
            weekly[weekday][0] += reading.value
            weekly[weekday][1] += 1
        return [
                WeeklyUsage(
                    day_of_week=weekday,
                    day_name=day_names[weekday],
                    avg_kwh=round(total / count, 4),
                    total_kwh=round(total, 3),
                )
            for weekday, (total, count) in sorted(weekly.items())
        ]

    def get_usage_summary(
        self,
        meter_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> UsageSummary | None:
        """Get comprehensive usage summary for a meter."""
        meter = self.db.query(Meter).filter(Meter.id == meter_id).first()
        if not meter:
            return None

        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=30)

        market_start, market_end = market_bounds_for_local_dates(
            start_date, end_date, meter.state
        )
        readings = (
            self.db.query(Reading)
            .filter(
                Reading.meter_id == meter_id,
                consumption_reading_filter(),
                Reading.timestamp > market_start,
                Reading.timestamp <= market_end,
            )
            .all()
        )
        if not readings:
            return None

        total_kwh = sum(reading.value for reading in readings)
        daily_totals_by_date: dict[date, float] = defaultdict(float)
        for reading in readings:
            local_day = local_interval_end_date(reading.timestamp, meter.state)
            daily_totals_by_date[local_day] += reading.value
        daily_totals = list(daily_totals_by_date.values())
        days_count = len(daily_totals)

        if days_count == 0:
            return None

        # Get peak hour
        hourly = self.get_hourly_usage(meter_id, start_date, end_date)
        peak_hour_data = max(hourly, key=lambda x: x.avg_kwh) if hourly else None

        # Calculate off-peak percentage
        off_peak_total = sum(
            h.total_kwh for h in hourly if h.hour >= self.OFF_PEAK_START or h.hour < self.OFF_PEAK_END
        )
        off_peak_pct = (off_peak_total / total_kwh * 100) if total_kwh > 0 else 0

        return UsageSummary(
            meter_id=meter_id,
            meter_name=meter.name,
            nmi=meter.nmi,
            start_date=min(reading.timestamp for reading in readings),
            end_date=max(reading.timestamp for reading in readings),
            days_count=days_count,
            total_kwh=round(total_kwh, 3),
            avg_daily_kwh=round(total_kwh / days_count, 3),
            max_daily_kwh=round(max(daily_totals), 3),
            min_daily_kwh=round(min(daily_totals), 3),
            peak_hour=peak_hour_data.hour if peak_hour_data else 18,
            peak_avg_kwh=round(peak_hour_data.avg_kwh, 4) if peak_hour_data else 0,
            off_peak_percentage=round(off_peak_pct, 1),
            estimated_total_cost=None,
            estimated_daily_cost=None,
        )
