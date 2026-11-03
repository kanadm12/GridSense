"""Coverage-aware energy analytics using explicitly eligible intervals."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.meter import Meter
from app.models.reading import Reading
from app.schemas.usage import DailyUsage, HourlyUsage, UsageSummary, WeeklyUsage
from app.services.interval_quality import (
    calculate_coverage,
    evaluate_interval,
    expected_interval_ends_utc,
)
from app.services.tariff import (
    OFF_PEAK_END_HOUR,
    OFF_PEAK_START_HOUR,
    PEAK_END_HOUR,
    PEAK_START_HOUR,
    TouPeriod,
    classify_interval_tou_period,
    timezone_for_state,
)

UTC = timezone.utc


def _ensure_date(value: date | str) -> date:
    """Convert string to date if needed (SQLite returns strings)."""
    if isinstance(value, str):
        return date.fromisoformat(value)
    return value


@dataclass
class _DayMetrics:
    result: DailyUsage


class UsageAnalyzer:
    """Analyze verified imports without treating missing intervals as zero."""

    PEAK_START = PEAK_START_HOUR
    PEAK_END = PEAK_END_HOUR
    OFF_PEAK_START = OFF_PEAK_START_HOUR
    OFF_PEAK_END = OFF_PEAK_END_HOUR

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _local_dates(start_date: date, end_date: date) -> list[date]:
        if end_date < start_date:
            raise ValueError("Usage period end cannot be before its start")
        return [
            start_date + timedelta(days=offset)
            for offset in range((end_date - start_date).days + 1)
        ]

    def _readings_for_window(
        self, meter_id: int, state: str, start_date: date, end_date: date
    ) -> list[Reading]:
        zone = timezone_for_state(state)
        start_utc = datetime.combine(start_date, time.min, tzinfo=zone).astimezone(UTC)
        end_utc = datetime.combine(
            end_date + timedelta(days=1), time.min, tzinfo=zone
        ).astimezone(UTC)
        # Source clocks can be UTC or fixed market time; query a padded range and
        # apply exact UTC-window membership after the source basis is validated.
        query_start = (start_utc - timedelta(days=1)).replace(tzinfo=None)
        query_end = (end_utc + timedelta(days=1)).replace(tzinfo=None)
        return (
            self.db.query(Reading)
            .filter(
                Reading.meter_id == meter_id,
                Reading.timestamp >= query_start,
                Reading.timestamp <= query_end,
            )
            .order_by(Reading.timestamp, Reading.id)
            .all()
        )

    def _daily_metrics(
        self,
        meter: Meter,
        start_date: date,
        end_date: date,
        readings: list[Reading],
    ) -> tuple[list[_DayMetrics], dict[date, list[Reading]], int]:
        dates = self._local_dates(start_date, end_date)
        expected_to_day: dict[datetime, date] = {}
        for day in dates:
            for end_utc in expected_interval_ends_utc(
                day, meter.state, meter.interval_minutes
            ):
                expected_to_day[end_utc] = day

        per_day: dict[date, list[tuple[Reading, object]]] = {
            day: [] for day in dates
        }
        source_time_unresolved = 0
        for reading in readings:
            decision = evaluate_interval(
                reading,
                source_unit=reading.source_unit,
                source_time_basis=reading.source_time_basis,
                provenance_kind=reading.provenance_kind,
            )
            if decision.reason == "unresolved_time_basis":
                source_time_unresolved += 1
                continue
            if decision.end_utc in expected_to_day:
                per_day[expected_to_day[decision.end_utc]].append((reading, decision))

        metrics: list[_DayMetrics] = []
        readings_by_day: dict[date, list[Reading]] = {}
        for day in dates:
            rows = per_day[day]
            day_readings = [reading for reading, _ in rows]
            readings_by_day[day] = day_readings
            coverage = calculate_coverage(
                [day],
                state=meter.state,
                interval_minutes=meter.interval_minutes,
                readings=day_readings,
            )

            slot_rows: dict[
                tuple[datetime, str | None], list[tuple[Reading, object]]
            ] = defaultdict(list)
            for reading, decision in rows:
                if decision.end_utc is not None:
                    slot_rows[(decision.end_utc, reading.direction)].append(
                        (reading, decision)
                    )

            eligible: list[tuple[Reading, float, datetime]] = []
            for same_slot in slot_rows.values():
                if len(same_slot) != 1:
                    continue
                reading, decision = same_slot[0]
                if (
                    decision.eligible
                    and reading.direction == "import"
                    and decision.end_utc is not None
                ):
                    eligible.append(
                        (reading, decision.energy_kwh or 0.0, decision.end_utc)
                    )

            eligible_kwh = sum(value for _, value, _ in eligible)
            eligible_minutes = sum(
                reading.interval_minutes for reading, _, _ in eligible
            )
            observed_average_kw = (
                eligible_kwh / (eligible_minutes / 60) if eligible_minutes else None
            )
            observed_peak_kw = max(
                (
                    value * 60 / reading.interval_minutes
                    for reading, value, _ in eligible
                ),
                default=None,
            )
            tou_totals = {period.value: 0.0 for period in TouPeriod}
            for reading, energy, end_utc in eligible:
                period = classify_interval_tou_period(
                    end_utc,
                    reading.interval_minutes,
                    meter.state,
                )
                tou_totals[period.value] += energy

            day_status = coverage.coverage_status
            if coverage.unresolved_time_basis_count:
                day_status = "unavailable_source_time_basis"
            daily = DailyUsage(
                date=day,
                observed_eligible_kwh=round(eligible_kwh, 3),
                total_kwh=round(eligible_kwh, 3),
                peak_kwh=round(tou_totals[TouPeriod.PEAK.value], 3),
                off_peak_kwh=round(tou_totals[TouPeriod.OFF_PEAK.value], 3),
                shoulder_kwh=round(tou_totals[TouPeriod.SHOULDER.value], 3),
                max_interval_kwh=round(
                    max((value for _, value, _ in eligible), default=0.0), 3
                ),
                expected_interval_count=coverage.expected_interval_count,
                observed_interval_count=coverage.observed_interval_count,
                eligible_interval_count=coverage.eligible_interval_count,
                missing_interval_count=coverage.missing_interval_count,
                excluded_quality_count=coverage.excluded_quality_count,
                unresolved_direction_count=coverage.unresolved_direction_count,
                legacy_direction_unverified_count=coverage.legacy_direction_unverified_count,
                duplicate_interval_count=coverage.duplicate_interval_count,
                invalid_interval_count=coverage.invalid_interval_count,
                invalid_unit_count=coverage.invalid_unit_count,
                coverage_fraction=coverage.coverage_fraction,
                coverage_status=day_status,
                provenance_status=coverage.provenance_status,
                observed_interval_average_demand_kw=(
                    round(observed_average_kw, 4)
                    if observed_average_kw is not None
                    else None
                ),
                observed_interval_peak_demand_kw=(
                    round(observed_peak_kw, 4)
                    if observed_peak_kw is not None
                    else None
                ),
                full_period_average_demand_kw=(
                    round(observed_average_kw, 4)
                    if coverage.coverage_status == "complete"
                    else None
                ),
            )
            metrics.append(_DayMetrics(result=daily))
        return metrics, readings_by_day, source_time_unresolved

    def get_daily_usage(
        self,
        meter_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 30,
    ) -> list[DailyUsage]:
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=max(limit - 1, 0))
        meter = self.db.query(Meter).filter(Meter.id == meter_id).first()
        if meter is None:
            return []
        readings = self._readings_for_window(meter_id, meter.state, start_date, end_date)
        if not readings:
            return []
        metrics, _, _ = self._daily_metrics(meter, start_date, end_date, readings)
        return [metric.result for metric in metrics[-limit:][::-1]]

    def _get_tou_breakdown(self, meter_id: int, day: date | str) -> dict[str, float]:
        day = _ensure_date(day)
        daily = self.get_daily_usage(meter_id, day, day, limit=1)
        if not daily:
            return {"peak": 0.0, "off_peak": 0.0, "shoulder": 0.0}
        result = daily[0]
        return {
            "peak": result.peak_kwh,
            "off_peak": result.off_peak_kwh,
            "shoulder": result.shoulder_kwh,
        }

    def _batch_tou_breakdown(
        self, readings: list[Reading], state: str = "VIC"
    ) -> dict[date, dict[str, float]]:
        result: dict[date, dict[str, float]] = defaultdict(
            lambda: {"peak": 0.0, "off_peak": 0.0, "shoulder": 0.0}
        )
        seen_slots: set[tuple[datetime, str]] = set()
        zone = timezone_for_state(state)
        for reading in readings:
            decision = evaluate_interval(
                reading,
                source_unit=reading.source_unit,
                source_time_basis=reading.source_time_basis,
                provenance_kind=reading.provenance_kind,
            )
            if not decision.eligible or decision.end_utc is None:
                continue
            slot_key = (decision.end_utc, reading.direction)
            if slot_key in seen_slots:
                continue
            seen_slots.add(slot_key)
            local_start = decision.start_utc.astimezone(zone).replace(tzinfo=None)
            period = classify_interval_tou_period(
                decision.end_utc, reading.interval_minutes, state
            )
            result[local_start.date()][period.value] += decision.energy_kwh or 0.0
        return dict(result)

    def get_hourly_usage(
        self,
        meter_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[HourlyUsage]:
        end_date = end_date or date.today()
        start_date = start_date or end_date - timedelta(days=29)
        meter = self.db.query(Meter).filter(Meter.id == meter_id).first()
        if meter is None:
            return []
        readings = self._readings_for_window(meter_id, meter.state, start_date, end_date)
        daily_metrics, readings_by_day, _ = self._daily_metrics(
            meter, start_date, end_date, readings
        )
        hourly_totals: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for metric in daily_metrics:
            day = metric.result.date
            for reading in readings_by_day[day]:
                decision = evaluate_interval(
                    reading,
                    source_unit=reading.source_unit,
                    source_time_basis=reading.source_time_basis,
                    provenance_kind=reading.provenance_kind,
                )
                if not decision.eligible or reading.direction != "import":
                    continue
                hour = (
                    decision.start_utc.astimezone(timezone_for_state(meter.state)).hour
                    if decision.start_utc
                    else reading.timestamp.hour
                )
                hourly_totals[hour][0] += decision.energy_kwh or 0.0
                hourly_totals[hour][1] += 1
        return [
            HourlyUsage(
                hour=hour,
                avg_kwh=round(total / count, 4),
                total_kwh=round(total, 3),
                reading_count=int(count),
            )
            for hour, (total, count) in sorted(hourly_totals.items())
        ]

    def get_weekly_usage(
        self,
        meter_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[WeeklyUsage]:
        end_date = end_date or date.today()
        start_date = start_date or end_date - timedelta(days=89)
        meter = self.db.query(Meter).filter(Meter.id == meter_id).first()
        if meter is None:
            return []
        daily = self.get_daily_usage(
            meter_id, start_date=start_date, end_date=end_date, limit=365
        )
        complete_by_weekday: dict[int, list[float]] = defaultdict(list)
        for day in daily:
            if day.coverage_status == "complete":
                complete_by_weekday[day.date.weekday()].append(day.observed_eligible_kwh)
        day_names = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        return [
            WeeklyUsage(
                day_of_week=weekday,
                day_name=day_names[weekday],
                avg_kwh=round(sum(values) / len(values), 4),
                total_kwh=round(sum(values), 3),
                complete_day_count=len(values),
                coverage_status="complete",
            )
            for weekday, values in sorted(complete_by_weekday.items())
        ]

    def get_usage_summary(
        self,
        meter_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> UsageSummary | None:
        meter = self.db.query(Meter).filter(Meter.id == meter_id).first()
        if meter is None:
            return None
        end_date = end_date or date.today()
        start_date = start_date or end_date - timedelta(days=29)
        dates = self._local_dates(start_date, end_date)
        readings = self._readings_for_window(meter_id, meter.state, start_date, end_date)
        if not readings:
            return None

        metrics, _, source_time_unresolved = self._daily_metrics(
            meter, start_date, end_date, readings
        )
        daily = [metric.result for metric in metrics]
        total_kwh = sum(item.observed_eligible_kwh for item in daily)
        eligible_count = sum(item.eligible_interval_count for item in daily)
        expected_count = sum(item.expected_interval_count for item in daily)
        observed_count = sum(item.observed_interval_count for item in daily)
        excluded_quality_count = sum(item.excluded_quality_count for item in daily)
        unresolved_direction_count = sum(item.unresolved_direction_count for item in daily)
        legacy_count = sum(item.legacy_direction_unverified_count for item in daily)
        duplicate_count = sum(item.duplicate_interval_count for item in daily)
        invalid_count = sum(item.invalid_interval_count for item in daily)
        invalid_unit_count = sum(item.invalid_unit_count for item in daily)
        coverage_fraction = eligible_count / expected_count if expected_count else 0.0
        if eligible_count == 0:
            coverage_status = "unavailable"
        elif eligible_count == expected_count:
            coverage_status = "complete"
        else:
            coverage_status = "partial"
        if source_time_unresolved and eligible_count == 0:
            coverage_status = "unavailable_source_time_basis"
        provenances = {item.provenance_status for item in daily if item.eligible_interval_count}
        provenance_status = (
            next(iter(provenances))
            if len(provenances) == 1
            else "mixed"
            if provenances
            else "unavailable"
        )
        channel_classification_status = (
            "unresolved"
            if unresolved_direction_count + legacy_count > 0
            else "classified"
            if eligible_count
            else "unavailable"
        )

        export_readings = [
            reading
            for reading in readings
            if reading.direction == "export"
            and reading.quality == "A"
            and reading.provenance_kind in {"measured", "synthetic"}
            and reading.source_unit
            and reading.source_unit.casefold() in {"kwh", "wh"}
        ]
        # Export is reported only when its intervals can be normalized and
        # deduplicated. It is not netted into imported energy.
        export_slots: dict[datetime, list[float]] = defaultdict(list)
        expected_ends = {
            end_utc
            for day in dates
            for end_utc in expected_interval_ends_utc(
                day, meter.state, meter.interval_minutes
            )
        }
        for reading in export_readings:
            decision = evaluate_interval(
                reading,
                source_unit=reading.source_unit,
                source_time_basis=reading.source_time_basis,
                provenance_kind=reading.provenance_kind,
                required_direction="export",
            )
            if (
                decision.eligible
                and decision.end_utc is not None
                and decision.end_utc in expected_ends
            ):
                export_slots[decision.end_utc].append(decision.energy_kwh or 0.0)
        eligible_export_kwh = sum(
            values[0] for values in export_slots.values() if len(values) == 1
        )
        net_grid_kwh = (
            total_kwh - eligible_export_kwh
            if provenance_status != "unavailable" and not source_time_unresolved
            else None
        )

        interval_hours = (
            sum(item.eligible_interval_count for item in daily)
            * meter.interval_minutes
            / 60
        )
        observed_average_kw = total_kwh / interval_hours if interval_hours else None
        observed_peak_kw = max(
            (
                item.observed_interval_peak_demand_kw
                for item in daily
                if item.observed_interval_peak_demand_kw is not None
            ),
            default=None,
        )
        complete_days = [
            item.observed_eligible_kwh
            for item in daily
            if item.coverage_status == "complete"
        ]
        hourly = self.get_hourly_usage(meter_id, start_date, end_date)
        peak_hour = max(hourly, key=lambda item: item.avg_kwh).hour if hourly else None
        all_eligible_kwh = sum(item.total_kwh for item in hourly)
        off_peak_kwh = sum(
            item.total_kwh
            for item in hourly
            if item.hour >= self.OFF_PEAK_START or item.hour < self.OFF_PEAK_END
        )
        explanation = None
        if source_time_unresolved:
            explanation = (
                "Some retrieved records have an unverified source timestamp basis and "
                "cannot be assigned to this local-date window; they are excluded from "
                "UTC-dependent metrics."
            )
        elif channel_classification_status == "unresolved":
            explanation = (
                "One or more channels have unresolved direction. They are retained for audit "
                "but excluded from eligible import/export energy."
            )
        elif coverage_status == "partial":
            explanation = (
                "This is observed eligible energy for a partially covered period; missing "
                "intervals are not treated as zero and daily averages require complete days."
            )

        zone = timezone_for_state(meter.state)
        period_start = datetime.combine(start_date, time.min, tzinfo=zone).astimezone(UTC)
        period_end = datetime.combine(
            end_date + timedelta(days=1), time.min, tzinfo=zone
        ).astimezone(UTC)
        return UsageSummary(
            meter_id=meter.id,
            meter_name=meter.name,
            nmi=meter.nmi,
            start_date=period_start,
            end_date=period_end,
            days_count=len(complete_days),
            total_kwh=round(total_kwh, 3),
            avg_daily_kwh=(
                round(sum(complete_days) / len(complete_days), 3)
                if complete_days
                else None
            ),
            max_daily_kwh=round(max(complete_days), 3) if complete_days else None,
            min_daily_kwh=round(min(complete_days), 3) if complete_days else None,
            peak_hour=peak_hour,
            peak_avg_kwh=(
                round(max(hour.avg_kwh for hour in hourly), 4) if hourly else None
            ),
            off_peak_percentage=(
                round(off_peak_kwh / all_eligible_kwh * 100, 1)
                if all_eligible_kwh > 0
                else None
            ),
            estimated_total_cost=None,
            estimated_daily_cost=None,
            eligible_import_kwh=round(total_kwh, 3),
            eligible_export_kwh=round(eligible_export_kwh, 3),
            net_grid_kwh=round(net_grid_kwh, 3) if net_grid_kwh is not None else None,
            expected_interval_count=expected_count,
            observed_interval_count=observed_count,
            eligible_interval_count=eligible_count,
            missing_interval_count=max(expected_count - observed_count, 0),
            excluded_quality_count=excluded_quality_count,
            unresolved_direction_count=unresolved_direction_count,
            legacy_direction_unverified_count=legacy_count,
            duplicate_interval_count=duplicate_count,
            invalid_interval_count=invalid_count,
            invalid_unit_count=invalid_unit_count,
            unresolved_time_basis_count=source_time_unresolved,
            coverage_fraction=coverage_fraction,
            coverage_status=coverage_status,
            provenance_status=provenance_status,
            channel_classification_status=channel_classification_status,
            explanation=explanation,
            observed_interval_average_demand_kw=(
                round(observed_average_kw, 4) if observed_average_kw is not None else None
            ),
            observed_interval_peak_demand_kw=(
                round(observed_peak_kw, 4) if observed_peak_kw is not None else None
            ),
            full_period_average_demand_kw=(
                round(total_kwh / ((period_end - period_start).total_seconds() / 3600), 4)
                if coverage_status == "complete"
                else None
            ),
        )
