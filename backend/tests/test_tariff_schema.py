"""Validation tests for explicit tariff inputs."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.tariff import TariffCreate, TariffPeriod, TariffType


def test_tariff_period_accepts_weekday_window():
    period = TariffPeriod(
        name="weekday_peak",
        start_minute=900,
        end_minute=1260,
        rate_cents_kwh=42.5,
        days=[0, 1, 2, 3, 4],
    )

    assert period.start_minute == 900
    assert period.days == [0, 1, 2, 3, 4]


@pytest.mark.parametrize(
    "values",
    [
        {"start_minute": 900, "end_minute": 900, "days": [0]},
        {"start_minute": 1200, "end_minute": 300, "days": [0]},
        {"start_minute": 0, "end_minute": 60, "days": []},
        {"start_minute": 0, "end_minute": 60, "days": [7]},
        {"start_minute": 0, "end_minute": 60, "days": [0, 0]},
    ],
)
def test_invalid_tariff_periods_are_rejected(values):
    with pytest.raises(ValidationError):
        TariffPeriod(name="invalid", rate_cents_kwh=10, **values)


def test_tariff_rejects_reversed_effective_dates():
    with pytest.raises(ValidationError, match="effective_to"):
        TariffCreate(
            tariff_type=TariffType.FLAT,
            flat_rate_cents_kwh=30,
            effective_from=date(2026, 7, 1),
            effective_to=date(2026, 6, 30),
        )


def test_tariff_rejects_overlapping_windows_per_weekday():
    with pytest.raises(ValidationError, match="overlap"):
        TariffCreate(
            tariff_type=TariffType.TOU,
            periods=[
                TariffPeriod(
                    name="first",
                    start_minute=600,
                    end_minute=900,
                    rate_cents_kwh=20,
                    days=[0],
                ),
                TariffPeriod(
                    name="second",
                    start_minute=850,
                    end_minute=1000,
                    rate_cents_kwh=30,
                    days=[0],
                ),
            ],
        )


def test_flat_tariff_requires_rate_and_optional_values_are_non_negative():
    with pytest.raises(ValidationError, match="flat_rate_cents_kwh"):
        TariffCreate(tariff_type=TariffType.FLAT)
    with pytest.raises(ValidationError):
        TariffCreate(
            tariff_type=TariffType.FLAT,
            flat_rate_cents_kwh=30,
            feed_in_rate_cents_kwh=-1,
        )
