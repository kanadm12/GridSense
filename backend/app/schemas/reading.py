"""Reading schemas."""

from datetime import datetime

from pydantic import BaseModel


class ReadingResponse(BaseModel):
    """Schema for reading response."""

    id: int
    meter_id: int
    timestamp: datetime
    interval_minutes: int = 30
    value: float
    quality: str
    register_type: str
    direction: str | None = None
    quality_method: str | None = None
    reason_code: str | None = None
    reason_description: str | None = None

    model_config = {"from_attributes": True}


class ReadingBulkCreate(BaseModel):
    """Schema for bulk creating readings (internal use)."""

    timestamp: datetime
    interval_minutes: int = 30
    value: float
    quality: str = "A"
    register_type: str = "U"
    direction: str = "unknown"
    quality_method: str | None = None
    reason_code: str | None = None
    reason_description: str | None = None
