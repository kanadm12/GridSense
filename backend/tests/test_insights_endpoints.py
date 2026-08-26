"""End-to-end smoke tests for the insights, usage and billing endpoints.

These are regression guards for the runtime-fatal bugs that a unit test alone would miss,
because they only surface once the full request/response cycle runs:

- ``/insights/*`` used to 500 because the services read ``r.kwh`` (the model has ``value``).
- ``/usage/weekly/{id}`` referenced an undefined ``get_user_meter`` -> ``NameError`` -> 500.
- ``/billing/comparison/{id}`` referenced an uncaptured ``meter`` -> ``NameError`` on
  ``meter.name``.
- Every endpoint's default-meter path selects ``Meter.is_active``; before the column
  existed the query raised at runtime. Calling these endpoints *without* an explicit
  meter_id exercises that path.
"""

from datetime import date, datetime, timedelta
from importlib import import_module
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from slowapi import Limiter
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_current_user
from app.database import get_db
from app.main import app
from app.models.base import Base
from app.models.meter import Meter
from app.models.reading import Reading
from app.models.user import User

import_module("app.models")

# Distinct shared in-memory DB so this module never collides with test_auth's.
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///file:insights_tests_db?mode=memory&cache=shared"
engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False, "uri": True},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _seed(db) -> tuple[int, int]:
    """Seed a user, one active meter, and ~5 weeks of half-hourly readings."""
    user = User(email="insights@example.com", hashed_password="x", full_name="Insights User")
    db.add(user)
    db.commit()
    db.refresh(user)

    meter = Meter(
        user_id=user.id, nmi="1234567890", suffix="B1", state="VIC",
        name="Insights Meter", is_active=True,
    )
    db.add(meter)
    db.commit()
    db.refresh(meter)

    readings = []
    for day_offset in range(35, -1, -1):  # today-35 .. today inclusive
        day = date.today() - timedelta(days=day_offset)
        for half_hour in range(48):
            ts = datetime.combine(day, datetime.min.time()) + timedelta(minutes=30 * half_hour)
            hour = ts.hour
            if 15 <= hour < 21:
                value = 1.0
            elif hour >= 22 or hour < 7:
                value = 0.3
            else:
                value = 0.5
            readings.append(
                Reading(meter_id=meter.id, timestamp=ts, value=value, quality="A", register_type="B")
            )
    db.add_all(readings)
    db.commit()
    return user.id, meter.id


@pytest.fixture
def api():
    """Authenticated TestClient plus the seeded ids, with db + auth overridden."""
    app.state.limiter = Limiter(key_func=lambda req: "test", default_limits=[])

    db = TestingSessionLocal()
    try:
        user_id, meter_id = _seed(db)
    finally:
        db.close()

    app.dependency_overrides[get_db] = override_get_db
    import sys

    for mod in list(sys.modules.values()):
        try:
            candidate = getattr(mod, "get_db", None)
            if callable(candidate):
                app.dependency_overrides[candidate] = override_get_db
        except Exception:
            continue

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)

    with TestClient(app) as client:
        yield SimpleNamespace(client=client, user_id=user_id, meter_id=meter_id)

    app.dependency_overrides.clear()


class TestInsightsEndpoints:
    def test_forecast_default_meter(self, api):
        # No meter_id -> exercises the Meter.is_active default-meter lookup.
        resp = api.client.get("/api/v1/insights/forecast")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["meter_id"] == api.meter_id
        assert body["usage_so_far_kwh"] >= 0
        assert "projected_total_cost" in body

    def test_forecast_explicit_meter(self, api):
        resp = api.client.get(f"/api/v1/insights/forecast?meter_id={api.meter_id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["meter_id"] == api.meter_id

    def test_trend(self, api):
        resp = api.client.get("/api/v1/insights/trend?months=3")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["meter_id"] == api.meter_id
        assert isinstance(body["months"], list)

    def test_anomalies(self, api):
        resp = api.client.get("/api/v1/insights/anomalies?days=30")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_anomalies"] == len(body["anomalies"])

    def test_daily_brief(self, api):
        resp = api.client.get("/api/v1/insights/daily-brief")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "greeting" in body
        assert "yesterday_usage_kwh" in body


class TestUsageEndpoint:
    def test_weekly_usage_does_not_raise_name_error(self, api):
        # Before the fix this endpoint referenced an undefined get_user_meter -> 500.
        resp = api.client.get(f"/api/v1/usage/weekly/{api.meter_id}")
        assert resp.status_code == 200, resp.text
        assert isinstance(resp.json(), list)


class TestBillingEndpoint:
    def test_comparison_returns_meter_name(self, api):
        # Before the fix, meter was uncaptured and meter.name raised NameError.
        current_end = date.today()
        current_start = current_end - timedelta(days=13)
        resp = api.client.get(
            f"/api/v1/billing/comparison/{api.meter_id}",
            params={"current_start": current_start.isoformat(), "current_end": current_end.isoformat()},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["meter_name"] == "Insights Meter"
        assert "comparison" in body
