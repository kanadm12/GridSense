"""Tariff schemas for Victorian electricity rates."""

from enum import Enum
from pydantic import BaseModel, Field


class TariffType(str, Enum):
    """Types of electricity tariffs available in Victoria."""

    FLAT = "flat"
    TOU = "tou"  # Time of Use
    DEMAND = "demand"
    FLEXIBLE = "flexible"


class TariffPeriod(BaseModel):
    """A time period with associated rate."""

    name: str  # e.g., "peak", "off_peak", "shoulder"
    start_hour: int = Field(..., ge=0, le=23)
    end_hour: int = Field(..., ge=0, le=23)
    rate_cents_kwh: float
    days: list[int] = Field(default=[0, 1, 2, 3, 4, 5, 6])  # 0=Mon, 6=Sun


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

    # Demand tariff
    demand_charge_dollars_kw: float | None = None

    # Supply charge
    daily_supply_charge_cents: float = 100.0  # ~$1/day typical


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
    demand_charge_dollars_kw: float | None
    daily_supply_charge_cents: float

    model_config = {"from_attributes": True}


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
    daily_supply_charge_cents: float


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
