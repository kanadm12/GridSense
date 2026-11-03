"""Versioned scheduling contract endpoints."""

import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.ownership import verify_meter_ownership
from app.database import get_db
from app.models.tariff import Tariff, TariffRevision
from app.models.user import User
from app.schemas.recommendation import (
    EvidenceCoverage,
    RecommendationStatus,
)
from app.schemas.scheduling import (
    BaselineEligibilityV1,
    SchedulingCalculationEvidence,
    SchedulingRequestV1,
    SchedulingResponseV1,
    SchedulingStatus,
    TariffResolutionStatus,
    TariffResolutionV1,
)
from app.services.scheduling_baseline import assess_scheduling_baseline
from app.services.scheduling_optimizer import (
    interval_energy_rates_aud,
    optimize_schedule_v1,
)
from app.services.tariff import applicable_tariff_revisions, timezone_for_state

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
_SCHEDULING_RULE_VERSION = "1.0"
_SCHEDULING_EVIDENCE_TTL = timedelta(hours=1)


def _rate_is_valid(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value >= 0


def _has_usable_energy_rates(tariff: TariffRevision) -> bool:
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
    tariff: Tariff | None,
    revisions: list[TariffRevision],
    start_date: date,
    end_date: date,
) -> tuple[TariffResolutionV1, str | None, TariffRevision | None]:
    if tariff is None:
        return (
            TariffResolutionV1(tariff_id=None, status=TariffResolutionStatus.MISSING),
            "No user-owned tariff is configured.",
            None,
        )

    if not revisions:
        if tariff.is_preset:
            return (
                TariffResolutionV1(
                    tariff_id=tariff.id,
                    status=TariffResolutionStatus.ILLUSTRATIVE,
                ),
                "Illustrative tariffs cannot support a schedule cost objective.",
                None,
            )
        return (
            TariffResolutionV1(tariff_id=tariff.id, status=TariffResolutionStatus.MISSING),
            "A user-confirmed tariff revision is required for scheduling costs.",
            None,
        )

    daily_revisions = [
        applicable_tariff_revisions(revisions, start_date + timedelta(days=offset))
        for offset in range((end_date - start_date).days + 1)
    ]
    if not any(daily_revisions) and (tariff.is_preset or revisions[-1].is_illustrative):
        return (
            TariffResolutionV1(
                tariff_id=tariff.id,
                status=TariffResolutionStatus.ILLUSTRATIVE,
            ),
            "Illustrative tariffs cannot support a schedule cost objective.",
            None,
        )
    if any(len(day_revisions) > 1 for day_revisions in daily_revisions):
        return (
            TariffResolutionV1(
                tariff_id=tariff.id,
                status=TariffResolutionStatus.MISSING,
            ),
            "Overlapping confirmed tariff revisions make this scheduling horizon ambiguous.",
            None,
        )
    if any(not day_revisions for day_revisions in daily_revisions):
        return (
            TariffResolutionV1(
                tariff_id=tariff.id,
                status=TariffResolutionStatus.OUTSIDE_EFFECTIVE_DATES,
            ),
            "A confirmed tariff revision does not cover the complete scheduling horizon.",
            None,
        )

    distinct_revisions = {day_revisions[0].id for day_revisions in daily_revisions}
    if len(distinct_revisions) != 1:
        return (
            TariffResolutionV1(
                tariff_id=tariff.id,
                status=TariffResolutionStatus.MISSING,
            ),
            "The scheduling horizon crosses a tariff revision boundary; "
            "price it in separate requests.",
            None,
        )
    revision = daily_revisions[0][0]
    if not _has_usable_energy_rates(revision):
        return (
            TariffResolutionV1(tariff_id=tariff.id, status=TariffResolutionStatus.MISSING_RATES),
            "The tariff does not contain usable energy rates for the schedule.",
            None,
        )

    return (
        TariffResolutionV1(tariff_id=tariff.id, status=TariffResolutionStatus.CONFIGURED),
        None,
        revision,
    )


