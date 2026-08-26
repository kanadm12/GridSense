"""Tests for notification preference and delivery behavior."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base
from app.models.notification import (
    Notification,
    NotificationPreferences,
    NotificationType,
    PushToken,
)
from app.models.user import User
from app.services.notification_service import NotificationService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def user(db):
    user = User(email="notifications@example.com", hashed_password="hash")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_send_push_marks_notification_sent_when_delivery_succeeds(db, user, monkeypatch):
    db.add(PushToken(user_id=user.id, token="ExponentPushToken[test]", platform="android"))
    db.commit()
    service = NotificationService(db)

    async def successful_delivery(*args, **kwargs):
        return True

    monkeypatch.setattr(service, "_send_expo_push", successful_delivery)

    sent = await service.send_push_notification(
        user.id,
        NotificationType.RECOMMENDATION,
        "Tip",
        "Shift usage off peak",
    )

    notification = db.query(Notification).one()
    assert sent is True
    assert notification.sent_at is not None


@pytest.mark.asyncio
async def test_send_push_respects_disabled_preference(db, user, monkeypatch):
    db.add(NotificationPreferences(user_id=user.id, recommendations=False))
    db.add(PushToken(user_id=user.id, token="ExponentPushToken[test]", platform="android"))
    db.commit()
    service = NotificationService(db)

    async def unexpected_delivery(*args, **kwargs):
        raise AssertionError("Push delivery should not run when the preference is disabled")

    monkeypatch.setattr(service, "_send_expo_push", unexpected_delivery)

    sent = await service.send_push_notification(
        user.id,
        NotificationType.RECOMMENDATION,
        "Tip",
        "Shift usage off peak",
    )

    assert sent is False
    assert db.query(Notification).count() == 0


@pytest.mark.asyncio
async def test_failed_delivery_keeps_notification_for_in_app_history(db, user, monkeypatch):
    db.add(PushToken(user_id=user.id, token="ExponentPushToken[test]", platform="android"))
    db.commit()
    service = NotificationService(db)

    async def failed_delivery(*args, **kwargs):
        return False

    monkeypatch.setattr(service, "_send_expo_push", failed_delivery)

    sent = await service.send_push_notification(
        user.id,
        NotificationType.RECOMMENDATION,
        "Tip",
        "Shift usage off peak",
    )

    notification = db.query(Notification).one()
    assert sent is False
    assert notification.sent_at is None
