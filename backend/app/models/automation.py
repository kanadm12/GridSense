"""Home automation models."""

from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Boolean
from sqlalchemy.orm import relationship
import enum

from app.models.base import Base


def _utc_now() -> datetime:
    """Return current UTC time (replaces deprecated datetime.utcnow)."""
    return datetime.now(timezone.utc)


class DeviceType(str, enum.Enum):
    """Smart device types."""
    HVAC = "hvac"
    WATER_HEATER = "water_heater"
    EV_CHARGER = "ev_charger"
    POOL_PUMP = "pool_pump"
    SOLAR_INVERTER = "solar_inverter"
    BATTERY = "battery"
    SMART_PLUG = "smart_plug"
    SMART_SWITCH = "smart_switch"
    OTHER = "other"


class AutomationTrigger(str, enum.Enum):
    """Automation trigger types."""
    TIME = "time"
    PRICE = "price"
    GRID_DEMAND = "grid_demand"
    SOLAR_PRODUCTION = "solar_production"
    TEMPERATURE = "temperature"
    MANUAL = "manual"


class SmartDevice(Base):
    """Smart device connected to the home."""
    __tablename__ = "smart_devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    device_type = Column(Enum(DeviceType), nullable=False)
    brand = Column(String(50), nullable=True)
    model = Column(String(100), nullable=True)
    
    # Integration details
    integration_type = Column(String(50), nullable=True)  # home_assistant, tuya, etc.
    device_id = Column(String(255), nullable=True)  # External device ID
    api_endpoint = Column(String(255), nullable=True)
    
    # Power info
    power_rating_watts = Column(Float, nullable=True)
    standby_watts = Column(Float, nullable=True)
    
    # State
    is_online = Column(Boolean, default=True)
    current_state = Column(JSON, nullable=True)  # Device-specific state
    last_seen = Column(DateTime, nullable=True)
    
    # Metadata
    location = Column(String(100), nullable=True)  # Room/area
    is_controllable = Column(Boolean, default=True)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)

    # Relationships
    user = relationship("User", back_populates="smart_devices")
    automations = relationship("Automation", back_populates="device", cascade="all, delete-orphan")
    schedules = relationship("DeviceSchedule", back_populates="device", cascade="all, delete-orphan")


class Automation(Base):
    """Automation rule for a smart device."""
    __tablename__ = "automations"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("smart_devices.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    
    # Trigger
    trigger_type = Column(Enum(AutomationTrigger), nullable=False)
    trigger_conditions = Column(JSON, nullable=False)  # Conditions for triggering
    
    # Action
    action = Column(JSON, nullable=False)  # What to do when triggered
    
    # State
    is_enabled = Column(Boolean, default=True)
    last_triggered = Column(DateTime, nullable=True)
    trigger_count = Column(Integer, default=0)
    
    # Energy savings tracking
    estimated_savings_kwh = Column(Float, nullable=True)
    estimated_savings_dollars = Column(Float, nullable=True)
    
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)

    # Relationships
    device = relationship("SmartDevice", back_populates="automations")


class DeviceSchedule(Base):
    """Schedule for a smart device."""
    __tablename__ = "device_schedules"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("smart_devices.id"), nullable=False)
    name = Column(String(100), nullable=False)
    
    # Schedule timing
    days_of_week = Column(JSON, nullable=False)  # [0,1,2,3,4,5,6] for Mon-Sun
    start_time = Column(String(5), nullable=False)  # "HH:MM"
    end_time = Column(String(5), nullable=True)  # "HH:MM" or null for instant action
    
    # Action
    action = Column(String(50), nullable=False)  # "on", "off", "set_temp", etc.
    action_params = Column(JSON, nullable=True)  # Additional parameters
    
    # Priority
    priority = Column(Integer, default=5)  # 1=highest, 10=lowest
    
    # State
    is_enabled = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    device = relationship("SmartDevice", back_populates="schedules")


class GridSignal(Base):
    """Grid demand/price signals for automation."""
    __tablename__ = "grid_signals"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    signal_type = Column(String(50), nullable=False)  # "price", "demand", "renewable"
    
    # Values
    value = Column(Float, nullable=False)
    unit = Column(String(20), nullable=True)
    region = Column(String(10), default="VIC")
    
    # Metadata
    source = Column(String(50), nullable=True)  # "aemo", "amber", etc.
    forecast = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
