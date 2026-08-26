"""Notification service for sending and tracking notifications."""

import json
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationType, NotificationPreferences, PushToken
from app.models.user import User


class NotificationService:
    """Service for sending and managing notifications."""

    EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

    def __init__(self, db: Session):
        self.db = db

    def get_or_create_preferences(self, user_id: int) -> NotificationPreferences:
        """Get or create default notification preferences for a user."""
        prefs = self.db.query(NotificationPreferences).filter(NotificationPreferences.user_id == user_id).first()
        if not prefs:
            prefs = NotificationPreferences(user_id=user_id)
            self.db.add(prefs)
            self.db.commit()
        return prefs

    def should_send_notification(self, user_id: int, notification_type: NotificationType) -> bool:
        """Check if notification type is enabled for user."""
        prefs = self.get_or_create_preferences(user_id)
        type_map = {
            NotificationType.ANOMALY_ALERT: prefs.anomaly_alerts,
            NotificationType.FORECAST_UPDATE: prefs.forecast_updates,
            NotificationType.RECOMMENDATION: prefs.recommendations,
            NotificationType.PEAK_ALERT: prefs.peak_alerts,
            NotificationType.WEEKLY_SUMMARY: prefs.weekly_summary,
            NotificationType.SAVINGS_TIP: prefs.savings_tips,
        }
        return type_map.get(notification_type, True)

    def create_notification(
        self,
        user_id: int,
        notification_type: NotificationType,
        title: str,
        message: str,
        data: Optional[dict] = None,
    ) -> Notification:
        """Create and store a notification in the database."""
        notification = Notification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            data=json.dumps(data) if data else None,
        )
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        return notification

    async def send_push_notification(
        self,
        user_id: int,
        notification_type: NotificationType,
        title: str,
        message: str,
        data: Optional[dict] = None,
    ) -> bool:
        """Create notification and send push notification to all user's devices.

        Returns True if at least one push was sent successfully.
        """
        # Check preferences
        if not self.should_send_notification(user_id, notification_type):
            return False

        # Create notification record
        notification = self.create_notification(user_id, notification_type, title, message, data)

        # Get user's push tokens
        tokens = (
            self.db.query(PushToken)
            .filter(PushToken.user_id == user_id, PushToken.is_active == True)
            .all()
        )

        if not tokens:
            return False

        success_count = 0
        for token in tokens:
            try:
                success = await self._send_expo_push(token.token, title, message, data)
                if success:
                    success_count += 1
            except Exception as e:
                print(f"Failed to send push to {token.token}: {e}")

        # Update sent_at if at least one was sent
        if success_count > 0:
            notification.sent_at = datetime.now()
            self.db.add(notification)
            self.db.commit()

        return success_count > 0

    async def _send_expo_push(self, token: str, title: str, message: str, data: Optional[dict] = None) -> bool:
        """Send a single push notification via Expo."""
        try:
            payload = {
                "to": token,
                "sound": "default",
                "title": title,
                "body": message,
                "data": data or {},
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(self.EXPO_PUSH_URL, json=payload, timeout=10.0)
                return response.status_code == 200
        except Exception as e:
            print(f"Expo push error: {e}")
            return False

    def mark_as_read(self, notification_id: int, user_id: int) -> bool:
        """Mark a notification as read."""
        notification = (
            self.db.query(Notification)
            .filter(Notification.id == notification_id, Notification.user_id == user_id)
            .first()
        )
        if notification:
            notification.is_read = True
            notification.read_at = datetime.now()
            self.db.add(notification)
            self.db.commit()
            return True
        return False

    def get_unread_count(self, user_id: int) -> int:
        """Get count of unread notifications for a user."""
        return self.db.query(Notification).filter(
            Notification.user_id == user_id, Notification.is_read == False
        ).count()
