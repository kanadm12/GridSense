"""Anomaly detection service for identifying unusual energy patterns."""

from collections import defaultdict
from datetime import date, timedelta
from enum import Enum
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.models.reading import Reading, measured_import_reading_filter
from app.services.tariff import is_peak, market_interval_start_to_local
from app.services.usage_analyzer import UsageAnalyzer


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

    def _complete_measured_days(
        self, meter_id: int, start_date: date, end_date: date
    ) -> set[date]:
        daily = UsageAnalyzer(self.db).get_daily_usage(
            meter_id=meter_id,
            start_date=start_date,
            end_date=end_date,
            limit=max((end_date - start_date).days + 1, 1),
        )
        return {
            row.date
            for row in daily
            if row.coverage_status == "complete"
            and row.provenance_status == "measured"
            and row.unresolved_direction_count == 0
            and row.legacy_direction_unverified_count == 0
        }

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
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=lookback_days - 1)
        complete_days = self._complete_measured_days(meter_id, start_date, end_date)
        daily_totals = [
            row
            for row in UsageAnalyzer(self.db).get_daily_usage(
                meter_id=meter_id,
                start_date=start_date,
                end_date=end_date,
                limit=lookback_days,
            )
            if row.date in complete_days
        ]

        if len(daily_totals) < 7:
            return []  # Not enough data

        # Calculate statistics
        values = [row.observed_eligible_kwh for row in daily_totals]
        mean = np.mean(values)
        std = np.std(values)

        anomalies = []
        for row in daily_totals:
            z_score = self._calculate_z_score(row.observed_eligible_kwh, mean, std)

            if z_score > self.Z_SCORE_THRESHOLD:
                # Determine percentage above normal
                pct_above = (
                    (row.observed_eligible_kwh - mean) / mean * 100 if mean > 0 else 0
                )

                anomalies.append({
                    "type": AnomalyType.DAILY_SPIKE,
                    "date": str(row.date),
                    "value_kwh": round(row.observed_eligible_kwh, 2),
                    "expected_kwh": round(mean, 2),
                    "z_score": round(z_score, 2),
                    "severity": "high" if z_score > 3.5 else "medium",
                    "message": (
                        f"Eligible import was {pct_above:.0f}% above the mean of "
                        f"complete measured days ({row.observed_eligible_kwh:.1f} "
                        f"kWh vs {mean:.1f} kWh). This does not identify a cause."
                    ),
                    "suggestions": [
                        (
                            "Compare the interval record with your own notes; aggregate "
                            "readings do not identify appliances or causes."
                        ),
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
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=lookback_days - 1)
        complete_days = self._complete_measured_days(meter_id, start_date, end_date)

        # Get overnight readings (midnight to 6am)
        overnight_readings = (
            self.db.query(Reading)
            .filter(
                Reading.meter_id == meter_id,
                measured_import_reading_filter(),
                Reading.timestamp >= start_date,
                Reading.timestamp < end_date + timedelta(days=2),
            )
            .all()
        )

        # Filter to overnight hours and group by night
        nightly_usage: dict[date, float] = defaultdict(float)
        nightly_readings: dict[date, int] = defaultdict(int)

        for r in overnight_readings:
            if r.timestamp:
                local_start = market_interval_start_to_local(
                    r.timestamp, r.interval_minutes, r.meter.state
                )
                night_date = local_start.date()
                if night_date not in complete_days or not 0 <= local_start.hour < 6:
                    continue
                nightly_usage[night_date] += r.value
                nightly_readings[night_date] += r.interval_minutes

        anomalies = []
        for night_date, total_kwh in nightly_usage.items():
            readings_count = nightly_readings[night_date]
            if readings_count == 0:
                continue

            # Calculate hourly rate
            hours = readings_count / 60
            hourly_rate = total_kwh / hours if hours > 0 else 0

            if hourly_rate > self.OVERNIGHT_THRESHOLD:
                anomalies.append({
                    "type": AnomalyType.OVERNIGHT_USAGE,
                    "date": str(night_date),
                    "value_kwh": round(total_kwh, 2),
                    "hourly_rate_kwh": round(hourly_rate, 2),
                    "severity": "medium",
                    "message": (
                        f"Eligible overnight import averaged {hourly_rate:.2f} "
                        "kWh/hour between midnight and 6am."
                    ),
                    "suggestions": [
                        (
                            "Compare eligible overnight intervals with your own notes; "
                            "aggregate readings do not identify devices."
                        ),
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
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=lookback_days - 1)
        complete_days = self._complete_measured_days(meter_id, start_date, end_date)

        # Get all readings
        readings = (
            self.db.query(Reading)
            .filter(
                Reading.meter_id == meter_id,
                measured_import_reading_filter(),
                Reading.timestamp >= start_date,
                Reading.timestamp < end_date + timedelta(days=2),
            )
            .all()
        )

        # Group by day and calculate peak ratio
        daily_usage: dict[date, dict[str, float]] = defaultdict(lambda: {"peak": 0, "total": 0})

        for r in readings:
            if r.timestamp:
                local_start = market_interval_start_to_local(
                    r.timestamp, r.interval_minutes, r.meter.state
                )
                day = local_start.date()
                if day not in complete_days:
                    continue

                daily_usage[day]["total"] += r.value

                # Peak is 3pm-9pm on weekdays (shared Victorian ToU definition)
                if is_peak(r.timestamp, r.interval_minutes, r.meter.state):
                    daily_usage[day]["peak"] += r.value

        anomalies = []
        for day, usage in daily_usage.items():
            if usage["total"] == 0:
                continue

            peak_ratio = usage["peak"] / usage["total"]

            if peak_ratio > self.PEAK_RATIO_THRESHOLD:
                anomalies.append({
                    "type": AnomalyType.PEAK_HEAVY,
                    "date": str(day),
                    "peak_usage_kwh": round(usage["peak"], 2),
                    "total_usage_kwh": round(usage["total"], 2),
                    "peak_ratio": round(peak_ratio, 2),
                    "severity": "low",
                    "message": (
                        f"{peak_ratio*100:.0f}% of eligible import on {day} fell in "
                        "GridSense's shared peak window. This may not match your tariff."
                    ),
                    "extra_cost": None,
                    "suggestions": [
                        (
                            "Check your confirmed tariff and user-declared task "
                            "constraints before considering a schedule change."
                        ),
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
        all_anomalies.sort(
            key=lambda x: (
                severity_order.get(x.get("severity", "low"), 2),
                x.get("date", ""),
            )
        )

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
