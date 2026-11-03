"""Reading schemas."""

from datetime import date, datetime

from pydantic import BaseModel


class ReadingResponse(BaseModel):
    """Schema for reading response."""

    id: int
    meter_id: int
    timestamp: datetime
    interval_minutes: int = 30
    value: float
    source_value: float | None = None
    source_unit: str | None = None
    source_interval_date: date | None = None
    source_interval_number: int | None = None
    source_nmi_configuration: str | None = None
    source_record_quality_method: str | None = None
    provenance_kind: str | None = None
    source_time_basis: str | None = None
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
    source_value: float | None = None
    source_unit: str | None = None
    source_interval_date: date | None = None
    source_interval_number: int | None = None
    source_nmi_configuration: str | None = None
    source_record_quality_method: str | None = None
    provenance_kind: str | None = None
    source_time_basis: str | None = None
    quality: str = "A"
    register_type: str = "U"
    direction: str = "unknown"
    quality_method: str | None = None
    reason_code: str | None = None
    reason_description: str | None = None
