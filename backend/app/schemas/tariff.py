"""Tariff schemas for Victorian electricity rates."""

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TariffType(str, Enum):
    """Types of electricity tariffs available in Victoria."""

    FLAT = "flat"
    TOU = "tou"  # Time of Use
    DEMAND = "demand"
    FLEXIBLE = "flexible"


class TariffPeriod(BaseModel):
    """Local-clock window and rate; start/end are minutes since midnight."""

    name: str = Field(min_length=1, max_length=40)
    start_minute: int = Field(ge=0, le=1439)
    end_minute: int = Field(ge=1, le=1440)
    rate_cents_kwh: float = Field(ge=0)
    days: list[int] = Field(default_factory=lambda: list(range(7)))  # 0=Mon, 6=Sun

    @model_validator(mode="after")
    def validate_window(self):
        if self.start_minute >= self.end_minute:
            raise ValueError("Tariff window must end after it starts; split windows at midnight")
        if not self.days or any(day not in range(7) for day in self.days):
            raise ValueError("Tariff days must contain one or more weekday values from 0 to 6")
        if len(set(self.days)) != len(self.days):
            raise ValueError("Tariff days cannot contain duplicates")
        return self


class TariffCreate(BaseModel):
    """Schema for creating/updating user tariff settings."""

    tariff_type: TariffType
    retailer_name: str | None = None

    # Flat rate
    flat_rate_cents_kwh: float | None = None

    # TOU rates
    peak_rate_cents_kwh: float | None = None
    off_peak_rate_cents_kwh: float | None = None
    shoulder_rate_cents_kwh: float | None = None
    feed_in_rate_cents_kwh: float | None = Field(default=None, ge=0)
    periods: list[TariffPeriod] | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    rates_include_gst: bool = True
    confirmed: bool = False
    unmodeled_components_confirmed_absent: bool = False
    unsupported_components: list[str] = Field(default_factory=list)

    # Demand tariff
    demand_charge_dollars_kw: float | None = Field(default=None, ge=0)

    # Supply charge
    daily_supply_charge_cents: float = Field(default=100.0, ge=0)

    @model_validator(mode="after")
    def validate_tariff(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot be before effective_from")
        rate_fields = (
            self.flat_rate_cents_kwh,
            self.peak_rate_cents_kwh,
            self.off_peak_rate_cents_kwh,
            self.shoulder_rate_cents_kwh,
        )
        if any(rate is not None and rate < 0 for rate in rate_fields):
            raise ValueError("Tariff rates cannot be negative")
        if self.tariff_type == TariffType.FLAT and self.flat_rate_cents_kwh is None:
            raise ValueError("Flat tariffs require flat_rate_cents_kwh")
        if self.periods is not None and self.tariff_type == TariffType.FLAT:
            raise ValueError("Custom time windows require a time-of-use or flexible tariff")
        if self.periods:
            for day in range(7):
                windows = sorted(
                    (period.start_minute, period.end_minute)
                    for period in self.periods
                    if day in period.days
                )
                if any(current[0] < previous[1] for previous, current in zip(windows, windows[1:])):
                    raise ValueError(f"Tariff windows overlap on weekday {day}")
        return self


class TariffResponse(BaseModel):
    """Schema for tariff response."""

    id: int
    user_id: int
    tariff_type: TariffType
    retailer_name: str | None

    flat_rate_cents_kwh: float | None
    peak_rate_cents_kwh: float | None
    off_peak_rate_cents_kwh: float | None
    shoulder_rate_cents_kwh: float | None
    feed_in_rate_cents_kwh: float | None
    periods: list[TariffPeriod] | None
    effective_from: date | None
    effective_to: date | None
    rates_include_gst: bool
    is_preset: bool
    demand_charge_dollars_kw: float | None
    daily_supply_charge_cents: float
    revision_number: int | None = None
    confirmed_at: datetime | None = None
    confirmation_source: str | None = None
    is_confirmed: bool = False
    unsupported_components: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class TariffRevisionResponse(BaseModel):
    id: int
    tariff_id: int
    revision_number: int
    source_type: str
    source_plan_id: str | None
    confirmed_at: datetime | None
    effective_from: date | None
    effective_to: date | None
    tariff_type: TariffType
    retailer_name: str | None
    flat_rate_cents_kwh: float | None
    peak_rate_cents_kwh: float | None
    off_peak_rate_cents_kwh: float | None
    shoulder_rate_cents_kwh: float | None
    feed_in_rate_cents_kwh: float | None
    periods: list[TariffPeriod] | None
    rates_include_gst: bool
    demand_charge_dollars_kw: float | None
    daily_supply_charge_cents: float | None
    unsupported_components: list[str]
    is_illustrative: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TariffPreset(BaseModel):
    """Preset tariff from a known retailer."""

    id: str
    retailer: str
    plan_name: str
    tariff_type: TariffType
    flat_rate_cents_kwh: float | None = None
    peak_rate_cents_kwh: float | None = None
    off_peak_rate_cents_kwh: float | None = None
    shoulder_rate_cents_kwh: float | None = None
    feed_in_rate_cents_kwh: float | None = None
    daily_supply_charge_cents: float
    rates_include_gst: bool = True
    is_illustrative: bool = True


# Victorian retailer presets (approximate rates as of 2026)
VICTORIAN_TARIFF_PRESETS: list[TariffPreset] = [
    TariffPreset(
        id="agl_residential_flat",
        retailer="AGL",
        plan_name="Residential Flat",
        tariff_type=TariffType.FLAT,
        flat_rate_cents_kwh=28.5,
        daily_supply_charge_cents=98.0,
    ),
    TariffPreset(
        id="agl_residential_tou",
        retailer="AGL",
        plan_name="Residential Time of Use",
        tariff_type=TariffType.TOU,
        peak_rate_cents_kwh=38.5,
        shoulder_rate_cents_kwh=25.0,
        off_peak_rate_cents_kwh=18.5,
        daily_supply_charge_cents=98.0,
    ),
    TariffPreset(
        id="origin_residential_flat",
        retailer="Origin Energy",
        plan_name="Basic Home",
        tariff_type=TariffType.FLAT,
        flat_rate_cents_kwh=29.0,
        daily_supply_charge_cents=102.0,
    ),
    TariffPreset(
        id="origin_residential_tou",
        retailer="Origin Energy",
        plan_name="Solar Boost Plus",
        tariff_type=TariffType.TOU,
        peak_rate_cents_kwh=42.0,
        shoulder_rate_cents_kwh=26.5,
        off_peak_rate_cents_kwh=16.0,
        daily_supply_charge_cents=102.0,
    ),
    TariffPreset(
        id="energyaus_flat",
        retailer="Energy Australia",
        plan_name="Total Plan Home",
        tariff_type=TariffType.FLAT,
        flat_rate_cents_kwh=27.5,
        daily_supply_charge_cents=95.0,
    ),
    TariffPreset(
        id="energyaus_tou",
        retailer="Energy Australia",
        plan_name="Total Plan Flexible",
        tariff_type=TariffType.TOU,
        peak_rate_cents_kwh=40.0,
        shoulder_rate_cents_kwh=24.0,
        off_peak_rate_cents_kwh=17.0,
        daily_supply_charge_cents=95.0,
    ),
    TariffPreset(
        id="simply_energy_flat",
        retailer="Simply Energy",
        plan_name="Simply Plus",
        tariff_type=TariffType.FLAT,
        flat_rate_cents_kwh=26.0,
        daily_supply_charge_cents=90.0,
    ),
    TariffPreset(
        id="powershop_tou",
        retailer="Powershop",
        plan_name="Shopper Market",
        tariff_type=TariffType.TOU,
        peak_rate_cents_kwh=36.0,
        shoulder_rate_cents_kwh=23.0,
        off_peak_rate_cents_kwh=15.0,
        daily_supply_charge_cents=88.0,
    ),
]
