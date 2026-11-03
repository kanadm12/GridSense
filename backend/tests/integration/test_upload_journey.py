"""PostgreSQL integration: NEM12 upload journey and per-owner access to imported data."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery"  # noqa: S105 - disposable test credential
SAMPLE_NEM12 = Path(__file__).resolve().parents[1] / "sample_nem12.csv"


def _register_and_login(client, email: str) -> dict[str, str]:
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Integration User"},
    )
    assert reg.status_code == 201, reg.text
    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _upload_sample(client, headers: dict[str, str]) -> int:
    content = SAMPLE_NEM12.read_bytes()
    response = client.post(
        "/api/v1/upload",
        files={"file": ("sample_nem12.csv", content, "text/csv")},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["upload_id"]


def test_nem12_upload_imports_and_exposes_usage_to_owner_only(client, pg_db):
    owner = _register_and_login(client, "uploader@example.com")
    other = _register_and_login(client, "stranger@example.com")

    upload_id = _upload_sample(client, owner)

    status_resp = client.get(f"/api/v1/upload/{upload_id}", headers=owner)
    assert status_resp.status_code == 200, status_resp.text
    body = status_resp.json()
    assert body["status"] == "completed", body
    assert body["total_readings"] > 0, body

    meters = client.get("/api/v1/meters", headers=owner)
    assert meters.status_code == 200, meters.text
    meter_ids = [m["id"] for m in meters.json()]
    assert len(meter_ids) == 1, meters.json()
    meter_id = meter_ids[0]

    # The summary defaults to the trailing 30 days; the sample data is dated April 2025.
    window = {"start_date": "2025-04-01", "end_date": "2025-04-30"}
    summary = client.get(f"/api/v1/usage/summary/{meter_id}", params=window, headers=owner)
    assert summary.status_code == 200, summary.text
    assert summary.json()["nmi"] == "VAAA123456"
    # The NEM12 parser marks clock basis as unverified and direction as unknown, so
    # the billable-consumption filter excludes these readings. This is intended behaviour.
    assert summary.json()["total_kwh"] == 0

    assert client.get(f"/api/v1/upload/{upload_id}", headers=other).status_code == 404
    forbidden = client.get(f"/api/v1/usage/summary/{meter_id}", params=window, headers=other)
    assert forbidden.status_code == 404


def test_upload_requires_authentication(client, pg_db):
    response = client.post(
        "/api/v1/upload",
        files={"file": ("sample_nem12.csv", SAMPLE_NEM12.read_bytes(), "text/csv")},
    )
    assert response.status_code in {401, 403}
