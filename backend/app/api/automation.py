"""Home automation API endpoints."""

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.automation import (
    SmartDevice as SmartDeviceModel,
    Automation as AutomationModel,
    DeviceSchedule as DeviceScheduleModel,
    DeviceType,
    AutomationTrigger,
)
from app.models.user import User
from app.schemas.automation import (
    SmartDevice,
    SmartDeviceCreate,
    SmartDeviceUpdate,
    Automation,
    AutomationCreate,
    AutomationUpdate,
    DeviceSchedule,
    DeviceScheduleCreate,
    DeviceScheduleUpdate,
    AutomationSuggestion,
    GridSignal,
    DeviceCommand,
    DeviceCommandResponse,
)

router = APIRouter(prefix="/automation", tags=["Home Automation"])


# ===== Smart Devices =====

@router.get("/devices", response_model=list[SmartDevice])
async def get_devices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SmartDevice]:
    """Get all smart devices for the current user."""
    devices = (
        db.query(SmartDeviceModel)
        .filter(SmartDeviceModel.user_id == current_user.id)
        .order_by(SmartDeviceModel.name)
        .all()
    )
    return devices


@router.post("/devices", response_model=SmartDevice, status_code=status.HTTP_201_CREATED)
async def create_device(
    device: SmartDeviceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SmartDevice:
    """Add a new smart device."""
    # Validate device type
    try:
        device_type = DeviceType(device.device_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid device type. Must be one of: {[t.value for t in DeviceType]}",
        )

    db_device = SmartDeviceModel(
        user_id=current_user.id,
        name=device.name,
        device_type=device_type,
        brand=device.brand,
        model=device.model,
        power_rating_watts=device.power_rating_watts,
        standby_watts=device.standby_watts,
        location=device.location,
        is_controllable=device.is_controllable,
    )
    db.add(db_device)
    db.commit()
    db.refresh(db_device)
    return db_device


@router.get("/devices/{device_id}", response_model=SmartDevice)
async def get_device(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SmartDevice:
    """Get a specific smart device."""
    device = (
        db.query(SmartDeviceModel)
        .filter(
            SmartDeviceModel.id == device_id,
            SmartDeviceModel.user_id == current_user.id,
        )
        .first()
    )
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )
    return device


@router.patch("/devices/{device_id}", response_model=SmartDevice)
async def update_device(
    device_id: int,
    update: SmartDeviceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SmartDevice:
    """Update a smart device."""
    device = (
        db.query(SmartDeviceModel)
        .filter(
            SmartDeviceModel.id == device_id,
            SmartDeviceModel.user_id == current_user.id,
        )
        .first()
    )
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )

    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(device, field, value)

    db.commit()
    db.refresh(device)
    return device


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a smart device and all its automations."""
    device = (
        db.query(SmartDeviceModel)
        .filter(
            SmartDeviceModel.id == device_id,
            SmartDeviceModel.user_id == current_user.id,
        )
        .first()
    )
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )

    db.delete(device)
    db.commit()


@router.post("/devices/{device_id}/command", response_model=DeviceCommandResponse)
async def send_device_command(
    device_id: int,
    command: DeviceCommand,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DeviceCommandResponse:
    """Send a command to a smart device."""
    device = (
        db.query(SmartDeviceModel)
        .filter(
            SmartDeviceModel.id == device_id,
            SmartDeviceModel.user_id == current_user.id,
        )
        .first()
    )
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )

    if not device.is_controllable:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Device is not controllable",
        )

    # Simulate device control (in real implementation, would call device API)
    new_state = device.current_state or {}
    
    if command.command == "on":
        new_state["power"] = "on"
    elif command.command == "off":
        new_state["power"] = "off"
    elif command.command == "set_temp" and command.params:
        new_state["temperature"] = command.params.get("temperature")
    elif command.command == "set_mode" and command.params:
        new_state["mode"] = command.params.get("mode")

    device.current_state = new_state
    device.last_seen = datetime.utcnow()
    db.commit()

    return DeviceCommandResponse(
        success=True,
        message=f"Command '{command.command}' sent successfully",
        new_state=new_state,
    )


# ===== Automations =====

@router.get("/rules", response_model=list[Automation])
async def get_automations(
    device_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Automation]:
    """Get all automation rules."""
    query = (
        db.query(AutomationModel)
        .join(SmartDeviceModel)
        .filter(SmartDeviceModel.user_id == current_user.id)
    )
    
    if device_id:
        query = query.filter(AutomationModel.device_id == device_id)
    
    return query.all()


@router.post("/rules", response_model=Automation, status_code=status.HTTP_201_CREATED)
async def create_automation(
    automation: AutomationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Automation:
    """Create a new automation rule."""
    # Verify device belongs to user
    device = (
        db.query(SmartDeviceModel)
        .filter(
            SmartDeviceModel.id == automation.device_id,
            SmartDeviceModel.user_id == current_user.id,
        )
        .first()
    )
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )

    # Validate trigger type
    try:
        trigger_type = AutomationTrigger(automation.trigger_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid trigger type. Must be one of: {[t.value for t in AutomationTrigger]}",
        )

    db_automation = AutomationModel(
        device_id=automation.device_id,
        name=automation.name,
        description=automation.description,
        trigger_type=trigger_type,
        trigger_conditions=automation.trigger_conditions,
        action=automation.action,
        is_enabled=automation.is_enabled,
    )
    db.add(db_automation)
    db.commit()
    db.refresh(db_automation)
    return db_automation


@router.patch("/rules/{rule_id}", response_model=Automation)
async def update_automation(
    rule_id: int,
    update: AutomationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Automation:
    """Update an automation rule."""
    automation = (
        db.query(AutomationModel)
        .join(SmartDeviceModel)
        .filter(
            AutomationModel.id == rule_id,
            SmartDeviceModel.user_id == current_user.id,
        )
        .first()
    )
    if not automation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Automation rule not found",
        )

    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(automation, field, value)

    db.commit()
    db.refresh(automation)
    return automation


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_automation(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete an automation rule."""
    automation = (
        db.query(AutomationModel)
        .join(SmartDeviceModel)
        .filter(
            AutomationModel.id == rule_id,
            SmartDeviceModel.user_id == current_user.id,
        )
        .first()
    )
    if not automation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Automation rule not found",
        )

    db.delete(automation)
    db.commit()


