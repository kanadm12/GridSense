"""ML model training job tracking."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.meter import Meter


class MLTrainingJob(Base, TimestampMixin):
    """Track ML model training runs."""

    __tablename__ = "ml_training_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    meter_id: Mapped[int] = mapped_column(ForeignKey("meters.id", ondelete="CASCADE"), nullable=False)

    job_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "forecast", "anomaly", or "all"
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending, running, completed, failed
    
    rq_job_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    metrics: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON metrics (MSE, MAE, anomaly count, etc.)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    meter: Mapped["Meter"] = relationship("Meter", back_populates="ml_training_jobs")

    def __repr__(self) -> str:
        return f"<MLTrainingJob(id={self.id}, meter_id={self.meter_id}, status={self.status})>"
