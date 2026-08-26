"""Application configuration settings."""

import secrets
from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _generate_dev_secret() -> str:
    """Generate a random secret key for development."""
    return secrets.token_urlsafe(32)


INSECURE_SECRET_KEYS = {
    "",
    "your-secret-key-change-in-production",
    "dev-secret-key-change-in-production-use-openssl-rand-hex-32",
    "dev-secret-change-me",
}


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_name: str = "GridSense API"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "sqlite:///./gridsense.db"
    # Redis for background jobs
    redis_url: str = "redis://localhost:6380/0"

    # Password reset email
    email_provider: str = "local"
    email_from: str = "GridSense <no-reply@gridsense.local>"
    frontend_reset_url: str = "gridsense://reset-password"
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True

    # Home automation
    automation_provider: str = "simulator"
    home_assistant_url: str = "http://homeassistant:8123"
    home_assistant_token: str = ""

    # Authentication
    secret_key: str = ""
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    refresh_token_expire_days: int = 30

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:19006", "exp://"]

    @field_validator("secret_key", mode="before")
    @classmethod
    def normalize_secret_key(cls, value: str | None) -> str:
        """Normalize an unset secret key before environment validation."""
        return value or ""

    @model_validator(mode="after")
    def validate_environment(self) -> "Settings":
        """Reject unsafe production settings while keeping local development ergonomic."""
        if self.debug:
            if self.secret_key in INSECURE_SECRET_KEYS:
                self.secret_key = _generate_dev_secret()
            return self

        if self.secret_key in INSECURE_SECRET_KEYS or len(self.secret_key) < 32:
            raise ValueError(
                "SECRET_KEY must be explicitly set to at least 32 characters when DEBUG=false"
            )

        if not self.cors_origins or any(
            origin == "*" or "localhost" in origin or "127.0.0.1" in origin
            for origin in self.cors_origins
        ):
            raise ValueError(
                "CORS_ORIGINS must contain explicit non-localhost origins when DEBUG=false"
            )

        if self.email_provider not in {"local", "smtp"}:
            raise ValueError("EMAIL_PROVIDER must be either 'local' or 'smtp'")
        if self.email_provider == "smtp" and not self.smtp_host:
            raise ValueError("SMTP_HOST is required when EMAIL_PROVIDER=smtp")

        if self.automation_provider not in {"simulator", "home_assistant"}:
            raise ValueError("AUTOMATION_PROVIDER must be either 'simulator' or 'home_assistant'")
        if self.automation_provider == "home_assistant" and not self.home_assistant_token:
            raise ValueError(
                "HOME_ASSISTANT_TOKEN is required when AUTOMATION_PROVIDER=home_assistant"
            )

        return self


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
