"""Interval eligibility, time normalization, and coverage contracts."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from math import isfinite
from typing import Iterable

from app.services.tariff import timezone_for_state

UTC = timezone.utc
FIXED_UTC_PLUS_10 = timezone(timedelta(hours=10))
NORMALIZABLE_SOURCE_TIME_BASES = {
    "UTC": UTC,
    "fixed_utc_plus_10": FIXED_UTC_PLUS_10,
}
ELIGIBLE_PROVENANCE = {"measured", "synthetic"}
ELIGIBLE_QUALITY_CODES = {"A"}
ENERGY_UNITS = {"kwh", "wh"}


@dataclass(frozen=True)
class IntervalDecision:
    """Eligibility and normalized bounds for one stored interval."""

    start_utc: datetime | None
    end_utc: datetime | None
    energy_kwh: float | None
    eligible: bool
    reason: str | None


@dataclass(frozen=True)
class Coverage:
    """Coverage and exclusion counts for a requested local-date range."""

    expected_interval_count: int
    observed_interval_count: int
    eligible_interval_count: int
    missing_interval_count: int
    excluded_quality_count: int
    unresolved_direction_count: int
    legacy_direction_unverified_count: int
    duplicate_interval_count: int
    invalid_interval_count: int
    invalid_unit_count: int
    unresolved_time_basis_count: int
    coverage_fraction: float
    coverage_status: str
    provenance_status: str


def expected_interval_ends_utc(
    local_date: date, state: str, interval_minutes: int
) -> tuple[datetime, ...]:
    """Return expected UTC interval ends for a complete local civil day."""
    if interval_minutes <= 0 or 1440 % interval_minutes:
        raise ValueError("Interval duration must divide a 24-hour day exactly")
    zone = timezone_for_state(state)
    local_start = datetime.combine(local_date, time.min, tzinfo=zone)
    local_end = datetime.combine(local_date + timedelta(days=1), time.min, tzinfo=zone)
    start_utc = local_start.astimezone(UTC)
    end_utc = local_end.astimezone(UTC)
    duration_seconds = int((end_utc - start_utc).total_seconds())
    interval_seconds = interval_minutes * 60
    if duration_seconds % interval_seconds:
        raise ValueError("Local-day duration is not divisible by the interval length")
    return tuple(
        start_utc + timedelta(seconds=interval_seconds * (slot + 1))
        for slot in range(duration_seconds // interval_seconds)
    )


def interval_bounds_utc(
    timestamp: datetime, interval_minutes: int, source_time_basis: str | None
) -> tuple[datetime, datetime] | None:
    """Normalize an interval only when the stored timestamp basis is explicit."""
    if interval_minutes <= 0:
        return None
    # Aware timestamps still require an explicitly verified basis: a missing or
    # unverified basis (e.g. the NEM12 clock) must not be trusted because the
    # stored value carries an offset.
    if source_time_basis not in NORMALIZABLE_SOURCE_TIME_BASES:
        return None
    if timestamp.tzinfo is not None and timestamp.utcoffset() is not None:
        end_utc = timestamp.astimezone(UTC)
    else:
        source_zone = NORMALIZABLE_SOURCE_TIME_BASES.get(source_time_basis or "")
        if source_zone is None:
            return None
        end_utc = timestamp.replace(tzinfo=source_zone).astimezone(UTC)
    return end_utc - timedelta(minutes=interval_minutes), end_utc


def evaluate_interval(
    reading: object,
    *,
    source_unit: str | None,
    source_time_basis: str | None,
    provenance_kind: str | None,
    required_direction: str = "import",
    allowed_provenance: set[str] = ELIGIBLE_PROVENANCE,
) -> IntervalDecision:
    """Apply conservative headline-energy eligibility to one reading."""
    timestamp = getattr(reading, "timestamp", None)
    interval_minutes = getattr(reading, "interval_minutes", None)
    value = getattr(reading, "value", None)
    direction = getattr(reading, "direction", None)
    register_type = getattr(reading, "register_type", None)
    quality = getattr(reading, "quality", None)
    unit = (source_unit or "").strip().casefold()

    if not isinstance(timestamp, datetime) or not isinstance(interval_minutes, int):
        return IntervalDecision(None, None, None, False, "invalid_interval")
    bounds = interval_bounds_utc(timestamp, interval_minutes, source_time_basis)
    if bounds is None:
        return IntervalDecision(None, None, None, False, "unresolved_time_basis")
    start_utc, end_utc = bounds
    if unit not in ENERGY_UNITS or not isinstance(value, (int, float)) or not isfinite(value):
        return IntervalDecision(start_utc, end_utc, None, False, "invalid_unit_or_value")
    if value < 0:
        return IntervalDecision(start_utc, end_utc, None, False, "invalid_negative_energy")
    if direction not in {"import", "export"}:
        reason = (
            "legacy_direction_unverified"
            if direction is None and register_type == "B"
            else "unresolved_direction"
        )
        return IntervalDecision(start_utc, end_utc, None, False, reason)
    if direction != required_direction:
        return IntervalDecision(start_utc, end_utc, None, False, f"excluded_{direction}")
    if quality not in ELIGIBLE_QUALITY_CODES:
        return IntervalDecision(start_utc, end_utc, None, False, "excluded_quality")
    if provenance_kind not in allowed_provenance:
        return IntervalDecision(start_utc, end_utc, None, False, "excluded_provenance")
    return IntervalDecision(start_utc, end_utc, float(value), True, None)


def calculate_coverage(
    local_dates: Iterable[date],
    *,
    state: str,
    interval_minutes: int,
    readings: Iterable[object],
    required_direction: str = "import",
    allowed_provenance: set[str] = ELIGIBLE_PROVENANCE,
) -> Coverage:
    """Count eligible and excluded interval slots without double-counting."""
    expected_ends: set[datetime] = set()
    expected_by_local_date: dict[date, set[datetime]] = {}
    for local_date in local_dates:
        day_ends = set(expected_interval_ends_utc(local_date, state, interval_minutes))
        expected_by_local_date[local_date] = day_ends
        expected_ends.update(day_ends)

    per_slot: dict[
        tuple[datetime, str | None], list[tuple[object, IntervalDecision]]
    ] = {}
    unresolved_time = 0
    invalid_intervals = 0
    for reading in readings:
        decision = evaluate_interval(
            reading,
            source_unit=getattr(reading, "source_unit", None),
            source_time_basis=getattr(reading, "source_time_basis", None),
            provenance_kind=getattr(reading, "provenance_kind", None),
            required_direction=required_direction,
            allowed_provenance=allowed_provenance,
        )
        if decision.reason == "unresolved_time_basis":
            unresolved_time += 1
            continue
        if decision.end_utc is None:
            invalid_intervals += 1
            continue
        if decision.end_utc in expected_ends:
            direction = getattr(reading, "direction", None)
            per_slot.setdefault((decision.end_utc, direction), []).append(
                (reading, decision)
            )

    observed_slots = {
        end_utc
        for end_utc, direction in per_slot
        if direction == required_direction
        or direction not in {"import", "export"}
    }
    duplicate_count = sum(
        max(len(slot_rows) - 1, 0)
        for (end_utc, direction), slot_rows in per_slot.items()
        if direction == required_direction or direction not in {"import", "export"}
    )
    eligible_slots = 0
    excluded_quality = 0
    unresolved_direction = 0
    legacy_direction_unverified = 0
    invalid_unit = 0
    eligible_provenance: set[str] = set()
    for (end_utc, direction), slot_rows in per_slot.items():
        if direction not in {required_direction, None, "unknown"}:
            continue
        if len(slot_rows) > 1:
            continue
        reading, decision = slot_rows[0]
        if decision.eligible:
            eligible_slots += 1
            eligible_provenance.add(getattr(reading, "provenance_kind", None))
        elif decision.reason == "excluded_quality":
            excluded_quality += 1
        elif decision.reason == "unresolved_direction":
            unresolved_direction += 1
        elif decision.reason == "legacy_direction_unverified":
            legacy_direction_unverified += 1
        elif decision.reason == "invalid_unit_or_value":
            invalid_unit += 1
        elif decision.reason == "invalid_negative_energy":
            invalid_intervals += 1

    expected_count = len(expected_ends)
    coverage_fraction = eligible_slots / expected_count if expected_count else 0.0
    if eligible_slots == 0:
        status = "unavailable"
    elif eligible_slots == expected_count:
        status = "complete"
    else:
        status = "partial"
    provenance_status = (
        "synthetic"
        if eligible_provenance == {"synthetic"}
        else "mixed"
        if len(eligible_provenance) > 1
        else "measured"
        if eligible_provenance == {"measured"}
        else "unavailable"
    )
    return Coverage(
        expected_interval_count=expected_count,
        observed_interval_count=len(observed_slots),
        eligible_interval_count=eligible_slots,
        missing_interval_count=max(expected_count - len(observed_slots), 0),
        excluded_quality_count=excluded_quality,
        unresolved_direction_count=unresolved_direction,
        legacy_direction_unverified_count=legacy_direction_unverified,
        duplicate_interval_count=duplicate_count,
        invalid_interval_count=invalid_intervals,
        invalid_unit_count=invalid_unit,
        unresolved_time_basis_count=unresolved_time,
        coverage_fraction=coverage_fraction,
        coverage_status=status,
        provenance_status=provenance_status,
    )


def comparable_weekday_periods(
    first_daily: dict[date, Coverage], second_daily: dict[date, Coverage]
) -> bool:
    """Require full, equal weekday composition—not identical calendar dates."""
    first_complete = {
        day for day, coverage in first_daily.items() if coverage.coverage_status == "complete"
    }
    second_complete = {
        day for day, coverage in second_daily.items() if coverage.coverage_status == "complete"
    }
    if len(first_complete) < 7 or len(second_complete) < 7:
        return False
    first_weekdays = Counter(day.weekday() for day in first_complete)
    second_weekdays = Counter(day.weekday() for day in second_complete)
    return first_weekdays == second_weekdays
