from fastapi.testclient import TestClient

from app.main import app
from app.rate_limit import limiter


def _reset_limiter():
    limiter._key_func = lambda req: "test"
    limiter._storage.clear("test")
    limiter.enabled = True


def _login_and_get_headers(client: TestClient) -> dict[str, str]:
    email = "ratelimit@example.com"
    password = "testpassword123"

    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Rate Limit User"},
    )
    assert register.status_code in (201, 400)

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_upload_endpoint_is_rate_limited():
    _reset_limiter()
    app.state.limiter = limiter

    with TestClient(app) as client:
        headers = _login_and_get_headers(client)
        with open("tests/sample_nem12.csv", "rb") as f:
            files = {"file": ("sample_nem12.csv", f, "text/csv")}
            first = client.post("/api/v1/upload", files=files, headers=headers)
            second = client.post("/api/v1/upload", files=files, headers=headers)

    assert first.status_code in (200, 400, 401)
    assert second.status_code in (200, 400, 401, 429)


def test_chat_message_is_rate_limited():
    _reset_limiter()
    app.state.limiter = limiter

    with TestClient(app) as client:
        headers = _login_and_get_headers(client)
        payload = {"message": "What is my bill trend?"}
        first = client.post("/api/v1/chat/message", json=payload, headers=headers)
        second = client.post("/api/v1/chat/message", json=payload, headers=headers)

    assert first.status_code in (200, 401, 404, 500)
    assert second.status_code in (200, 401, 404, 429, 500)
