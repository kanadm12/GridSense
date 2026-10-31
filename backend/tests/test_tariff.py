"""Unit tests for the shared Victorian Time-of-Use tariff module.

This module is the single source of truth for ToU classification used by billing,
forecasting, usage analysis and anomaly detection, so its boundaries are pinned here.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.tariff import (
    TouPeriod,
    classify_interval_tou_period,
    classify_tou_period,
    is_peak,
    market_bounds_for_local_dates,
    market_timestamp_to_local,
    split_readings_by_period,
)

# 2024-06-05 is a Wednesday; 2024-06-08 is a Saturday; 2024-06-09 is a Sunday.
WED = "2024-06-05"
SAT = "2024-06-08"
SUN = "2024-06-09"


def _dt(day: str, hour: int, minute: int = 0) -> datetime:
    return datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00")


class TestClassifyWeekday:
    """Weekday classification and boundary conditions."""

    def test_peak_window(self):
        assert classify_tou_period(_dt(WED, 15)) is TouPeriod.PEAK  # 3pm start (inclusive)
        assert classify_tou_period(_dt(WED, 18)) is TouPeriod.PEAK
        assert classify_tou_period(_dt(WED, 20, 30)) is TouPeriod.PEAK

    def test_peak_end_is_exclusive(self):
        # 9pm rolls into shoulder, not peak.
        assert classify_tou_period(_dt(WED, 21)) is TouPeriod.SHOULDER

    def test_morning_shoulder(self):
        assert classify_tou_period(_dt(WED, 7)) is TouPeriod.SHOULDER  # 7am start
        assert classify_tou_period(_dt(WED, 14, 59)) is TouPeriod.SHOULDER

    def test_evening_shoulder(self):
        assert classify_tou_period(_dt(WED, 21, 30)) is TouPeriod.SHOULDER

    def test_off_peak_overnight(self):
        assert classify_tou_period(_dt(WED, 22)) is TouPeriod.OFF_PEAK  # 10pm resumes
        assert classify_tou_period(_dt(WED, 23, 30)) is TouPeriod.OFF_PEAK
        assert classify_tou_period(_dt(WED, 0)) is TouPeriod.OFF_PEAK
        assert classify_tou_period(_dt(WED, 6, 59)) is TouPeriod.OFF_PEAK


class TestClassifyWeekend:
    """Weekends are entirely off-peak under the Victorian residential convention."""

    def test_saturday_afternoon_is_off_peak(self):
        # Same 3pm-9pm window that is peak on a weekday.
        assert classify_tou_period(_dt(SAT, 16)) is TouPeriod.OFF_PEAK
        assert not is_peak(_dt(SAT, 16))

    def test_sunday_all_off_peak(self):
        for hour in (0, 8, 16, 21, 23):
            assert classify_tou_period(_dt(SUN, hour)) is TouPeriod.OFF_PEAK


class TestSplitReadingsByPeriod:
    """Bucketing a batch of readings into ToU totals."""

    def test_buckets_sum_correctly(self):
        readings = [
            SimpleNamespace(timestamp=_dt(WED, 16), value=2.0),  # peak
            SimpleNamespace(timestamp=_dt(WED, 17), value=3.0),  # peak
            SimpleNamespace(timestamp=_dt(WED, 10), value=1.5),  # shoulder
            SimpleNamespace(timestamp=_dt(WED, 3), value=0.5),   # off-peak
            SimpleNamespace(timestamp=_dt(SAT, 16), value=4.0),  # weekend -> off-peak
        ]
        buckets = split_readings_by_period(readings)
        assert buckets[TouPeriod.PEAK] == 5.0
        assert buckets[TouPeriod.SHOULDER] == 1.5
        assert buckets[TouPeriod.OFF_PEAK] == 4.5

    def test_all_period_keys_always_present(self):
        buckets = split_readings_by_period([])
        assert set(buckets) == {TouPeriod.PEAK, TouPeriod.SHOULDER, TouPeriod.OFF_PEAK}
        assert all(v == 0.0 for v in buckets.values())

    def test_skips_readings_without_timestamp(self):
        readings = [
            SimpleNamespace(timestamp=None, value=99.0),
            SimpleNamespace(timestamp=_dt(WED, 16), value=1.0),
        ]
        buckets = split_readings_by_period(readings)
        assert buckets[TouPeriod.PEAK] == 1.0
        assert sum(buckets.values()) == 1.0


class TestMarketTimeAndDst:
    def test_spring_transition_skips_nonexistent_melbourne_hour(self):
        local = market_timestamp_to_local(datetime(2024, 10, 6, 2), "VIC")
        assert local.isoformat() == "2024-10-06T03:00:00+11:00"

    def test_autumn_transition_resolves_repeated_hour_by_market_instant(self):
        local = market_timestamp_to_local(datetime(2024, 4, 7, 2), "VIC")
        assert local.isoformat() == "2024-04-07T02:00:00+10:00"
        assert local.fold == 1

    def test_spring_and_autumn_local_date_bounds_conserve_interval_count(self):
        spring_start, spring_end = market_bounds_for_local_dates(
            datetime(2024, 10, 6).date(), datetime(2024, 10, 6).date(), "VIC"
        )
        autumn_start, autumn_end = market_bounds_for_local_dates(
            datetime(2024, 4, 7).date(), datetime(2024, 4, 7).date(), "VIC"
        )
        assert (spring_end - spring_start) == timedelta(hours=23)
        assert (autumn_end - autumn_start) == timedelta(hours=25)
        assert self._daily_intervals_conserve(spring_start, spring_end) == 46
        assert self._daily_intervals_conserve(autumn_start, autumn_end) == 50

    @staticmethod
    def _daily_intervals_conserve(start, end):
        interval_count = int((end - start) / timedelta(minutes=30))
        readings = [
            SimpleNamespace(
                timestamp=start + timedelta(minutes=30 * index),
                interval_minutes=30,
                value=0.25,
            )
            for index in range(1, interval_count + 1)
        ]
        buckets = split_readings_by_period(readings, "VIC")
        assert sum(reading.value for reading in readings) == pytest.approx(
            sum(buckets.values())
        )
        return interval_count

    def test_tariff_boundaries_use_interval_start_in_local_time(self):
        # In winter, market 15:00 ends the 14:30-15:00 shoulder interval.
        assert classify_interval_tou_period(datetime(2024, 6, 5, 15), 30, "VIC") is TouPeriod.SHOULDER
        # In summer, market 14:30 is 15:30 local; its 15:00 start is peak.
        assert classify_interval_tou_period(datetime(2024, 1, 17, 14, 30), 30, "VIC") is TouPeriod.PEAK

    @pytest.mark.parametrize(
        ("timestamp", "interval_minutes", "expected"),
        [
            (datetime(2024, 6, 5, 15, 0), 15, TouPeriod.SHOULDER),
            (datetime(2024, 6, 5, 15, 15), 15, TouPeriod.PEAK),
            (datetime(2024, 6, 5, 15, 5), 5, TouPeriod.PEAK),
        ],
    )
    def test_subhour_intervals_classify_by_start(
        self, timestamp, interval_minutes, expected
    ):
        assert classify_interval_tou_period(
            timestamp, interval_minutes, "VIC"
        ) is expected

    def test_unknown_state_is_not_silently_assigned_a_timezone(self):
        with pytest.raises(ValueError, match="cannot align local billing time"):
            market_timestamp_to_local(datetime(2024, 6, 5, 15), "ZZ")

    def test_leap_day_midnight_interval_is_preserved_in_local_bounds(self):
        start, end = market_bounds_for_local_dates(
            datetime(2024, 2, 29).date(), datetime(2024, 2, 29).date(), "VIC"
        )
        assert end - start == timedelta(days=1)
        assert market_timestamp_to_local(end, "VIC").isoformat() == "2024-03-01T00:00:00+11:00"
