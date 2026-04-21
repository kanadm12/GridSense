"""Push notification registration endpoint."""

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/notifications", tags=["Notifications"])

# In-memory store for push tokens (use Redis/DB in production)
push_tokens: dict[int, dict] = {}


class PushTokenRegister(BaseModel):
    """Request to register a push token."""

    token: str
    platform: str  # "ios" or "android"


class NotificationPreferences(BaseModel):
    """User notification preferences."""

    peak_alerts: bool = True
    weekly_summary: bool = True
    savings_tips: bool = True
    price_alerts: bool = False


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_push_token(
    data: PushTokenRegister,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Register a device push token for notifications."""
    push_tokens[current_user.id] = {
        "token": data.token,
        "platform": data.platform,
    }

    # TODO: Store in database in production
    print(f"Registered push token for user {current_user.id}: {data.token[:20]}...")

    return {"message": "Push token registered successfully"}


@router.delete("/register")
async def unregister_push_token(
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Unregister push token (disable notifications)."""
    if current_user.id in push_tokens:
        del push_tokens[current_user.id]

    return {"message": "Push token unregistered"}


@router.get("/preferences", response_model=NotificationPreferences)
async def get_notification_preferences(
    current_user: User = Depends(get_current_user),
) -> NotificationPreferences:
    """Get user's notification preferences."""
    # TODO: Load from database
    return NotificationPreferences()


@router.put("/preferences", response_model=NotificationPreferences)
async def update_notification_preferences(
    preferences: NotificationPreferences,
    current_user: User = Depends(get_current_user),
) -> NotificationPreferences:
    """Update user's notification preferences."""
    # TODO: Save to database
    return preferences


# Utility function for sending notifications (called by background tasks)
async def send_push_notification(user_id: int, title: str, body: str, data: dict | None = None):
    """Send a push notification to a user.

    This is a placeholder - integrate with Expo Push API or Firebase in production.
    """
    if user_id not in push_tokens:
        return False

    token_info = push_tokens[user_id]
    print(f"Sending notification to user {user_id}: {title}")

    # TODO: Integrate with Expo Push Notifications
    # import httpx
    # async with httpx.AsyncClient() as client:
    #     await client.post(
    #         "https://exp.host/--/api/v2/push/send",
    #         json={
    #             "to": token_info["token"],
    #             "title": title,
    #             "body": body,
    #             "data": data or {},
    #         }
    #     )

    return True
