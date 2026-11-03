"""Tariff management endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.tariff import Tariff, TariffRevision
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.aer_prd import (
    AERPlanDetailResponse,
    AERPlanSearchResponse,
    AERRetailerCatalogResponse,
)
from app.schemas.tariff import (
    VICTORIAN_TARIFF_PRESETS,
    TariffCreate,
    TariffPreset,
    TariffResponse,
    TariffRevisionResponse,
)
from app.services.aer_prd import (
    AERPRDClient,
    AERProviderError,
    registry_metadata,
    retailer_catalog,
)

router = APIRouter(prefix="/tariffs", tags=["Tariffs"])


@router.get(
    "/catalog/aer/retailers",
    response_model=AERRetailerCatalogResponse,
)
async def get_aer_retailers() -> dict:
    """Return the versioned official AER retailer base-URI registry."""
    return retailer_catalog()


@router.get(
    "/catalog/aer/plans",
    response_model=AERPlanSearchResponse,
)
@limiter.limit("5/minute")
async def list_aer_plans(
    request: Request,
    brand: str = Query(min_length=1, max_length=80),
    postcode: str = Query(pattern=r"^\d{4}$"),
) -> dict:
    """Browse current generic electricity plans applicable to the supplied postcode."""
    try:
        plans = await AERPRDClient().list_victorian_electricity_plans(brand, postcode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AERProviderError as exc:
        headers = {"Retry-After": exc.retry_after} if exc.retry_after else None
        raise HTTPException(
            status_code=exc.status_code, detail=str(exc), headers=headers
        ) from exc
    metadata = registry_metadata()
    return {
        "source": metadata["source"],
        "source_registry_version": metadata["document_version"],
        "retrieved_at": datetime.now(timezone.utc),
        "plans": plans,
    }


@router.get(
    "/catalog/aer/plans/{plan_id}",
    response_model=AERPlanDetailResponse,
)
@limiter.limit("5/minute")
async def get_aer_plan_detail(
    request: Request,
    plan_id: str,
    brand: str = Query(min_length=1, max_length=80),
) -> dict:
    """Retrieve generic plan terms for review; this endpoint never activates a tariff."""
    try:
        return await AERPRDClient().get_plan_detail(brand, plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AERProviderError as exc:
        headers = {"Retry-After": exc.retry_after} if exc.retry_after else None
        raise HTTPException(
            status_code=exc.status_code, detail=str(exc), headers=headers
        ) from exc


def _tariff_values(tariff_data: TariffCreate, exclude_unset: bool = False) -> dict:
    values = tariff_data.model_dump(exclude_unset=exclude_unset)
    values.pop("confirmed", None)
    values.pop("unmodeled_components_confirmed_absent", None)
    values.pop("unsupported_components", None)
    if tariff_data.periods is not None:
        values["periods"] = [
            period.model_dump(mode="json") for period in tariff_data.periods
        ]
    return values


def _append_revision(
    db: Session,
    tariff: Tariff,
    values: dict,
    *,
    source_type: str,
    confirmed: bool,
    source_plan_id: str | None = None,
    is_illustrative: bool = False,
    unsupported_components: list[str] | None = None,
    unmodeled_components_confirmed_absent: bool = False,
) -> TariffRevision:
    latest_number = (
        db.query(TariffRevision.revision_number)
        .filter(TariffRevision.tariff_id == tariff.id)
        .order_by(TariffRevision.revision_number.desc())
        .limit(1)
        .scalar()
        or 0
    )
    unsupported = list(unsupported_components or [])
    if not unmodeled_components_confirmed_absent:
        unsupported.extend(
            [
                "demand_charge_rules",
                "controlled_loads",
                "conditional_discounts",
                "other_contract_terms",
            ]
        )
    if values.get("demand_charge_dollars_kw") is not None:
        unsupported.append("demand_charge_rules")
    if values.get("tariff_type") == "demand":
        unsupported.append("demand_charge_method")
    revision_values = {
        key: value
        for key, value in values.items()
        if key in {
            "tariff_type",
            "retailer_name",
            "flat_rate_cents_kwh",
            "peak_rate_cents_kwh",
            "off_peak_rate_cents_kwh",
            "shoulder_rate_cents_kwh",
            "feed_in_rate_cents_kwh",
            "periods",
            "effective_from",
            "effective_to",
            "rates_include_gst",
            "demand_charge_dollars_kw",
            "daily_supply_charge_cents",
        }
    }
    revision = TariffRevision(
        tariff_id=tariff.id,
        revision_number=latest_number + 1,
        source_type=source_type,
        source_plan_id=source_plan_id,
        confirmed_at=datetime.now(timezone.utc) if confirmed else None,
        unsupported_components=list(dict.fromkeys(unsupported)),
        is_illustrative=is_illustrative,
        **revision_values,
    )
    db.add(revision)
    return revision


@router.get("/presets", response_model=list[TariffPreset])
async def get_tariff_presets() -> list[TariffPreset]:
    """Get explicitly illustrative examples, not current retailer offers."""
    return VICTORIAN_TARIFF_PRESETS


@router.get("", response_model=TariffResponse | None)
async def get_my_tariff(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Tariff | None:
    """Get the current user's tariff configuration."""
    tariff = (
        db.query(Tariff)
        .filter(Tariff.user_id == current_user.id, Tariff.archived_at.is_(None))
        .first()
    )
    return tariff


