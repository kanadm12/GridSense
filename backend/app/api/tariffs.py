"""Tariff management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.tariff import Tariff
from app.models.user import User
from app.schemas.tariff import (
    VICTORIAN_TARIFF_PRESETS,
    TariffCreate,
    TariffPreset,
    TariffResponse,
)

router = APIRouter(prefix="/tariffs", tags=["Tariffs"])


@router.get("/presets", response_model=list[TariffPreset])
async def get_tariff_presets() -> list[TariffPreset]:
    """Get list of Victorian tariff presets from major retailers."""
    return VICTORIAN_TARIFF_PRESETS


@router.get("", response_model=TariffResponse | None)
async def get_my_tariff(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Tariff | None:
    """Get the current user's tariff configuration."""
    tariff = db.query(Tariff).filter(Tariff.user_id == current_user.id).first()
    return tariff


@router.post("", response_model=TariffResponse, status_code=status.HTTP_201_CREATED)
async def create_or_update_tariff(
    tariff_data: TariffCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Tariff:
    """Create or update the user's tariff configuration."""
    # Check if tariff exists
    existing = db.query(Tariff).filter(Tariff.user_id == current_user.id).first()

    if existing:
        # Update existing
        for field, value in tariff_data.model_dump(exclude_unset=True).items():
            setattr(existing, field, value)
        db.commit()
        db.refresh(existing)
        return existing
    else:
        # Create new
        tariff = Tariff(
            user_id=current_user.id,
            **tariff_data.model_dump(),
        )
        db.add(tariff)
        db.commit()
        db.refresh(tariff)
        return tariff


@router.post("/from-preset/{preset_id}", response_model=TariffResponse)
async def apply_tariff_preset(
    preset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Tariff:
    """Apply a preset tariff configuration."""
    # Find preset
    preset = next((p for p in VICTORIAN_TARIFF_PRESETS if p.id == preset_id), None)
    if not preset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preset '{preset_id}' not found.",
        )

    # Check if tariff exists
    existing = db.query(Tariff).filter(Tariff.user_id == current_user.id).first()

    tariff_data = {
        "tariff_type": preset.tariff_type.value,
        "retailer_name": f"{preset.retailer} - {preset.plan_name}",
        "flat_rate_cents_kwh": preset.flat_rate_cents_kwh,
        "peak_rate_cents_kwh": preset.peak_rate_cents_kwh,
        "off_peak_rate_cents_kwh": preset.off_peak_rate_cents_kwh,
        "shoulder_rate_cents_kwh": preset.shoulder_rate_cents_kwh,
        "daily_supply_charge_cents": preset.daily_supply_charge_cents,
    }

    if existing:
        for field, value in tariff_data.items():
            setattr(existing, field, value)
        db.commit()
        db.refresh(existing)
        return existing
    else:
        tariff = Tariff(user_id=current_user.id, **tariff_data)
        db.add(tariff)
        db.commit()
        db.refresh(tariff)
        return tariff


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tariff(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete user's tariff configuration (resets to default)."""
    tariff = db.query(Tariff).filter(Tariff.user_id == current_user.id).first()
    if tariff:
        db.delete(tariff)
        db.commit()
