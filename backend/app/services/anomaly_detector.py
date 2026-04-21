"""Anomaly detection service for identifying unusual energy patterns."""

from collections import defaultdict
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.reading import Reading


class AnomalyType(str, Enum):
    """Types of energy usage anomalies."""
    DAILY_SPIKE = "daily_spike"
    OVERNIGHT_USAGE = "overnight_usage"
    UNUSUAL_PATTERN = "unusual_pattern"
    PEAK_HEAVY = "peak_heavy"
    APPLIANCE_LEFT_ON = "appliance_left_on"


class AnomalyDetector:
    """Detects anomalies in energy usage patterns."""

    # Thresholds for anomaly detection
    Z_SCORE_THRESHOLD = 2.5  # Standard deviations from mean
    OVERNIGHT_THRESHOLD = 0.5  # kWh per hour threshold for overnight
    PEAK_RATIO_THRESHOLD = 0.6  # If >60% usage during peak, flag it

    def __init__(self, db: Session):
        """Initialize the anomaly detector with database session."""
        self.db = db

    def _calculate_z_score(self, value: float, mean: float, std: float) -> float:
        """Calculate z-score for a value."""
        if std == 0:
            return 0.0
        return (value - mean) / std

    def detect_daily_spikes(
        self,
        meter_id: int,
        lookback_days: int = 30,
    ) -> list[dict[str, Any]]:
        """Detect days with unusually high usage.

        Args:
            meter_id: The meter ID to analyze
            lookback_days: Number of days to analyze

        Returns:
            List of anomaly dictionaries
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=lookback_days)

        # Get daily totals
        daily_totals = (
            self.db.query(
                func.date(Reading.timestamp).label("date"),
                func.sum(Reading.kwh).label("total_kwh"),
            )
            .filter(
                Reading.meter_id == meter_id,
                Reading.timestamp >= start_date,
                Reading.timestamp <= end_date,
            )
            .group_by(func.date(Reading.timestamp))
            .all()
        )

        if len(daily_totals) < 7:
            return []  # Not enough data

        # Calculate statistics
        values = [row.total_kwh for row in daily_totals]
        mean = np.mean(values)
        std = np.std(values)

        anomalies = []
        for row in daily_totals:
            z_score = self._calculate_z_score(row.total_kwh, mean, std)
            
            if z_score > self.Z_SCORE_THRESHOLD:
                # Determine percentage above normal
                pct_above = ((row.total_kwh - mean) / mean) * 100 if mean > 0 else 0
                
                anomalies.append({
                    "type": AnomalyType.DAILY_SPIKE,
                    "date": str(row.date),
                    "value_kwh": round(row.total_kwh, 2),
                    "expected_kwh": round(mean, 2),
                    "z_score": round(z_score, 2),
                    "severity": "high" if z_score > 3.5 else "medium",
                    "message": f"Usage was {pct_above:.0f}% higher than usual ({row.total_kwh:.1f} kWh vs {mean:.1f} kWh average)",
                    "suggestions": [
                        "Check if you had guests or unusual activity",
                        "Look for appliances that may have been left on",
                        "Consider if weather changes caused increased HVAC usage",
                    ],
                })

        return anomalies

    def detect_overnight_usage(
        self,
        meter_id: int,
        lookback_days: int = 7,
    ) -> list[dict[str, Any]]:
        """Detect unusually high overnight usage (possible appliance left on).

        Args:
            meter_id: The meter ID to analyze
            lookback_days: Number of days to analyze

        Returns:
            List of anomaly dictionaries
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=lookback_days)

        # Get overnight readings (midnight to 6am)
        overnight_readings = (
            self.db.query(Reading)
            .filter(
                Reading.meter_id == meter_id,
                Reading.timestamp >= start_date,
                Reading.timestamp <= end_date,
            )
            .all()
        )

        # Filter to overnight hours and group by night
        nightly_usage: dict[date, float] = defaultdict(float)
        nightly_readings: dict[date, int] = defaultdict(int)
        
        for r in overnight_readings:
            if r.timestamp and 0 <= r.timestamp.hour < 6:
                night_date = r.timestamp.date()
                nightly_usage[night_date] += r.kwh
                nightly_readings[night_date] += 1

        anomalies = []
        for night_date, total_kwh in nightly_usage.items():
            readings_count = nightly_readings[night_date]
            if readings_count == 0:
                continue
                
            # Calculate hourly rate
            hours = readings_count * 0.5  # 30-min readings
            hourly_rate = total_kwh / hours if hours > 0 else 0

            if hourly_rate > self.OVERNIGHT_THRESHOLD:
                anomalies.append({
                    "type": AnomalyType.OVERNIGHT_USAGE,
                    "date": str(night_date),
                    "value_kwh": round(total_kwh, 2),
                    "hourly_rate_kwh": round(hourly_rate, 2),
                    "severity": "medium",
                    "message": f"High overnight usage detected: {hourly_rate:.2f} kWh/hour average between midnight and 6am",
                    "suggestions": [
                        "Check if heating/cooling was running all night",
                        "Look for appliances on standby (TV, gaming consoles)",
                        "A pool pump or hot water system might be scheduled incorrectly",
                    ],
                })

        return anomalies

    def detect_peak_heavy_usage(
        self,
        meter_id: int,
        lookback_days: int = 7,
    ) -> list[dict[str, Any]]:
        """Detect days where most usage occurred during peak hours.

        Args:
            meter_id: The meter ID to analyze
            lookback_days: Number of days to analyze

        Returns:
            List of anomaly dictionaries
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=lookback_days)

        # Get all readings
        readings = (
            self.db.query(Reading)
            .filter(
                Reading.meter_id == meter_id,
                Reading.timestamp >= start_date,
                Reading.timestamp <= end_date,
            )
            .all()
        )

        # Group by day and calculate peak ratio
        daily_usage: dict[date, dict[str, float]] = defaultdict(lambda: {"peak": 0, "total": 0})
        
        for r in readings:
            if r.timestamp:
                day = r.timestamp.date()
                hour = r.timestamp.hour
                weekday = r.timestamp.weekday()
                
                daily_usage[day]["total"] += r.kwh
                
                # Peak is 3pm-9pm on weekdays
                if weekday < 5 and 15 <= hour < 21:
                    daily_usage[day]["peak"] += r.kwh

        anomalies = []
        for day, usage in daily_usage.items():
            if usage["total"] == 0:
                continue
                
            peak_ratio = usage["peak"] / usage["total"]
            
            if peak_ratio > self.PEAK_RATIO_THRESHOLD:
                extra_cost = usage["peak"] * (0.38 - 0.18)  # Peak vs off-peak difference
                
                anomalies.append({
                    "type": AnomalyType.PEAK_HEAVY,
                    "date": str(day),
                    "peak_usage_kwh": round(usage["peak"], 2),
                    "total_usage_kwh": round(usage["total"], 2),
                    "peak_ratio": round(peak_ratio, 2),
                    "severity": "low",
                    "message": f"{peak_ratio*100:.0f}% of your usage on {day} was during peak hours (3-9pm)",
                    "extra_cost": round(extra_cost, 2),
                    "suggestions": [
                        "Shift dishwasher and laundry to after 10pm",
                        "Pre-cool your home before 3pm",
                        "Consider a smart plug to delay appliance start times",
                    ],
                })

        return anomalies

    def get_all_anomalies(
        self,
        meter_id: int,
        lookback_days: int = 30,
    ) -> dict[str, Any]:
        """Run all anomaly detection checks.

        Args:
            meter_id: The meter ID to analyze
            lookback_days: Number of days to analyze

        Returns:
            Dictionary with all anomaly results
        """
        daily_spikes = self.detect_daily_spikes(meter_id, lookback_days)
        overnight = self.detect_overnight_usage(meter_id, min(lookback_days, 7))
        peak_heavy = self.detect_peak_heavy_usage(meter_id, min(lookback_days, 7))

        all_anomalies = daily_spikes + overnight + peak_heavy
        
        # Sort by severity
        severity_order = {"high": 0, "medium": 1, "low": 2}
        all_anomalies.sort(key=lambda x: (severity_order.get(x.get("severity", "low"), 2), x.get("date", "")))

        return {
            "meter_id": meter_id,
            "analysis_period_days": lookback_days,
            "total_anomalies": len(all_anomalies),
            "high_severity_count": sum(1 for a in all_anomalies if a.get("severity") == "high"),
            "medium_severity_count": sum(1 for a in all_anomalies if a.get("severity") == "medium"),
            "low_severity_count": sum(1 for a in all_anomalies if a.get("severity") == "low"),
            "anomalies": all_anomalies,
        }


def get_anomaly_detector(db: Session) -> AnomalyDetector:
    """Factory function to create an anomaly detector instance."""
    return AnomalyDetector(db)
