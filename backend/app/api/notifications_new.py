"""Updated push notification registration and preference endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.notification import PushToken, NotificationPreferences, Notification
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class PushTokenRegister(BaseModel):
    """Request to register a push token."""

    token: str
    platform: str  # "ios", "android", "web"


class NotificationPreferencesUpdate(BaseModel):
    """Request to update notification preferences."""

    anomaly_alerts: bool | None = None
    forecast_updates: bool | None = None
    recommendations: bool | None = None
    peak_alerts: bool | None = None
    weekly_summary: bool | None = None
    savings_tips: bool | None = None


class NotificationResponse(BaseModel):
    """Response representing a notification."""

    id: int
    title: str
    message: str
    notification_type: str
    is_read: bool
    created_at: str

    class Config:
        from_attributes = True


@router.post("/register-token", status_code=status.HTTP_201_CREATED)
async def register_push_token(
    data: PushTokenRegister,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Register a device push token for notifications.

    Tokens are stored securely in the database and used to send push notifications.
    """
    # Check if token already exists
    existing = db.query(PushToken).filter(PushToken.token == data.token).first()
    if existing:
        if existing.user_id == current_user.id:
            return {"message": "Push token already registered"}
        else:
            # Token registered to another user, update it
            existing.user_id = current_user.id
            existing.is_active = True
            db.add(existing)
            db.commit()
            return {"message": "Push token updated"}

    # Create new push token
    push_token = PushToken(
        user_id=current_user.id,
        token=data.token,
        platform=data.platform.lower(),
    )
    db.add(push_token)
    db.commit()

    return {"message": "Push token registered successfully"}


@router.post("/unregister-token")
async def unregister_push_token(
    data: PushTokenRegister,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Unregister a device push token."""
    token = (
        db.query(PushToken)
        .filter(PushToken.token == data.token, PushToken.user_id == current_user.id)
        .first()
    )
    if token:
        token.is_active = False
        db.add(token)
        db.commit()
        return {"message": "Push token unregistered"}
    raise HTTPException(status_code=404, detail="Token not found")


@router.get("/preferences")
async def get_notification_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationPreferencesUpdate:
    """Get notification preferences for the current user."""
    service = NotificationService(db)
    prefs = service.get_or_create_preferences(current_user.id)

    return NotificationPreferencesUpdate(
        anomaly_alerts=prefs.anomaly_alerts,
        forecast_updates=prefs.forecast_updates,
        recommendations=prefs.recommendations,
        peak_alerts=prefs.peak_alerts,
        weekly_summary=prefs.weekly_summary,
        savings_tips=prefs.savings_tips,
    )


@router.put("/preferences")
async def update_notification_preferences(
    data: NotificationPreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationPreferencesUpdate:
    """Update notification preferences for the current user."""
    service = NotificationService(db)
    prefs = service.get_or_create_preferences(current_user.id)

    # Update only provided fields
    if data.anomaly_alerts is not None:
        prefs.anomaly_alerts = data.anomaly_alerts
    if data.forecast_updates is not None:
        prefs.forecast_updates = data.forecast_updates
    if data.recommendations is not None:
        prefs.recommendations = data.recommendations
    if data.peak_alerts is not None:
        prefs.peak_alerts = data.peak_alerts
    if data.weekly_summary is not None:
        prefs.weekly_summary = data.weekly_summary
    if data.savings_tips is not None:
        prefs.savings_tips = data.savings_tips

    db.add(prefs)
    db.commit()

    return NotificationPreferencesUpdate(
        anomaly_alerts=prefs.anomaly_alerts,
        forecast_updates=prefs.forecast_updates,
        recommendations=prefs.recommendations,
        peak_alerts=prefs.peak_alerts,
        weekly_summary=prefs.weekly_summary,
        savings_tips=prefs.savings_tips,
    )


@router.get("/unread-count")
async def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, int]:
    """Get count of unread notifications."""
    service = NotificationService(db)
    count = service.get_unread_count(current_user.id)
    return {"unread_count": count}


@router.get("/list")
async def list_notifications(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, list[NotificationResponse]]:
    """List notifications for the current user."""
    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "notifications": [
            NotificationResponse(
                id=n.id,
                title=n.title,
                message=n.message,
                notification_type=n.notification_type.value,
                is_read=n.is_read,
                created_at=n.created_at.isoformat(),
            )
            for n in notifications
        ]
    }


@router.post("/mark-as-read/{notification_id}")
async def mark_notification_as_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Mark a notification as read."""
    service = NotificationService(db)
    success = service.mark_as_read(notification_id, current_user.id)
    if success:
        return {"message": "Notification marked as read"}
    raise HTTPException(status_code=404, detail="Notification not found")
