"""Deterministic appliance scheduling with SciPy's HiGHS-backed MILP solver."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_array

from app.models.tariff import Tariff
from app.schemas.scheduling import (
    ApplianceTaskV1,
    ObjectiveBreakdownV1,
    ScheduledTaskV1,
    ScheduleV1,
    SchedulingRequestV1,
    SchedulingStatus,
)

SOLVER_TIME_LIMIT_SECONDS = 5.0
_FEASIBILITY_TOLERANCE = 1e-6


@dataclass(frozen=True)
class OptimizationResult:
    """Public outcome from the MILP and its deterministic reference heuristic."""

    status: SchedulingStatus
    candidate_schedule: ScheduleV1 | None
    reference_schedule: ScheduleV1
    preferred_schedule: ScheduleV1
    objective_breakdown: ObjectiveBreakdownV1
    blockers: list[str]


@dataclass(frozen=True)
class _Candidate:
    start_index: int
    power_kw: float
    energy_cost_aud: float
    preference_penalty_aud: float

    @property
    def objective_aud(self) -> float:
        return self.energy_cost_aud + self.preference_penalty_aud


def _valid_rate(value: object) -> float | None:
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return None
    return float(value)


def interval_energy_rates_aud(
    tariff: Tariff, request: SchedulingRequestV1, state: str
) -> list[float] | None:
    """Resolve an explicit AUD/kWh energy price for every baseline interval."""
    zone = ZoneInfo(request.timezone)
    gst_multiplier = 1.0 if tariff.rates_include_gst else 1.1
    result: list[float] = []

    for interval in request.baseline_profile.intervals:
        local_start = interval.interval_start.astimezone(zone)
        rate: float | None = None

        if tariff.periods:
            minute_of_day = local_start.hour * 60 + local_start.minute
            matches = [
                period
                for period in tariff.periods
                if isinstance(period, dict)
                and isinstance(period.get("days"), list)
                and local_start.weekday() in period["days"]
                and isinstance(period.get("start_minute"), int)
                and isinstance(period.get("end_minute"), int)
                and period["start_minute"] <= minute_of_day < period["end_minute"]
            ]
            if len(matches) == 1:
                rate = _valid_rate(matches[0].get("rate_cents_kwh"))
        elif tariff.tariff_type == "flat":
            rate = _valid_rate(tariff.flat_rate_cents_kwh)
        if rate is None:
            return None
        result.append(rate * gst_multiplier / 100)

    return result


def _task_power_kw(task: ApplianceTaskV1) -> float:
    if task.rated_power_kw is not None:
        return task.rated_power_kw
    if task.energy_kwh is None:
        raise ValueError(f"Task {task.task_id} has no energy or rated-power input")
    return task.energy_kwh / (task.duration_minutes / 60)


def _task_energy_kwh(task: ApplianceTaskV1, power_kw: float) -> float:
    if task.energy_kwh is not None:
        return task.energy_kwh
    return power_kw * task.duration_minutes / 60


def _build_candidates(
    request: SchedulingRequestV1,
    interval_prices_aud_per_kwh: list[float],
) -> tuple[list[list[_Candidate]], list[int]]:
    step = timedelta(minutes=request.interval_minutes)
    step_hours = request.interval_minutes / 60
    starts = [
        item.interval_start.astimezone(timezone.utc) for item in request.baseline_profile.intervals
    ]
    candidates_by_task: list[list[_Candidate]] = []
    durations: list[int] = []

    for task in request.tasks:
        duration_slots = task.duration_minutes // request.interval_minutes
        durations.append(duration_slots)
        if not task.mandatory and task.omission_penalty_aud is None:
            candidates_by_task.append([])
            continue
        power_kw = _task_power_kw(task)
        earliest = task.earliest_start.astimezone(timezone.utc)
        latest_end = task.deadline.astimezone(timezone.utc)
        preferred = (
            task.preferred_start.astimezone(timezone.utc)
            if task.preferred_start is not None
            else None
        )
        task_candidates: list[_Candidate] = []

        for index, start in enumerate(starts):
            end_index = index + duration_slots
            if end_index > len(starts):
                continue
            end = start + step * duration_slots
            if start < earliest or end > latest_end:
                continue
            energy_cost = sum(
                power_kw * step_hours * interval_prices_aud_per_kwh[slot]
                for slot in range(index, end_index)
            )
            preference_penalty = 0.0
            if preferred is not None:
                distance_slots = abs((start - preferred).total_seconds()) / step.total_seconds()
                preference_penalty = request.preference_penalty_aud_per_interval * distance_slots
            task_candidates.append(
                _Candidate(
                    start_index=index,
                    power_kw=power_kw,
                    energy_cost_aud=energy_cost,
                    preference_penalty_aud=preference_penalty,
                )
            )
        candidates_by_task.append(task_candidates)

    return candidates_by_task, durations


def _effective_power_limit(request: SchedulingRequestV1) -> float | None:
    limits = [
        limit
        for limit in (
            request.household_power_limit_kw,
            request.grid_power_limit_kw,
        )
        if limit is not None
    ]
    return min(limits) if limits else None


def _baseline_energy_cost(
    request: SchedulingRequestV1,
    interval_prices_aud_per_kwh: list[float],
) -> float:
    step_hours = request.interval_minutes / 60
    return sum(
        interval.demand_kw * step_hours * price
        for interval, price in zip(
            request.baseline_profile.intervals, interval_prices_aud_per_kwh, strict=True
        )
    )


def _preference_penalty(
    selected: dict[int, _Candidate | None],
) -> float:
    return sum(
        candidate.preference_penalty_aud for candidate in selected.values() if candidate is not None
    )


def _omission_penalty(
    request: SchedulingRequestV1,
    selected: dict[int, _Candidate | None],
) -> float:
    return sum(
        task.omission_penalty_aud or 0.0
        for index, task in enumerate(request.tasks)
        if not task.mandatory and selected[index] is None
    )


def _schedule_penalties(
    request: SchedulingRequestV1,
    schedule: ScheduleV1,
) -> tuple[float, float]:
    tasks_by_id = {item.task_id: item for item in schedule.tasks}
    preference_penalty = 0.0
    omission_penalty = 0.0
    interval_seconds = request.interval_minutes * 60

    for task in request.tasks:
        scheduled = tasks_by_id.get(task.task_id)
        if scheduled is None:
            raise RuntimeError(f"Reference schedule is missing task {task.task_id}")
        if scheduled.omitted:
            omission_penalty += task.omission_penalty_aud or 0.0
        elif task.preferred_start is not None and scheduled.start is not None:
            distance_intervals = (
                abs(
                    (
                        scheduled.start.astimezone(timezone.utc)
                        - task.preferred_start.astimezone(timezone.utc)
                    ).total_seconds()
                )
                / interval_seconds
            )
            preference_penalty += request.preference_penalty_aud_per_interval * distance_intervals

    return preference_penalty, omission_penalty


def _schedule_metrics(
    request: SchedulingRequestV1,
    interval_prices_aud_per_kwh: list[float],
    selected: dict[int, _Candidate | None],
) -> tuple[float, float, list[ScheduledTaskV1]]:
    zone = ZoneInfo(request.timezone)
    step_hours = request.interval_minutes / 60
    baseline_energy = sum(
        item.demand_kw * step_hours for item in request.baseline_profile.intervals
    )
    baseline_cost = _baseline_energy_cost(request, interval_prices_aud_per_kwh)
    total_energy = baseline_energy
    total_cost = baseline_cost
    tasks: list[ScheduledTaskV1] = []

    for task_index, task in enumerate(request.tasks):
        candidate = selected[task_index]
        power_kw = _task_power_kw(task)
        energy_kwh = _task_energy_kwh(task, power_kw)
        if candidate is None:
            tasks.append(
                ScheduledTaskV1(
                    task_id=task.task_id,
                    start=None,
                    end=None,
                    power_kw=power_kw,
                    energy_kwh=energy_kwh,
                    omitted=True,
                )
            )
            continue

        start = request.baseline_profile.intervals[candidate.start_index].interval_start
        start_utc = start.astimezone(timezone.utc)
        end_utc = start_utc + timedelta(minutes=task.duration_minutes)
        occupied = range(
            candidate.start_index,
            candidate.start_index + task.duration_minutes // request.interval_minutes,
        )
        task_cost = sum(
            power_kw * step_hours * interval_prices_aud_per_kwh[slot] for slot in occupied
        )
        total_energy += energy_kwh
        total_cost += task_cost
        tasks.append(
            ScheduledTaskV1(
                task_id=task.task_id,
                start=start_utc.astimezone(zone),
                end=end_utc.astimezone(zone),
                power_kw=power_kw,
                energy_kwh=energy_kwh,
                omitted=False,
            )
        )

    return round(total_energy, 6), round(total_cost, 6), tasks


def _selected_schedule(
    request: SchedulingRequestV1,
    interval_prices_aud_per_kwh: list[float],
    selected: dict[int, _Candidate | None],
    *,
    method: Literal["milp", "deterministic_greedy", "preferred"],
) -> ScheduleV1:
    total_energy, total_cost, scheduled_tasks = _schedule_metrics(
        request, interval_prices_aud_per_kwh, selected
    )
    return ScheduleV1(
        status="feasible",
        method=method,
        tasks=scheduled_tasks,
        total_energy_kwh=total_energy,
        total_cost_aud=total_cost,
    )


def _preferred_schedule(
    request: SchedulingRequestV1,
    interval_prices_aud_per_kwh: list[float],
) -> ScheduleV1:
    """Price the exact requested start times when all tasks are jointly feasible."""
    selected: dict[int, _Candidate | None] = {}
    starts = [
        item.interval_start.astimezone(timezone.utc)
        for item in request.baseline_profile.intervals
    ]
    step_hours = request.interval_minutes / 60
    for task_index, task in enumerate(request.tasks):
        if task.preferred_start is None:
            return ScheduleV1(
                status="not_found",
                method="preferred",
                reason=f"Task {task.task_id} has no preferred start time.",
                tasks=[],
            )
        preferred_start = task.preferred_start.astimezone(timezone.utc)
        start_index = next(
            (index for index, start in enumerate(starts) if start == preferred_start),
            None,
        )
        duration_slots = task.duration_minutes // request.interval_minutes
        if start_index is None or start_index + duration_slots > len(starts):
            return ScheduleV1(
                status="not_found",
                method="preferred",
                reason=f"Preferred start for task {task.task_id} is unavailable.",
                tasks=[],
            )
        power_kw = _task_power_kw(task)
        energy_cost = sum(
            power_kw * step_hours * interval_prices_aud_per_kwh[slot]
            for slot in range(start_index, start_index + duration_slots)
        )
        selected[task_index] = _Candidate(
            start_index=start_index,
            power_kw=power_kw,
            energy_cost_aud=energy_cost,
            preference_penalty_aud=0.0,
        )

    power_limit = _effective_power_limit(request)
    if power_limit is not None:
        interval_power = [item.demand_kw for item in request.baseline_profile.intervals]
        for task_index, candidate in selected.items():
            if candidate is None:
                continue
            duration_slots = request.tasks[task_index].duration_minutes // request.interval_minutes
            for slot in range(candidate.start_index, candidate.start_index + duration_slots):
                interval_power[slot] += candidate.power_kw
                if interval_power[slot] > power_limit + _FEASIBILITY_TOLERANCE:
                    return ScheduleV1(
                        status="not_found",
                        method="preferred",
                        reason="Preferred task starts exceed a configured power limit.",
                        tasks=[],
                    )

    return _selected_schedule(
        request,
        interval_prices_aud_per_kwh,
        selected,
        method="preferred",
    )


def _greedy_reference(
    request: SchedulingRequestV1,
    interval_prices_aud_per_kwh: list[float],
    candidates_by_task: list[list[_Candidate]],
    durations: list[int],
) -> ScheduleV1:
    """Choose lowest-objective feasible slots with stable task and time tie-breaks."""
    limit = _effective_power_limit(request)
    baseline = [item.demand_kw for item in request.baseline_profile.intervals]
    if limit is not None and any(demand > limit + _FEASIBILITY_TOLERANCE for demand in baseline):
        return ScheduleV1(
            status="not_found",
            method="deterministic_greedy",
            reason="The fixed baseline already exceeds a configured power limit.",
            tasks=[],
        )
    remaining = (
        [limit - demand for demand in baseline] if limit is not None else [math.inf] * len(baseline)
    )
    selected: dict[int, _Candidate | None] = {}
    task_order = sorted(
        range(len(request.tasks)),
        key=lambda index: (
            not request.tasks[index].mandatory,
            len(candidates_by_task[index]),
            -(request.tasks[index].omission_penalty_aud or 0.0),
            request.tasks[index].task_id,
        ),
    )

    for task_index in task_order:
        task = request.tasks[task_index]
        if not task.mandatory and task.omission_penalty_aud is None:
            selected[task_index] = None
            continue
        feasible = [
            candidate
            for candidate in candidates_by_task[task_index]
            if all(
                remaining[slot] + _FEASIBILITY_TOLERANCE >= candidate.power_kw
                for slot in range(
                    candidate.start_index,
                    candidate.start_index + durations[task_index],
                )
            )
        ]
        best = min(
            feasible,
            key=lambda candidate: (
                candidate.objective_aud,
                candidate.start_index,
            ),
            default=None,
        )
        if task.mandatory:
            if best is None:
                return ScheduleV1(
                    status="not_found",
                    method="deterministic_greedy",
                    reason=f"Greedy reference could not place required task {task.task_id}.",
                    tasks=[],
                )
            selected[task_index] = best
        elif best is not None and best.objective_aud < (task.omission_penalty_aud or 0.0):
            selected[task_index] = best
        else:
            selected[task_index] = None

        chosen = selected[task_index]
        if chosen is not None and limit is not None:
            for slot in range(chosen.start_index, chosen.start_index + durations[task_index]):
                remaining[slot] -= chosen.power_kw

    return _selected_schedule(
        request,
        interval_prices_aud_per_kwh,
        selected,
        method="deterministic_greedy",
    )


def _solve_milp(
    request: SchedulingRequestV1,
    candidates_by_task: list[list[_Candidate]],
    durations: list[int],
    time_limit_seconds: float,
) -> tuple[SchedulingStatus, dict[int, _Candidate | None] | None]:
    variable_objective: list[float] = []
    candidate_columns: dict[tuple[int, int], int] = {}
    omission_columns: dict[int, int] = {}
    for task_index, candidates in enumerate(candidates_by_task):
        for candidate_index, candidate in enumerate(candidates):
            candidate_columns[(task_index, candidate_index)] = len(variable_objective)
            variable_objective.append(candidate.objective_aud)
        task = request.tasks[task_index]
        if not task.mandatory:
            omission_columns[task_index] = len(variable_objective)
            variable_objective.append(task.omission_penalty_aud or 0.0)

    if not variable_objective:
        return SchedulingStatus.INFEASIBLE, None

    baseline = [item.demand_kw for item in request.baseline_profile.intervals]
    power_limit = _effective_power_limit(request)
    task_rows = len(request.tasks)
    n_intervals = len(baseline)
    n_rows = task_rows + (n_intervals if power_limit is not None else 0)
    row_indices: list[int] = []
    column_indices: list[int] = []
    coefficients: list[float] = []
    lower_bounds = np.full(n_rows, -np.inf)
    upper_bounds = np.full(n_rows, np.inf)

    for task_index, candidates in enumerate(candidates_by_task):
        lower_bounds[task_index] = 1.0
        upper_bounds[task_index] = 1.0
        for candidate_index, candidate in enumerate(candidates):
            column = candidate_columns[(task_index, candidate_index)]
            row_indices.append(task_index)
            column_indices.append(column)
            coefficients.append(1.0)
            if power_limit is not None:
                for slot in range(
                    candidate.start_index,
                    candidate.start_index + durations[task_index],
                ):
                    row_indices.append(task_rows + slot)
                    column_indices.append(column)
                    coefficients.append(candidate.power_kw)

        omission_column = omission_columns.get(task_index)
        if omission_column is not None:
            row_indices.append(task_index)
            column_indices.append(omission_column)
            coefficients.append(1.0)

    if power_limit is not None:
        for slot, baseline_demand in enumerate(baseline):
            row = task_rows + slot
            lower_bounds[row] = -np.inf
            upper_bounds[row] = power_limit - baseline_demand

    matrix = coo_array(
        (coefficients, (row_indices, column_indices)),
        shape=(n_rows, len(variable_objective)),
    ).tocsc()
    result = milp(
        c=np.asarray(variable_objective, dtype=float),
        integrality=np.ones(len(variable_objective), dtype=np.uint8),
        bounds=Bounds(
            np.zeros(len(variable_objective)),
            np.ones(len(variable_objective)),
        ),
        constraints=LinearConstraint(matrix, lower_bounds, upper_bounds),
        options={"time_limit": time_limit_seconds, "presolve": True},
    )

    if result.status == 2:
        return SchedulingStatus.INFEASIBLE, None
    if result.status == 1:
        return SchedulingStatus.TIMEOUT, None
    if result.status != 0 or result.x is None:
        raise RuntimeError(f"MILP solver failed with status {result.status}: {result.message}")

    selected: dict[int, _Candidate | None] = {}
    for task_index, candidates in enumerate(candidates_by_task):
        chosen = [
            candidate
            for candidate_index, candidate in enumerate(candidates)
            if result.x[candidate_columns[(task_index, candidate_index)]] > 0.5
        ]
        omitted = (
            result.x[omission_columns[task_index]] > 0.5
            if task_index in omission_columns
            else False
        )
        if len(chosen) + int(omitted) != 1:
            raise RuntimeError(
                f"MILP returned an invalid assignment for task {request.tasks[task_index].task_id}"
            )
        selected[task_index] = chosen[0] if chosen else None

    if power_limit is not None:
        for slot, baseline_demand in enumerate(baseline):
            task_power = sum(
                candidate.power_kw
                for task_index, candidate in selected.items()
                if candidate is not None
                and candidate.start_index <= slot < candidate.start_index + durations[task_index]
            )
            if baseline_demand + task_power > power_limit + _FEASIBILITY_TOLERANCE:
                raise RuntimeError("MILP returned a schedule exceeding the configured power limit")

    return SchedulingStatus.FEASIBLE, selected


def optimize_schedule_v1(
    request: SchedulingRequestV1,
    interval_prices_aud_per_kwh: list[float],
    *,
    time_limit_seconds: float = SOLVER_TIME_LIMIT_SECONDS,
) -> OptimizationResult:
    """Optimize tasks and compare with a deterministic greedy plan on the same inputs."""
    if len(interval_prices_aud_per_kwh) != len(request.baseline_profile.intervals):
        raise ValueError("An energy price is required for every baseline interval")
    if any(not math.isfinite(price) or price < 0 for price in interval_prices_aud_per_kwh):
        raise ValueError("Interval energy prices must be finite and nonnegative")
    if not math.isfinite(time_limit_seconds) or time_limit_seconds <= 0:
        raise ValueError("time_limit_seconds must be finite and greater than zero")

    candidates_by_task, durations = _build_candidates(request, interval_prices_aud_per_kwh)
    preferred = _preferred_schedule(request, interval_prices_aud_per_kwh)
    reference = _greedy_reference(
        request,
        interval_prices_aud_per_kwh,
        candidates_by_task,
        durations,
    )
    baseline_cost = _baseline_energy_cost(request, interval_prices_aud_per_kwh)
    power_limit = _effective_power_limit(request)
    baseline_exceeds_limit = power_limit is not None and any(
        interval.demand_kw > power_limit + _FEASIBILITY_TOLERANCE
        for interval in request.baseline_profile.intervals
    )

    if baseline_exceeds_limit:
        status = SchedulingStatus.INFEASIBLE
        selected = None
    else:
        status, selected = _solve_milp(
            request,
            candidates_by_task,
            durations,
            time_limit_seconds,
        )

    if status != SchedulingStatus.FEASIBLE or selected is None:
        blocker = (
            "The MILP solve reached its time limit before proving an optimal schedule."
            if status == SchedulingStatus.TIMEOUT
            else "No schedule satisfies all required task windows and configured power limits."
        )
        return OptimizationResult(
            status=status,
            candidate_schedule=None,
            reference_schedule=reference,
            preferred_schedule=preferred,
            objective_breakdown=ObjectiveBreakdownV1(
                baseline_energy_cost_aud=round(baseline_cost, 6)
            ),
            blockers=[blocker],
        )

    candidate_schedule = _selected_schedule(
        request,
        interval_prices_aud_per_kwh,
        selected,
        method="milp",
    )
    preference_penalty = _preference_penalty(selected)
    omission_penalty = _omission_penalty(request, selected)
    reference_cost = reference.total_cost_aud
    candidate_cost = candidate_schedule.total_cost_aud
    reference_penalties = (
        _schedule_penalties(request, reference) if reference.status == "feasible" else None
    )
    reference_preference = reference_penalties[0] if reference_penalties is not None else None
    reference_omission = reference_penalties[1] if reference_penalties is not None else None
    preferred_cost = preferred.total_cost_aud
    return OptimizationResult(
        status=SchedulingStatus.FEASIBLE,
        candidate_schedule=candidate_schedule,
        reference_schedule=reference,
        preferred_schedule=preferred,
        objective_breakdown=ObjectiveBreakdownV1(
            baseline_energy_cost_aud=round(baseline_cost, 6),
            candidate_energy_cost_aud=candidate_cost,
            reference_energy_cost_aud=reference_cost,
            energy_cost_delta_aud=(
                round(candidate_cost - reference_cost, 6)
                if reference.status == "feasible" and reference_cost is not None
                else None
            ),
            preference_penalty_aud=round(preference_penalty, 6),
            omission_penalty_aud=round(omission_penalty, 6),
            total_objective_aud=round(candidate_cost + preference_penalty + omission_penalty, 6),
            reference_preference_penalty_aud=(
                round(reference_preference, 6) if reference_preference is not None else None
            ),
            reference_omission_penalty_aud=(
                round(reference_omission, 6) if reference_omission is not None else None
            ),
            reference_objective_aud=(
                round(reference_cost + reference_preference + reference_omission, 6)
                if reference_cost is not None
                and reference_preference is not None
                and reference_omission is not None
                else None
            ),
            preferred_energy_cost_aud=preferred_cost,
            milp_vs_preferred_energy_cost_delta_aud=(
                round(candidate_cost - preferred_cost, 6)
                if preferred_cost is not None
                else None
            ),
            greedy_vs_preferred_energy_cost_delta_aud=(
                round(reference_cost - preferred_cost, 6)
                if reference_cost is not None and preferred_cost is not None
                else None
            ),
        ),
        blockers=[],
    )
