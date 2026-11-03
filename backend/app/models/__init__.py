"""Database models."""

from app.models.aggregate import DailyAggregate
from app.models.automation import Automation, DeviceSchedule, GridSignal, SmartDevice
from app.models.base import Base
from app.models.chat import ChatMessage, ChatSession
from app.models.external_data import ExternalFetchRun, WeatherForecastValue
from app.models.meter import Meter
from app.models.ml_training import MLTrainingJob
from app.models.notification import (
    Notification,
    NotificationPreferences,
    NotificationType,
    PushToken,
)
from app.models.password_reset import PasswordResetToken
from app.models.reading import Reading
from app.models.tariff import Tariff, TariffRevision
from app.models.upload import NEM12Upload
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "Meter",
    "Reading",
    "Tariff",
    "TariffRevision",
    "PasswordResetToken",
    "SmartDevice",
    "Automation",
    "DeviceSchedule",
    "GridSignal",
    "NEM12Upload",
    "DailyAggregate",
    "ExternalFetchRun",
    "WeatherForecastValue",
    "Notification",
    "PushToken",
    "NotificationPreferences",
    "NotificationType",
    "ChatMessage",
    "ChatSession",
    "MLTrainingJob",
]
