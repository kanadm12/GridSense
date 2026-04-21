"""Reading schemas."""

from datetime import datetime

from pydantic import BaseModel


class ReadingResponse(BaseModel):
    """Schema for reading response."""

    id: int
    meter_id: int
    timestamp: datetime
    value: float
    quality: str
    register_type: str

    model_config = {"from_attributes": True}


class ReadingBulkCreate(BaseModel):
    """Schema for bulk creating readings (internal use)."""

    timestamp: datetime
    value: float
    quality: str = "A"
    register_type: str = "B"
