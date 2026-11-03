"""Licensed Open-Meteo forecast adapter with auditable retrieval-time caching."""

import asyncio
import hashlib
import math
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models.external_data import ExternalFetchRun, WeatherForecastValue
from app.schemas.external_data import (
    ProviderFreshness,
    ProviderId,
    ProviderStatus,
    WeatherForecastResponse,
    WeatherHour,
)

OPEN_METEO_URL = "https://customer-api.open-meteo.com/v1/forecast"
SOURCE_VERSION = "Forecast API v1"
ATTRIBUTION = "Weather data by Open-Meteo.com"
ATTRIBUTION_URL = "https://open-meteo.com/"
HOURLY_VARIABLES = (
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "cloud_cover",
    "shortwave_radiation",
)
SOURCE_UNITS = {
    "temperature_2m": "°C",
    "apparent_temperature": "°C",
    "relative_humidity_2m": "%",
    "cloud_cover": "%",
    "shortwave_radiation": "W/m²",
}
NORMALIZED_UNITS = SOURCE_UNITS.copy()
MAX_FORECAST_HOURS = 72


class OpenMeteoError(Exception):
    """Sanitized provider failure safe to expose in API status fields."""

    def __init__(
        self,
        status: ProviderStatus,
        error_code: str,
        *,
        retry_after: str | None = None,
    ) -> None:
        super().__init__(error_code)
        self.status = status
        self.error_code = error_code
        self.retry_after = retry_after


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _coordinate_key(latitude: float, longitude: float) -> tuple[str, float, float]:
    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        raise ValueError("Latitude must be a finite value between -90 and 90.")
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError("Longitude must be a finite value between -180 and 180.")
    rounded_latitude = round(latitude, 2)
    rounded_longitude = round(longitude, 2)
    key_material = f"{rounded_latitude:.2f},{rounded_longitude:.2f}"
    location_key = hashlib.sha256(key_material.encode("ascii")).hexdigest()
    return location_key, rounded_latitude, rounded_longitude


def parse_forecast_payload(payload: Any) -> tuple[dict, list[dict]]:
    """Validate and normalize documented hourly fields without inventing issue time."""
    if not isinstance(payload, dict):
        raise OpenMeteoError(ProviderStatus.MALFORMED, "invalid_payload")

    hourly = payload.get("hourly")
    units = payload.get("hourly_units")
    times = hourly.get("time") if isinstance(hourly, dict) else None
    if not isinstance(times, list) or not times or not isinstance(units, dict):
        raise OpenMeteoError(ProviderStatus.MALFORMED, "missing_hourly_schema")

    if any(not isinstance(hourly.get(name), list) for name in HOURLY_VARIABLES):
        raise OpenMeteoError(ProviderStatus.MALFORMED, "missing_hourly_variable")
    if any(len(hourly[name]) != len(times) for name in HOURLY_VARIABLES):
        raise OpenMeteoError(ProviderStatus.MALFORMED, "hourly_length_mismatch")
    if any(name not in units for name in HOURLY_VARIABLES):
        raise OpenMeteoError(ProviderStatus.MALFORMED, "missing_hourly_unit")

    normalized_units = dict(NORMALIZED_UNITS)
    source_units = {name: units[name] for name in HOURLY_VARIABLES}
    for field in ("temperature_2m", "apparent_temperature"):
        if source_units[field] not in {"°C", "°F"}:
            raise OpenMeteoError(ProviderStatus.MALFORMED, "unsupported_temperature_unit")
    if source_units["relative_humidity_2m"] != "%":
        raise OpenMeteoError(ProviderStatus.MALFORMED, "unsupported_humidity_unit")
    if source_units["cloud_cover"] != "%":
        raise OpenMeteoError(ProviderStatus.MALFORMED, "unsupported_cloud_cover_unit")
    if source_units["shortwave_radiation"] != "W/m²":
        raise OpenMeteoError(ProviderStatus.MALFORMED, "unsupported_radiation_unit")

    rows = []
    seen_times: set[datetime] = set()
    for index, source_label in enumerate(times):
        if not isinstance(source_label, str):
            raise OpenMeteoError(ProviderStatus.MALFORMED, "invalid_time_label")
        try:
            target_time = datetime.fromisoformat(source_label)
        except ValueError as exc:
            raise OpenMeteoError(
                ProviderStatus.MALFORMED, "invalid_time_label"
            ) from exc
        if target_time.tzinfo is None:
            target_time = target_time.replace(tzinfo=timezone.utc)
        else:
            target_time = target_time.astimezone(timezone.utc)
        if target_time in seen_times:
            raise OpenMeteoError(ProviderStatus.MALFORMED, "duplicate_target_time")
        seen_times.add(target_time)

        values: dict[str, float | None] = {}
        for field in HOURLY_VARIABLES:
            raw_value = hourly[field][index]
            if raw_value is None:
                values[field] = None
                continue
            if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
                raise OpenMeteoError(ProviderStatus.MALFORMED, "invalid_hourly_value")
            value = float(raw_value)
            if not math.isfinite(value):
                raise OpenMeteoError(ProviderStatus.MALFORMED, "non_finite_hourly_value")
            if field in {"temperature_2m", "apparent_temperature"}:
                if source_units[field] == "°F":
                    value = (value - 32) * 5 / 9
            elif field in {"relative_humidity_2m", "cloud_cover"}:
                if not 0 <= value <= 100:
                    raise OpenMeteoError(ProviderStatus.MALFORMED, "percentage_out_of_range")
            elif field == "shortwave_radiation" and value < 0:
                raise OpenMeteoError(ProviderStatus.MALFORMED, "negative_radiation")
            values[field] = value

        rows.append(
            {
                "source_time_label": source_label,
                "target_time_utc": target_time,
                "values": values,
            }
        )

    metadata = {
        "provider_latitude": payload.get("latitude"),
        "provider_longitude": payload.get("longitude"),
        "timezone": payload.get("timezone"),
        "timezone_abbreviation": payload.get("timezone_abbreviation"),
        "utc_offset_seconds": payload.get("utc_offset_seconds"),
        "elevation_m": payload.get("elevation"),
        "generationtime_ms": payload.get("generationtime_ms"),
        "model_selection": "best_match",
        "forecast_issue_time_available": False,
        "source_units": source_units,
        "normalized_units": normalized_units,
    }
    return metadata, rows


