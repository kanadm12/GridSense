"""Application configuration settings."""

import secrets
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _generate_dev_secret() -> str:
    """Generate a random secret key for development."""
    return secrets.token_urlsafe(32)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_name: str = "GridSense API"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "sqlite:///./gridsense.db"

    # Authentication
    secret_key: str = ""
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    refresh_token_expire_days: int = 30

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:19006", "exp://"]

    @field_validator("secret_key", mode="before")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        """Validate or generate secret key based on environment."""
        if v and v != "your-secret-key-change-in-production":
            return v
        # In production (debug=False), require explicit secret key
        # For now, generate a warning-worthy default for development
        import warnings
        warnings.warn(
            "Using auto-generated SECRET_KEY. Set SECRET_KEY environment variable in production!",
            UserWarning,
            stacklevel=2,
        )
        return _generate_dev_secret()


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
