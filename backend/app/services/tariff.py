"""Single source of truth for Victorian Time-of-Use (ToU) classification and rates.

Every GridSense service that reasons about tariff periods — billing, bill forecasting,
usage analysis and anomaly detection — classifies interval timestamps through this module
so the period boundaries can never diverge between features.

Victorian residential ToU convention (typical distributor definition, e.g. CitiPower /
Powercor / United Energy):

    Peak      15:00-21:00 on business days (Mon-Fri)
    Shoulder  07:00-15:00 and 21:00-22:00 on business days
    Off-peak  22:00-07:00 every day, and all day on weekends

Timestamps are interpreted as AEST wall-clock. Australia's National Electricity Market
runs on fixed "market time" (UTC+10, no daylight saving), so the hour-of-day boundaries
above are applied directly to the stored timestamp with no timezone conversion. See
``app/services/nem12_parser.py`` for the ingestion-side contract.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Iterable, Protocol


class TouPeriod(str, Enum):
    """Time-of-Use period for a given interval."""

    PEAK = "peak"
    SHOULDER = "shoulder"
    OFF_PEAK = "off_peak"


# --- Period boundaries (24h clock, AEST wall-clock) -------------------------------------
PEAK_START_HOUR = 15  # 3pm
PEAK_END_HOUR = 21  # 9pm
SHOULDER_MORNING_START_HOUR = 7  # 7am (shoulder begins)
OFF_PEAK_START_HOUR = 22  # 10pm (off-peak resumes)
OFF_PEAK_END_HOUR = 7  # up to 7am is off-peak

# --- Default Victorian residential rates ------------------------------------------------
# Indicative retail values in dollars per kWh; overridden per-user by the Tariff model
# whenever the user has configured their own rates.
DEFAULT_PEAK_RATE = 0.38
DEFAULT_SHOULDER_RATE = 0.25
DEFAULT_OFF_PEAK_RATE = 0.18
DEFAULT_FLAT_RATE = 0.25
DEFAULT_SUPPLY_CHARGE = 1.20  # $/day

# Same defaults expressed in cents/kWh, matching the units stored on the Tariff model.
DEFAULT_PEAK_RATE_CENTS = DEFAULT_PEAK_RATE * 100
DEFAULT_SHOULDER_RATE_CENTS = DEFAULT_SHOULDER_RATE * 100
DEFAULT_OFF_PEAK_RATE_CENTS = DEFAULT_OFF_PEAK_RATE * 100
DEFAULT_FLAT_RATE_CENTS = DEFAULT_FLAT_RATE * 100

DEFAULT_TOU_RATES: dict[TouPeriod, float] = {
    TouPeriod.PEAK: DEFAULT_PEAK_RATE,
    TouPeriod.SHOULDER: DEFAULT_SHOULDER_RATE,
    TouPeriod.OFF_PEAK: DEFAULT_OFF_PEAK_RATE,
}


class _HasInterval(Protocol):
    """Minimal shape shared by Reading rows and reading-like objects."""

    timestamp: datetime
    value: float


def classify_tou_period(timestamp: datetime) -> TouPeriod:
    """Classify an interval timestamp into its Victorian ToU period.

    Weekday-aware: peak pricing applies only on business days, so weekends are
    entirely off-peak (the standard Victorian residential convention).
    """
    # 5 = Saturday, 6 = Sunday -> off-peak all day.
    if timestamp.weekday() >= 5:
        return TouPeriod.OFF_PEAK

    hour = timestamp.hour
    if PEAK_START_HOUR <= hour < PEAK_END_HOUR:
        return TouPeriod.PEAK
    if hour >= OFF_PEAK_START_HOUR or hour < OFF_PEAK_END_HOUR:
        return TouPeriod.OFF_PEAK
    return TouPeriod.SHOULDER


def is_peak(timestamp: datetime) -> bool:
    """True if the timestamp falls in the peak ToU window."""
    return classify_tou_period(timestamp) is TouPeriod.PEAK


def split_readings_by_period(readings: Iterable[_HasInterval]) -> dict[TouPeriod, float]:
    """Sum reading ``value`` into ToU buckets.

    Accepts any iterable of objects exposing ``timestamp`` (datetime) and ``value``
    (float) attributes — e.g. ORM ``Reading`` rows. Readings without a timestamp are
    skipped. Always returns all three period keys so callers can index safely.
    """
    totals: dict[TouPeriod, float] = {
        TouPeriod.PEAK: 0.0,
        TouPeriod.SHOULDER: 0.0,
        TouPeriod.OFF_PEAK: 0.0,
    }
    for reading in readings:
        if reading.timestamp is None:
            continue
        totals[classify_tou_period(reading.timestamp)] += reading.value
    return totals