class OpenMeteoClient:
    """Client for Open-Meteo's paid API endpoint only."""

    def __init__(
        self,
        api_key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.api_key = api_key
        self.transport = transport
        self.timeout_seconds = timeout_seconds

    async def fetch(self, latitude: float, longitude: float) -> tuple[dict, list[dict]]:
        if not self.api_key:
            raise OpenMeteoError(ProviderStatus.UNAVAILABLE, "provider_not_configured")

        params = {
            "latitude": f"{latitude:.2f}",
            "longitude": f"{longitude:.2f}",
            "hourly": ",".join(HOURLY_VARIABLES),
            "temperature_unit": "celsius",
            "timezone": "UTC",
            "forecast_days": 3,
            "models": "best_match",
            "apikey": self.api_key,
        }
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds, transport=self.transport
                ) as client:
                    response = await client.get(OPEN_METEO_URL, params=params)
            except httpx.TimeoutException as exc:
                if attempt == 0:
                    await asyncio.sleep(0.25)
                    continue
                raise OpenMeteoError(
                    ProviderStatus.UNAVAILABLE, "provider_timeout"
                ) from exc
            except httpx.HTTPError as exc:
                raise OpenMeteoError(
                    ProviderStatus.UNAVAILABLE, "provider_transport_error"
                ) from exc

            if response.status_code == 429:
                raise OpenMeteoError(
                    ProviderStatus.RATE_LIMITED,
                    "provider_rate_limited",
                    retry_after=response.headers.get("Retry-After"),
                )
            if response.status_code in {401, 403}:
                raise OpenMeteoError(ProviderStatus.UNAUTHORIZED, "provider_unauthorized")
            if response.status_code >= 500:
                if attempt == 0:
                    await asyncio.sleep(0.25)
                    continue
                raise OpenMeteoError(
                    ProviderStatus.UNAVAILABLE, "provider_server_error"
                )
            if response.status_code >= 400:
                raise OpenMeteoError(
                    ProviderStatus.UNAVAILABLE, "provider_request_rejected"
                )
            if len(response.content) > 1_000_000:
                raise OpenMeteoError(ProviderStatus.MALFORMED, "response_too_large")
            try:
                return parse_forecast_payload(response.json())
            except ValueError as exc:
                raise OpenMeteoError(
                    ProviderStatus.MALFORMED, "invalid_json"
                ) from exc
        raise OpenMeteoError(ProviderStatus.UNAVAILABLE, "provider_server_error")