def _build_scheduling_evidence(
    *,
    request: SchedulingRequestV1,
    owner_user_id: int,
    tariff_revision: TariffRevision | None,
    baseline_eligibility: BaselineEligibilityV1,
    plan,
    now: datetime | None = None,
) -> SchedulingCalculationEvidence:
    created_at = now or datetime.now(timezone.utc)
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("Evidence evaluation time must be timezone-aware.")
    created_at = created_at.astimezone(timezone.utc)

    serialized_request = request.model_dump(mode="json")
    task_digest = hashlib.sha256(
        json.dumps(
            serialized_request["tasks"],
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    tariff_reference = (
        f"tariff-revision:{tariff_revision.id}"
        if tariff_revision is not None
        else "tariff-revision:unavailable"
    )
    serialized_inputs = {
        "request": serialized_request,
        "tariff_revision_id": tariff_revision.id if tariff_revision else None,
    }
    input_digest = hashlib.sha256(
        json.dumps(
            serialized_inputs,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()

    breakdown = plan.objective_breakdown if plan is not None else None
    numeric_values = {
        name: value
        for name, value in (
            ("baseline_energy_cost_aud", breakdown.baseline_energy_cost_aud if breakdown else None),
            ("milp_energy_cost_aud", breakdown.candidate_energy_cost_aud if breakdown else None),
            ("greedy_energy_cost_aud", breakdown.reference_energy_cost_aud if breakdown else None),
            (
                "preferred_energy_cost_aud",
                breakdown.preferred_energy_cost_aud if breakdown else None,
            ),
            (
                "milp_preference_penalty_aud",
                breakdown.preference_penalty_aud if breakdown else None,
            ),
            (
                "milp_omission_penalty_aud",
                breakdown.omission_penalty_aud if breakdown else None,
            ),
            (
                "milp_total_objective_aud",
                breakdown.total_objective_aud if breakdown else None,
            ),
            (
                "greedy_preference_penalty_aud",
                breakdown.reference_preference_penalty_aud if breakdown else None,
            ),
            (
                "greedy_omission_penalty_aud",
                breakdown.reference_omission_penalty_aud if breakdown else None,
            ),
            (
                "greedy_total_objective_aud",
                breakdown.reference_objective_aud if breakdown else None,
            ),
            (
                "milp_vs_greedy_energy_cost_delta_aud",
                breakdown.energy_cost_delta_aud if breakdown else None,
            ),
            (
                "milp_vs_preferred_energy_cost_delta_aud",
                breakdown.milp_vs_preferred_energy_cost_delta_aud if breakdown else None,
            ),
        )
        if value is not None
    }
    scenarios = {}
    if plan is not None:
        scenarios = {
            "preferred": {
                "energy_charge_aud": breakdown.preferred_energy_cost_aud,
                "preference_penalty_aud": 0.0,
                "omission_penalty_aud": 0.0,
            },
            "greedy": {
                "energy_charge_aud": breakdown.reference_energy_cost_aud,
                "preference_penalty_aud": breakdown.reference_preference_penalty_aud,
                "omission_penalty_aud": breakdown.reference_omission_penalty_aud,
            },
            "milp": {
                "energy_charge_aud": breakdown.candidate_energy_cost_aud,
                "preference_penalty_aud": breakdown.preference_penalty_aud,
                "omission_penalty_aud": breakdown.omission_penalty_aud,
            },
        }

    is_illustrative = baseline_eligibility.source.value == "synthetic"
    status = (
        RecommendationStatus.ILLUSTRATIVE
        if is_illustrative
        else RecommendationStatus.UNAVAILABLE
    )
    tariff_revision_ids = [tariff_revision.id] if tariff_revision is not None else []
    return SchedulingCalculationEvidence(
        recommendation_id=f"meter-{request.meter_id}:schedule:{request.scenario_id}:v1",
        rule_id="scheduling.preview",
        rule_version=_SCHEDULING_RULE_VERSION,
        owner_user_id=owner_user_id,
        meter_id=request.meter_id,
        created_at=created_at,
        expires_at=created_at + _SCHEDULING_EVIDENCE_TTL,
        status=status,
        analysis_start_date=min(
            item.interval_start.astimezone(ZoneInfo(request.timezone)).date()
            for item in request.baseline_profile.intervals
        ),
        analysis_end_date=max(
            item.interval_start.astimezone(ZoneInfo(request.timezone)).date()
            for item in request.baseline_profile.intervals
        ),
        input_references=[
            f"scheduling-input-set:sha256:{input_digest}",
            f"scheduling-task-set:sha256:{task_digest}",
            tariff_reference,
        ],
        input_record_count=len(request.baseline_profile.intervals) + len(request.tasks),
        input_digest_sha256=input_digest,
        provenance_counts={baseline_eligibility.source.value: 1},
        coverage=EvidenceCoverage(),
        eligibility_checks={
            "non_task_baseline": (
                "pass" if baseline_eligibility.eligible_for_costed_preview else "fail"
            ),
            "confirmed_tariff_revision": "pass" if tariff_revision is not None else "fail",
            "task_constraints_validated": "pass",
            "meter_ownership": "pass",
        },
        tariff_revision_id=tariff_revision.id if tariff_revision else None,
        baseline_scenario=baseline_eligibility.source.value,
        proposed_scenario="MILP candidate compared with preferred and deterministic greedy",
        calculation_method_version="scheduling_optimizer:1.0",
        calculated_values=numeric_values,
        value_units={name: "AUD" for name in numeric_values},
        energy_difference_kwh=(
            plan.candidate_schedule.total_energy_kwh
            - plan.reference_schedule.total_energy_kwh
            if plan is not None
            and plan.candidate_schedule is not None
            and plan.reference_schedule.total_energy_kwh is not None
            and plan.candidate_schedule.total_energy_kwh is not None
            else None
        ),
        financial_difference_aud=(
            breakdown.energy_cost_delta_aud if breakdown is not None else None
        ),
        task_set_digest_sha256=task_digest,
        tariff_revision_ids=tariff_revision_ids,
        tariff_effective_from=tariff_revision.effective_from if tariff_revision else None,
        tariff_effective_to=tariff_revision.effective_to if tariff_revision else None,
        baseline_source_classification=baseline_eligibility.status.value,
        formulas={
            "baseline_energy_cost_aud": (
                "sum(baseline_kw * interval_hours * interval_rate_aud_per_kwh)"
            ),
            "scenario_energy_charge_aud": (
                "baseline_energy_cost_aud + sum(task_kw * task_interval_hours * "
                "interval_rate_aud_per_kwh)"
            ),
            "candidate_minus_reference_aud": (
                "MILP scenario energy_charge_aud - greedy scenario energy_charge_aud"
            ),
            "preference_penalty_aud": (
                "preference_penalty_aud_per_interval * absolute_start_distance_intervals"
            ),
        },
        formula_inputs={
            "interval_minutes": float(request.interval_minutes),
            "preference_penalty_aud_per_interval": request.preference_penalty_aud_per_interval,
            "baseline_energy_kwh": sum(
                item.demand_kw * request.interval_minutes / 60
                for item in request.baseline_profile.intervals
            ),
            "modeled_task_energy_kwh": sum(
                task.energy_kwh
                if task.energy_kwh is not None
                else (task.rated_power_kw or 0) * task.duration_minutes / 60
                for task in request.tasks
            ),
        },
        scenario_values=scenarios,
        rounding_rule=(
            "Optimizer values retain six decimal places; mobile display rounds to two "
            "decimal places for presentation only."
        ),
        assumptions=list(_SCHEDULING_ASSUMPTIONS),
        limitations=[
            "Evidence is response-scoped and expires after one hour; it is not durably archived.",
            (
                "A user-declared measured baseline is not accepted without server-verified "
                "disaggregation evidence."
            ),
            "Modeled energy-charge differences are not household savings or bill estimates.",
            "Daily supply and demand charges are excluded.",
        ],
        invalidation_conditions=[
            (
                "Any change to task, baseline, tariff revision, interval prices, or constraints "
                "requires recalculation."
            )
        ],
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
        tariff = (
            db.query(Tariff)
            .filter(
                Tariff.user_id == current_user.id,
                Tariff.archived_at.is_(None),
            )
            .first()
        )
    else:
        # Owner-scoped lookup: another user's tariff is indistinguishable from a missing one.
        tariff = (
            db.query(Tariff)
            .filter(
                Tariff.id == request.tariff_id,
                Tariff.user_id == current_user.id,
                Tariff.archived_at.is_(None),
            )
            .first()
        )
        if tariff is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tariff not found",
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
    revisions = (
        db.query(TariffRevision)
        .filter(TariffRevision.tariff_id == tariff.id)
        .order_by(TariffRevision.revision_number)
        .all()
        if tariff is not None
        else []
    )
    tariff_resolution, tariff_blocker, pricing_revision = _resolve_tariff(
        tariff, revisions, start_date, end_date
    )

    baseline_result = assess_scheduling_baseline(request.baseline_profile)
    baseline_eligibility = BaselineEligibilityV1(
        status=baseline_result.status,
        source=baseline_result.source,
        eligible_for_costed_preview=baseline_result.eligible_for_costed_preview,
        explanation=baseline_result.explanation,
    )
    plan = None
    if not baseline_result.eligible_for_costed_preview:
        tariff_blocker = baseline_result.explanation
    if tariff_blocker is None and pricing_revision is not None:
        interval_prices = interval_energy_rates_aud(
            pricing_revision, request, meter.state
        )
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
        preferred_schedule=plan.preferred_schedule if plan is not None else None,
        baseline_eligibility=baseline_eligibility,
        calculation_evidence=_build_scheduling_evidence(
            request=request,
            owner_user_id=current_user.id,
            tariff_revision=pricing_revision if tariff_blocker is None else None,
            baseline_eligibility=baseline_eligibility,
            plan=plan,
        ),
        assumptions=assumptions,
        blockers=blockers,
    )
