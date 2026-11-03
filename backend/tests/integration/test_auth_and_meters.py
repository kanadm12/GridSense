"""PostgreSQL integration: authentication, ownership isolation and meter lifecycle."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery"  # noqa: S105 - disposable test credential


def _register_and_login(client, email: str) -> dict[str, str]:
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Integration User"},
    )
    assert reg.status_code == 201, reg.text
    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_register_login_and_me(client, pg_db):
    headers = _register_and_login(client, "alice@example.com")

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["email"] == "alice@example.com"


def test_duplicate_registration_is_rejected(client, pg_db):
    _register_and_login(client, "dup@example.com")
    again = client.post(
        "/api/v1/auth/register",
        json={"email": "dup@example.com", "password": PASSWORD},
    )
    assert again.status_code == 400


def test_wrong_password_is_rejected(client, pg_db):
    _register_and_login(client, "wrongpw@example.com")
    bad = client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpw@example.com", "password": "not-the-password"},
    )
    assert bad.status_code == 401


def test_meter_access_is_isolated_per_owner(client, pg_db):
    owner = _register_and_login(client, "owner@example.com")
    other = _register_and_login(client, "other@example.com")

    created = client.post(
        "/api/v1/meters",
        json={"nmi": "VAAA123456", "name": "Owner meter"},
        headers=owner,
    )
    assert created.status_code == 201, created.text
    meter_id = created.json()["id"]

    own_list = client.get("/api/v1/meters", headers=owner)
    assert own_list.status_code == 200
    assert [m["id"] for m in own_list.json()] == [meter_id]

    assert client.get("/api/v1/meters", headers=other).json() == []

    forbidden = client.get(f"/api/v1/meters/{meter_id}", headers=other)
    assert forbidden.status_code == 404

    missing = client.get("/api/v1/meters/999999", headers=owner)
    assert missing.status_code == 404


def test_unauthenticated_meter_access_is_rejected(client, pg_db):
    response = client.get("/api/v1/meters")
    assert response.status_code in {401, 403}
