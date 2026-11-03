"""Reading model for storing interval meter data."""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, and_, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.elements import ColumnElement

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.meter import Meter


class Reading(Base):
    """Interval reading from a smart meter."""

    __tablename__ = "readings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    meter_id: Mapped[int] = mapped_column(
        ForeignKey("meters.id", ondelete="CASCADE"), nullable=False
    )

    # Preserve the parsed source timestamp. Consumers may normalize it only when
    # source_time_basis carries an explicitly supported time basis.
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Length of the interval represented by timestamp and value.
    interval_minutes: Mapped[int] = mapped_column(
        Integer, default=30, server_default="30", nullable=False
    )

    # Normalized energy in kWh when supported; unsupported source units remain ineligible.
    value: Mapped[float] = mapped_column(Float, nullable=False)
    # Original value and unit are retained alongside the normalized value.
    source_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_unit: Mapped[str | None] = mapped_column(String(10), nullable=True)
    source_interval_date: Mapped[date | None] = mapped_column(nullable=True)
    source_interval_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_nmi_configuration: Mapped[str | None] = mapped_column(String(240), nullable=True)
    source_record_quality_method: Mapped[str | None] = mapped_column(String(3), nullable=True)
    # Null on pre-migration rows: historical provenance/time basis is not inferred.
    provenance_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_time_basis: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Quality flag from NEM12 (A/E/F/S/V); U means the source metadata was unresolved.
    quality: Mapped[str] = mapped_column(String(1), default="A", nullable=False)
    quality_method: Mapped[str | None] = mapped_column(String(3), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    reason_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Legacy classification retained for existing consumers; U means unresolved.
    register_type: Mapped[str] = mapped_column(String(1), default="B", nullable=False)
    # NULL preserves the legacy interpretation for readings predating this field.
    direction: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Relationships
    meter: Mapped["Meter"] = relationship("Meter", back_populates="readings")

    # Composite index for efficient time-range queries
    __table_args__ = (
        Index("ix_readings_meter_timestamp", "meter_id", "timestamp"),
        Index("ix_readings_timestamp", "timestamp"),
    )

    def __repr__(self) -> str:
        return (
            f"<Reading(meter_id={self.meter_id}, timestamp={self.timestamp}, value={self.value})>"
        )


def consumption_reading_filter() -> ColumnElement[bool]:
    """Include eligible measured or synthetic actual-import inputs."""
    return and_(
        Reading.direction == "import",
        Reading.quality == "A",
        Reading.provenance_kind.in_(("measured", "synthetic")),
        func.lower(Reading.source_unit).in_(("kwh", "wh")),
        Reading.source_time_basis.in_(("UTC", "fixed_utc_plus_10")),
        Reading.value >= 0,
    )


def measured_import_reading_filter() -> ColumnElement[bool]:
    """Include only quality-A, measured, explicitly classified import data."""
    return and_(
        Reading.direction == "import",
        Reading.quality == "A",
        Reading.provenance_kind == "measured",
        func.lower(Reading.source_unit).in_(("kwh", "wh")),
        Reading.source_time_basis.in_(("UTC", "fixed_utc_plus_10")),
        Reading.value >= 0,
    )
