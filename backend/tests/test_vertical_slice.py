"""Authenticated API journey for registration through NEM12 billing."""

from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import get_db
from app.main import app as fastapi_app
from app.models.base import Base
from app.services.auth import AuthService

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
SAMPLE_NEM12 = Path(__file__).with_name("sample_nem12.csv")


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(monkeypatch):
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("app.api.upload.SessionLocal", TestingSessionLocal)
    fastapi_app.dependency_overrides[get_db] = override_get_db

    def disable_external_queue(*args, **kwargs):
        raise RuntimeError("External queue disabled for deterministic integration test")

    monkeypatch.setattr("app.tasks.enqueue_import", disable_external_queue)
    try:
        with TestClient(
            fastapi_app,
            client=("198.51.100.10", 12345),
        ) as test_client:
            yield test_client
    finally:
        fastapi_app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


def test_authenticated_nem12_to_tariff_and_billing_journey(client):
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": "journey@example.com",
            "password": "testpassword123",
            "full_name": "Journey User",
        },
    )
    assert registration.status_code == 201

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "journey@example.com", "password": "testpassword123"},
    )
    assert login.status_code == 200
    tokens = login.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    fixture_bytes = SAMPLE_NEM12.read_bytes()
    uploaded = client.post(
        "/api/v1/upload",
        files={"file": ("sample_nem12.csv", fixture_bytes, "text/csv")},
        headers=headers,
    )
    assert uploaded.status_code == 200
    upload_id = uploaded.json()["upload_id"]
    status = client.get(f"/api/v1/upload/{upload_id}", headers=headers)
    assert status.status_code == 200
    assert status.json()["status"] == "completed"
    assert status.json()["total_readings"] == 336
    assert any("Direction is unresolved" in warning for warning in status.json()["warnings"])

    meters_response = client.get("/api/v1/meters", headers=headers)
    assert meters_response.status_code == 200
    meters = meters_response.json()
    assert len(meters) == 1
    meter_id = meters[0]["id"]

    repeated_upload = client.post(
        "/api/v1/upload",
        files={"file": ("sample_nem12.csv", fixture_bytes, "text/csv")},
        headers=headers,
    )
    assert repeated_upload.status_code == 200
    assert repeated_upload.json()["upload_id"] == upload_id
    assert "already imported" in repeated_upload.json()["message"].lower()

    invalid_upload = client.post(
        "/api/v1/upload",
        files={"file": ("invalid.csv", b"not a NEM12 file", "text/csv")},
        headers=headers,
    )
    assert invalid_upload.status_code == 400

    tariff = client.post(
        "/api/v1/tariffs",
        json={
            "tariff_type": "flat",
            "flat_rate_cents_kwh": 30,
            "feed_in_rate_cents_kwh": 5,
            "daily_supply_charge_cents": 100,
            "rates_include_gst": True,
        },
        headers=headers,
    )
    assert tariff.status_code == 201

    # NEM12 suffix-to-direction semantics remain unverified, so these imported
    # readings must not be presented as consumption or used in usage totals.
    usage = client.get(f"/api/v1/usage/summary/{meter_id}", headers=headers)
    assert usage.status_code == 404
    assert "No usage data found" in usage.json()["detail"]

    comparison = client.get(
        f"/api/v1/billing/comparison/{meter_id}",
        params={
            "current_start": "2025-04-01",
            "current_end": "2025-04-02",
            "previous_start": "2025-03-30",
            "previous_end": "2025-03-31",
        },
        headers=headers,
    )
    assert comparison.status_code == 200
    breakdown = comparison.json()["current_breakdown"]
    assert breakdown["data_status"] == "partial"
    assert breakdown["import_kwh"] == 0
    assert breakdown["unresolved_reading_count"] > 0
    assert breakdown["missing_interval_count"] > 0
    assert breakdown["estimate_type"] == "configured_tariff_estimate"
    assert comparison.json()["comparison"]["trend"] == "unavailable"
    assert comparison.json()["comparison"]["kwh_change_percent"] is None
    assert comparison.json()["recommendations"] == []

    user_id = registration.json()["id"]
    expired_access = AuthService.create_access_token(
        {"sub": str(user_id)},
        expires_delta=timedelta(seconds=-1),
    )
    expired_response = client.get(
        "/api/v1/meters",
        headers={"Authorization": f"Bearer {expired_access}"},
    )
    assert expired_response.status_code == 401

    refresh = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh.status_code == 200
    refreshed_meters = client.get(
        "/api/v1/meters",
        headers={"Authorization": f"Bearer {refresh.json()['access_token']}"},
    )
    assert refreshed_meters.status_code == 200
    assert len(refreshed_meters.json()) == 1
