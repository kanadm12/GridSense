"""Tariff model for user electricity rates."""

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Tariff(Base, TimestampMixin):
    """User's electricity tariff configuration."""

    __tablename__ = "tariffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    # Tariff type: flat, tou, demand
    tariff_type: Mapped[str] = mapped_column(String(20), default="flat", nullable=False)
    retailer_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Flat rate (c/kWh)
    flat_rate_cents_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)

    # TOU rates (c/kWh)
    peak_rate_cents_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    off_peak_rate_cents_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    shoulder_rate_cents_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Demand charge ($/kW)
    demand_charge_dollars_kw: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Daily supply charge (c/day)
    daily_supply_charge_cents: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)

    # Relationship
    user = relationship("User", backref="tariff")

    def __repr__(self) -> str:
        return f"<Tariff(user_id={self.user_id}, type={self.tariff_type})>"

    def calculate_cost(self, kwh: float, is_peak: bool = False, is_shoulder: bool = False) -> float:
        """Calculate cost for given kWh based on tariff type."""
        if self.tariff_type == "flat":
            rate = self.flat_rate_cents_kwh or 25.0
        elif self.tariff_type == "tou":
            if is_peak:
                rate = self.peak_rate_cents_kwh or 38.0
            elif is_shoulder:
                rate = self.shoulder_rate_cents_kwh or 25.0
            else:
                rate = self.off_peak_rate_cents_kwh or 18.0
        else:
            rate = self.flat_rate_cents_kwh or 25.0

        return (kwh * rate) / 100  # Convert cents to dollars
