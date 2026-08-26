"""Schemas for home automation."""

from datetime import datetime
from pydantic import BaseModel, Field
from typing import Any


class SmartDeviceCreate(BaseModel):
    """Create a new smart device."""
    name: str = Field(..., max_length=100)
    device_type: str
    brand: str | None = None
    model: str | None = None
    integration_type: str = "simulator"
    device_id: str | None = None
    api_endpoint: str | None = None
    power_rating_watts: float | None = None
    standby_watts: float | None = None
    location: str | None = None
    is_controllable: bool = True


class SmartDeviceUpdate(BaseModel):
    """Update a smart device."""
    name: str | None = None
    brand: str | None = None
    model: str | None = None
    integration_type: str | None = None
    device_id: str | None = None
    api_endpoint: str | None = None
    power_rating_watts: float | None = None
    standby_watts: float | None = None
    location: str | None = None
    is_controllable: bool | None = None
    is_enabled: bool | None = None


class SmartDevice(BaseModel):
    """Smart device response."""
    id: int
    name: str
    device_type: str
    brand: str | None
    model: str | None
    integration_type: str | None
    device_id: str | None
    api_endpoint: str | None
    power_rating_watts: float | None
    standby_watts: float | None
    location: str | None
    is_online: bool
    is_controllable: bool
    is_enabled: bool
    current_state: dict[str, Any] | None
    last_seen: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class AutomationCreate(BaseModel):
    """Create an automation rule."""
    device_id: int
    name: str = Field(..., max_length=100)
    description: str | None = None
    trigger_type: str
    trigger_conditions: dict[str, Any]
    action: dict[str, Any]
    is_enabled: bool = True


class AutomationUpdate(BaseModel):
    """Update an automation rule."""
    name: str | None = None
    description: str | None = None
    trigger_conditions: dict[str, Any] | None = None
    action: dict[str, Any] | None = None
    is_enabled: bool | None = None


class Automation(BaseModel):
    """Automation rule response."""
    id: int
    device_id: int
    name: str
    description: str | None
    trigger_type: str
    trigger_conditions: dict[str, Any]
    action: dict[str, Any]
    is_enabled: bool
    last_triggered: datetime | None
    trigger_count: int
    estimated_savings_kwh: float | None
    estimated_savings_dollars: float | None
    created_at: datetime

    class Config:
        from_attributes = True


class DeviceScheduleCreate(BaseModel):
    """Create a device schedule."""
    device_id: int
    name: str = Field(..., max_length=100)
    days_of_week: list[int] = Field(..., min_length=1)  # 0=Mon, 6=Sun
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end_time: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    action: str
    action_params: dict[str, Any] | None = None
    priority: int = Field(5, ge=1, le=10)
    is_enabled: bool = True


class DeviceScheduleUpdate(BaseModel):
    """Update a device schedule."""
    name: str | None = None
    days_of_week: list[int] | None = None
    start_time: str | None = None
    end_time: str | None = None
    action: str | None = None
    action_params: dict[str, Any] | None = None
    priority: int | None = None
    is_enabled: bool | None = None


class DeviceSchedule(BaseModel):
    """Device schedule response."""
    id: int
    device_id: int
    name: str
    days_of_week: list[int]
    start_time: str
    end_time: str | None
    action: str
    action_params: dict[str, Any] | None
    priority: int
    is_enabled: bool
    last_executed_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class AutomationSuggestion(BaseModel):
    """Suggested automation based on usage patterns."""
    device_type: str
    suggestion_title: str
    description: str
    potential_savings_kwh: float
    potential_savings_dollars: float
    trigger_type: str
    recommended_schedule: dict[str, Any]
    confidence: float = Field(..., ge=0, le=1)


class GridSignal(BaseModel):
    """Current grid signal."""
    timestamp: datetime
    signal_type: str
    value: float
    unit: str | None
    region: str
    recommendation: str  # "reduce", "normal", "increase" usage


class DeviceCommand(BaseModel):
    """Command to send to a device."""
    command: str  # "on", "off", "set_temp", etc.
    params: dict[str, Any] | None = None


class DeviceCommandResponse(BaseModel):
    """Response from device command."""
    success: bool
    message: str
    new_state: dict[str, Any] | None = None
