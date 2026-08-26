"""User model for authentication and user management."""

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.meter import Meter
    from app.models.automation import SmartDevice
    from app.models.notification import PushToken, Notification, NotificationPreferences
    from app.models.chat import ChatSession


class User(Base, TimestampMixin):
    """User account model."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    meters: Mapped[list["Meter"]] = relationship("Meter", back_populates="user", lazy="selectin")
    smart_devices: Mapped[list["SmartDevice"]] = relationship("SmartDevice", back_populates="user", lazy="selectin")
    push_tokens: Mapped[list["PushToken"]] = relationship("PushToken", back_populates="user", lazy="selectin", cascade="all, delete-orphan")
    notifications: Mapped[list["Notification"]] = relationship("Notification", back_populates="user", lazy="selectin", cascade="all, delete-orphan")
    notification_preferences: Mapped["NotificationPreferences | None"] = relationship("NotificationPreferences", back_populates="user", uselist=False, cascade="all, delete-orphan")
    chat_sessions: Mapped[list["ChatSession"]] = relationship("ChatSession", back_populates="user", lazy="selectin", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"
