"""Bill forecasting service using time series analysis."""

from datetime import date, timedelta
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.models.meter import Meter
from app.models.reading import Reading
from app.services.tariff import (
    DEFAULT_SUPPLY_CHARGE,
    DEFAULT_TOU_RATES,
    classify_tou_period,
)


class BillForecaster:
    """Forecasts end-of-month bill based on usage patterns."""

    # Victorian TOU rates and supply charge, sourced from the shared tariff module so
    # every feature prices intervals identically.
    RATES = DEFAULT_TOU_RATES
    DAILY_SUPPLY_CHARGE = DEFAULT_SUPPLY_CHARGE  # $/day

    def __init__(self, db: Session):
        """Initialize the forecaster with database session."""
        self.db = db

    def _calculate_daily_cost(self, readings: list[Reading]) -> float:
        """Calculate cost for a day's readings."""
        total_cost = 0.0

        for reading in readings:
            if reading.timestamp:
                period = classify_tou_period(reading.timestamp)
                total_cost += reading.value * self.RATES[period]

        return total_cost + self.DAILY_SUPPLY_CHARGE

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
        if target_month is None:
            target_month = date.today()

        # Get first and last day of month
        first_day = target_month.replace(day=1)
        if target_month.month == 12:
            last_day = target_month.replace(year=target_month.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            last_day = target_month.replace(month=target_month.month + 1, day=1) - timedelta(days=1)
        
        days_in_month = (last_day - first_day).days + 1
        days_elapsed = min((date.today() - first_day).days + 1, days_in_month)
        days_remaining = days_in_month - days_elapsed

        # Get readings for current month so far
        readings_so_far = (
            self.db.query(Reading)
            .filter(
                Reading.meter_id == meter_id,
                Reading.timestamp >= first_day,
                Reading.timestamp < date.today() + timedelta(days=1),
            )
            .all()
        )

        # Calculate usage so far
        usage_so_far = sum(r.value for r in readings_so_far)
        cost_so_far = 0.0
        
        # Group by day for cost calculation
        from collections import defaultdict
        daily_readings: dict[date, list[Reading]] = defaultdict(list)
        for r in readings_so_far:
            if r.timestamp:
                daily_readings[r.timestamp.date()].append(r)
        
        for day_readings in daily_readings.values():
            cost_so_far += self._calculate_daily_cost(day_readings)

        # Get historical data for same period last month
        last_month = first_day - timedelta(days=30)
        historical_readings = (
            self.db.query(Reading)
            .filter(
                Reading.meter_id == meter_id,
                Reading.timestamp >= last_month,
                Reading.timestamp < first_day,
            )
            .all()
        )

        # Calculate historical daily average
        if historical_readings:
            historical_total = sum(r.value for r in historical_readings)
            historical_days = 30
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
        projected_remaining_cost = (
            projected_remaining_usage * 0.27 +  # Average rate
            days_remaining * self.DAILY_SUPPLY_CHARGE
        )

        # Calculate totals
        projected_total_usage = usage_so_far + projected_remaining_usage
        projected_total_cost = cost_so_far + projected_remaining_cost

        # Calculate confidence interval (wider with less data)
        std_dev = max(current_daily_avg * 0.2, 1.0)  # 20% std dev
        confidence_margin = 1.96 * std_dev * np.sqrt(days_remaining)  # 95% CI

        return {
            "meter_id": meter_id,
            "month": target_month.strftime("%Y-%m"),
            "days_in_month": days_in_month,
            "days_elapsed": days_elapsed,
            "days_remaining": days_remaining,
            "usage_so_far_kwh": round(usage_so_far, 2),
            "cost_so_far": round(cost_so_far, 2),
            "projected_total_kwh": round(projected_total_usage, 2),
            "projected_total_cost": round(projected_total_cost, 2),
            "projected_cost_low": round(max(projected_total_cost - confidence_margin * 0.27, cost_so_far), 2),
            "projected_cost_high": round(projected_total_cost + confidence_margin * 0.27, 2),
            "daily_average_kwh": round(current_daily_avg, 2),
            "confidence_level": 0.95,
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
        today = date.today()

        for i in range(months):
            # Calculate target month
            target = today.replace(day=1) - timedelta(days=30 * i)
            first_day = target.replace(day=1)
            
            if target.month == 12:
                last_day = target.replace(year=target.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                last_day = target.replace(month=target.month + 1, day=1) - timedelta(days=1)

            # Get readings for this month
            readings = (
                self.db.query(Reading)
                .filter(
                    Reading.meter_id == meter_id,
                    Reading.timestamp >= first_day,
                    Reading.timestamp <= last_day,
                )
                .all()
            )

            if readings:
                total_kwh = sum(r.value for r in readings)
                
                # Group by day for cost calculation
                from collections import defaultdict
                daily_readings: dict[date, list[Reading]] = defaultdict(list)
                for r in readings:
                    if r.timestamp:
                        daily_readings[r.timestamp.date()].append(r)
                
                total_cost = sum(
                    self._calculate_daily_cost(day_readings) 
                    for day_readings in daily_readings.values()
                )

                results.append({
                    "month": first_day.strftime("%Y-%m"),
                    "total_kwh": round(total_kwh, 2),
                    "total_cost": round(total_cost, 2),
                    "days_with_data": len(daily_readings),
                })

        return list(reversed(results))


def get_forecaster(db: Session) -> BillForecaster:
    """Factory function to create a bill forecaster instance."""
    return BillForecaster(db)
