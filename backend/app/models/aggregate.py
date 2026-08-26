"""Aggregated summaries generated from interval readings."""

from datetime import date

from sqlalchemy import Integer, Date, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class DailyAggregate(Base, TimestampMixin):
    """Daily aggregated energy metrics for a meter."""

    __tablename__ = "daily_aggregates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meter_id: Mapped[int] = mapped_column(ForeignKey("meters.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)

    total_kwh: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    peak_kwh: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    offpeak_kwh: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    meter = relationship("Meter", backref="daily_aggregates")

    def __repr__(self) -> str:
        return f"<DailyAggregate(meter_id={self.meter_id}, date={self.date}, total_kwh={self.total_kwh})>"
