"""Authorization helpers for resource ownership validation."""

from typing import TypeVar

from sqlalchemy.orm import Session

from app.api.errors import raise_forbidden, raise_not_found
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
        HTTPException: 404 if meter not found, 403 if not owned by user
    """
    meter = db.query(Meter).filter(Meter.id == meter_id).first()

    if not meter:
        logger.warning(
            "Meter not found",
            extra={"event": "ownership_check", "meter_id": meter_id, "user_id": user_id},
        )
        raise_not_found("Meter", meter_id)

    if meter.user_id != user_id:
        logger.warning(
            "Unauthorized meter access",
            extra={
                "event": "ownership_violation",
                "meter_id": meter_id,
                "user_id": user_id,
                "owner_id": meter.user_id,
            },
        )
        raise_forbidden("You don't have permission to access this meter")

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
        HTTPException: 404 if device not found, 403 if not owned by user
    """
    device = db.query(SmartDevice).filter(SmartDevice.id == device_id).first()

    if not device:
        logger.warning(
            "Device not found",
            extra={"event": "ownership_check", "device_id": device_id, "user_id": user_id},
        )
        raise_not_found("Device", device_id)

    if device.user_id != user_id:
        logger.warning(
            "Unauthorized device access",
            extra={
                "event": "ownership_violation",
                "device_id": device_id,
                "user_id": user_id,
                "owner_id": device.user_id,
            },
        )
        raise_forbidden("You don't have permission to access this device")

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
        HTTPException: 404 if rule not found, 403 if not owned by user
    """
    rule = db.query(Automation).filter(Automation.id == rule_id).first()

    if not rule:
        logger.warning(
            "Automation rule not found",
            extra={"event": "ownership_check", "rule_id": rule_id, "user_id": user_id},
        )
        raise_not_found("Automation rule", rule_id)

    owner_id = rule.device.user_id
    if owner_id != user_id:
        logger.warning(
            "Unauthorized rule access",
            extra={
                "event": "ownership_violation",
                "rule_id": rule_id,
                "user_id": user_id,
                "owner_id": owner_id,
            },
        )
        raise_forbidden("You don't have permission to access this automation rule")

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
        HTTPException: 404 if schedule not found, 403 if not owned by user
    """
    schedule = db.query(DeviceSchedule).filter(DeviceSchedule.id == schedule_id).first()

    if not schedule:
        logger.warning(
            "Schedule not found",
            extra={"event": "ownership_check", "schedule_id": schedule_id, "user_id": user_id},
        )
        raise_not_found("Schedule", schedule_id)

    owner_id = schedule.device.user_id
    if owner_id != user_id:
        logger.warning(
            "Unauthorized schedule access",
            extra={
                "event": "ownership_violation",
                "schedule_id": schedule_id,
                "user_id": user_id,
                "owner_id": owner_id,
            },
        )
        raise_forbidden("You don't have permission to access this schedule")

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
