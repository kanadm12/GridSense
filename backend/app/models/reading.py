"""Reading model for storing interval meter data."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

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

    # Timestamp of the interval end
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Energy value in kWh (positive = consumption, negative = export/generation)
    value: Mapped[float] = mapped_column(Float, nullable=False)

    # Quality flag from NEM12 (A=Actual, E=Estimated, S=Substituted)
    quality: Mapped[str] = mapped_column(String(1), default="A", nullable=False)

    # Register type: E=Export (generation), B=Import (consumption)
    register_type: Mapped[str] = mapped_column(String(1), default="B", nullable=False)

    # Relationships
    meter: Mapped["Meter"] = relationship("Meter", back_populates="readings")

    # Composite index for efficient time-range queries
    __table_args__ = (
        Index("ix_readings_meter_timestamp", "meter_id", "timestamp"),
        Index("ix_readings_timestamp", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<Reading(meter_id={self.meter_id}, timestamp={self.timestamp}, value={self.value})>"
