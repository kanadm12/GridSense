"""Reading model for storing interval meter data."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, and_, or_
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

    # NEM12 source interval-end wall-clock, preserved as naive fixed-market-time (UTC+10).
    # Consumers convert it to meter-local time only when applying local billing windows.
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Length of the interval represented by timestamp and value.
    interval_minutes: Mapped[int] = mapped_column(
        Integer, default=30, server_default="30", nullable=False
    )

    # Energy value in kWh; sign semantics depend on the source register/direction.
    value: Mapped[float] = mapped_column(Float, nullable=False)

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
        return f"<Reading(meter_id={self.meter_id}, timestamp={self.timestamp}, value={self.value})>"


def consumption_reading_filter() -> ColumnElement[bool]:
    """Include confirmed imports and legacy readings, but exclude unresolved channels."""
    return or_(
        Reading.direction == "import",
        and_(Reading.direction.is_(None), Reading.register_type == "B"),
    )
