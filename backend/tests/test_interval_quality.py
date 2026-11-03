"""Acceptance tests for conservative interval and coverage behavior."""

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.interval_quality import (
    calculate_coverage,
    comparable_weekday_periods,
    evaluate_interval,
    expected_interval_ends_utc,
)


def _reading(
    timestamp,
    *,
    value=0.5,
    direction="import",
    quality="A",
    register_type="U",
    source_unit="kWh",
    source_time_basis="UTC",
    provenance_kind="measured",
):
    return SimpleNamespace(
        timestamp=timestamp,
        interval_minutes=30,
        value=value,
        direction=direction,
        quality=quality,
        register_type=register_type,
        source_unit=source_unit,
        source_time_basis=source_time_basis,
        provenance_kind=provenance_kind,
    )


def _full_day(local_date: date, state="VIC"):
    return [
        _reading(end_utc.replace(tzinfo=None))
        for end_utc in expected_interval_ends_utc(local_date, state, 30)
    ]


@pytest.mark.parametrize(
    ("local_date", "expected"),
    [
        (date(2024, 4, 7), 50),
        (date(2024, 10, 6), 46),
        (date(2024, 6, 5), 48),
    ],
)
def test_melbourne_expected_slots_respect_dst(local_date, expected):
    assert len(expected_interval_ends_utc(local_date, "VIC", 30)) == expected


def test_partial_day_24_of_48_is_half_coverage():
    day = date(2024, 6, 5)
    readings = _full_day(day)[:24]
    coverage = calculate_coverage(
        [day], state="VIC", interval_minutes=30, readings=readings
    )

    assert coverage.expected_interval_count == 48
    assert coverage.observed_interval_count == 24
    assert coverage.eligible_interval_count == 24
    assert coverage.missing_interval_count == 24
    assert coverage.coverage_fraction == pytest.approx(0.5)
    assert coverage.coverage_status == "partial"


def test_unknown_direction_and_legacy_null_b_are_excluded_and_counted():
    day = date(2024, 6, 5)
    expected = expected_interval_ends_utc(day, "VIC", 30)
    readings = [
        _reading(
            expected[0].replace(tzinfo=None),
            direction=None,
            register_type="B",
        ),
        _reading(expected[1].replace(tzinfo=None), direction="unknown"),
    ]

    coverage = calculate_coverage(
        [day], state="VIC", interval_minutes=30, readings=readings
    )

    assert coverage.eligible_interval_count == 0
    assert coverage.legacy_direction_unverified_count == 1
    assert coverage.unresolved_direction_count == 1
    assert coverage.coverage_status == "unavailable"


def test_quality_a_is_headline_eligible_but_non_a_is_reported():
    day = date(2024, 6, 5)
    expected = expected_interval_ends_utc(day, "VIC", 30)
    readings = [
        _reading(expected[0].replace(tzinfo=None), quality="A"),
        _reading(expected[1].replace(tzinfo=None), quality="E"),
    ]

    coverage = calculate_coverage(
        [day], state="VIC", interval_minutes=30, readings=readings
    )

    assert coverage.eligible_interval_count == 1
    assert coverage.excluded_quality_count == 1


def test_duplicate_utc_slot_is_not_double_counted():
    day = date(2024, 6, 5)
    readings = _full_day(day)
    readings.append(readings[0])

    coverage = calculate_coverage(
        [day], state="VIC", interval_minutes=30, readings=readings
    )

    assert coverage.observed_interval_count == 48
    assert coverage.duplicate_interval_count == 1
    assert coverage.eligible_interval_count == 47
    assert coverage.coverage_status == "partial"


def test_import_and_export_channels_do_not_collide_as_duplicates():
    day = date(2024, 6, 5)
    timestamp = expected_interval_ends_utc(day, "VIC", 30)[0].replace(tzinfo=None)
    readings = [
        _reading(timestamp, direction="import", value=0.75),
        _reading(timestamp, direction="export", value=0.25),
    ]

    coverage = calculate_coverage(
        [day], state="VIC", interval_minutes=30, readings=readings
    )

    assert coverage.observed_interval_count == 1
    assert coverage.eligible_interval_count == 1
    assert coverage.duplicate_interval_count == 0


def test_zero_energy_interval_is_valid_observation_not_missing():
    day = date(2024, 6, 5)
    reading = _reading(expected_interval_ends_utc(day, "VIC", 30)[0].replace(tzinfo=None), value=0)

    decision = evaluate_interval(
        reading,
        source_unit=reading.source_unit,
        source_time_basis=reading.source_time_basis,
        provenance_kind=reading.provenance_kind,
    )
    coverage = calculate_coverage(
        [day], state="VIC", interval_minutes=30, readings=[reading]
    )

    assert decision.eligible
    assert decision.energy_kwh == 0
    assert coverage.observed_interval_count == 1
    assert coverage.eligible_interval_count == 1
    assert coverage.missing_interval_count == 47


