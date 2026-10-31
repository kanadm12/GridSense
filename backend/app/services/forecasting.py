"""Bill forecasting service using time series analysis."""

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.meter import Meter
from app.models.reading import Reading, consumption_reading_filter
from app.services.tariff import (
    local_interval_end_date,
    market_bounds_for_local_dates,
    timezone_for_state,
)


class BillForecaster:
    """Projects end-of-month usage; tariff-backed bill pricing is not implemented."""

    def __init__(self, db: Session):
        """Initialize the forecaster with database session."""
        self.db = db

    def forecast_monthly_bill(
        self,
        meter_id: int,
        target_month: date | None = None,
    ) -> dict[str, Any]:
        """Forecast the bill for a target month.

        Args:
            meter_id: The meter ID to forecast
            target_month: The month to forecast (defaults to current)

        Returns:
            Dictionary with forecast details
        """
        meter_state = (
            self.db.query(Meter.state).filter(Meter.id == meter_id).scalar()
        )
        if meter_state is None:
            raise ValueError(f"Meter {meter_id} was not found; cannot determine tariff timezone")
        today = datetime.now(timezone_for_state(meter_state)).date()
        if target_month is None:
            target_month = today

        # Get first and last day of month
        first_day = target_month.replace(day=1)
        if target_month.month == 12:
            last_day = (
                target_month.replace(year=target_month.year + 1, month=1, day=1)
                - timedelta(days=1)
            )
        else:
            last_day = (
                target_month.replace(month=target_month.month + 1, day=1)
                - timedelta(days=1)
            )
        
        days_in_month = (last_day - first_day).days + 1
        days_elapsed = min(max((today - first_day).days + 1, 0), days_in_month)
        days_remaining = days_in_month - days_elapsed

        # Get readings for current month so far
        current_end = min(today, last_day)
        readings_so_far = []
        if current_end >= first_day:
            market_start, market_end = market_bounds_for_local_dates(
                first_day, current_end, meter_state
            )
            readings_so_far = (
                self.db.query(Reading)
                .filter(
                    Reading.meter_id == meter_id,
                    consumption_reading_filter(),
                    Reading.timestamp > market_start,
                    Reading.timestamp <= market_end,
                )
                .all()
            )

        # Calculate usage so far. Cost is omitted rather than priced with a default rate.
        usage_so_far = sum(r.value for r in readings_so_far)

        # Get historical data for same period last month
        previous_month_end = first_day - timedelta(days=1)
        previous_month_start = previous_month_end.replace(day=1)
        historical_start, historical_end = market_bounds_for_local_dates(
            previous_month_start, previous_month_end, meter_state
        )
        historical_readings = (
            self.db.query(Reading)
            .filter(
                Reading.meter_id == meter_id,
                consumption_reading_filter(),
                Reading.timestamp > historical_start,
                Reading.timestamp <= historical_end,
            )
            .all()
        )

        # Calculate historical daily average
        if historical_readings:
            historical_total = sum(r.value for r in historical_readings)
            historical_days = (previous_month_end - previous_month_start).days + 1
            historical_daily_avg = historical_total / historical_days
        else:
            # Fallback to this month's average
            historical_daily_avg = usage_so_far / max(days_elapsed, 1)

        # Calculate current month's daily average
        current_daily_avg = usage_so_far / max(days_elapsed, 1) if days_elapsed > 0 else 0

        # Weighted average of current and historical patterns
        # More weight to current as month progresses
        current_weight = days_elapsed / days_in_month
        projected_daily_avg = (
            current_weight * current_daily_avg + 
            (1 - current_weight) * historical_daily_avg
        )

        # Project remaining usage
        projected_remaining_usage = projected_daily_avg * days_remaining

        projected_total_usage = usage_so_far + projected_remaining_usage

        return {
            "meter_id": meter_id,
            "month": target_month.strftime("%Y-%m"),
            "days_in_month": days_in_month,
            "days_elapsed": days_elapsed,
            "days_remaining": days_remaining,
            "usage_so_far_kwh": round(usage_so_far, 2),
            "cost_so_far": None,
            "projected_total_kwh": round(projected_total_usage, 2),
            "projected_total_cost": None,
            "projected_cost_low": None,
            "projected_cost_high": None,
            "daily_average_kwh": round(current_daily_avg, 2),
            "confidence_level": None,
        }

    def get_bill_trend(
        self,
        meter_id: int,
        months: int = 6,
    ) -> list[dict[str, Any]]:
        """Get historical bill data for trend analysis.

        Args:
            meter_id: The meter ID
            months: Number of months to look back

        Returns:
            List of monthly bill summaries
        """
        results = []
        state = self.db.query(Meter.state).filter(Meter.id == meter_id).scalar()
        if state is None:
            raise ValueError(f"Meter {meter_id} was not found; cannot determine tariff timezone")
        today = datetime.now(timezone_for_state(state)).date()

        for i in range(months):
            # Calculate target month
            target = today.replace(day=1) - timedelta(days=30 * i)
            first_day = target.replace(day=1)
            
            if target.month == 12:
                last_day = target.replace(year=target.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                last_day = target.replace(month=target.month + 1, day=1) - timedelta(days=1)

            # Get readings for this month
            market_start, market_end = market_bounds_for_local_dates(
                first_day, last_day, state
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

            if readings:
                total_kwh = sum(r.value for r in readings)

                results.append({
                    "month": first_day.strftime("%Y-%m"),
                    "total_kwh": round(total_kwh, 2),
                    "total_cost": None,
                    "days_with_data": len(
                        {
                            local_interval_end_date(reading.timestamp, state)
                            for reading in readings
                            if reading.timestamp is not None
                        }
                    ),
                })

        return list(reversed(results))


def get_forecaster(db: Session) -> BillForecaster:
    """Factory function to create a bill forecaster instance."""
    return BillForecaster(db)
