"""Usage analyzer service for calculating consumption metrics."""

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, extract
from sqlalchemy.orm import Session

from app.models.meter import Meter
from app.models.reading import Reading
from app.schemas.usage import DailyUsage, HourlyUsage, UsageSummary, WeeklyUsage
from app.services.tariff import (
    DEFAULT_FLAT_RATE,
    OFF_PEAK_END_HOUR,
    OFF_PEAK_START_HOUR,
    PEAK_END_HOUR,
    PEAK_START_HOUR,
    TouPeriod,
    classify_tou_period,
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

    # Flat rate estimate ($/kWh) - Victorian average
    FLAT_RATE = DEFAULT_FLAT_RATE  # $0.25 per kWh

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

        # Query for daily aggregations
        query = (
            self.db.query(
                func.date(Reading.timestamp).label("date"),
                func.sum(Reading.value).label("total_kwh"),
                func.max(Reading.value).label("max_interval_kwh"),
            )
            .filter(
                Reading.meter_id == meter_id,
                Reading.timestamp >= datetime.combine(start_date, datetime.min.time()),
                Reading.timestamp <= datetime.combine(end_date, datetime.max.time()),
            )
            .group_by(func.date(Reading.timestamp))
            .order_by(func.date(Reading.timestamp).desc())
            .limit(limit)
        )

        results = query.all()
        
        if not results:
            return []

        # Batch fetch all readings for TOU breakdown (avoids N+1 query)
        date_values = [_ensure_date(row.date) for row in results]
        min_date = min(date_values)
        max_date = max(date_values)
        
        all_readings = (
            self.db.query(Reading)
            .filter(
                Reading.meter_id == meter_id,
                Reading.timestamp >= datetime.combine(min_date, datetime.min.time()),
                Reading.timestamp <= datetime.combine(max_date, datetime.max.time()),
            )
            .all()
        )
        
        # Group readings by date and calculate TOU breakdown
        tou_by_date = self._batch_tou_breakdown(all_readings)
        
        daily_usage = []
        for row in results:
            day = _ensure_date(row.date)
            tou_data = tou_by_date.get(day, {"peak": 0.0, "off_peak": 0.0, "shoulder": 0.0})

            daily_usage.append(
                DailyUsage(
                    date=day,
                    total_kwh=round(row.total_kwh, 3),
                    peak_kwh=round(tou_data["peak"], 3),
                    off_peak_kwh=round(tou_data["off_peak"], 3),
                    shoulder_kwh=round(tou_data["shoulder"], 3),
                    max_interval_kwh=round(row.max_interval_kwh, 3),
                    estimated_cost=round(row.total_kwh * self.FLAT_RATE, 2),
                )
            )

        return daily_usage

    def _batch_tou_breakdown(self, readings: list[Reading]) -> dict[date, dict[str, float]]:
        """Calculate weekday-aware TOU breakdown for multiple days from a batch of readings."""
        result: dict[date, dict[str, float]] = defaultdict(
            lambda: {"peak": 0.0, "off_peak": 0.0, "shoulder": 0.0}
        )

        for reading in readings:
            if reading.timestamp is None:
                continue
            day = reading.timestamp.date()
            period = classify_tou_period(reading.timestamp)
            result[day][period.value] += reading.value

        return dict(result)

    def _get_tou_breakdown(self, meter_id: int, day: date | str) -> dict[str, float]:
        """Get weekday-aware Time-of-Use breakdown for a specific day."""
        day = _ensure_date(day)
        start = datetime.combine(day, datetime.min.time())
        end = datetime.combine(day, datetime.max.time())

        readings = (
            self.db.query(Reading)
            .filter(
                Reading.meter_id == meter_id,
                Reading.timestamp >= start,
                Reading.timestamp <= end,
            )
            .all()
        )

        buckets = split_readings_by_period(readings)
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

        query = (
            self.db.query(
                extract("hour", Reading.timestamp).label("hour"),
                func.avg(Reading.value).label("avg_kwh"),
                func.sum(Reading.value).label("total_kwh"),
                func.count(Reading.id).label("reading_count"),
            )
            .filter(
                Reading.meter_id == meter_id,
                Reading.timestamp >= datetime.combine(start_date, datetime.min.time()),
                Reading.timestamp <= datetime.combine(end_date, datetime.max.time()),
            )
            .group_by(extract("hour", Reading.timestamp))
            .order_by(extract("hour", Reading.timestamp))
        )

        results = query.all()

        return [
            HourlyUsage(
                hour=int(row.hour),
                avg_kwh=round(row.avg_kwh, 4),
                total_kwh=round(row.total_kwh, 3),
                reading_count=row.reading_count,
            )
            for row in results
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

        query = (
            self.db.query(
                extract("dow", Reading.timestamp).label("day_of_week"),
                func.avg(Reading.value).label("avg_kwh"),
                func.sum(Reading.value).label("total_kwh"),
            )
            .filter(
                Reading.meter_id == meter_id,
                Reading.timestamp >= datetime.combine(start_date, datetime.min.time()),
                Reading.timestamp <= datetime.combine(end_date, datetime.max.time()),
            )
            .group_by(extract("dow", Reading.timestamp))
            .order_by(extract("dow", Reading.timestamp))
        )

        results = query.all()

        # Map results (PostgreSQL dow: 0=Sunday, 1=Monday, ...)
        weekly_data = []
        for row in results:
            dow = int(row.day_of_week)
            # Convert to Python weekday (0=Monday)
            python_dow = (dow - 1) % 7
            weekly_data.append(
                WeeklyUsage(
                    day_of_week=python_dow,
                    day_name=day_names[python_dow],
                    avg_kwh=round(row.avg_kwh, 4),
                    total_kwh=round(row.total_kwh, 3),
                )
            )

        return sorted(weekly_data, key=lambda x: x.day_of_week)

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

        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        # Get overall stats
        overall = (
            self.db.query(
                func.sum(Reading.value).label("total"),
                func.min(Reading.timestamp).label("min_ts"),
                func.max(Reading.timestamp).label("max_ts"),
            )
            .filter(
                Reading.meter_id == meter_id,
                Reading.timestamp >= start_dt,
                Reading.timestamp <= end_dt,
            )
            .first()
        )

        if not overall or overall.total is None:
            return None

        # Get daily stats
        daily_stats = (
            self.db.query(
                func.date(Reading.timestamp).label("date"),
                func.sum(Reading.value).label("daily_total"),
            )
            .filter(
                Reading.meter_id == meter_id,
                Reading.timestamp >= start_dt,
                Reading.timestamp <= end_dt,
            )
            .group_by(func.date(Reading.timestamp))
            .all()
        )

        daily_totals = [row.daily_total for row in daily_stats]
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
        off_peak_pct = (off_peak_total / overall.total * 100) if overall.total > 0 else 0

        return UsageSummary(
            meter_id=meter_id,
            meter_name=meter.name,
            nmi=meter.nmi,
            start_date=overall.min_ts,
            end_date=overall.max_ts,
            days_count=days_count,
            total_kwh=round(overall.total, 3),
            avg_daily_kwh=round(overall.total / days_count, 3),
            max_daily_kwh=round(max(daily_totals), 3),
            min_daily_kwh=round(min(daily_totals), 3),
            peak_hour=peak_hour_data.hour if peak_hour_data else 18,
            peak_avg_kwh=round(peak_hour_data.avg_kwh, 4) if peak_hour_data else 0,
            off_peak_percentage=round(off_peak_pct, 1),
            estimated_total_cost=round(overall.total * self.FLAT_RATE, 2),
            estimated_daily_cost=round(overall.total / days_count * self.FLAT_RATE, 2),
        )
