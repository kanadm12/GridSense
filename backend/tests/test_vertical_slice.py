"""Authenticated API journey for registration through advisory scheduling."""

import json
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

    other_registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": "journey-other@example.com",
            "password": "testpassword123",
            "full_name": "Other Journey User",
        },
    )
    assert other_registration.status_code == 201
    other_login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "journey-other@example.com",
            "password": "testpassword123",
        },
    )
    assert other_login.status_code == 200
    other_headers = {
        "Authorization": f"Bearer {other_login.json()['access_token']}"
    }
    assert client.get("/api/v1/meters", headers=other_headers).json() == []
    assert client.get(
        f"/api/v1/recommendations/{meter_id}",
        headers=other_headers,
    ).status_code == 404

    recommendations = client.get(
        f"/api/v1/recommendations/{meter_id}",
        headers=headers,
    )
    assert recommendations.status_code == 200
    assert recommendations.json()["total_potential_savings"] is None
    assert all(
        item["potential_savings_dollars"] is None
        for item in recommendations.json()["recommendations"]
    )

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
            "confirmed": True,
            "effective_from": "2025-03-01",
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
    assert breakdown["estimate_type"] == "partial_estimate"
    assert comparison.json()["comparison"]["trend"] == "unavailable"
    assert comparison.json()["comparison"]["kwh_change_percent"] is None
    assert comparison.json()["recommendations"] == []

    scheduling_request = json.loads(
        (Path(__file__).parent / "fixtures" / "scheduling_v1.json").read_text(
            encoding="utf-8"
        )
    )["request"]
    scheduling_request["meter_id"] = meter_id
    scheduling_request["tariff_id"] = tariff.json()["id"]
    preview = client.post(
        "/api/v1/scheduling/v1/plans/preview",
        json=scheduling_request,
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["baseline_eligibility"]["status"] == "eligible_synthetic"
    assert preview.json()["calculation_evidence"]["status"] == "illustrative"
    assert preview.json()["candidate_schedule"]["status"] == "feasible"

    provider_status = client.get("/api/v1/context/providers", headers=headers)
    assert provider_status.status_code == 200
    assert provider_status.json()["providers"][0]["error_code"] == "provider_not_configured"
    market_status = client.get("/api/v1/context/market/summary", headers=headers)
    assert market_status.status_code == 200
    assert market_status.json()["provider"]["status"] == "blocked"


def test_tariff_revisions_require_confirmation_and_preserve_scenario_history(client):
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": "tariff-history@example.com",
            "password": "testpassword123",
            "full_name": "Tariff User",
        },
    )
    assert registration.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "tariff-history@example.com", "password": "testpassword123"},
    )
    tokens = login.json()
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    unconfirmed = client.post(
        "/api/v1/tariffs",
        json={"tariff_type": "flat", "flat_rate_cents_kwh": 31},
        headers=headers,
    )
    assert unconfirmed.status_code == 422

    first = client.post(
        "/api/v1/tariffs",
        json={
            "tariff_type": "flat",
            "flat_rate_cents_kwh": 31,
            "effective_from": "2026-01-01",
            "confirmed": True,
            "unmodeled_components_confirmed_absent": True,
        },
        headers=headers,
    )
    assert first.status_code == 201
    first_revision = first.json()["revision_number"]

    second = client.post(
        "/api/v1/tariffs",
        json={
            "tariff_type": "flat",
            "flat_rate_cents_kwh": 35,
            "effective_from": "2026-10-01",
            "confirmed": True,
            "unmodeled_components_confirmed_absent": True,
        },
        headers=headers,
    )
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["revision_number"] == first_revision + 1

    history = client.get("/api/v1/tariffs/revisions", headers=headers)
    assert history.status_code == 200
    revisions = history.json()
    assert [revision["revision_number"] for revision in revisions] == [2, 1]
    assert revisions[1]["flat_rate_cents_kwh"] == 31
    assert revisions[0]["flat_rate_cents_kwh"] == 35
    assert all(revision["confirmed_at"] for revision in revisions)
    assert all(not revision["is_illustrative"] for revision in revisions)

    preset = client.post(
        "/api/v1/tariffs/from-preset/agl_residential_flat",
        headers=headers,
    )
    assert preset.status_code == 200
    assert preset.json()["is_confirmed"] is False
    history_after_preset = client.get("/api/v1/tariffs/revisions", headers=headers)
    assert history_after_preset.status_code == 200
    latest = history_after_preset.json()[0]
    assert latest["is_illustrative"] is True
    assert latest["source_type"] == "illustrative_preset"
    assert latest["confirmed_at"] is None

    other_registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": "other-tariff-history@example.com",
            "password": "testpassword123",
            "full_name": "Other User",
        },
    )
    assert other_registration.status_code == 201
    other_login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "other-tariff-history@example.com",
            "password": "testpassword123",
        },
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}
    other_history = client.get("/api/v1/tariffs/revisions", headers=other_headers)
    assert other_history.status_code == 200
    assert other_history.json() == []

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
    assert refreshed_meters.json() == []


def test_aer_generic_plan_detail_does_not_activate_or_rewrite_tariff(client, monkeypatch):
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": "aer-reference@example.com",
            "password": "testpassword123",
            "full_name": "AER Reference User",
        },
    )
    assert registration.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "aer-reference@example.com", "password": "testpassword123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    tariff = client.post(
        "/api/v1/tariffs",
        json={
            "tariff_type": "flat",
            "flat_rate_cents_kwh": 32,
            "effective_from": "2026-01-01",
            "confirmed": True,
            "unmodeled_components_confirmed_absent": True,
        },
        headers=headers,
    )
    assert tariff.status_code == 201
    before = client.get("/api/v1/tariffs/revisions", headers=headers).json()

    class MockAERClient:
        async def get_plan_detail(self, brand: str, plan_id: str) -> dict:
            return {
                "plan_id": plan_id,
                "brand": brand,
                "brand_name": "AGL",
                "display_name": "Reference plan",
                "effective_from": "2026-10-01T00:00:00Z",
                "effective_to": "2026-11-01T00:00:00Z",
                "last_updated": "2026-10-28T00:00:00Z",
                "source_api_version": 3,
                "source_registry_version": "January 2026",
                "retrieved_at": "2026-10-31T00:00:00Z",
                "terms": {"pricingModel": "SINGLE_RATE"},
                "unsupported_components": ["generic reference only"],
                "requires_manual_user_review": True,
                "source_url": "https://cdr.energymadeeasy.gov.au/agl/cds-au/v1/energy/plans/plan",
            }

    monkeypatch.setattr("app.api.tariffs.AERPRDClient", MockAERClient)
    detail = client.get(
        "/api/v1/tariffs/catalog/aer/plans/reference-plan",
        params={"brand": "agl"},
    )

    assert detail.status_code == 200
    assert detail.json()["requires_manual_user_review"] is True
    assert client.get("/api/v1/tariffs/revisions", headers=headers).json() == before
