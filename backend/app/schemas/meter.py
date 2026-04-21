"""Meter schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class MeterCreate(BaseModel):
    """Schema for creating a meter."""

    nmi: str = Field(..., min_length=10, max_length=10)
    meter_serial: str | None = None
    suffix: str | None = Field(None, max_length=2)
    unit_of_measure: str = "kWh"
    interval_minutes: int = 30
    state: str = "VIC"
    postcode: str | None = Field(None, max_length=4)
    name: str | None = Field(None, max_length=100)


class MeterResponse(BaseModel):
    """Schema for meter response."""

    id: int
    nmi: str
    meter_serial: str | None
    suffix: str | None
    unit_of_measure: str
    interval_minutes: int
    state: str
    postcode: str | None
    name: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
