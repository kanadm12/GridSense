"""Single source of truth for Victorian Time-of-Use (ToU) classification and rates.

Every GridSense service that reasons about tariff periods — billing, bill forecasting,
usage analysis and anomaly detection — classifies interval timestamps through this module
so the period boundaries can never diverge between features.

Victorian residential ToU convention (typical distributor definition, e.g. CitiPower /
Powercor / United Energy):

    Peak      15:00-21:00 on business days (Mon-Fri)
    Shoulder  07:00-15:00 and 21:00-22:00 on business days
    Off-peak  22:00-07:00 every day, and all day on weekends

The current application interprets naive NEM12 timestamps as interval ends in
fixed market time (UTC+10), but the applicable AEMO procedure has not yet been
independently verified. ToU conversion remains a compatibility assumption, not
an authoritative metering rule. See ``app/services/nem12_parser.py``.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from typing import Iterable, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class TouPeriod(str, Enum):
    """Time-of-Use period for a given interval."""

    PEAK = "peak"
    SHOULDER = "shoulder"
    OFF_PEAK = "off_peak"


# --- Period boundaries (24h local civil clock) -------------------------------------------
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
    interval_minutes: int


class _EffectiveTariffRevision(Protocol):
    """Fields required to test a tariff revision's evidenced effective dates."""

    confirmed_at: datetime | None
    effective_from: date | None
    effective_to: date | None
    is_illustrative: bool


def applicable_tariff_revisions(
    revisions: Iterable[_EffectiveTariffRevision], target_date: date
) -> list[_EffectiveTariffRevision]:
    """Return confirmed, non-illustrative tariff revisions covering one local date."""
    return [
        revision
        for revision in revisions
        if revision.confirmed_at is not None
        and not revision.is_illustrative
        and revision.effective_from is not None
        and revision.effective_from <= target_date
        and (revision.effective_to is None or target_date <= revision.effective_to)
    ]


MARKET_TIME = timezone(timedelta(hours=10), name="AEST")
STATE_TIMEZONES = {
    "ACT": "Australia/Sydney",
    "NSW": "Australia/Sydney",
    "NT": "Australia/Darwin",
    "QLD": "Australia/Brisbane",
    "SA": "Australia/Adelaide",
    "TAS": "Australia/Hobart",
    "VIC": "Australia/Melbourne",
}


def timezone_for_state(state: str) -> ZoneInfo:
    """Return a meter state's civil-time zone or fail explicitly for unknown states."""
    timezone_name = STATE_TIMEZONES.get(state.upper())
    if timezone_name is None:
        raise ValueError(f"Unsupported meter state '{state}'; cannot align local billing time")
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"Timezone data is unavailable for {timezone_name}") from exc


def market_timestamp_to_local(timestamp: datetime, state: str) -> datetime:
    """Convert timestamps using the application's provisional market-time assumption.

    Naive timestamps use fixed UTC+10 for compatibility. NEM12 rows marked with
    an unverified basis must not be used for validated metrics.
    """
    market_instant = (
        timestamp.replace(tzinfo=MARKET_TIME)
        if timestamp.tzinfo is None
        else timestamp
    )
    return market_instant.astimezone(timezone_for_state(state))


def local_interval_end_date(timestamp: datetime, state: str) -> date:
    """Return the local billing date for an interval ending at ``timestamp``."""
    local_end = market_timestamp_to_local(timestamp, state)
    if local_end.timetz().replace(tzinfo=None) == time.min:
        return local_end.date() - timedelta(days=1)
    return local_end.date()


def market_interval_start_to_local(
    timestamp: datetime, interval_minutes: int, state: str
) -> datetime:
    """Return an interval's local start instant from its stored market-time end."""
    if interval_minutes not in (5, 15, 30):
        raise ValueError(f"Unsupported interval length {interval_minutes} minutes")
    interval_end = market_timestamp_to_local(timestamp, state)
    return (
        interval_end.astimezone(timezone.utc) - timedelta(minutes=interval_minutes)
    ).astimezone(interval_end.tzinfo)


def market_bounds_for_local_dates(
    start_date: date, end_date: date, state: str
) -> tuple[datetime, datetime]:
    """Return exclusive/inclusive NEM timestamp bounds for local calendar dates."""
    local_zone = timezone_for_state(state)
    local_start = datetime.combine(start_date, time.min).replace(tzinfo=local_zone)
    local_end = datetime.combine(end_date + timedelta(days=1), time.min).replace(
        tzinfo=local_zone
    )
    return (
        local_start.astimezone(MARKET_TIME).replace(tzinfo=None),
        local_end.astimezone(MARKET_TIME).replace(tzinfo=None),
    )


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


def classify_interval_tou_period(
    timestamp: datetime, interval_minutes: int = 30, state: str = "VIC"
) -> TouPeriod:
    """Classify an interval by its local start boundary, not its end timestamp."""
    return classify_tou_period(
        market_interval_start_to_local(timestamp, interval_minutes, state)
    )


def is_peak(timestamp: datetime, interval_minutes: int = 30, state: str = "VIC") -> bool:
    """True if the interval's local start falls in the peak ToU window."""
    return classify_interval_tou_period(timestamp, interval_minutes, state) is TouPeriod.PEAK


def split_readings_by_period(
    readings: Iterable[_HasInterval], state: str = "VIC"
) -> dict[TouPeriod, float]:
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
        interval_minutes = getattr(reading, "interval_minutes", 30)
        totals[
            classify_interval_tou_period(reading.timestamp, interval_minutes, state)
        ] += reading.value
    return totals
