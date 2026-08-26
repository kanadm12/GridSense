"""Models for tracking uploaded NEM12 files and import jobs."""

from datetime import datetime

from sqlalchemy import Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class NEM12Upload(Base, TimestampMixin):
    """Represents an uploaded NEM12 file and its import status."""

    __tablename__ = "nem12_uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    rq_job_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    progress_percent: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    total_readings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    errors: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings: Mapped[str | None] = mapped_column(Text, nullable=True)

    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", backref="nem12_uploads")

    def __repr__(self) -> str:
        return f"<NEM12Upload(id={self.id}, filename={self.filename}, status={self.status})>"
