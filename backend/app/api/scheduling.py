"""Versioned scheduling contract endpoints."""

import math
from datetime import date
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.ownership import verify_meter_ownership
from app.database import get_db
from app.models.tariff import Tariff
from app.models.user import User
from app.schemas.scheduling import (
    SchedulingRequestV1,
    SchedulingResponseV1,
    SchedulingStatus,
    TariffResolutionStatus,
    TariffResolutionV1,
)
from app.services.scheduling_optimizer import (
    interval_energy_rates_aud,
    optimize_schedule_v1,
)
from app.services.tariff import timezone_for_state

router = APIRouter(prefix="/scheduling/v1", tags=["Scheduling v1"])

_SCHEDULING_ASSUMPTIONS = [
    "The fixed baseline excludes scheduled tasks; its energy and cost are included exactly once.",
    "Task demand is constant fixed power for the full non-interruptible task duration.",
    "Energy charges use the owned tariff's interval rates; "
    "daily supply and demand charges are excluded.",
    "The candidate-minus-reference energy cost delta is not a household savings estimate.",
    "Optional tasks without an omission penalty are omitted under the no-savings treatment.",
    "The deterministic greedy reference uses the same tasks, tariff, baseline, and power limits; "
    "it is not an optimum.",
    "This endpoint returns a preview only and never executes or dispatches devices.",
]


def _rate_is_valid(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value >= 0


def _has_usable_energy_rates(tariff: Tariff) -> bool:
    if tariff.periods:
        return all(
            isinstance(period, dict)
            and _rate_is_valid(period.get("rate_cents_kwh"))
            and isinstance(period.get("start_minute"), int)
            and isinstance(period.get("end_minute"), int)
            and isinstance(period.get("days"), list)
            for period in tariff.periods
        )

    if tariff.tariff_type == "flat":
        return _rate_is_valid(tariff.flat_rate_cents_kwh)

    if tariff.tariff_type in ("tou", "demand"):
        return all(
            _rate_is_valid(rate)
            for rate in (
                tariff.peak_rate_cents_kwh,
                tariff.shoulder_rate_cents_kwh,
                tariff.off_peak_rate_cents_kwh,
            )
        )
    return False


def _resolve_tariff(
    tariff: Tariff | None, start_date: date, end_date: date
) -> tuple[TariffResolutionV1, str | None]:
    if tariff is None:
        return (
            TariffResolutionV1(tariff_id=None, status=TariffResolutionStatus.MISSING),
            "No user-owned tariff is configured.",
        )

    if tariff.is_preset:
        return (
            TariffResolutionV1(tariff_id=tariff.id, status=TariffResolutionStatus.ILLUSTRATIVE),
            "Illustrative tariffs cannot support a schedule cost objective.",
        )

    if (tariff.effective_from is not None and tariff.effective_from > start_date) or (
        tariff.effective_to is not None and tariff.effective_to < end_date
    ):
        return (
            TariffResolutionV1(
                tariff_id=tariff.id,
                status=TariffResolutionStatus.OUTSIDE_EFFECTIVE_DATES,
            ),
            "Tariff effective dates do not cover the complete scheduling horizon.",
        )

    if not _has_usable_energy_rates(tariff):
        return (
            TariffResolutionV1(tariff_id=tariff.id, status=TariffResolutionStatus.MISSING_RATES),
            "The tariff does not contain usable energy rates for the schedule.",
        )

    return (
        TariffResolutionV1(tariff_id=tariff.id, status=TariffResolutionStatus.CONFIGURED),
        None,
    )


@router.post(
    "/plans/preview",
    response_model=SchedulingResponseV1,
    response_model_exclude_none=True,
    summary="Validate a versioned schedule-planning request",
    description=(
        "Validates task, baseline, timezone, meter ownership, and tariff provenance, "
        "then returns a bounded MILP preview and deterministic greedy reference when feasible. "
        "Schedules are not executed or dispatched."
    ),
)
def preview_schedule_v1(
    request: SchedulingRequestV1,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SchedulingResponseV1:
    """Validate a scheduling request and report why planning is not yet available."""
    meter = verify_meter_ownership(db, request.meter_id, current_user.id)
    meter_timezone = timezone_for_state(meter.state).key
    if request.timezone != meter_timezone:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="timezone must match the meter's local timezone",
        )

    if request.tariff_id is None:
        tariff = db.query(Tariff).filter(Tariff.user_id == current_user.id).first()
    else:
        tariff = db.query(Tariff).filter(Tariff.id == request.tariff_id).first()
        if tariff is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tariff not found",
            )
        if tariff.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to use this tariff",
            )

    zone = ZoneInfo(request.timezone)
    relevant_dates = [
        interval.interval_start.astimezone(zone).date()
        for interval in request.baseline_profile.intervals
    ]
    relevant_dates.extend(
        task_time.astimezone(zone).date()
        for task in request.tasks
        for task_time in (task.earliest_start, task.deadline)
    )
    start_date = min(relevant_dates)
    end_date = max(relevant_dates)
    tariff_resolution, tariff_blocker = _resolve_tariff(tariff, start_date, end_date)

    plan = None
    if tariff_blocker is None and tariff is not None:
        interval_prices = interval_energy_rates_aud(tariff, request, meter.state)
        if interval_prices is None:
            tariff_resolution = TariffResolutionV1(
                tariff_id=tariff.id,
                status=TariffResolutionStatus.MISSING_RATES,
            )
            tariff_blocker = (
                "The tariff has no unambiguous energy rate for every scheduling interval."
            )
        else:
            plan = optimize_schedule_v1(request, interval_prices)

    if tariff_blocker is not None:
        schedule_status = SchedulingStatus.BLOCKED
        blockers = [tariff_blocker]
    else:
        if plan is None:
            raise RuntimeError("A tariff passed validation but no scheduling result was produced")
        schedule_status = plan.status
        blockers = plan.blockers

    assumptions = list(_SCHEDULING_ASSUMPTIONS)
    if request.baseline_profile.source.value == "synthetic":
        assumptions.append(
            f"Baseline profile {request.baseline_profile.profile_id} is synthetic "
            f"for scenario {request.baseline_profile.scenario_id}."
        )
    else:
        assumptions.append(
            f"Baseline profile {request.baseline_profile.profile_id} is independently measured "
            f"using {request.baseline_profile.measurement_method}."
        )
    assumptions.append(
        "Preference cost is preference_penalty_aud_per_interval times the distance "
        "from preferred_start in scheduling intervals."
    )
    if request.household_power_limit_kw is not None or request.grid_power_limit_kw is not None:
        assumptions.append(
            "Configured household/grid power limits apply to baseline plus scheduled task power; "
            "the tighter limit governs."
        )

    return SchedulingResponseV1(
        schema_version="1.0",
        scenario_id=request.scenario_id,
        meter_id=meter.id,
        status=schedule_status,
        tariff=tariff_resolution,
        objective_breakdown=plan.objective_breakdown if plan is not None else None,
        candidate_schedule=plan.candidate_schedule if plan is not None else None,
        reference_schedule=plan.reference_schedule if plan is not None else None,
        assumptions=assumptions,
        blockers=blockers,
    )
