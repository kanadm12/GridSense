"""Tests for the password reset delivery and token lifecycle."""

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import get_db
from app.main import app
from app.models import Base

engine = create_engine(
    "sqlite:///file:password_reset_tests?mode=memory&cache=shared",
    connect_args={"check_same_thread": False, "uri": True},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class CapturingEmailProvider:
    """Test provider that records the generated reset URL."""

    reset_url: str | None = None

    async def send_password_reset(self, recipient: str, reset_url: str) -> None:
        self.reset_url = reset_url


def test_password_reset_uses_delivered_token_and_invalidates_it(monkeypatch):
    Base.metadata.create_all(bind=engine)
    provider = CapturingEmailProvider()
    monkeypatch.setattr("app.api.password_reset.get_email_provider", lambda settings: provider)
    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            register_response = client.post(
                "/api/v1/auth/register",
                json={"email": "reset@example.com", "password": "OriginalPass123!"},
            )
            assert register_response.status_code == 201

            forgot_response = client.post(
                "/api/v1/auth/forgot-password",
                json={"email": "reset@example.com"},
            )
            assert forgot_response.status_code == 200
            assert provider.reset_url is not None

            token = parse_qs(urlparse(provider.reset_url).query)["token"][0]
            reset_response = client.post(
                "/api/v1/auth/reset-password",
                json={"token": token, "new_password": "UpdatedPass123!"},
            )
            assert reset_response.status_code == 200

            login_response = client.post(
                "/api/v1/auth/login",
                json={"email": "reset@example.com", "password": "UpdatedPass123!"},
            )
            assert login_response.status_code == 200

            reused_token_response = client.post(
                "/api/v1/auth/reset-password",
                json={"token": token, "new_password": "AnotherPass123!"},
            )
            assert reused_token_response.status_code == 400
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
