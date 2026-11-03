"""Persisted provider fetch metadata and hourly weather forecast values."""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ExternalFetchRun(Base):
    """One provider request or cache refresh, retaining provider-level provenance."""

    __tablename__ = "external_fetch_runs"
    __table_args__ = (
        Index(
            "ix_external_fetch_provider_location_status",
            "provider",
            "location_key",
            "status",
            "completed_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    source_version: Mapped[str] = mapped_column(String(80), nullable=False)
    location_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    provider_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    weather_values: Mapped[list["WeatherForecastValue"]] = relationship(
        back_populates="fetch_run", cascade="all, delete-orphan"
    )


class WeatherForecastValue(Base):
    """Normalized weather values returned in one specific provider retrieval."""

    __tablename__ = "weather_forecast_values"
    __table_args__ = (
        UniqueConstraint(
            "fetch_run_id",
            "target_time_utc",
            name="uq_weather_forecast_run_target",
        ),
        Index("ix_weather_forecast_target_time", "target_time_utc"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fetch_run_id: Mapped[str] = mapped_column(
        ForeignKey("external_fetch_runs.id", ondelete="CASCADE"), nullable=False
    )
    source_time_label: Mapped[str] = mapped_column(String(40), nullable=False)
    target_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    interval_start_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    interval_end_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    time_semantics: Mapped[str] = mapped_column(String(40), nullable=False)
    temperature_2m_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    apparent_temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    relative_humidity_2m_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    cloud_cover_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    shortwave_radiation_w_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_units: Mapped[dict] = mapped_column(JSON, nullable=False)
    normalized_units: Mapped[dict] = mapped_column(JSON, nullable=False)

    fetch_run: Mapped[ExternalFetchRun] = relationship(back_populates="weather_values")
