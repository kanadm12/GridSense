"""Shared contracts for external provider context and freshness."""

import math
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProviderId(StrEnum):
    OPEN_METEO = "open_meteo"
    AEMO_NEMWEB = "aemo_nemweb"


class DataKind(StrEnum):
    OBSERVED = "observed"
    FORECAST = "forecast"
    SIMULATED = "simulated"


class ProviderStatus(StrEnum):
    VALID = "valid"
    STALE = "stale"
    UNAVAILABLE = "unavailable"
    MALFORMED = "malformed"
    UNAUTHORIZED = "unauthorized"
    RATE_LIMITED = "rate_limited"
    BLOCKED = "blocked"


class ProviderFreshness(BaseModel):
    provider: ProviderId
    source_version: str
    status: ProviderStatus
    configured: bool = False
    retrieved_at: datetime | None = None
    fresh_until: datetime | None = None
    last_successful_fetch_at: datetime | None = None
    error_code: str | None = None
    retry_after: str | None = None
    attribution: str | None = None
    attribution_url: str | None = None


class WeatherHour(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_time_label: str
    target_time_utc: datetime
    interval_start_utc: datetime | None
    interval_end_utc: datetime | None
    time_semantics: str
    interval_semantics_field: str | None = None
    temperature_2m: float | None = None
    apparent_temperature: float | None = None
    relative_humidity: float | None = None
    cloud_cover: float | None = None
    shortwave_radiation: float | None = None
    source_units: dict[str, str]
    normalized_units: dict[str, str]


class WeatherForecastResponse(BaseModel):
    provider: ProviderFreshness
    data_kind: DataKind = DataKind.FORECAST
    latitude: float | None = None
    longitude: float | None = None
    timezone: str = "Australia/Melbourne"
    forecast_issued_at: datetime | None = None
    issue_time_available: bool = False
    model_selection: str | None = None
    provider_metadata: dict = Field(default_factory=dict)
    hourly: list[WeatherHour] = Field(default_factory=list)


class ProviderAvailabilityResponse(BaseModel):
    providers: list[ProviderFreshness]


class WeatherLocationRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    hours: int = Field(default=24, ge=1, le=72)

    @model_validator(mode="after")
    def require_finite_coordinates(self) -> "WeatherLocationRequest":
        if not math.isfinite(self.latitude):
            raise ValueError("Latitude must be finite.")
        if not math.isfinite(self.longitude):
            raise ValueError("Longitude must be finite.")
        return self


class WeatherHourlyRequest(WeatherLocationRequest):
    hours: int = Field(default=24, ge=1, le=72)


class MarketContextResponse(BaseModel):
    provider: ProviderFreshness
    region: str | None = None
    data_kind: DataKind = DataKind.OBSERVED
    price_aud_mwh: float | None = None
    demand_mw: float | None = None
    target_time_utc: datetime | None = None
    interval_start_utc: datetime | None = None
    interval_end_utc: datetime | None = None
    message: str
