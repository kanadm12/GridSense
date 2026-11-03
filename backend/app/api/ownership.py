"""Authorization helpers for resource ownership validation."""

from typing import TypeVar

from sqlalchemy.orm import Session

from app.api.errors import raise_not_found
from app.logging_config import get_logger
from app.models.automation import Automation, DeviceSchedule, SmartDevice
from app.models.meter import Meter

logger = get_logger(__name__)

T = TypeVar("T")


def verify_meter_ownership(db: Session, meter_id: int, user_id: int) -> Meter:
    """Verify that a meter belongs to the specified user.

    Args:
        db: Database session
        meter_id: Meter ID to check
        user_id: User ID that should own the meter

    Returns:
        Meter object if ownership is verified

    Raises:
        HTTPException: 404 if the meter is missing or owned by another user.
            Both cases return the same response so existence is not disclosed.
    """
    meter = (
        db.query(Meter).filter(Meter.id == meter_id, Meter.user_id == user_id).first()
    )

    if not meter:
        logger.warning(
            "Meter not found or not owned by user",
            extra={"event": "ownership_check", "meter_id": meter_id, "user_id": user_id},
        )
        raise_not_found("Meter", meter_id)

    return meter


def verify_device_ownership(db: Session, device_id: int, user_id: int) -> SmartDevice:
    """Verify that a device belongs to the specified user.

    Args:
        db: Database session
        device_id: Device ID to check
        user_id: User ID that should own the device

    Returns:
        SmartDevice object if ownership is verified

    Raises:
        HTTPException: 404 if the device is missing or owned by another user.
    """
    device = (
        db.query(SmartDevice)
        .filter(SmartDevice.id == device_id, SmartDevice.user_id == user_id)
        .first()
    )

    if not device:
        logger.warning(
            "Device not found or not owned by user",
            extra={"event": "ownership_check", "device_id": device_id, "user_id": user_id},
        )
        raise_not_found("Device", device_id)

    return device


def verify_rule_ownership(db: Session, rule_id: int, user_id: int) -> Automation:
    """Verify that an automation rule belongs to the specified user.

    Args:
        db: Database session
        rule_id: Rule ID to check
        user_id: User ID that should own the rule

    Returns:
        Automation object if ownership is verified

    Raises:
        HTTPException: 404 if the rule is missing or owned by another user.
    """
    rule = (
        db.query(Automation)
        .join(Automation.device)
        .filter(Automation.id == rule_id, SmartDevice.user_id == user_id)
        .first()
    )

    if not rule:
        logger.warning(
            "Automation rule not found or not owned by user",
            extra={"event": "ownership_check", "rule_id": rule_id, "user_id": user_id},
        )
        raise_not_found("Automation rule", rule_id)

    return rule


def verify_schedule_ownership(db: Session, schedule_id: int, user_id: int) -> DeviceSchedule:
    """Verify that a schedule belongs to the specified user.

    Args:
        db: Database session
        schedule_id: Schedule ID to check
        user_id: User ID that should own the schedule

    Returns:
        DeviceSchedule object if ownership is verified

    Raises:
        HTTPException: 404 if the schedule is missing or owned by another user.
    """
    schedule = (
        db.query(DeviceSchedule)
        .join(DeviceSchedule.device)
        .filter(DeviceSchedule.id == schedule_id, SmartDevice.user_id == user_id)
        .first()
    )

    if not schedule:
        logger.warning(
            "Schedule not found or not owned by user",
            extra={"event": "ownership_check", "schedule_id": schedule_id, "user_id": user_id},
        )
        raise_not_found("Schedule", schedule_id)

    return schedule


def get_user_meters(db: Session, user_id: int) -> list[Meter]:
    """Get all meters belonging to a user.

    Args:
        db: Database session
        user_id: User ID

    Returns:
        List of Meter objects
    """
    return db.query(Meter).filter(Meter.user_id == user_id).all()


def get_user_devices(db: Session, user_id: int) -> list[SmartDevice]:
    """Get all devices belonging to a user.

    Args:
        db: Database session
        user_id: User ID

    Returns:
        List of SmartDevice objects
    """
    return db.query(SmartDevice).filter(SmartDevice.user_id == user_id).all()
