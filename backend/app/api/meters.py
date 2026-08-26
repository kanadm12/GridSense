"""Meter management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.ownership import verify_meter_ownership
from app.database import get_db
from app.models.meter import Meter
from app.models.user import User
from app.schemas.meter import MeterCreate, MeterResponse

router = APIRouter(prefix="/meters", tags=["Meters"])


@router.get("", response_model=list[MeterResponse])
async def list_meters(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MeterResponse]:
    """List all meters for the current user."""
    meters = db.query(Meter).filter(Meter.user_id == current_user.id).all()
    return meters


@router.get("/{meter_id}", response_model=MeterResponse)
async def get_meter(
    meter_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MeterResponse:
    """Get a specific meter by ID."""
    meter = verify_meter_ownership(db, meter_id, current_user.id)
    return meter


@router.post("", response_model=MeterResponse, status_code=status.HTTP_201_CREATED)
async def create_meter(
    meter_data: MeterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MeterResponse:
    """Create a new meter."""
    meter = Meter(
        user_id=current_user.id,
        nmi=meter_data.nmi,
        meter_serial=meter_data.meter_serial,
        suffix=meter_data.suffix,
        unit_of_measure=meter_data.unit_of_measure,
        interval_minutes=meter_data.interval_minutes,
        state=meter_data.state,
        postcode=meter_data.postcode,
        name=meter_data.name,
    )
    db.add(meter)
    db.commit()
    db.refresh(meter)
    return meter


@router.delete("/{meter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meter(
    meter_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a meter and all its readings."""
    meter = verify_meter_ownership(db, meter_id, current_user.id)

    db.delete(meter)
    db.commit()
