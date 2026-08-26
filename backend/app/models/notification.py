"""Notification and push token models."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Boolean, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class NotificationType(str, Enum):
    """Types of notifications."""

    ANOMALY_ALERT = "anomaly_alert"
    FORECAST_UPDATE = "forecast_update"
    RECOMMENDATION = "recommendation"
    PEAK_ALERT = "peak_alert"
    WEEKLY_SUMMARY = "weekly_summary"
    SAVINGS_TIP = "savings_tip"


class PushToken(Base, TimestampMixin):
    """Registered device push tokens for notifications."""

    __tablename__ = "push_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    token: Mapped[str] = mapped_column(String(500), nullable=False, unique=True, index=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)  # ios, android, web
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="push_tokens")

    def __repr__(self) -> str:
        return f"<PushToken(user_id={self.user_id}, platform={self.platform})>"


class Notification(Base, TimestampMixin):
    """Notification history and status."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    notification_type: Mapped[NotificationType] = mapped_column(SQLEnum(NotificationType), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    data: Mapped[str | None] = mapped_column(String(2000), nullable=True)  # JSON for extra data

    is_read: Mapped[bool] = mapped_column(default=False, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="notifications")

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, user_id={self.user_id}, type={self.notification_type})>"


class NotificationPreferences(Base, TimestampMixin):
    """User notification preferences."""

    __tablename__ = "notification_preferences"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)

    # Preference flags
    anomaly_alerts: Mapped[bool] = mapped_column(default=True, nullable=False)
    forecast_updates: Mapped[bool] = mapped_column(default=True, nullable=False)
    recommendations: Mapped[bool] = mapped_column(default=True, nullable=False)
    peak_alerts: Mapped[bool] = mapped_column(default=True, nullable=False)
    weekly_summary: Mapped[bool] = mapped_column(default=True, nullable=False)
    savings_tips: Mapped[bool] = mapped_column(default=True, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="notification_preferences")

    def __repr__(self) -> str:
        return f"<NotificationPreferences(user_id={self.user_id})>"
