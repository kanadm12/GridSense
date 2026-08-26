"""Unit tests for the shared Victorian Time-of-Use tariff module.

This module is the single source of truth for ToU classification used by billing,
forecasting, usage analysis and anomaly detection, so its boundaries are pinned here.
"""

from datetime import datetime
from types import SimpleNamespace

from app.services.tariff import (
    TouPeriod,
    classify_tou_period,
    is_peak,
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
