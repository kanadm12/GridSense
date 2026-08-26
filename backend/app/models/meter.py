"""Meter model for storing smart meter information."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.reading import Reading
    from app.models.user import User
    from app.models.chat import ChatSession
    from app.models.ml_training import MLTrainingJob


class Meter(Base, TimestampMixin):
    """Smart meter model representing a NMI (National Meter Identifier)."""

    __tablename__ = "meters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # NMI is the unique identifier for meters in Australia's NEM
    nmi: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    meter_serial: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Meter configuration
    suffix: Mapped[str | None] = mapped_column(String(2), nullable=True)  # E1, B1, etc.
    unit_of_measure: Mapped[str] = mapped_column(String(10), default="kWh", nullable=False)
    interval_minutes: Mapped[int] = mapped_column(default=30, nullable=False)

    # Location
    state: Mapped[str] = mapped_column(String(3), default="VIC", nullable=False)
    postcode: Mapped[str | None] = mapped_column(String(4), nullable=True)

    # Display name for the meter
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Whether this meter is the user's active meter (used as the default for insights,
    # forecasting and the AI assistant when no explicit meter_id is supplied).
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="meters")
    readings: Mapped[list["Reading"]] = relationship(
        "Reading", back_populates="meter", lazy="dynamic", cascade="all, delete-orphan"
    )
    chat_sessions: Mapped[list["ChatSession"]] = relationship("ChatSession", back_populates="meter", cascade="all, delete-orphan")
    ml_training_jobs: Mapped[list["MLTrainingJob"]] = relationship("MLTrainingJob", back_populates="meter", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Meter(id={self.id}, nmi={self.nmi})>"
