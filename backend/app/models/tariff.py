"""Tariff model for user electricity rates."""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Tariff(Base, TimestampMixin):
    """Stable customer tariff identity with a legacy current-value projection."""

    __tablename__ = "tariffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Tariff type: flat, tou, demand
    tariff_type: Mapped[str] = mapped_column(String(20), default="flat", nullable=False)
    retailer_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Flat rate (c/kWh)
    flat_rate_cents_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)

    # TOU rates (c/kWh)
    peak_rate_cents_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    off_peak_rate_cents_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    shoulder_rate_cents_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    feed_in_rate_cents_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    periods: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)

    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    rates_include_gst: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    is_preset: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )

    # Demand charge ($/kW)
    demand_charge_dollars_kw: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Daily supply charge (c/day)
    daily_supply_charge_cents: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)

    # Relationship
    user = relationship("User", backref="tariff")
    revisions: Mapped[list["TariffRevision"]] = relationship(
        back_populates="tariff", order_by="TariffRevision.revision_number"
    )

    @property
    def revision_number(self) -> int | None:
        return self.revisions[-1].revision_number if self.revisions else None

    @property
    def confirmed_at(self) -> datetime | None:
        return self.revisions[-1].confirmed_at if self.revisions else None

    @property
    def confirmation_source(self) -> str | None:
        return self.revisions[-1].source_type if self.revisions else None

    @property
    def is_confirmed(self) -> bool:
        if not self.revisions:
            return False
        latest = self.revisions[-1]
        return latest.confirmed_at is not None and not latest.is_illustrative

    @property
    def unsupported_components(self) -> list[str]:
        if not self.revisions:
            return []
        return self.revisions[-1].unsupported_components

    def __repr__(self) -> str:
        return f"<Tariff(user_id={self.user_id}, type={self.tariff_type})>"

    def calculate_cost(self, kwh: float, is_peak: bool = False, is_shoulder: bool = False) -> float:
        """Return a cost only when the configured rate exists."""
        if self.tariff_type == "flat":
            rate = self.flat_rate_cents_kwh
        elif self.tariff_type == "tou":
            if is_peak:
                rate = self.peak_rate_cents_kwh
            elif is_shoulder:
                rate = self.shoulder_rate_cents_kwh
            else:
                rate = self.off_peak_rate_cents_kwh
        else:
            rate = self.flat_rate_cents_kwh

        if rate is None:
            raise ValueError("The tariff does not define a rate for this usage")
        return (kwh * rate) / 100  # Convert cents to dollars


class TariffRevision(Base):
    """Append-only snapshot of user-reviewed or illustrative tariff terms."""

    __tablename__ = "tariff_revisions"
    __table_args__ = (
        UniqueConstraint("tariff_id", "revision_number", name="uq_tariff_revision_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tariff_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tariffs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_plan_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    tariff_type: Mapped[str] = mapped_column(String(20), nullable=False)
    retailer_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    flat_rate_cents_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    peak_rate_cents_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    off_peak_rate_cents_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    shoulder_rate_cents_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    feed_in_rate_cents_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    periods: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    rates_include_gst: Mapped[bool] = mapped_column(Boolean, nullable=False)
    demand_charge_dollars_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    daily_supply_charge_cents: Mapped[float | None] = mapped_column(Float, nullable=True)
    unsupported_components: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    is_illustrative: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tariff: Mapped[Tariff] = relationship(back_populates="revisions")