@router.get("/revisions", response_model=list[TariffRevisionResponse])
async def list_tariff_revisions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TariffRevision]:
    tariff = db.query(Tariff).filter(Tariff.user_id == current_user.id).first()
    if tariff is None:
        return []
    return (
        db.query(TariffRevision)
        .filter(TariffRevision.tariff_id == tariff.id)
        .order_by(TariffRevision.revision_number.desc())
        .all()
    )


@router.post("", response_model=TariffResponse, status_code=status.HTTP_201_CREATED)
async def create_or_update_tariff(
    tariff_data: TariffCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Tariff:
    """Append a user-confirmed tariff revision and update the compatibility projection."""
    if not tariff_data.confirmed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Explicit confirmation is required before using these tariff terms.",
        )
    existing = db.query(Tariff).filter(Tariff.user_id == current_user.id).first()
    values = _tariff_values(tariff_data)

    if existing:
        existing.archived_at = None
        for field, value in values.items():
            setattr(existing, field, value)
        existing.is_preset = False
        tariff = existing
    else:
        tariff = Tariff(user_id=current_user.id, **values)
        db.add(tariff)
        db.flush()
    _append_revision(
        db,
        tariff,
        values,
        source_type="user_entered",
        confirmed=True,
        unsupported_components=tariff_data.unsupported_components,
        unmodeled_components_confirmed_absent=(
            tariff_data.unmodeled_components_confirmed_absent
        ),
    )
    db.commit()
    db.refresh(tariff)
    return tariff


@router.post("/from-preset/{preset_id}", response_model=TariffResponse)
async def apply_tariff_preset(
    preset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Tariff:
    """Save a selected preset as an illustrative scenario, not a confirmed plan."""
    preset = next((p for p in VICTORIAN_TARIFF_PRESETS if p.id == preset_id), None)
    if not preset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preset '{preset_id}' not found.",
        )

    existing = db.query(Tariff).filter(Tariff.user_id == current_user.id).first()

    tariff_data = {
        "tariff_type": preset.tariff_type.value,
        "retailer_name": f"{preset.retailer} - {preset.plan_name}",
        "flat_rate_cents_kwh": preset.flat_rate_cents_kwh,
        "peak_rate_cents_kwh": preset.peak_rate_cents_kwh,
        "off_peak_rate_cents_kwh": preset.off_peak_rate_cents_kwh,
        "shoulder_rate_cents_kwh": preset.shoulder_rate_cents_kwh,
        "feed_in_rate_cents_kwh": preset.feed_in_rate_cents_kwh,
        "daily_supply_charge_cents": preset.daily_supply_charge_cents,
        "rates_include_gst": preset.rates_include_gst,
        "is_preset": True,
        "effective_from": None,
        "effective_to": None,
        "periods": None,
    }

    if existing:
        existing.archived_at = None
        for field, value in tariff_data.items():
            setattr(existing, field, value)
        tariff = existing
    else:
        tariff = Tariff(user_id=current_user.id, **tariff_data)
        db.add(tariff)
        db.flush()
    _append_revision(
        db,
        tariff,
        tariff_data,
        source_type="illustrative_preset",
        confirmed=False,
        source_plan_id=preset.id,
        is_illustrative=True,
        unsupported_components=[
            "customer-specific discounts",
            "demand charges",
            "controlled loads",
            "eligibility conditions",
        ],
    )
    db.commit()
    db.refresh(tariff)
    return tariff


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tariff(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Archive the tariff identity while retaining its immutable revision history."""
    tariff = db.query(Tariff).filter(Tariff.user_id == current_user.id).first()
    if tariff:
        tariff.archived_at = datetime.now(timezone.utc)
        db.commit()