def test_raw_wh_value_is_retained_and_unsupported_units_are_ineligible():
    day = date(2024, 6, 5)
    reading = _reading(
        expected_interval_ends_utc(day, "VIC", 30)[0].replace(tzinfo=None),
        value=1.0,
        source_unit="Wh",
    )
    reading.source_value = 1000.0
    decision = evaluate_interval(
        reading,
        source_unit=reading.source_unit,
        source_time_basis=reading.source_time_basis,
        provenance_kind=reading.provenance_kind,
    )
    assert decision.eligible
    assert decision.energy_kwh == 1.0
    assert reading.source_value == 1000.0

    unsupported = _reading(
        reading.timestamp,
        source_unit="kW",
    )
    rejected = evaluate_interval(
        unsupported,
        source_unit=unsupported.source_unit,
        source_time_basis=unsupported.source_time_basis,
        provenance_kind=unsupported.provenance_kind,
    )
    assert not rejected.eligible
    assert rejected.reason == "invalid_unit_or_value"


def test_versioned_mixed_direction_and_quality_fixture():
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "metering"
        / "prompt17_interval_quality_v1.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert fixture["fixture_version"] == "prompt17-interval-quality-v1"
    assert fixture["provenance_kind"] == "synthetic"
    assert sum(item["eligible_import"] for item in fixture["intervals"]) == 1
    assert fixture["intervals"][0]["source_value"] == 1000
    assert fixture["intervals"][0]["value"] == 1


def test_unverified_source_timestamp_basis_is_not_normalized():
    reading = _reading(
        expected_interval_ends_utc(date(2024, 6, 5), "VIC", 30)[0].replace(tzinfo=None),
        source_time_basis="unverified_fixed_utc_plus_10",
    )
    result = evaluate_interval(
        reading,
        source_unit=reading.source_unit,
        source_time_basis=reading.source_time_basis,
        provenance_kind=reading.provenance_kind,
    )
    assert not result.eligible
    assert result.start_utc is None
    assert result.reason == "unresolved_time_basis"


def test_unverified_basis_is_not_normalized_even_with_aware_timestamp():
    aware = expected_interval_ends_utc(date(2024, 6, 5), "VIC", 30)[0]
    reading = _reading(aware, source_time_basis="unverified_nem12_clock_basis")
    result = evaluate_interval(
        reading,
        source_unit=reading.source_unit,
        source_time_basis=reading.source_time_basis,
        provenance_kind=reading.provenance_kind,
    )
    assert not result.eligible
    assert result.start_utc is None
    assert result.reason == "unresolved_time_basis"


@pytest.mark.parametrize(
    ("aware", "basis", "eligible"),
    [
        (True, "UTC", True),
        (False, "UTC", True),
        (True, None, False),
        (False, None, False),
        (True, "unverified_nem12_clock_basis", False),
        (False, "unverified_nem12_clock_basis", False),
        (True, "unverified_fixed_utc_plus_10", False),
    ],
)
def test_source_time_basis_matrix_for_aware_and_naive_timestamps(aware, basis, eligible):
    end_utc = expected_interval_ends_utc(date(2024, 6, 5), "VIC", 30)[0]
    timestamp = end_utc if aware else end_utc.replace(tzinfo=None)
    reading = _reading(timestamp, source_time_basis=basis)
    result = evaluate_interval(
        reading,
        source_unit=reading.source_unit,
        source_time_basis=basis,
        provenance_kind=reading.provenance_kind,
    )
    assert result.eligible is eligible
    if eligible:
        assert result.start_utc is not None
    else:
        assert result.start_utc is None
        assert result.reason == "unresolved_time_basis"


def test_weekday_aligned_periods_allow_distinct_complete_dates():
    first_days = [date(2024, 6, 3 + offset) for offset in range(7)]
    second_days = [date(2024, 6, 10 + offset) for offset in range(7)]
    first = {
        day: calculate_coverage(
            [day],
            state="VIC",
            interval_minutes=30,
            readings=_full_day(day),
        )
        for day in first_days
    }
    second = {
        day: calculate_coverage(
            [day],
            state="VIC",
            interval_minutes=30,
            readings=_full_day(day),
        )
        for day in second_days
    }

    assert set(first).isdisjoint(second)
    assert comparable_weekday_periods(first, second)
