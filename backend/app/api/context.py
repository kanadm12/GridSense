"""Read-only weather and market-context endpoints."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.external_data import (
    DataKind,
    MarketContextResponse,
    ProviderAvailabilityResponse,
    ProviderFreshness,
    ProviderId,
    ProviderStatus,
    WeatherForecastResponse,
    WeatherHourlyRequest,
    WeatherLocationRequest,
)
from app.services.open_meteo import SOURCE_VERSION, WeatherContextService

router = APIRouter(prefix="/context", tags=["External context"])


@router.post("/weather/summary", response_model=WeatherForecastResponse)
@limiter.limit("15/minute")
async def weather_summary(
    request: Request,
    location: WeatherLocationRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> WeatherForecastResponse:
    """Return up to the next 24 forecast hours for a user-provided approximate location."""
    return await WeatherContextService(db).get_forecast(
        location.latitude, location.longitude, hours=24
    )


@router.post("/weather/hourly", response_model=WeatherForecastResponse)
@limiter.limit("15/minute")
async def weather_hourly(
    request: Request,
    location: WeatherHourlyRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> WeatherForecastResponse:
    """Return hourly weather context with UTC target timestamps and source units."""
    return await WeatherContextService(db).get_forecast(
        location.latitude, location.longitude, hours=location.hours
    )


@router.get("/market/summary", response_model=MarketContextResponse)
async def market_summary(_: User = Depends(get_current_user)) -> MarketContextResponse:
    """Report the market-data gate without exposing unverified prices."""
    return MarketContextResponse(
        provider=ProviderFreshness(
            provider=ProviderId.AEMO_NEMWEB,
            source_version="NEMWeb file contracts not verified",
            status=ProviderStatus.BLOCKED,
            configured=False,
            error_code="source_contract_unverified",
        ),
        region=None,
        data_kind=DataKind.OBSERVED,
        message=(
            "Victorian wholesale market values are unavailable until AEMO file "
            "semantics, regional identifier, and data-use terms are verified. "
            "Wholesale prices are not a customer retail tariff."
        ),
    )


@router.get("/providers", response_model=ProviderAvailabilityResponse)
async def provider_availability(
    _: User = Depends(get_current_user),
) -> ProviderAvailabilityResponse:
    """Return configuration and source-verification state without contacting providers."""
    settings = get_settings()
    weather_configured = bool(settings.open_meteo_api_key)
    return ProviderAvailabilityResponse(
        providers=[
            ProviderFreshness(
                provider=ProviderId.OPEN_METEO,
                source_version=SOURCE_VERSION,
                status=ProviderStatus.UNAVAILABLE,
                configured=weather_configured,
                error_code=(
                    "provider_not_configured"
                    if not weather_configured
                    else "awaiting_location_request"
                ),
                attribution="Weather data by Open-Meteo.com",
                attribution_url="https://open-meteo.com/",
            ),
            ProviderFreshness(
                provider=ProviderId.AEMO_NEMWEB,
                source_version="NEMWeb file contracts not verified",
                status=ProviderStatus.BLOCKED,
                configured=False,
                error_code="source_contract_unverified",
            ),
        ]
    )
