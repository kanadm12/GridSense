"""Tests for environment-sensitive application configuration."""

import pytest
from pydantic import ValidationError

from app.config import Settings


def _production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "debug": False,
        "secret_key": "a" * 32,
        "cors_origins": ["https://app.gridsense.example.com"],
    }
    values.update(overrides)
    return Settings(**values)


def test_development_generates_secret_for_unset_key():
    settings = Settings(debug=True, secret_key="")

    assert len(settings.secret_key) >= 32


@pytest.mark.parametrize(
    "secret_key",
    ["", "your-secret-key-change-in-production", "short-secret"],
)
def test_production_rejects_unsafe_secret_key(secret_key: str):
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        _production_settings(secret_key=secret_key)


def test_production_rejects_localhost_cors_origin():
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        _production_settings(cors_origins=["http://localhost:3000"])


def test_production_accepts_explicit_secure_settings():
    settings = _production_settings()

    assert settings.debug is False
    assert settings.secret_key == "a" * 32


def test_smtp_provider_requires_host():
    with pytest.raises(ValidationError, match="SMTP_HOST"):
        _production_settings(email_provider="smtp", smtp_host="")


def test_home_assistant_provider_requires_token():
    with pytest.raises(ValidationError, match="HOME_ASSISTANT_TOKEN"):
        _production_settings(automation_provider="home_assistant", home_assistant_token="")
