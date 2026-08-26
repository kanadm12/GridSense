"""Database models."""

from app.models.base import Base
from app.models.automation import Automation, DeviceSchedule, GridSignal, SmartDevice
from app.models.chat import ChatMessage, ChatSession
from app.models.meter import Meter
from app.models.ml_training import MLTrainingJob
from app.models.notification import Notification, PushToken, NotificationPreferences, NotificationType
from app.models.password_reset import PasswordResetToken
from app.models.reading import Reading
from app.models.tariff import Tariff
from app.models.user import User
from app.models.upload import NEM12Upload
from app.models.aggregate import DailyAggregate

__all__ = [
    "Base",
    "User",
    "Meter",
    "Reading",
    "Tariff",
    "PasswordResetToken",
    "SmartDevice",
    "Automation",
    "DeviceSchedule",
    "GridSignal",
    "NEM12Upload",
    "DailyAggregate",
    "Notification",
    "PushToken",
    "NotificationPreferences",
    "NotificationType",
    "ChatMessage",
    "ChatSession",
    "MLTrainingJob",
]