# ===== Schedules =====

@router.get("/schedules", response_model=list[DeviceSchedule])
async def get_schedules(
    device_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DeviceSchedule]:
    """Get all device schedules."""
    query = (
        db.query(DeviceScheduleModel)
        .join(SmartDeviceModel)
        .filter(SmartDeviceModel.user_id == current_user.id)
    )
    
    if device_id:
        query = query.filter(DeviceScheduleModel.device_id == device_id)
    
    return query.all()


@router.post("/schedules", response_model=DeviceSchedule, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    schedule: DeviceScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DeviceSchedule:
    """Create a new device schedule."""
    # Verify device belongs to user
    device = (
        db.query(SmartDeviceModel)
        .filter(
            SmartDeviceModel.id == schedule.device_id,
            SmartDeviceModel.user_id == current_user.id,
        )
        .first()
    )
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )

    db_schedule = DeviceScheduleModel(
        device_id=schedule.device_id,
        name=schedule.name,
        days_of_week=schedule.days_of_week,
        start_time=schedule.start_time,
        end_time=schedule.end_time,
        action=schedule.action,
        action_params=schedule.action_params,
        priority=schedule.priority,
        is_enabled=schedule.is_enabled,
    )
    db.add(db_schedule)
    db.commit()
    db.refresh(db_schedule)
    return db_schedule


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a device schedule."""
    schedule = (
        db.query(DeviceScheduleModel)
        .join(SmartDeviceModel)
        .filter(
            DeviceScheduleModel.id == schedule_id,
            SmartDeviceModel.user_id == current_user.id,
        )
        .first()
    )
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )

    db.delete(schedule)
    db.commit()


# ===== Suggestions & Grid Signals =====

@router.get("/suggestions", response_model=list[AutomationSuggestion])
async def get_automation_suggestions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AutomationSuggestion]:
    """Get AI-powered automation suggestions based on usage patterns."""
    # In real implementation, would analyze user's meter data and devices
    suggestions = [
        AutomationSuggestion(
            device_type="water_heater",
            suggestion_title="Shift Water Heating to Off-Peak",
            description="Your water heater uses ~4kWh daily. Running it between 11pm-6am could save up to 40% on water heating costs.",
            potential_savings_kwh=1.6,
            potential_savings_dollars=12.80,
            trigger_type="time",
            recommended_schedule={
                "start_time": "23:00",
                "end_time": "06:00",
                "days": [0, 1, 2, 3, 4, 5, 6],
            },
            confidence=0.85,
        ),
        AutomationSuggestion(
            device_type="hvac",
            suggestion_title="Pre-cool Before Peak Hours",
            description="Pre-cool your home before 3pm peak pricing starts. This can reduce AC usage during expensive peak hours by 30%.",
            potential_savings_kwh=2.5,
            potential_savings_dollars=18.75,
            trigger_type="time",
            recommended_schedule={
                "start_time": "14:00",
                "end_time": "15:00",
                "action": "set_temp",
                "params": {"temperature": 22},
            },
            confidence=0.78,
        ),
        AutomationSuggestion(
            device_type="pool_pump",
            suggestion_title="Run Pool Pump During Solar Hours",
            description="If you have solar, run your pool pump between 10am-2pm when solar production is highest.",
            potential_savings_kwh=3.0,
            potential_savings_dollars=22.50,
            trigger_type="solar_production",
            recommended_schedule={
                "start_time": "10:00",
                "end_time": "14:00",
                "trigger": "solar_production > 2kW",
            },
            confidence=0.72,
        ),
        AutomationSuggestion(
            device_type="ev_charger",
            suggestion_title="Smart EV Charging",
            description="Charge your EV during off-peak hours (10pm-7am) to save up to 50% on charging costs.",
            potential_savings_kwh=8.0,
            potential_savings_dollars=60.00,
            trigger_type="time",
            recommended_schedule={
                "start_time": "22:00",
                "end_time": "07:00",
                "days": [0, 1, 2, 3, 4],  # Weekdays
            },
            confidence=0.92,
        ),
    ]
    return suggestions


@router.get("/grid-signal", response_model=GridSignal)
async def get_current_grid_signal(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GridSignal:
    """Get current grid demand/price signal for Victoria."""
    now = datetime.utcnow()
    hour = now.hour

    # Simulate grid signal based on typical Victorian patterns
    # Peak: 3pm-9pm (15:00-21:00)
    # Shoulder: 7am-3pm, 9pm-10pm
    # Off-peak: 10pm-7am

    if 15 <= hour < 21:
        signal_value = 0.45  # High price
        recommendation = "reduce"
    elif 22 <= hour or hour < 7:
        signal_value = 0.15  # Low price
        recommendation = "increase"
    else:
        signal_value = 0.28  # Medium price
        recommendation = "normal"

    return GridSignal(
        timestamp=now,
        signal_type="price",
        value=signal_value,
        unit="$/kWh",
        region="VIC",
        recommendation=recommendation,
    )
