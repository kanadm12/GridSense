"""Contract and failure tests for Open-Meteo and market-context boundaries."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.context import market_summary
from app.api.deps import get_current_user
from app.database import get_db
from app.main import app
from app.models.external_data import ExternalFetchRun, WeatherForecastValue
from app.schemas.external_data import (
    ProviderFreshness,
    ProviderId,
    ProviderStatus,
    WeatherForecastResponse,
)
from app.services.open_meteo import (
    OpenMeteoClient,
    OpenMeteoError,
    WeatherContextService,
    parse_forecast_payload,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "external" / "open_meteo_forecast_api_v1.json"


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _future_fixture(now: datetime) -> dict:
    payload = _fixture()
    start = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start += timedelta(hours=1)
    payload["hourly"]["time"] = [
        (start + timedelta(hours=index)).strftime("%Y-%m-%dT%H:%M")
        for index in range(len(payload["hourly"]["time"]))
    ]
    return payload


def test_weather_parser_preserves_units_metadata_and_interval_semantics():
    metadata, rows = parse_forecast_payload(_fixture())

    assert metadata["model_selection"] == "best_match"
    assert metadata["forecast_issue_time_available"] is False
    assert metadata["source_units"]["temperature_2m"] == "°C"
    assert metadata["normalized_units"]["shortwave_radiation"] == "W/m²"
    assert rows[0]["target_time_utc"] == datetime(2030, 1, 15, tzinfo=timezone.utc)


def test_weather_parser_converts_fahrenheit_and_preserves_original_unit():
    payload = _fixture()
    payload["hourly_units"]["temperature_2m"] = "°F"
    payload["hourly"]["temperature_2m"] = [68.0, 69.8, 71.6]

    metadata, rows = parse_forecast_payload(payload)

    assert metadata["source_units"]["temperature_2m"] == "°F"
    assert metadata["normalized_units"]["temperature_2m"] == "°C"
    assert [row["values"]["temperature_2m"] for row in rows] == pytest.approx(
        [20.0, 21.0, 22.0]
    )


@pytest.mark.parametrize(
    "mutation,error_code",
    [
        (lambda p: p.pop("hourly"), "missing_hourly_schema"),
        (lambda p: p["hourly"].pop("cloud_cover"), "missing_hourly_variable"),
        (
            lambda p: p["hourly_units"].update({"temperature_2m": "K"}),
            "unsupported_temperature_unit",
        ),
        (
            lambda p: p["hourly"]["relative_humidity_2m"].__setitem__(0, 101),
            "percentage_out_of_range",
        ),
        (
            lambda p: p["hourly"]["time"].__setitem__(1, p["hourly"]["time"][0]),
            "duplicate_target_time",
        ),
    ],
)
def test_weather_parser_rejects_malformed_or_unsupported_payloads(mutation, error_code):
    payload = _fixture()
    mutation(payload)

    with pytest.raises(OpenMeteoError) as raised:
        parse_forecast_payload(payload)

    assert raised.value.status == ProviderStatus.MALFORMED
    assert raised.value.error_code == error_code


def test_open_meteo_client_uses_paid_endpoint_and_keeps_secret_out_of_errors():
    requested = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request)
        return httpx.Response(200, json=_fixture())

    metadata, rows = asyncio.run(
        OpenMeteoClient(
            "test-secret", transport=httpx.MockTransport(handler)
        ).fetch(-37.81, 144.96)
    )

    assert requested[0].url.host == "customer-api.open-meteo.com"
    assert requested[0].url.params["apikey"] == "test-secret"
    assert requested[0].url.params["timezone"] == "UTC"
    assert requested[0].url.params["forecast_days"] == "3"
    assert requested[0].url.params["models"] == "best_match"
    assert len(rows) == 3
    assert metadata["forecast_issue_time_available"] is False


def test_open_meteo_retries_server_errors_once_without_exposing_credentials():
    attempts = []

    async def handler(_: httpx.Request) -> httpx.Response:
        attempts.append(True)
        if len(attempts) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json=_fixture())

    asyncio.run(
        OpenMeteoClient(
            "credential-must-not-escape",
            transport=httpx.MockTransport(handler),
        ).fetch(-37.81, 144.96)
    )

    assert len(attempts) == 2


def test_open_meteo_retries_timeout_once():
    attempts = []

    async def handler(_: httpx.Request) -> httpx.Response:
        attempts.append(True)
        if len(attempts) == 1:
            raise httpx.ReadTimeout("provider timed out")
        return httpx.Response(200, json=_fixture())

    asyncio.run(
        OpenMeteoClient(
            "test-secret", transport=httpx.MockTransport(handler)
        ).fetch(-37.81, 144.96)
    )

    assert len(attempts) == 2


def test_open_meteo_exhausted_server_error_is_safe_and_explicit():
    attempts = []
    credential = "credential-must-not-escape"

    async def handler(_: httpx.Request) -> httpx.Response:
        attempts.append(True)
        return httpx.Response(503, text=credential)

    with pytest.raises(OpenMeteoError) as raised:
        asyncio.run(
            OpenMeteoClient(
                credential, transport=httpx.MockTransport(handler)
            ).fetch(-37.81, 144.96)
        )

    assert len(attempts) == 2
    assert raised.value.status == ProviderStatus.UNAVAILABLE
    assert raised.value.error_code == "provider_server_error"
    assert credential not in str(raised.value)


def test_aemo_market_status_is_blocked_without_retail_price():
    response = asyncio.run(market_summary(None))

    assert response.provider.status == ProviderStatus.BLOCKED
    assert response.region is None
    assert response.price_aud_mwh is None
    assert response.demand_mw is None
    assert "not a customer retail tariff" in response.message


def test_context_api_returns_weather_status_and_blocked_market_without_live_calls(
    test_db, monkeypatch
):
    class FakeWeatherService:
        def __init__(self, _db):
            pass

        async def get_forecast(self, latitude, longitude, hours):
            assert latitude == -37.81
            assert longitude == 144.96
            assert hours == 24
            return WeatherForecastResponse(
                provider=ProviderFreshness(
                    provider=ProviderId.OPEN_METEO,
                    source_version="Forecast API v1",
                    status=ProviderStatus.UNAVAILABLE,
                    configured=False,
                    error_code="provider_not_configured",
                ),
                latitude=latitude,
                longitude=longitude,
            )

    previous_overrides = app.dependency_overrides.copy()

    def override_db():
        yield test_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: object()
    monkeypatch.setattr(
        "app.api.context.WeatherContextService", FakeWeatherService
    )
    try:
        with TestClient(app) as client:
            weather = client.post(
                "/api/v1/context/weather/summary",
                json={"latitude": -37.81, "longitude": 144.96},
            )
            market = client.get("/api/v1/context/market/summary")
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)

    assert weather.status_code == 200
    assert weather.json()["provider"]["error_code"] == "provider_not_configured"
    assert market.status_code == 200
    assert market.json()["provider"]["status"] == "blocked"
    assert market.json()["price_aud_mwh"] is None


def test_context_market_api_requires_authentication():
    with TestClient(app) as client:
        response = client.get("/api/v1/context/market/summary")

    assert response.status_code == 403


@pytest.mark.parametrize(
    "status_code,expected",
    [
        (401, ProviderStatus.UNAUTHORIZED),
        (403, ProviderStatus.UNAUTHORIZED),
        (429, ProviderStatus.RATE_LIMITED),
    ],
)
def test_provider_access_and_rate_limits_are_explicit(status_code, expected):
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, headers={"Retry-After": "30"})

    with pytest.raises(OpenMeteoError) as raised:
        asyncio.run(
            OpenMeteoClient(
                "test-secret", transport=httpx.MockTransport(handler)
            ).fetch(-37.81, 144.96)
        )

    assert raised.value.status == expected
    if expected == ProviderStatus.RATE_LIMITED:
        assert raised.value.retry_after == "30"


def test_weather_context_persists_fetch_and_serves_fresh_cache(test_db):
    now = datetime.now(timezone.utc)
    calls = []

    async def handler(_: httpx.Request) -> httpx.Response:
        calls.append(True)
        return httpx.Response(200, json=_future_fixture(now))

    first = asyncio.run(
        WeatherContextService(
            test_db,
            api_key="test-secret",
            transport=httpx.MockTransport(handler),
            now=now,
        ).get_forecast(-37.8123, 144.9632, hours=2)
    )
    second = asyncio.run(
        WeatherContextService(
            test_db,
            api_key="test-secret",
            transport=httpx.MockTransport(handler),
            now=now + timedelta(seconds=1),
        ).get_forecast(-37.814, 144.964, hours=2)
    )

    assert len(calls) == 1
    assert first.provider.status == ProviderStatus.VALID
    assert first.forecast_issued_at is None
    assert first.provider.retrieved_at is not None
    assert len(second.hourly) == 2
    assert test_db.query(ExternalFetchRun).count() == 1
    assert test_db.query(WeatherForecastValue).count() == 3
    assert second.hourly[0].interval_start_utc is not None
    assert "shortwave_radiation=preceding_hour_mean" in second.hourly[0].time_semantics


def test_weather_context_does_not_serve_paid_data_without_configured_subscription(test_db):
    now = datetime.now(timezone.utc)

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_future_fixture(now))

    asyncio.run(
        WeatherContextService(
            test_db,
            api_key="test-secret",
            transport=httpx.MockTransport(handler),
            now=now,
        ).get_forecast(-37.81, 144.96)
    )
    stale = asyncio.run(
        WeatherContextService(
            test_db,
            api_key="",
            now=now + timedelta(hours=2),
        ).get_forecast(-37.81, 144.96)
    )

    assert stale.provider.status == ProviderStatus.UNAVAILABLE
    assert stale.provider.error_code == "provider_not_configured"
    assert stale.hourly == []


def test_weather_context_returns_stale_cache_when_provider_is_temporarily_unavailable(test_db):
    now = datetime.now(timezone.utc)

    async def successful(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_future_fixture(now))

    asyncio.run(
        WeatherContextService(
            test_db,
            api_key="test-secret",
            transport=httpx.MockTransport(successful),
            now=now,
        ).get_forecast(-37.81, 144.96)
    )

    async def unavailable(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    stale = asyncio.run(
        WeatherContextService(
            test_db,
            api_key="test-secret",
            cache_ttl_seconds=1,
            transport=httpx.MockTransport(unavailable),
            now=now + timedelta(hours=2),
        ).get_forecast(-37.81, 144.96)
    )

    assert stale.provider.status == ProviderStatus.STALE
    assert stale.provider.error_code == "provider_server_error"
    assert stale.provider.last_successful_fetch_at is not None


def test_revised_weather_forecast_is_a_distinct_auditable_fetch_run(test_db):
    now = datetime.now(timezone.utc)
    revised_payload = _future_fixture(now + timedelta(hours=2))

    async def first_fetch(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_future_fixture(now))

    asyncio.run(
        WeatherContextService(
            test_db,
            api_key="test-secret",
            transport=httpx.MockTransport(first_fetch),
            now=now,
        ).get_forecast(-37.81, 144.96)
    )
    revised_payload["hourly"]["temperature_2m"][0] += 3

    async def second_fetch(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=revised_payload)

    asyncio.run(
        WeatherContextService(
            test_db,
            api_key="test-secret",
            cache_ttl_seconds=1,
            transport=httpx.MockTransport(second_fetch),
            now=now + timedelta(hours=2),
        ).get_forecast(-37.81, 144.96)
    )

    runs = (
        test_db.query(ExternalFetchRun)
        .filter(ExternalFetchRun.status == ProviderStatus.VALID.value)
        .all()
    )
    assert len(runs) == 2
    assert test_db.query(WeatherForecastValue).count() == 6
    assert runs[0].id != runs[1].id