class WeatherContextService:
    """Fetch, cache and return explicitly time-stamped weather forecasts."""

    def __init__(
        self,
        db: Session,
        *,
        api_key: str | None = None,
        cache_ttl_seconds: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        now: datetime | None = None,
    ) -> None:
        settings = get_settings()
        self.db = db
        self.api_key = settings.open_meteo_api_key if api_key is None else api_key
        self.cache_ttl_seconds = (
            settings.weather_cache_ttl_seconds
            if cache_ttl_seconds is None
            else cache_ttl_seconds
        )
        self.transport = transport
        self.now = _aware_utc(now or datetime.now(timezone.utc))
        if self.cache_ttl_seconds <= 0:
            raise ValueError("Weather cache TTL must be greater than zero.")

    async def get_forecast(
        self, latitude: float, longitude: float, hours: int = 24
    ) -> WeatherForecastResponse:
        if not 1 <= hours <= MAX_FORECAST_HOURS:
            raise ValueError(f"Forecast hours must be between 1 and {MAX_FORECAST_HOURS}.")
        location_key, rounded_latitude, rounded_longitude = _coordinate_key(
            latitude, longitude
        )

        if self.api_key:
            cached = self._latest_success(location_key)
            if (
                cached is not None
                and cached.expires_at is not None
                and _aware_utc(cached.expires_at) > self.now
            ):
                return self._response(
                    cached,
                    rounded_latitude,
                    rounded_longitude,
                    hours,
                    ProviderStatus.VALID,
                )

        started_at = self.now
        try:
            metadata, rows = await OpenMeteoClient(
                self.api_key, transport=self.transport
            ).fetch(rounded_latitude, rounded_longitude)
            future_rows = [
                row for row in rows if row["target_time_utc"] >= started_at
            ]
            if not future_rows:
                raise OpenMeteoError(
                    ProviderStatus.MALFORMED, "forecast_has_no_future_targets"
                )
            completed_at = datetime.now(timezone.utc)
            run = ExternalFetchRun(
                provider=ProviderId.OPEN_METEO.value,
                source_version=SOURCE_VERSION,
                location_key=location_key,
                status=ProviderStatus.VALID.value,
                started_at=started_at,
                completed_at=completed_at,
                expires_at=completed_at
                + timedelta(seconds=self.cache_ttl_seconds),
                provider_metadata=metadata,
            )
            self.db.add(run)
            self.db.flush()
            for row in future_rows:
                values = row["values"]
                radiation_interval_start = row["target_time_utc"] - timedelta(hours=1)
                self.db.add(
                    WeatherForecastValue(
                        fetch_run_id=run.id,
                        source_time_label=row["source_time_label"],
                        target_time_utc=row["target_time_utc"],
                        interval_start_utc=(
                            radiation_interval_start
                            if values["shortwave_radiation"] is not None
                            else None
                        ),
                        interval_end_utc=(
                            row["target_time_utc"]
                            if values["shortwave_radiation"] is not None
                            else None
                        ),
                        time_semantics=(
                            "instantaneous_valid_time; "
                            "shortwave_radiation=preceding_hour_mean"
                        ),
                        temperature_2m_c=values["temperature_2m"],
                        apparent_temperature_c=values["apparent_temperature"],
                        relative_humidity_2m_percent=values["relative_humidity_2m"],
                        cloud_cover_percent=values["cloud_cover"],
                        shortwave_radiation_w_m2=values["shortwave_radiation"],
                        source_units=metadata["source_units"],
                        normalized_units=metadata["normalized_units"],
                    )
                )
            self.db.commit()
            self.db.refresh(run)
            self.db.refresh(run, attribute_names=["weather_values"])
            return self._response(
                run,
                rounded_latitude,
                rounded_longitude,
                hours,
                ProviderStatus.VALID,
            )
        except OpenMeteoError as exc:
            failed_run = ExternalFetchRun(
                provider=ProviderId.OPEN_METEO.value,
                source_version=SOURCE_VERSION,
                location_key=location_key,
                status=exc.status.value,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                expires_at=None,
                error_code=exc.error_code,
                provider_metadata={},
            )
            self.db.add(failed_run)
            self.db.commit()
            stale = self._latest_success(location_key)
            if (
                stale is not None
                and self.api_key
                and exc.error_code != "provider_not_configured"
                and exc.status != ProviderStatus.UNAUTHORIZED
            ):
                return self._response(
                    stale,
                    rounded_latitude,
                    rounded_longitude,
                    hours,
                    ProviderStatus.STALE,
                    error_code=exc.error_code,
                    configured=bool(self.api_key),
                    retry_after=exc.retry_after,
                )
            return WeatherForecastResponse(
                provider=ProviderFreshness(
                    provider=ProviderId.OPEN_METEO,
                    source_version=SOURCE_VERSION,
                    status=exc.status,
                    retrieved_at=datetime.now(timezone.utc),
                    error_code=exc.error_code,
                    retry_after=exc.retry_after,
                    configured=bool(self.api_key),
                    attribution=ATTRIBUTION,
                    attribution_url=ATTRIBUTION_URL,
                ),
                latitude=rounded_latitude,
                longitude=rounded_longitude,
            )

    def _latest_success(self, location_key: str) -> ExternalFetchRun | None:
        return (
            self.db.query(ExternalFetchRun)
            .options(selectinload(ExternalFetchRun.weather_values))
            .filter(
                ExternalFetchRun.provider == ProviderId.OPEN_METEO.value,
                ExternalFetchRun.location_key == location_key,
                ExternalFetchRun.status == ProviderStatus.VALID.value,
            )
            .order_by(ExternalFetchRun.completed_at.desc())
            .first()
        )

    @staticmethod
    def _response(
        run: ExternalFetchRun,
        latitude: float,
        longitude: float,
        hours: int,
        status: ProviderStatus,
        *,
        error_code: str | None = None,
        configured: bool = True,
        retry_after: str | None = None,
    ) -> WeatherForecastResponse:
        now = datetime.now(timezone.utc)
        values = sorted(run.weather_values, key=lambda row: row.target_time_utc)
        hourly = [
            WeatherHour(
                source_time_label=row.source_time_label,
                target_time_utc=_aware_utc(row.target_time_utc),
                interval_start_utc=(
                    _aware_utc(row.interval_start_utc)
                    if row.interval_start_utc is not None
                    else None
                ),
                interval_end_utc=(
                    _aware_utc(row.interval_end_utc)
                    if row.interval_end_utc is not None
                    else None
                ),
                time_semantics=row.time_semantics,
                interval_semantics_field=(
                    "shortwave_radiation"
                    if row.interval_start_utc is not None
                    else None
                ),
                temperature_2m=row.temperature_2m_c,
                apparent_temperature=row.apparent_temperature_c,
                relative_humidity=row.relative_humidity_2m_percent,
                cloud_cover=row.cloud_cover_percent,
                shortwave_radiation=row.shortwave_radiation_w_m2,
                source_units=row.source_units,
                normalized_units=row.normalized_units,
            )
            for row in values
            if _aware_utc(row.target_time_utc) >= now
        ][:hours]
        metadata = dict(run.provider_metadata)
        fresh_until = (
            _aware_utc(run.expires_at) if run.expires_at is not None else None
        )
        retrieved_at = _aware_utc(run.completed_at)
        return WeatherForecastResponse(
            provider=ProviderFreshness(
                provider=ProviderId.OPEN_METEO,
                source_version=run.source_version,
                status=status,
                retrieved_at=retrieved_at,
                fresh_until=fresh_until,
                last_successful_fetch_at=retrieved_at,
                error_code=error_code,
                retry_after=retry_after,
                configured=configured,
                attribution=ATTRIBUTION,
                attribution_url=ATTRIBUTION_URL,
            ),
            latitude=latitude,
            longitude=longitude,
            provider_metadata=metadata,
            model_selection=metadata.get("model_selection"),
            hourly=hourly,
        )
