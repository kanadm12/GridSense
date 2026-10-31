"""Reproducible synthetic experiment for scheduling strategy comparisons."""

from __future__ import annotations

import json
import math
import platform
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from datetime import time as datetime_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy
from scipy import stats

from app.schemas.scheduling import ScheduleV1, SchedulingRequestV1
from app.services.scheduling_optimizer import OptimizationResult, optimize_schedule_v1

TIMEZONE = "Australia/Melbourne"
SIMULATION_DATE = date(2026, 3, 2)
INTERVAL_MINUTES = 30
RANDOM_SEED = 20261031
FLEXIBILITY_HOURS = (2, 6, 10)
FORECAST_ERROR_SPREAD_FRACTIONS = (0.0, 0.5)
APPLIANCE_MIXES = ("light", "mixed")
TARIFF_SPREAD_FACTORS = (0.0, 1.0)
HOUSEHOLD_COUNT = 8
PREFERENCE_PENALTY_AUD_PER_INTERVAL = 0.01
HOUSEHOLD_POWER_LIMIT_KW = 8.0
STRATEGIES = (
    "S0_no_intervention",
    "S1_greedy_nominal",
    "S2_milp_nominal",
    "S2_milp_forecast",
    "oracle_milp_perfect_information",
    "oracle_milp_energy_only",
)
NUMERICAL_TOLERANCE_AUD = 1e-8
PAIRED_COMPARISONS = {
    "nominal_milp_minus_greedy": ("S2_milp_nominal", "S1_greedy_nominal"),
    "forecast_minus_nominal_milp": ("S2_milp_forecast", "S2_milp_nominal"),
    "forecast_milp_minus_greedy": ("S2_milp_forecast", "S1_greedy_nominal"),
}
EQUITY_STRATEGIES = (
    "S1_greedy_nominal",
    "S2_milp_nominal",
    "S2_milp_forecast",
)
EQUITY_METRIC_DEFINITIONS = {
    "software_access": (
        "Not measured; technically complete synthetic advisory inputs are a pipeline-eligibility "
        "proxy only and do not establish that a person can access or use the software."
    ),
    "actionability": (
        "Technical feasibility/completion only: the schedule is feasible and all mandatory "
        "tasks complete. Practical user actionability is not measured."
    ),
    "benefit": (
        "Absolute modeled energy-charge reduction from the same case's S0, in AUD; not a full "
        "bill or verified household saving."
    ),
    "inconvenience": (
        "Sum of absolute task start-time displacements from preferred starts, in hours."
    ),
    "weighted_objective": (
        "Realized energy charge plus the configured preference penalty; a model score, not a "
        "validated welfare measure."
    ),
    "group_labels": (
        "Only generated scenario categories (flexibility hours and appliance mix) are used; "
        "no demographic or socioeconomic groups are inferred."
    ),
    "der_comparison": (
        "Not estimable: source profiles do not encode PV generation, battery storage, or a "
        "verified DER-ownership category. EV charging is only a modeled load task."
    ),
}


@dataclass(frozen=True)
class ExperimentDesign:
    seed: int = RANDOM_SEED
    household_count: int = HOUSEHOLD_COUNT
    flexibility_hours: tuple[int, ...] = FLEXIBILITY_HOURS
    forecast_error_spread_fractions: tuple[float, ...] = FORECAST_ERROR_SPREAD_FRACTIONS
    appliance_mixes: tuple[str, ...] = APPLIANCE_MIXES
    tariff_spread_factors: tuple[float, ...] = TARIFF_SPREAD_FACTORS


@dataclass(frozen=True)
class StrategyScore:
    cost_aud: float | None
    non_flexible_baseline_cost_aud: float
    inconvenience_penalty_aud: float | None
    combined_objective_aud: float | None
    peak_demand_kw: float
    completed_tasks: int
    total_tasks: int
    completion_fraction: float
    inconvenience_hours: float
    feasible: bool


def _task_specs(mix: str) -> list[tuple[str, str, float, int, int]]:
    specs = [
        ("dishwasher", "Dishwasher", 1.2, 90, 19),
        ("laundry", "Laundry", 0.8, 60, 13),
    ]
    if mix == "mixed":
        specs.extend(
            [
                ("ev_charging", "EV charging", 3.3, 120, 17),
                ("water_heater", "Water heater", 2.0, 60, 7),
            ]
        )
    elif mix != "light":
        raise ValueError(f"Unknown appliance mix: {mix}")
    return specs


def _make_baseline(household_index: int, rng: np.random.Generator) -> np.ndarray:
    slot_hours = np.arange(48, dtype=float) / 2
    morning_peak = np.exp(-0.5 * ((slot_hours - (7.5 + household_index % 3 * 0.5)) / 1.4) ** 2)
    evening_peak = np.exp(-0.5 * ((slot_hours - (19.0 + household_index % 4 * 0.25)) / 2.0) ** 2)
    daily_level = 0.55 + 0.08 * (household_index % 5)
    demand = daily_level + 0.45 * morning_peak + 0.8 * evening_peak
    demand += rng.normal(0.0, 0.06, size=len(demand))
    return np.maximum(demand, 0.15)


def _tariff_profile(spread_factor: float) -> np.ndarray:
    prices = np.empty(48, dtype=float)
    for slot in range(48):
        hour = slot / 2
        if hour < 7 or hour >= 22:
            nominal_cents = 24 - 12 * spread_factor
        elif 16 <= hour < 20:
            nominal_cents = 24 + 18 * spread_factor
        else:
            nominal_cents = 24.0
        prices[slot] = nominal_cents / 100
    return prices


def _scenario_key(
    flexibility_hours: int,
    forecast_error_fraction: float,
    mix: str,
    spread_factor: float,
) -> str:
    return (
        f"flex-{flexibility_hours}h_error-{forecast_error_fraction:g}"
        f"_mix-{mix}_spread-{spread_factor:g}"
    )


def _make_request(
    household_index: int,
    scenario_id: str,
    flexibility_hours: int,
    mix: str,
    baseline_kw: np.ndarray,
    seed: int = RANDOM_SEED,
) -> SchedulingRequestV1:
    zone = ZoneInfo(TIMEZONE)
    start_of_day = datetime.combine(SIMULATION_DATE, datetime_time.min, tzinfo=zone)
    slots_per_hour = 60 // INTERVAL_MINUTES
    tasks: list[dict[str, Any]] = []
    rng = np.random.default_rng(seed + household_index * 1009)
    flex_slots = flexibility_hours * slots_per_hour

    for task_id, appliance, power_kw, duration_minutes, preferred_hour in _task_specs(mix):
        household_shift_slots = int(rng.integers(-2, 3))
        preferred_slot = preferred_hour * slots_per_hour + household_shift_slots
        duration_slots = duration_minutes // INTERVAL_MINUTES
        flex_before = flex_slots // 2
        earliest_slot = max(0, preferred_slot - flex_before)
        latest_start_slot = min(
            48 - duration_slots,
            preferred_slot + (flex_slots - flex_before),
        )
        if earliest_slot > preferred_slot or latest_start_slot < preferred_slot:
            raise ValueError(f"Task window for {task_id} falls outside the simulation day")
        earliest = start_of_day + timedelta(minutes=earliest_slot * INTERVAL_MINUTES)
        preferred = start_of_day + timedelta(minutes=preferred_slot * INTERVAL_MINUTES)
        deadline = start_of_day + timedelta(
            minutes=(latest_start_slot + duration_slots) * INTERVAL_MINUTES
        )
        tasks.append(
            {
                "task_id": task_id,
                "appliance": appliance,
                "rated_power_kw": power_kw,
                "duration_minutes": duration_minutes,
                "earliest_start": earliest.isoformat(),
                "deadline": deadline.isoformat(),
                "preferred_start": preferred.isoformat(),
                "mandatory": True,
            }
        )

    baseline = [
        {
            "interval_start": (
                start_of_day + timedelta(minutes=index * INTERVAL_MINUTES)
            ).isoformat(),
            "demand_kw": float(demand),
        }
        for index, demand in enumerate(baseline_kw)
    ]
    return SchedulingRequestV1.model_validate(
        {
            "schema_version": "1.0",
            "meter_id": household_index + 1,
            "scenario_id": scenario_id,
            "interval_minutes": INTERVAL_MINUTES,
            "timezone": TIMEZONE,
            "currency": "AUD",
            "preference_penalty_aud_per_interval": PREFERENCE_PENALTY_AUD_PER_INTERVAL,
            "household_power_limit_kw": HOUSEHOLD_POWER_LIMIT_KW,
            "tasks": tasks,
            "baseline_profile": {
                "source": "synthetic",
                "profile_id": f"synthetic-household-{household_index + 1}-baseline-v1",
                "scenario_id": scenario_id,
                "includes_scheduled_tasks": False,
                "intervals": baseline,
            },
        }
    )


def _assignment(schedule: ScheduleV1) -> dict[str, datetime | None]:
    return {task.task_id: task.start for task in schedule.tasks if not task.omitted}


def score_assignment(
    request: SchedulingRequestV1,
    assignment: dict[str, datetime | None],
    realized_prices_aud_per_kwh: list[float],
) -> StrategyScore:
    """Reconcile every scenario's realized charge from interval demand and price."""
    intervals = request.baseline_profile.intervals
    if len(realized_prices_aud_per_kwh) != len(intervals):
        raise ValueError("A realized interval price is required for every baseline interval")
    if any(not math.isfinite(price) or price < 0 for price in realized_prices_aud_per_kwh):
        raise ValueError("Realized prices must be finite and nonnegative")

    interval_hours = request.interval_minutes / 60
    baseline_cost = sum(
        interval.demand_kw * interval_hours * price
        for interval, price in zip(intervals, realized_prices_aud_per_kwh, strict=True)
    )
    total_demand = np.asarray([interval.demand_kw for interval in intervals], dtype=float)
    task_by_id = {task.task_id: task for task in request.tasks}
    completed = 0
    inconvenience_hours = 0.0
    first_utc = intervals[0].interval_start.astimezone(ZoneInfo("UTC"))
    step = timedelta(minutes=request.interval_minutes)

    for task_id, start in assignment.items():
        if task_id not in task_by_id:
            raise ValueError(f"Assignment contains unknown task {task_id}")
        if start is None:
            continue
        task = task_by_id[task_id]
        start_utc = start.astimezone(ZoneInfo("UTC"))
        slot_offset = (start_utc - first_utc).total_seconds() / step.total_seconds()
        if not slot_offset.is_integer():
            raise ValueError(f"Task {task_id} start is not aligned to the interval grid")
        start_index = int(slot_offset)
        duration_slots = task.duration_minutes // request.interval_minutes
        if start_index < 0 or start_index + duration_slots > len(intervals):
            raise ValueError(f"Task {task_id} falls outside the baseline price profile")
        if start_utc < task.earliest_start.astimezone(ZoneInfo("UTC")):
            raise ValueError(f"Task {task_id} starts before its allowed window")
        end_utc = start_utc + timedelta(minutes=task.duration_minutes)
        if end_utc > task.deadline.astimezone(ZoneInfo("UTC")):
            raise ValueError(f"Task {task_id} completes after its deadline")
        total_demand[start_index : start_index + duration_slots] += task.rated_power_kw
        completed += 1
        if task.preferred_start is not None:
            inconvenience_hours += (
                abs((start_utc - task.preferred_start.astimezone(ZoneInfo("UTC"))).total_seconds())
                / 3600
            )

    cost = sum(
        demand * interval_hours * price
        for demand, price in zip(total_demand, realized_prices_aud_per_kwh, strict=True)
    )
    limit = request.household_power_limit_kw
    feasible = completed == len(request.tasks) and (
        limit is None or float(total_demand.max()) <= limit + 1e-6
    )
    inconvenience_penalty = (
        inconvenience_hours
        / (request.interval_minutes / 60)
        * request.preference_penalty_aud_per_interval
    )
    return StrategyScore(
        cost_aud=round(cost, 8) if feasible else None,
        non_flexible_baseline_cost_aud=round(baseline_cost, 8),
        inconvenience_penalty_aud=round(inconvenience_penalty, 8) if feasible else None,
        combined_objective_aud=(round(cost + inconvenience_penalty, 8) if feasible else None),
        peak_demand_kw=round(float(total_demand.max()), 6),
        completed_tasks=completed,
        total_tasks=len(request.tasks),
        completion_fraction=completed / len(request.tasks),
        inconvenience_hours=round(inconvenience_hours, 6),
        feasible=feasible,
    )


def _strategy_result_row(
    *,
    scenario_key: str,
    household_id: str,
    mix: str,
    flexibility_hours: int,
    forecast_error_fraction: float,
    spread_factor: float,
    strategy: str,
    score: StrategyScore,
    runtime_ms: float,
    s0_cost_aud: float,
    optimizer_status: str,
    seed: int,
) -> dict[str, Any]:
    savings_aud = s0_cost_aud - score.cost_aud if score.cost_aud is not None else None
    savings_percent = (
        savings_aud / s0_cost_aud * 100 if savings_aud is not None and s0_cost_aud > 0 else None
    )
    return {
        "scenario_key": scenario_key,
        "household_id": household_id,
        "profile_source": "synthetic",
        "appliance_mix": mix,
        "flexibility_hours": flexibility_hours,
        "forecast_error_spread_fraction": forecast_error_fraction,
        "tariff_spread_factor": spread_factor,
        "strategy": strategy,
        "non_flexible_baseline_energy_cost_aud": score.non_flexible_baseline_cost_aud,
        # Kept for older CSV consumers; this alias is fixed baseline demand, not S0.
        "baseline_energy_cost_aud": score.non_flexible_baseline_cost_aud,
        "s0_reference_energy_cost_aud": s0_cost_aud,
        "realized_energy_cost_aud": score.cost_aud,
        "savings_vs_s0_aud": round(savings_aud, 8) if savings_aud is not None else None,
        "savings_vs_s0_percent": (
            round(savings_percent, 6) if savings_percent is not None else None
        ),
        "peak_demand_kw": score.peak_demand_kw,
        "completed_tasks": score.completed_tasks,
        "total_tasks": score.total_tasks,
        "task_completion_fraction": score.completion_fraction,
        "inconvenience_hours": score.inconvenience_hours,
        "inconvenience_penalty_aud": score.inconvenience_penalty_aud,
        "combined_objective_aud": score.combined_objective_aud,
        "objective_weighting_aud_per_interval": PREFERENCE_PENALTY_AUD_PER_INTERVAL,
        "feasible": score.feasible,
        "optimizer_status": optimizer_status,
        "runtime_ms": round(runtime_ms, 3),
        "seed": seed,
    }


def audit_billing_reconciliation(
    results: pd.DataFrame,
    interval_prices: pd.DataFrame,
    task_schedules: pd.DataFrame,
    tolerance_aud: float = NUMERICAL_TOLERANCE_AUD,
) -> None:
    """Recompute all feasible exported charges from interval load and realized prices."""
    if not math.isfinite(tolerance_aud) or tolerance_aud < 0:
        raise ValueError("Billing audit tolerance must be finite and nonnegative")
    case_keys = ["scenario_key", "household_id"]
    prices_by_case = {
        key: group.sort_values("interval_index").reset_index(drop=True)
        for key, group in interval_prices.groupby(case_keys, sort=False)
    }
    schedules_by_strategy = {
        key: group.reset_index(drop=True)
        for key, group in task_schedules.groupby([*case_keys, "strategy"], sort=False)
    }
    for row in results.itertuples():
        case_key = (row.scenario_key, row.household_id)
        if case_key not in prices_by_case:
            raise ValueError(f"Missing interval prices for {case_key}")
        strategy_key = (*case_key, row.strategy)
        if strategy_key not in schedules_by_strategy:
            raise ValueError(f"Missing task schedules for {strategy_key}")
        if not row.feasible:
            if not pd.isna(row.realized_energy_cost_aud):
                raise ValueError(f"Infeasible strategy {strategy_key} must not report a cost")
            continue

        prices = prices_by_case[case_key]
        schedules = schedules_by_strategy[strategy_key]
        if len(prices) == 0 or len(schedules) != row.total_tasks:
            raise ValueError(f"Incomplete billing inputs for {strategy_key}")
        demand = prices["baseline_demand_kw"].to_numpy(dtype=float, copy=True)
        realized_rate = prices["realized_price_aud_per_kwh"].to_numpy(dtype=float)
        first_start = pd.Timestamp(prices.iloc[0]["interval_start"]).tz_convert("UTC")
        for task in schedules.itertuples():
            if pd.isna(task.start):
                raise ValueError(f"Feasible strategy {strategy_key} omits task {task.task_id}")
            start = pd.Timestamp(task.start).tz_convert("UTC")
            offset_seconds = (start - first_start).total_seconds()
            step_seconds = INTERVAL_MINUTES * 60
            start_index = round(offset_seconds / step_seconds)
            if abs(offset_seconds - start_index * step_seconds) > 1e-6:
                raise ValueError(f"Task {task.task_id} start is off-grid in {strategy_key}")
            slots = task.duration_minutes // INTERVAL_MINUTES
            if start_index < 0 or start_index + slots > len(demand):
                raise ValueError(f"Task {task.task_id} is outside price trace in {strategy_key}")
            demand[start_index : start_index + slots] += task.rated_power_kw

        recomputed = float(np.sum(demand * (INTERVAL_MINUTES / 60) * realized_rate))
        if abs(recomputed - row.realized_energy_cost_aud) > tolerance_aud:
            raise ValueError(
                f"Billing mismatch for {strategy_key}: exported "
                f"{row.realized_energy_cost_aud:.12f}, recomputed {recomputed:.12f}, "
                f"tolerance {tolerance_aud:.12g} AUD"
            )


def paired_comparisons(results: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    factors = [
        "scenario_key",
        "household_id",
        "appliance_mix",
        "flexibility_hours",
        "forecast_error_spread_fraction",
        "tariff_spread_factor",
    ]
    pivots = results.pivot(index=factors, columns="strategy")
    rows: list[dict[str, Any]] = []
    for comparison, (left_strategy, right_strategy) in PAIRED_COMPARISONS.items():
        for index, values in pivots.iterrows():
            left_cost = values[("realized_energy_cost_aud", left_strategy)]
            right_cost = values[("realized_energy_cost_aud", right_strategy)]
            left_objective = values[("combined_objective_aud", left_strategy)]
            right_objective = values[("combined_objective_aud", right_strategy)]
            if any(
                pd.isna(value) for value in (left_cost, right_cost, left_objective, right_objective)
            ):
                raise ValueError(f"Cannot pair infeasible result in comparison {comparison}")
            cost_delta = float(left_cost - right_cost)
            objective_delta = float(left_objective - right_objective)
            rows.append(
                {
                    **dict(zip(factors, index, strict=True)),
                    "comparison": comparison,
                    "left_strategy": left_strategy,
                    "right_strategy": right_strategy,
                    "left_energy_cost_aud": float(left_cost),
                    "right_energy_cost_aud": float(right_cost),
                    "left_combined_objective_aud": float(left_objective),
                    "right_combined_objective_aud": float(right_objective),
                    "left_minus_right_energy_cost_aud": cost_delta,
                    "left_minus_right_combined_objective_aud": objective_delta,
                    "energy_cost_outcome": _paired_outcome(cost_delta),
                    "combined_objective_outcome": _paired_outcome(objective_delta),
                }
            )
    paired = pd.DataFrame(rows)
    summary_rows: list[dict[str, Any]] = []
    for comparison, group in paired.groupby("comparison", sort=True):
        summary_rows.append(_paired_summary_row("overall", "all", comparison, group))
    for factor, label in (
        ("flexibility_hours", "flexibility_hours"),
        ("forecast_error_spread_fraction", "forecast_error_spread_fraction"),
        ("tariff_spread_factor", "tariff_spread_factor"),
        ("appliance_mix", "appliance_mix"),
    ):
        for (comparison, level), group in paired.groupby(["comparison", factor], sort=True):
            summary_rows.append(_paired_summary_row(label, str(level), comparison, group))
    return paired, pd.DataFrame(summary_rows)


def _paired_outcome(delta: float) -> str:
    if abs(delta) <= NUMERICAL_TOLERANCE_AUD:
        return "tie"
    return "left_better" if delta < 0 else "right_better"


def _paired_summary_row(
    factor: str,
    level: str,
    comparison: str,
    group: pd.DataFrame,
) -> dict[str, Any]:
    profile_means = group.groupby("household_id")[
        ["left_minus_right_energy_cost_aud", "left_minus_right_combined_objective_aud"]
    ].mean()
    energy_profile_means = profile_means["left_minus_right_energy_cost_aud"]
    objective_profile_means = profile_means["left_minus_right_combined_objective_aud"]
    sample_count = len(energy_profile_means)
    energy_mean = float(energy_profile_means.mean())
    objective_mean = float(objective_profile_means.mean())
    if sample_count > 1:
        critical = float(stats.t.ppf(0.975, sample_count - 1))
        energy_half_width = critical * float(stats.sem(energy_profile_means))
        objective_half_width = critical * float(stats.sem(objective_profile_means))
    else:
        energy_half_width = float("nan")
        objective_half_width = float("nan")
    return {
        "factor": factor,
        "level": level,
        "comparison": comparison,
        "matched_household_scenario_pairs": len(group),
        "distinct_generated_profiles": sample_count,
        "mean_per_profile_energy_cost_difference_aud": energy_mean,
        "profile_level_95pct_t_interval_low_energy_aud": energy_mean - energy_half_width,
        "profile_level_95pct_t_interval_high_energy_aud": energy_mean + energy_half_width,
        "mean_per_profile_combined_objective_difference_aud": objective_mean,
        "profile_level_95pct_t_interval_low_objective_aud": (objective_mean - objective_half_width),
        "profile_level_95pct_t_interval_high_objective_aud": (
            objective_mean + objective_half_width
        ),
        "energy_cost_left_better_pairs": int((group["energy_cost_outcome"] == "left_better").sum()),
        "energy_cost_right_better_pairs": int(
            (group["energy_cost_outcome"] == "right_better").sum()
        ),
        "energy_cost_tied_pairs": int((group["energy_cost_outcome"] == "tie").sum()),
        "objective_left_better_pairs": int(
            (group["combined_objective_outcome"] == "left_better").sum()
        ),
        "objective_right_better_pairs": int(
            (group["combined_objective_outcome"] == "right_better").sum()
        ),
        "objective_tied_pairs": int((group["combined_objective_outcome"] == "tie").sum()),
    }


def _robustness_request(case: str) -> SchedulingRequestV1:
    base = _make_request(
        household_index=0,
        scenario_id=f"robustness-{case}",
        flexibility_hours=2,
        mix="light",
        baseline_kw=np.zeros(48),
    ).model_dump(mode="json")
    starts = [
        (
            datetime.combine(SIMULATION_DATE, datetime_time.min, tzinfo=ZoneInfo(TIMEZONE))
            + timedelta(minutes=INTERVAL_MINUTES * slot)
        ).isoformat()
        for slot in range(48)
    ]
    if case == "single_slot_window_cap_conflict":
        base["tasks"] = [
            {
                "task_id": "window-constrained-task",
                "appliance": "window-constrained-task",
                "rated_power_kw": 1.0,
                "duration_minutes": 30,
                "earliest_start": starts[16],
                "deadline": starts[17],
                "preferred_start": starts[16],
                "mandatory": True,
            }
        ]
        base["household_power_limit_kw"] = 1.5
    elif case == "power_cap_conflict":
        base["tasks"] = [
            {
                "task_id": task_id,
                "appliance": task_id,
                "rated_power_kw": 1.2,
                "duration_minutes": 30,
                "earliest_start": starts[16],
                "deadline": starts[17],
                "preferred_start": starts[16],
                "mandatory": True,
            }
            for task_id in ("task-a", "task-b")
        ]
        base["household_power_limit_kw"] = 2.0
    elif case == "baseline_over_cap":
        base["tasks"] = [
            {
                "task_id": "task-a",
                "appliance": "task-a",
                "rated_power_kw": 1.0,
                "duration_minutes": 30,
                "earliest_start": starts[16],
                "deadline": starts[18],
                "preferred_start": starts[16],
                "mandatory": True,
            }
        ]
        base["household_power_limit_kw"] = 0.5
        for interval in base["baseline_profile"]["intervals"]:
            interval["demand_kw"] = 0.6
    elif case == "greedy_suboptimal":
        base["tasks"] = [
            {
                "task_id": task_id,
                "appliance": task_id,
                "rated_power_kw": power_kw,
                "duration_minutes": 30,
                "earliest_start": starts[16],
                "deadline": starts[18],
                "preferred_start": None,
                "mandatory": True,
            }
            for task_id, power_kw in (("a-small", 1.0), ("b-large", 2.0))
        ]
        base["household_power_limit_kw"] = 2.0
    else:
        raise ValueError(f"Unknown robustness scenario: {case}")
    base["baseline_profile"]["intervals"] = [
        {**interval, "demand_kw": 0.0} for interval in base["baseline_profile"]["intervals"]
    ]
    if case == "baseline_over_cap":
        for interval in base["baseline_profile"]["intervals"]:
            interval["demand_kw"] = 0.6
    elif case == "single_slot_window_cap_conflict":
        base["baseline_profile"]["intervals"][16]["demand_kw"] = 0.6
    return SchedulingRequestV1.model_validate(base)


def run_optimizer_for_robustness(
    request: SchedulingRequestV1,
    prices: list[float],
    optimizer: Callable[[SchedulingRequestV1, list[float]], OptimizationResult] = (
        optimize_schedule_v1
    ),
) -> tuple[OptimizationResult | None, str | None]:
    try:
        return optimizer(request, prices), None
    except RuntimeError as exc:
        return None, f"{type(exc).__name__}: {exc}"


def run_robustness_cases() -> pd.DataFrame:
    flat_prices = [0.24] * 48
    robust_rows: list[dict[str, Any]] = []
    for case in (
        "single_slot_window_cap_conflict",
        "power_cap_conflict",
        "baseline_over_cap",
        "greedy_suboptimal",
    ):
        request = _robustness_request(case)
        prices = (
            [0.24] * 16 + [0.10, 10.0] + [0.24] * 30 if case == "greedy_suboptimal" else flat_prices
        )
        result, error = run_optimizer_for_robustness(request, prices)
        if result is None:
            robust_rows.append(
                {
                    "case": case,
                    "status": "solver_error",
                    "error_type": error.split(":", maxsplit=1)[0] if error else None,
                    "error_message": error,
                    "candidate_energy_cost_aud": None,
                    "greedy_energy_cost_aud": None,
                    "greedy_energy_cost_gap_aud": None,
                }
            )
            continue
        candidate = result.candidate_schedule
        reference = result.reference_schedule
        energy_cost_gap = (
            candidate.total_cost_aud - reference.total_cost_aud
            if candidate is not None
            and reference.status == "feasible"
            and reference.total_cost_aud is not None
            else None
        )
        robust_rows.append(
            {
                "case": case,
                "status": result.status.value,
                "error_type": None,
                "error_message": None,
                "candidate_status": candidate.status if candidate is not None else None,
                "greedy_status": reference.status,
                "candidate_energy_cost_aud": (
                    candidate.total_cost_aud if candidate is not None else None
                ),
                "greedy_energy_cost_aud": reference.total_cost_aud,
                "greedy_energy_cost_gap_aud": energy_cost_gap,
            }
        )

    def injected_solver_failure(*args, **kwargs):
        raise RuntimeError("Injected solver failure for fault-containment test")

    failed_request = _robustness_request("greedy_suboptimal")
    failed_result, error = run_optimizer_for_robustness(
        failed_request,
        [0.24] * 48,
        optimizer=injected_solver_failure,
    )
    if failed_result is None:
        robust_rows.append(
            {
                "case": "injected_solver_failure",
                "status": "solver_error",
                "error_type": error.split(":", maxsplit=1)[0] if error else None,
                "error_message": error,
                "candidate_energy_cost_aud": None,
                "greedy_energy_cost_aud": None,
                "greedy_energy_cost_gap_aud": None,
            }
        )
    return pd.DataFrame(robust_rows)


def run_equity_boundary_cases() -> pd.DataFrame:
    """Run bounded synthetic cases for fixed windows and sub-penalty benefits."""
    starts = [
        datetime.combine(SIMULATION_DATE, datetime_time.min, tzinfo=ZoneInfo(TIMEZONE))
        + timedelta(minutes=INTERVAL_MINUTES * slot)
        for slot in range(48)
    ]
    fixed_payload = _robustness_request("single_slot_window_cap_conflict").model_dump(mode="json")
    fixed_payload["household_power_limit_kw"] = 2.0
    fixed_request = SchedulingRequestV1.model_validate(fixed_payload)
    fixed_prices = _tariff_profile(1.0).tolist()
    fixed_result = optimize_schedule_v1(fixed_request, fixed_prices)
    fixed_score = score_assignment(
        fixed_request,
        _assignment(fixed_result.candidate_schedule),
        fixed_prices,
    )
    fixed_reference = score_assignment(
        fixed_request,
        {task.task_id: task.preferred_start for task in fixed_request.tasks},
        fixed_prices,
    )

    low_benefit_payload = _robustness_request("single_slot_window_cap_conflict").model_dump(
        mode="json"
    )
    low_benefit_payload["household_power_limit_kw"] = 2.0
    low_benefit_payload["baseline_profile"]["intervals"] = [
        {**interval, "demand_kw": 0.0}
        for interval in low_benefit_payload["baseline_profile"]["intervals"]
    ]
    low_benefit_payload["tasks"][0].update(
        {
            "earliest_start": starts[16].isoformat(),
            "deadline": starts[18].isoformat(),
            "preferred_start": starts[17].isoformat(),
        }
    )
    low_benefit_request = SchedulingRequestV1.model_validate(low_benefit_payload)
    low_benefit_prices = [0.24] * 48
    low_benefit_prices[16] = 0.23
    low_benefit_result = optimize_schedule_v1(low_benefit_request, low_benefit_prices)
    low_benefit_assignment = _assignment(low_benefit_result.candidate_schedule)
    low_benefit_score = score_assignment(
        low_benefit_request, low_benefit_assignment, low_benefit_prices
    )
    low_benefit_reference = score_assignment(
        low_benefit_request,
        {task.task_id: task.preferred_start for task in low_benefit_request.tasks},
        low_benefit_prices,
    )
    alternate_assignment = {low_benefit_request.tasks[0].task_id: starts[16]}
    alternate_score = score_assignment(
        low_benefit_request, alternate_assignment, low_benefit_prices
    )

    return pd.DataFrame(
        [
            {
                "case": "zero_flexibility_fixed_mandatory_task",
                "status": fixed_result.status.value,
                "feasible": fixed_score.feasible,
                "available_shift_benefit_aud": 0.0,
                "available_shift_inconvenience_penalty_aud": 0.0,
                "realized_energy_saving_vs_preferred_aud": round(
                    fixed_reference.cost_aud - fixed_score.cost_aud, 8
                ),
                "inconvenience_penalty_aud": fixed_score.inconvenience_penalty_aud,
                "weighted_objective_change_vs_preferred_aud": round(
                    fixed_score.combined_objective_aud - fixed_reference.combined_objective_aud,
                    8,
                ),
                "interpretation": (
                    "One feasible mandatory task has a single allowed start; it cannot shift."
                ),
            },
            {
                "case": "benefit_below_inconvenience_penalty",
                "status": low_benefit_result.status.value,
                "feasible": low_benefit_score.feasible,
                "available_shift_benefit_aud": round(
                    low_benefit_reference.cost_aud - alternate_score.cost_aud, 8
                ),
                "available_shift_inconvenience_penalty_aud": (
                    alternate_score.inconvenience_penalty_aud
                ),
                "realized_energy_saving_vs_preferred_aud": round(
                    low_benefit_reference.cost_aud - low_benefit_score.cost_aud, 8
                ),
                "inconvenience_penalty_aud": low_benefit_score.inconvenience_penalty_aud,
                "weighted_objective_change_vs_preferred_aud": round(
                    low_benefit_score.combined_objective_aud
                    - low_benefit_reference.combined_objective_aud,
                    8,
                ),
                "interpretation": (
                    "A 0.005 AUD possible energy-charge reduction is below the 0.01 AUD "
                    "one-interval preference penalty; MILP retains the preferred start."
                ),
            },
            {
                "case": "appliance_unavailable",
                "status": "not_representable",
                "feasible": None,
                "available_shift_benefit_aud": None,
                "available_shift_inconvenience_penalty_aud": None,
                "realized_energy_saving_vs_preferred_aud": None,
                "inconvenience_penalty_aud": None,
                "weighted_objective_change_vs_preferred_aud": None,
                "interpretation": (
                    "The v1 request requires at least one task and has no appliance availability "
                    "field; unavailable appliances are not simulated as eligible tasks."
                ),
            },
        ]
    )


def run_experiment(
    output_dir: Path,
    design: ExperimentDesign = ExperimentDesign(),
) -> dict[str, Path]:
    if design.household_count < 1:
        raise ValueError("household_count must be positive")
    if not design.flexibility_hours or any(value < 0 for value in design.flexibility_hours):
        raise ValueError("flexibility_hours must contain nonnegative values")
    if not design.forecast_error_spread_fractions or any(
        value < 0 for value in design.forecast_error_spread_fractions
    ):
        raise ValueError("Forecast error fractions must be nonnegative")
    output_dir.mkdir(parents=True, exist_ok=True)

    household_profiles: list[np.ndarray] = []
    for household_index in range(design.household_count):
        profile_rng = np.random.default_rng(design.seed + household_index * 1009)
        household_profiles.append(_make_baseline(household_index, profile_rng))

    rows: list[dict[str, Any]] = []
    price_rows: list[dict[str, Any]] = []
    task_schedule_rows: list[dict[str, Any]] = []
    total_cases = (
        design.household_count
        * len(design.flexibility_hours)
        * len(design.forecast_error_spread_fractions)
        * len(design.appliance_mixes)
        * len(design.tariff_spread_factors)
    )
    case_index = 0
    for flexibility_hours in design.flexibility_hours:
        for forecast_error_fraction in design.forecast_error_spread_fractions:
            for mix in design.appliance_mixes:
                for spread_factor in design.tariff_spread_factors:
                    case_key = _scenario_key(
                        flexibility_hours, forecast_error_fraction, mix, spread_factor
                    )
                    nominal_prices = _tariff_profile(spread_factor)
                    for household_index, baseline in enumerate(household_profiles):
                        case_index += 1
                        scenario_id = f"{case_key}_household-{household_index + 1}"
                        request = _make_request(
                            household_index,
                            scenario_id,
                            flexibility_hours,
                            mix,
                            baseline,
                            seed=design.seed,
                        )
                        spread_seed = int(spread_factor * 1000)
                        actual_rng = np.random.default_rng(
                            np.random.SeedSequence(
                                [design.seed, household_index, spread_seed, 8123]
                            )
                        )
                        forecast_rng = np.random.default_rng(
                            np.random.SeedSequence([design.seed, household_index, spread_seed, 991])
                        )
                        actual_noise = actual_rng.normal(0.0, 0.025 * spread_factor, size=48)
                        realized_prices = np.maximum(0.01, nominal_prices + actual_noise)
                        forecast_sigma = 0.25 * forecast_error_fraction * spread_factor
                        forecast_prices = np.maximum(
                            0.01,
                            realized_prices + forecast_rng.normal(0.0, forecast_sigma, size=48),
                        )
                        household_id = f"synthetic-household-{household_index + 1:02d}"
                        for interval_index, interval in enumerate(
                            request.baseline_profile.intervals
                        ):
                            price_rows.append(
                                {
                                    "scenario_key": case_key,
                                    "household_id": household_id,
                                    "profile_source": "synthetic",
                                    "interval_index": interval_index,
                                    "interval_start": interval.interval_start.isoformat(),
                                    "baseline_demand_kw": interval.demand_kw,
                                    "nominal_tariff_aud_per_kwh": nominal_prices[interval_index],
                                    "realized_price_aud_per_kwh": realized_prices[interval_index],
                                    "forecast_price_aud_per_kwh": forecast_prices[interval_index],
                                }
                            )

                        assignments: dict[str, tuple[dict[str, datetime | None], str, float]] = {}
                        preferred = {task.task_id: task.preferred_start for task in request.tasks}
                        assignments["S0_no_intervention"] = (preferred, "not_run", 0.0)

                        started = time.perf_counter()
                        nominal_result = optimize_schedule_v1(request, nominal_prices.tolist())
                        nominal_runtime = (time.perf_counter() - started) * 1000
                        greedy_schedule = nominal_result.reference_schedule
                        assignments["S1_greedy_nominal"] = (
                            _assignment(greedy_schedule)
                            if greedy_schedule.status == "feasible"
                            else {},
                            greedy_schedule.status,
                            nominal_runtime,
                        )
                        assignments["S2_milp_nominal"] = (
                            _assignment(nominal_result.candidate_schedule)
                            if nominal_result.candidate_schedule is not None
                            else {},
                            nominal_result.status.value,
                            nominal_runtime,
                        )

                        started = time.perf_counter()
                        forecast_result = optimize_schedule_v1(request, forecast_prices.tolist())
                        forecast_runtime = (time.perf_counter() - started) * 1000
                        assignments["S2_milp_forecast"] = (
                            _assignment(forecast_result.candidate_schedule)
                            if forecast_result.candidate_schedule is not None
                            else {},
                            forecast_result.status.value,
                            forecast_runtime,
                        )

                        started = time.perf_counter()
                        perfect_info_result = optimize_schedule_v1(
                            request, realized_prices.tolist()
                        )
                        perfect_info_runtime = (time.perf_counter() - started) * 1000
                        assignments["oracle_milp_perfect_information"] = (
                            _assignment(perfect_info_result.candidate_schedule)
                            if perfect_info_result.candidate_schedule is not None
                            else {},
                            perfect_info_result.status.value,
                            perfect_info_runtime,
                        )

                        energy_only_payload = request.model_dump(mode="json")
                        energy_only_payload["preference_penalty_aud_per_interval"] = 0.0
                        energy_only_request = SchedulingRequestV1.model_validate(
                            energy_only_payload
                        )
                        started = time.perf_counter()
                        energy_only_result = optimize_schedule_v1(
                            energy_only_request, realized_prices.tolist()
                        )
                        energy_only_runtime = (time.perf_counter() - started) * 1000
                        assignments["oracle_milp_energy_only"] = (
                            _assignment(energy_only_result.candidate_schedule)
                            if energy_only_result.candidate_schedule is not None
                            else {},
                            energy_only_result.status.value,
                            energy_only_runtime,
                        )

                        scores = {
                            name: score_assignment(request, values[0], realized_prices.tolist())
                            for name, values in assignments.items()
                        }
                        s0_cost = scores["S0_no_intervention"].cost_aud
                        if s0_cost is None:
                            raise RuntimeError("The S0 preferred schedule must be feasible")
                        for strategy in STRATEGIES:
                            assignment_value = assignments[strategy]
                            assigned_tasks = assignment_value[0]
                            for task in request.tasks:
                                task_start = assigned_tasks.get(task.task_id)
                                task_schedule_rows.append(
                                    {
                                        "scenario_key": case_key,
                                        "household_id": household_id,
                                        "strategy": strategy,
                                        "task_id": task.task_id,
                                        "appliance": task.appliance,
                                        "rated_power_kw": task.rated_power_kw,
                                        "energy_kwh": task.energy_kwh,
                                        "duration_minutes": task.duration_minutes,
                                        "start": (
                                            task_start.isoformat()
                                            if task_start is not None
                                            else None
                                        ),
                                        "optimizer_status": assignment_value[1],
                                    }
                                )
                            rows.append(
                                _strategy_result_row(
                                    scenario_key=case_key,
                                    household_id=household_id,
                                    mix=mix,
                                    flexibility_hours=flexibility_hours,
                                    forecast_error_fraction=forecast_error_fraction,
                                    spread_factor=spread_factor,
                                    strategy=strategy,
                                    score=scores[strategy],
                                    runtime_ms=assignment_value[2],
                                    s0_cost_aud=s0_cost,
                                    optimizer_status=assignment_value[1],
                                    seed=design.seed,
                                )
                            )

    results = pd.DataFrame(rows)
    case_keys = ["scenario_key", "household_id"]
    s0_objectives = results.loc[
        results["strategy"] == "S0_no_intervention",
        [*case_keys, "combined_objective_aud"],
    ].rename(columns={"combined_objective_aud": "s0_reference_objective_aud"})
    results = results.merge(s0_objectives, on=case_keys, validate="many_to_one")
    results["weighted_objective_change_vs_s0_aud"] = (
        results["combined_objective_aud"] - results["s0_reference_objective_aud"]
    )
    results = results.drop(columns=["s0_reference_objective_aud"])
    interval_price_frame = pd.DataFrame(price_rows)
    task_schedule_frame = pd.DataFrame(task_schedule_rows)
    summary = summarize_results(results)
    paired, paired_summary = paired_comparisons(results)
    equity_summary = summarize_equity(results)
    equity_flexibility = flexibility_equity_sensitivity(results)
    equity_provenance = equity_provenance_ledger()
    robustness = run_robustness_cases()
    equity_boundary_cases = run_equity_boundary_cases()
    detail_path = output_dir / "results.csv"
    summary_path = output_dir / "summary.csv"
    paired_path = output_dir / "paired_comparisons.csv"
    paired_summary_path = output_dir / "paired_summary.csv"
    equity_summary_path = output_dir / "equity_summary.csv"
    equity_flexibility_path = output_dir / "equity_flexibility_sensitivity.csv"
    equity_provenance_path = output_dir / "equity_provenance.csv"
    equity_boundary_cases_path = output_dir / "equity_boundary_cases.csv"
    robustness_path = output_dir / "robustness.csv"
    prices_path = output_dir / "interval_prices.csv"
    task_schedules_path = output_dir / "task_schedules.csv"
    config_path = output_dir / "config.json"
    paired_plot_path = output_dir / "paired_s1_s2.png"
    ablation_plot_path = output_dir / "flexibility_forecast_error.png"
    tradeoff_plot_path = output_dir / "cost_inconvenience.png"
    equity_distribution_plot_path = output_dir / "equity_savings_distribution.png"
    report_path = output_dir / "REPORT.md"
    results.to_csv(detail_path, index=False)
    summary.to_csv(summary_path, index=False)
    paired.to_csv(paired_path, index=False)
    paired_summary.to_csv(paired_summary_path, index=False)
    equity_summary.to_csv(equity_summary_path, index=False)
    equity_flexibility.to_csv(equity_flexibility_path, index=False)
    equity_provenance.to_csv(equity_provenance_path, index=False)
    equity_boundary_cases.to_csv(equity_boundary_cases_path, index=False)
    robustness.to_csv(robustness_path, index=False)
    interval_price_frame.to_csv(prices_path, index=False)
    task_schedule_frame.to_csv(task_schedules_path, index=False)
    audit_billing_reconciliation(
        pd.read_csv(detail_path),
        pd.read_csv(prices_path),
        pd.read_csv(task_schedules_path),
    )
    config = {
        "experiment": "synthetic_scheduling_strategy_comparison",
        "design": asdict(design),
        "strategies": {
            "S0_no_intervention": "Run each task at its original preferred start.",
            "S1_greedy_nominal": (
                "Existing deterministic greedy reference, using the nominal tariff."
            ),
            "S2_milp_nominal": ("Existing MILP, using the identical nominal tariff as S1."),
            "S2_milp_forecast": (
                "Existing MILP, using a noisy forecast of future realized interval prices."
            ),
            "oracle_milp_perfect_information": (
                "Existing MILP with realized prices, optimizing energy charge plus inconvenience."
            ),
            "oracle_milp_energy_only": (
                "Existing MILP with realized prices and the preference penalty set to zero."
            ),
        },
        "synthetic_assumptions": {
            "households": design.household_count,
            "household_profiles": (
                f"Generated synthetic profiles; the same {design.household_count} profiles "
                f"are reused across {total_cases} factorial cells and are not independent "
                "household observations."
            ),
            "tariff": (
                "Stylized synthetic AUD energy-only TOU schedule; not observed Australian "
                "retail prices."
            ),
            "scheduling_time_information": (
                "Nominal time-of-use periods and the price shape are assumed known when "
                "planning. S1 and S2_milp_nominal receive identical nominal prices."
            ),
            "realized_price_noise_sd_aud_per_kwh": (
                "0.025 * tariff_spread_factor; zero-mean sensitivity assumption, not calibrated "
                "to observed retail price deviations."
            ),
            "forecast_error_sd_aud_per_kwh": (
                "0.25 * forecast_error_spread_fraction * tariff_spread_factor; an uncalibrated "
                "stress sensitivity, not a validated forecast distribution."
            ),
            "forecast_generation": (
                "Realized synthetic price plus an independent Gaussian forecast-error perturbation."
            ),
            "price_floor_aud_per_kwh": 0.01,
            "price_assumption_rationale": (
                "Chosen to expose sensitivity to uncertainty and tariff spread only; not claimed "
                "to be representative of Australian retail tariffs or forecast errors."
            ),
            "appliance_profiles": "Fixed power and duration task assumptions in source.",
            "household_power_limit_kw": HOUSEHOLD_POWER_LIMIT_KW,
            "preference_penalty_aud_per_interval": PREFERENCE_PENALTY_AUD_PER_INTERVAL,
            "weighted_objective": (
                "realized energy charge AUD + preference_penalty_aud_per_interval times "
                "absolute start-time distance in scheduling intervals"
            ),
            "baseline_energy_cost_aud_compatibility": (
                "Deprecated alias for non_flexible_baseline_energy_cost_aud; not complete S0."
            ),
            "s0_reference_energy_cost_aud": "Complete realized energy charge at preferred starts.",
            "equity_metric_definitions": EQUITY_METRIC_DEFINITIONS,
            "equity_grouping": (
                "Synthetic flexibility-hours and appliance-mix categories only; no demographic "
                "inference or measured DER categories."
            ),
            "numerical_tolerance_aud": NUMERICAL_TOLERANCE_AUD,
            "simulation_date": SIMULATION_DATE.isoformat(),
            "timezone": TIMEZONE,
            "interval_minutes": INTERVAL_MINUTES,
            "solver": f"SciPy {scipy.__version__} milp (HiGHS backend)",
            "numpy_version": np.__version__,
            "platform": platform.platform(),
        },
        "case_count": total_cases,
        "result_rows": len(results),
        "paired_comparison_rows": len(paired),
        "paired_summary_rows": len(paired_summary),
        "equity_summary_rows": len(equity_summary),
        "equity_flexibility_sensitivity_rows": len(equity_flexibility),
        "equity_provenance_rows": len(equity_provenance),
        "equity_boundary_case_rows": len(equity_boundary_cases),
        "robustness_rows": len(robustness),
        "interval_price_rows": len(price_rows),
        "task_schedule_rows": len(task_schedule_rows),
        "seed": design.seed,
    }
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    plot_paired_comparisons(paired, paired_plot_path)
    plot_factorial_ablations(results, ablation_plot_path)
    plot_cost_inconvenience(results, tradeoff_plot_path)
    plot_equity_savings_distribution(results, equity_distribution_plot_path)
    write_experiment_report(
        report_path,
        results,
        paired_summary,
        robustness,
        config,
        equity_summary,
        equity_flexibility,
        equity_provenance,
        equity_boundary_cases,
    )
    return {
        "results": detail_path,
        "summary": summary_path,
        "paired_comparisons": paired_path,
        "paired_summary": paired_summary_path,
        "equity_summary": equity_summary_path,
        "equity_flexibility_sensitivity": equity_flexibility_path,
        "equity_provenance": equity_provenance_path,
        "equity_boundary_cases": equity_boundary_cases_path,
        "robustness": robustness_path,
        "equity_distribution_plot": equity_distribution_plot_path,
        "interval_prices": prices_path,
        "task_schedules": task_schedules_path,
        "config": config_path,
        "paired_plot": paired_plot_path,
        "ablation_plot": ablation_plot_path,
        "tradeoff_plot": tradeoff_plot_path,
        "report": report_path,
    }


def summarize_results(results: pd.DataFrame) -> pd.DataFrame:
    group_columns = [
        "scenario_key",
        "appliance_mix",
        "flexibility_hours",
        "forecast_error_spread_fraction",
        "tariff_spread_factor",
        "strategy",
    ]
    rows = []
    for keys, group in results.groupby(group_columns, sort=True, dropna=False):
        rows.append(
            {
                **dict(zip(group_columns, keys, strict=True)),
                "households": group["household_id"].nunique(),
                "mean_realized_energy_cost_aud": group["realized_energy_cost_aud"].mean(),
                "mean_savings_vs_s0_aud": group["savings_vs_s0_aud"].mean(),
                "mean_savings_vs_s0_percent": group["savings_vs_s0_percent"].mean(),
                "median_savings_vs_s0_aud": group["savings_vs_s0_aud"].median(),
                "mean_peak_demand_kw": group["peak_demand_kw"].mean(),
                "mean_task_completion_fraction": group["task_completion_fraction"].mean(),
                "mean_inconvenience_hours": group["inconvenience_hours"].mean(),
                "mean_inconvenience_penalty_aud": group["inconvenience_penalty_aud"].mean(),
                "mean_combined_objective_aud": group["combined_objective_aud"].mean(),
                "infeasible_households": int((~group["feasible"]).sum()),
                "mean_runtime_ms": group["runtime_ms"].mean(),
            }
        )
    return pd.DataFrame(rows)


def summarize_equity(results: pd.DataFrame) -> pd.DataFrame:
    """Summarize synthetic benefit and actionability by supported scenario categories."""
    strategy_results = results.loc[results["strategy"].isin(EQUITY_STRATEGIES)].copy()
    if strategy_results.empty:
        return pd.DataFrame(
            columns=[
                "group_axis",
                "group_label",
                "strategy",
                "scenario_cells",
                "distinct_generated_profiles",
                "technically_eligible_cells",
                "technically_incomplete_or_infeasible_cells",
                "technical_non_completion_rate",
                "no_actionable_recommendation_cells",
                "no_actionable_recommendation_rate",
                "mean_profile_energy_charge_aud",
                "profile_energy_charge_p10_aud",
                "profile_energy_charge_p90_aud",
                "mean_profile_savings_vs_s0_aud",
                "profile_savings_p10_aud",
                "profile_savings_p90_aud",
                "profile_savings_95pct_ci_low_aud",
                "profile_savings_95pct_ci_high_aud",
                "mean_profile_inconvenience_hours",
                "profile_inconvenience_p10_hours",
                "profile_inconvenience_p90_hours",
                "mean_profile_weighted_objective_change_vs_s0_aud",
                "profile_objective_change_p10_aud",
                "profile_objective_change_p90_aud",
            ]
        )

    definitions = (
        ("flexibility_hours", "flexibility_hours"),
        ("appliance_mix", "appliance_mix"),
    )
    rows: list[dict[str, Any]] = []
    for group_axis, column in definitions:
        for (group_label, strategy), group in strategy_results.groupby(
            [column, "strategy"], sort=True
        ):
            by_profile = group.groupby("household_id", sort=True).agg(
                energy_charge=("realized_energy_cost_aud", "mean"),
                savings=("savings_vs_s0_aud", "mean"),
                inconvenience=("inconvenience_hours", "mean"),
                objective_change=("weighted_objective_change_vs_s0_aud", "mean"),
            )
            profile_energy = by_profile["energy_charge"].dropna()
            profile_savings = by_profile["savings"].dropna()
            profile_count = len(profile_savings)
            savings_mean = float(profile_savings.mean()) if profile_count else float("nan")
            if profile_count > 1:
                half_width = float(stats.t.ppf(0.975, profile_count - 1)) * float(
                    stats.sem(profile_savings)
                )
            else:
                half_width = float("nan")
            technically_complete = group["feasible"] & (
                group["task_completion_fraction"] >= 1.0 - 1e-12
            )
            input_cases = group[["scenario_key", "household_id"]].drop_duplicates()
            rows.append(
                {
                    "group_axis": group_axis,
                    "group_label": str(group_label),
                    "strategy": strategy,
                    "scenario_cells": len(group),
                    "distinct_generated_profiles": group["household_id"].nunique(),
                    "technically_eligible_cells": len(input_cases),
                    "technically_incomplete_or_infeasible_cells": int(
                        (~technically_complete).sum()
                    ),
                    "technical_non_completion_rate": (
                        float((~technically_complete).mean())
                        if len(technically_complete)
                        else float("nan")
                    ),
                    "no_actionable_recommendation_cells": int((~technically_complete).sum()),
                    "no_actionable_recommendation_rate": (
                        float((~technically_complete).mean())
                        if len(technically_complete)
                        else float("nan")
                    ),
                    "mean_profile_energy_charge_aud": float(profile_energy.mean()),
                    "profile_energy_charge_p10_aud": float(profile_energy.quantile(0.10)),
                    "profile_energy_charge_p90_aud": float(profile_energy.quantile(0.90)),
                    "mean_profile_savings_vs_s0_aud": savings_mean,
                    "profile_savings_p10_aud": (
                        float(profile_savings.quantile(0.10)) if profile_count else float("nan")
                    ),
                    "profile_savings_p90_aud": (
                        float(profile_savings.quantile(0.90)) if profile_count else float("nan")
                    ),
                    "profile_savings_95pct_ci_low_aud": savings_mean - half_width,
                    "profile_savings_95pct_ci_high_aud": savings_mean + half_width,
                    "mean_profile_inconvenience_hours": float(by_profile["inconvenience"].mean()),
                    "profile_inconvenience_p10_hours": float(
                        by_profile["inconvenience"].quantile(0.10)
                    ),
                    "profile_inconvenience_p90_hours": float(
                        by_profile["inconvenience"].quantile(0.90)
                    ),
                    "mean_profile_weighted_objective_change_vs_s0_aud": float(
                        by_profile["objective_change"].mean()
                    ),
                    "profile_objective_change_p10_aud": float(
                        by_profile["objective_change"].quantile(0.10)
                    ),
                    "profile_objective_change_p90_aud": float(
                        by_profile["objective_change"].quantile(0.90)
                    ),
                }
            )
    return pd.DataFrame(rows)


def flexibility_equity_sensitivity(results: pd.DataFrame) -> pd.DataFrame:
    """Compare two-hour flexibility with wider windows on matched synthetic profiles."""
    columns = [
        "strategy",
        "comparison",
        "matched_scenario_cells",
        "distinct_generated_profiles",
        "mean_profile_savings_difference_aud",
        "profile_savings_difference_95pct_ci_low_aud",
        "profile_savings_difference_95pct_ci_high_aud",
        "limited_flexibility_lower_savings_cells",
        "limited_flexibility_higher_savings_cells",
        "tied_savings_cells",
        "technically_incomplete_or_infeasible_at_limited_flexibility_cells",
        "technically_incomplete_or_infeasible_at_comparator_flexibility_cells",
        "no_actionable_at_limited_flexibility_cells",
        "no_actionable_at_comparator_flexibility_cells",
        "mean_profile_inconvenience_difference_hours",
        "flat_tariff_tied_cells",
        "flat_tariff_comparison_cells",
        "variable_tariff_tied_cells",
        "variable_tariff_comparison_cells",
    ]
    flex_levels = sorted(results["flexibility_hours"].unique())
    if 2 not in flex_levels or len(flex_levels) < 2:
        return pd.DataFrame(columns=columns)

    strategies = results.loc[results["strategy"].isin(EQUITY_STRATEGIES)]
    match_keys = [
        "household_id",
        "forecast_error_spread_fraction",
        "appliance_mix",
        "tariff_spread_factor",
        "strategy",
    ]
    measures = [
        "savings_vs_s0_aud",
        "inconvenience_hours",
        "feasible",
        "task_completion_fraction",
    ]
    rows: list[dict[str, Any]] = []
    for comparator in flex_levels:
        if comparator <= 2:
            continue
        paired = strategies.loc[
            strategies["flexibility_hours"].isin([2, comparator]),
            [*match_keys, "flexibility_hours", *measures],
        ].pivot(index=match_keys, columns="flexibility_hours", values=measures)
        if (2 not in paired.columns.get_level_values(1)) or (
            comparator not in paired.columns.get_level_values(1)
        ):
            continue
        for strategy in EQUITY_STRATEGIES:
            subset = paired.xs(strategy, level="strategy")
            savings_difference = (
                subset[("savings_vs_s0_aud", 2)] - subset[("savings_vs_s0_aud", comparator)]
            ).dropna()
            spread_values = savings_difference.index.get_level_values("tariff_spread_factor")
            tied = savings_difference.abs() <= NUMERICAL_TOLERANCE_AUD
            flat_tariff = spread_values == 0
            variable_tariff = spread_values > 0
            inconvenience_difference = (
                subset[("inconvenience_hours", 2)] - subset[("inconvenience_hours", comparator)]
            ).dropna()
            profile_means = savings_difference.groupby(level="household_id").mean()
            profile_count = len(profile_means)
            mean_difference = float(profile_means.mean()) if profile_count else float("nan")
            if profile_count > 1:
                half_width = float(stats.t.ppf(0.975, profile_count - 1)) * float(
                    stats.sem(profile_means)
                )
            else:
                half_width = float("nan")
            no_action_limited = ~(
                subset[("feasible", 2)] & (subset[("task_completion_fraction", 2)] >= 1.0 - 1e-12)
            )
            no_action_comparator = ~(
                subset[("feasible", comparator)]
                & (subset[("task_completion_fraction", comparator)] >= 1.0 - 1e-12)
            )
            rows.append(
                {
                    "strategy": strategy,
                    "comparison": f"2h_minus_{comparator}h",
                    "matched_scenario_cells": len(savings_difference),
                    "distinct_generated_profiles": profile_count,
                    "mean_profile_savings_difference_aud": mean_difference,
                    "profile_savings_difference_95pct_ci_low_aud": (mean_difference - half_width),
                    "profile_savings_difference_95pct_ci_high_aud": (mean_difference + half_width),
                    "limited_flexibility_lower_savings_cells": int(
                        (savings_difference < -NUMERICAL_TOLERANCE_AUD).sum()
                    ),
                    "limited_flexibility_higher_savings_cells": int(
                        (savings_difference > NUMERICAL_TOLERANCE_AUD).sum()
                    ),
                    "tied_savings_cells": int(
                        (savings_difference.abs() <= NUMERICAL_TOLERANCE_AUD).sum()
                    ),
                    "technically_incomplete_or_infeasible_at_limited_flexibility_cells": int(
                        no_action_limited.sum()
                    ),
                    "technically_incomplete_or_infeasible_at_comparator_flexibility_cells": int(
                        no_action_comparator.sum()
                    ),
                    "no_actionable_at_limited_flexibility_cells": int(no_action_limited.sum()),
                    "no_actionable_at_comparator_flexibility_cells": int(
                        no_action_comparator.sum()
                    ),
                    "mean_profile_inconvenience_difference_hours": float(
                        inconvenience_difference.groupby(level="household_id").mean().mean()
                    ),
                    "flat_tariff_tied_cells": int((tied & flat_tariff).sum()),
                    "flat_tariff_comparison_cells": int(flat_tariff.sum()),
                    "variable_tariff_tied_cells": int((tied & variable_tariff).sum()),
                    "variable_tariff_comparison_cells": int(variable_tariff.sum()),
                }
            )
    return pd.DataFrame(rows, columns=columns)


def equity_provenance_ledger() -> pd.DataFrame:
    """Record provenance and unsupported equity dimensions for generated metrics."""
    entries = [
        (
            "software_access",
            "Not measured",
            EQUITY_METRIC_DEFINITIONS["software_access"],
            "No account, device, connectivity, uptake, or accessibility audit data.",
        ),
        (
            "technical_input_eligibility",
            "Generated scheduling requests and interval traces",
            "Count unique synthetic household/scenario inputs that passed request validation.",
            "Pipeline eligibility does not establish a person's ability to use the "
            "advisory service.",
        ),
        (
            "technical_feasibility_and_completion",
            "feasible, task_completion_fraction",
            EQUITY_METRIC_DEFINITIONS["actionability"],
            "A technical result only; it is not user acceptance, practical actionability, or "
            "device execution.",
        ),
        (
            "economic_worth",
            "savings_vs_s0_aud and weighted objective",
            "Not classified; no minimum acceptable benefit or welfare threshold is declared.",
            "A modeled cost reduction does not establish that shifting is worthwhile to a user.",
        ),
        (
            "practical_actionability_and_acceptance",
            "Not measured",
            "No user confirmation, acceptance, access, or ability-to-act observations.",
            "Technical feasibility does not establish practical actionability or adoption.",
        ),
        (
            "device_execution",
            "Not measured",
            "The experiment does not dispatch devices or verify task completion in a home.",
            "No device execution telemetry is included.",
        ),
        (
            "benefit_distribution",
            "savings_vs_s0_aud, inconvenience_hours, weighted objective",
            EQUITY_METRIC_DEFINITIONS["benefit"],
            "AUD values are modeled energy-charge differences, not complete bills or "
            "verified savings.",
        ),
        (
            "scenario_group_labels",
            "flexibility_hours, appliance_mix",
            EQUITY_METRIC_DEFINITIONS["group_labels"],
            "Synthetic design labels only; they do not represent protected or "
            "socioeconomic groups.",
        ),
        (
            "demographic_groups",
            "Not available",
            "No real demographic group labels are used.",
            "No consented demographic data, collection purpose, or provenance "
            "documentation exists.",
        ),
        (
            "der_comparison",
            "Not available",
            EQUITY_METRIC_DEFINITIONS["der_comparison"],
            "No PV/BESS/generation/DER ownership fields; EV is modeled as a flexible load.",
        ),
    ]
    return pd.DataFrame(
        entries,
        columns=[
            "metric",
            "source_fields",
            "definition",
            "scope_and_limitations",
        ],
    )


def plot_equity_savings_distribution(results: pd.DataFrame, output_path: Path) -> None:
    """Plot nominal-MILP profile means by flexibility and tariff-spread scenario."""
    spread_levels = sorted(results["tariff_spread_factor"].unique())
    flexibility_levels = sorted(results["flexibility_hours"].unique())
    figure, axes = plt.subplots(
        1, len(spread_levels), figsize=(6.2 * len(spread_levels), 4.8), squeeze=False
    )
    for axis, spread in zip(axes[0], spread_levels, strict=True):
        subset = results.loc[
            (results["strategy"] == "S2_milp_nominal") & (results["tariff_spread_factor"] == spread)
        ]
        profile_means = subset.groupby(["flexibility_hours", "household_id"], sort=True)[
            "savings_vs_s0_aud"
        ].mean()
        distributions = [
            profile_means.xs(flexibility, level="flexibility_hours").to_numpy(dtype=float)
            for flexibility in flexibility_levels
        ]
        axis.boxplot(
            distributions,
            positions=np.arange(1, len(flexibility_levels) + 1),
            widths=0.45,
            showfliers=False,
            patch_artist=True,
            boxprops={"facecolor": "#93c5fd", "alpha": 0.45},
            medianprops={"color": "#1d4ed8", "linewidth": 1.5},
        )
        for position, values in enumerate(distributions, start=1):
            jitter = np.linspace(-0.06, 0.06, len(values))
            axis.scatter(
                np.full(len(values), position) + jitter,
                values,
                color="#1d4ed8",
                alpha=0.75,
                s=24,
                zorder=3,
            )
        axis.axhline(0, color="black", linewidth=0.8)
        axis.set_xticks(
            np.arange(1, len(flexibility_levels) + 1),
            [str(value) for value in flexibility_levels],
        )
        axis.set_xlabel("Available scheduling flexibility (hours)")
        axis.set_ylabel("Profile-mean modeled charge reduction vs S0 (AUD)")
        axis.set_title("Flat synthetic tariff" if spread == 0 else "TOU synthetic tariff")
        axis.grid(axis="y", alpha=0.25)
    figure.suptitle(
        "Synthetic nominal-MILP profile means; boxes show median and IQR, dots are profiles"
    )
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def plot_paired_comparisons(paired: pd.DataFrame, output_path: Path) -> None:
    matched = paired.loc[paired["comparison"] == "nominal_milp_minus_greedy"]
    profile_count = matched["household_id"].nunique()
    figure, axes = plt.subplots(1, 2, figsize=(11, 5))
    for axis, right_column, left_column, metric in (
        (
            axes[0],
            "right_energy_cost_aud",
            "left_energy_cost_aud",
            "Realized energy charge",
        ),
        (
            axes[1],
            "right_combined_objective_aud",
            "left_combined_objective_aud",
            "Weighted objective",
        ),
    ):
        x_values = matched[right_column].to_numpy(dtype=float)
        y_values = matched[left_column].to_numpy(dtype=float)
        axis.scatter(x_values, y_values, alpha=0.4, s=22, color="#2563eb")
        lower = min(float(x_values.min()), float(y_values.min()))
        upper = max(float(x_values.max()), float(y_values.max()))
        padding = max((upper - lower) * 0.04, 0.01)
        limits = (lower - padding, upper + padding)
        axis.plot(limits, limits, linestyle="--", color="#6b7280", linewidth=1)
        axis.set_xlim(limits)
        axis.set_ylim(limits)
        axis.set_aspect("equal", adjustable="box")
        axis.set_xlabel(f"S1 greedy nominal {metric.lower()} (AUD)")
        axis.set_ylabel(f"S2 MILP nominal {metric.lower()} (AUD)")
        axis.set_title(f"Matched {metric.lower()}")
        axis.grid(alpha=0.25)
    figure.suptitle(
        f"Synthetic paired S1-versus-S2 cases; {profile_count} generated profiles reused"
    )
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def plot_factorial_ablations(results: pd.DataFrame, output_path: Path) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for strategy in (
        "S1_greedy_nominal",
        "S2_milp_nominal",
        "S2_milp_forecast",
        "oracle_milp_perfect_information",
    ):
        subset = results.loc[results["strategy"] == strategy]
        flex = subset.groupby("flexibility_hours")["savings_vs_s0_aud"].mean()
        axes[0].plot(flex.index, flex.values, marker="o", label=strategy)
    axes[0].set_xlabel("Flexibility window (hours)")
    axes[0].set_ylabel("Mean charge reduction vs S0 (AUD)")
    axes[0].set_title("Flexibility sensitivity")
    axes[0].grid(alpha=0.25)
    axes[0].legend(fontsize=7)

    nominal = results.loc[results["strategy"] == "S2_milp_nominal"]
    forecast = results.loc[results["strategy"] == "S2_milp_forecast"]
    for strategy, subset in (("MILP nominal", nominal), ("MILP forecast", forecast)):
        grouped = subset.groupby(["flexibility_hours", "forecast_error_spread_fraction"])[
            "savings_vs_s0_aud"
        ].mean()
        for error_fraction in sorted(subset["forecast_error_spread_fraction"].unique()):
            values = grouped.xs(error_fraction, level="forecast_error_spread_fraction")
            axes[1].plot(
                values.index,
                values.values,
                marker="o",
                label=f"{strategy}; error factor {error_fraction:g}",
            )
    axes[1].set_xlabel("Flexibility window (hours)")
    axes[1].set_ylabel("Mean charge reduction vs S0 (AUD)")
    axes[1].set_title("Forecast-error and flexibility sensitivity")
    axes[1].grid(alpha=0.25)
    axes[1].legend(fontsize=7)
    figure.suptitle("Synthetic factorial averages; descriptive, not population estimates")
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def plot_cost_inconvenience(results: pd.DataFrame, output_path: Path) -> None:
    figure, axis = plt.subplots(figsize=(8, 5))
    markers = ("o", "s", "^", "D", "P", "X")
    for marker, strategy in zip(markers, STRATEGIES, strict=True):
        subset = results.loc[results["strategy"] == strategy]
        axis.scatter(
            subset["realized_energy_cost_aud"],
            subset["inconvenience_hours"],
            label=strategy,
            marker=marker,
            alpha=0.35,
        )
    axis.set_xlabel("Realized synthetic energy charge (AUD)")
    axis.set_ylabel("Absolute start-time shift (hours)")
    axis.set_title("Synthetic case-level cost–inconvenience trade-off")
    axis.grid(alpha=0.25)
    axis.legend(fontsize=7)
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def write_experiment_report(
    report_path: Path,
    results: pd.DataFrame,
    paired_summary: pd.DataFrame,
    robustness: pd.DataFrame,
    config: dict[str, Any],
    equity_summary: pd.DataFrame,
    equity_flexibility: pd.DataFrame,
    equity_provenance: pd.DataFrame,
    equity_boundary_cases: pd.DataFrame,
) -> None:
    strategy_summary = (
        results.groupby("strategy", sort=False)
        .agg(
            rows=("household_id", "count"),
            energy=("realized_energy_cost_aud", "mean"),
            objective=("combined_objective_aud", "mean"),
            change_vs_s0=("savings_vs_s0_aud", "mean"),
            completion=("task_completion_fraction", "mean"),
            peak=("peak_demand_kw", "mean"),
            inconvenience=("inconvenience_hours", "mean"),
            infeasible=("feasible", lambda values: int((~values).sum())),
        )
        .reindex(STRATEGIES)
    )
    flex_ablation = (
        results.groupby(["flexibility_hours", "strategy"])["savings_vs_s0_aud"].mean().unstack()
    )
    error_ablation = (
        results.loc[results["strategy"].isin(["S2_milp_nominal", "S2_milp_forecast"])]
        .groupby(["forecast_error_spread_fraction", "strategy"])["savings_vs_s0_aud"]
        .mean()
        .unstack()
    )
    equity_strategies = set(EQUITY_STRATEGIES)
    equity_flexibility = equity_flexibility.loc[
        equity_flexibility["strategy"].isin(equity_strategies)
    ]
    overall_pairs = paired_summary.loc[paired_summary["factor"] == "overall"]
    factor_pairs = paired_summary.loc[paired_summary["factor"] != "overall"]
    profile_count = config["design"]["household_count"]
    case_count = config["case_count"]
    flexibility_levels = ", ".join(map(str, config["design"]["flexibility_hours"]))
    spread_levels = ", ".join(map(str, config["design"]["tariff_spread_factors"]))
    error_levels = ", ".join(map(str, config["design"]["forecast_error_spread_fractions"]))
    appliance_levels = ", ".join(config["design"]["appliance_mixes"])
    forecast_results = results.loc[results["strategy"] == "S2_milp_forecast"]
    negative_forecast_savings = forecast_results["savings_vs_s0_aud"].dropna()
    negative_forecast_savings = negative_forecast_savings[
        negative_forecast_savings < -NUMERICAL_TOLERANCE_AUD
    ]
    lines = [
        "# Synthetic scheduling strategy experiment",
        "",
        "## Findings and limitations",
        "",
        f"This is a synthetic sensitivity study using {profile_count} generated household profiles "
        f"repeatedly across {case_count} household/configuration cells. It is not measured "
        "customer behavior, an Australian tariff study, or evidence of real bill savings. No "
        "population-level inference is supported.",
        "",
        "## Equity metric definitions (specified before group outcomes)",
        "",
        f"- **Software access:** {EQUITY_METRIC_DEFINITIONS['software_access']}",
        f"- **Actionability:** {EQUITY_METRIC_DEFINITIONS['actionability']}",
        f"- **Benefit distribution:** {EQUITY_METRIC_DEFINITIONS['benefit']} "
        f"{EQUITY_METRIC_DEFINITIONS['inconvenience']}",
        f"- **Permitted groups:** {EQUITY_METRIC_DEFINITIONS['group_labels']}",
        f"- **DER comparison:** {EQUITY_METRIC_DEFINITIONS['der_comparison']}",
        "- Group sizes and descriptive uncertainty use generated-profile means; repeated "
        "factorial cells are not independent households.",
        "",
        "## Strategies and price information",
        "",
        "- **S0:** execute tasks at their preferred starts.",
        "- **S1 greedy nominal:** greedy reference using nominal tariff information.",
        "- **S2 MILP nominal:** MILP using the identical nominal price vector as S1. This matched "
        "comparison separates algorithm differences from price-information effects.",
        "- **S2 MILP forecast:** MILP using noisy future-price estimates; compare with S2 nominal "
        "to isolate forecast-information sensitivity.",
        "- **Perfect-information MILP:** realized prices supplied to MILP, optimizing energy "
        "charge plus the configured inconvenience penalty.",
        "- **Energy-only oracle:** realized prices supplied to MILP with the preference penalty "
        "set to zero; an energy-charge lower bound only within this modeled feasible set.",
        "",
        "The nominal time-of-use schedule and price shape are assumed known at scheduling time. "
        "Realized prices are nominal prices plus Gaussian perturbations drawn with mean zero and "
        "standard deviation $0.025/kWh times the spread factor, before a $0.01/kWh price floor. "
        "Forecast estimates add independent Gaussian perturbations drawn with mean zero and "
        "standard deviation $0.25 times the forecast-error factor times the spread factor, before "
        "the same floor; clipping can shift the resulting deviations away from zero mean. These "
        "uncalibrated stress parameters are not observed Australian retail prices or validated "
        "forecast-error distributions.",
        "",
        "## Design and assumptions",
        "",
        f"- {config['case_count']} household/configuration cells, {len(results)} strategy rows, "
        f"{config['design']['household_count']} fixed generated profiles.",
        f"- Factorial dimensions: flexibility hours [{flexibility_levels}], tariff-spread factors "
        f"[{spread_levels}], forecast-error factors [{error_levels}], and appliance mixes "
        f"[{appliance_levels}]; one synthetic Melbourne day at 30-minute resolution.",
        "- Profiles contain no measured DER, PV, EV ownership, demographics, or customer data. "
        "Tariffs are energy-only; supply/demand charges, tax, export credits, and retailer rules "
        "are excluded.",
        f"- The same {profile_count} generated profile IDs recur. The {case_count} cells are not "
        "independent households. Paired profile-level intervals average repeated cell differences "
        f"within profile before calculating intervals from the {profile_count} profile means.",
        "- The combined objective is realized energy charge plus $0.01 per interval of absolute "
        "start-time displacement. This preference weight is a modeling assumption, not a "
        "validated monetary value of inconvenience.",
        "- `baseline_energy_cost_aud` remains as a compatibility alias for "
        "`non_flexible_baseline_energy_cost_aud`; neither is the complete S0 charge. "
        "`s0_reference_energy_cost_aud` is the complete preferred-start charge.",
        "",
        "## Aggregate descriptive results",
        "",
        "| Strategy | Rows | Energy charge (AUD) | Weighted objective (AUD) | "
        "Change vs S0 (AUD) | Completion | Peak (kW) | Inconvenience (h) | Infeasible |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for strategy, row in strategy_summary.iterrows():
        lines.append(
            f"| {strategy} | {int(row['rows'])} | {row['energy']:.3f} | "
            f"{row['objective']:.3f} | {row['change_vs_s0']:.3f} | "
            f"{row['completion']:.1%} | {row['peak']:.3f} | "
            f"{row['inconvenience']:.2f} | {int(row['infeasible'])} |"
        )
    lines.extend(
        [
            "",
            "## Matched comparisons",
            "",
            "Differences are left minus right; negative favors the left strategy. Win/loss/tie "
            f"counts use matched cells and a {NUMERICAL_TOLERANCE_AUD:g} AUD numerical tie "
            f"tolerance. Profile-level 95% t intervals are descriptive and use {profile_count} "
            f"generated profile means, not {case_count} independent households.",
            "",
            "| Comparison | Paired cells | Profiles | Mean energy Δ (AUD) | "
            "95% profile t interval | Energy wins/losses/ties | "
            "Mean objective Δ (AUD) | Objective wins/losses/ties |",
            "|---|---:|---:|---:|---:|---|---:|---|",
        ]
    )
    for _, row in overall_pairs.iterrows():
        lines.append(
            f"| {row['comparison']} | {int(row['matched_household_scenario_pairs'])} | "
            f"{int(row['distinct_generated_profiles'])} | "
            f"{row['mean_per_profile_energy_cost_difference_aud']:.4f} | "
            f"[{row['profile_level_95pct_t_interval_low_energy_aud']:.4f}, "
            f"{row['profile_level_95pct_t_interval_high_energy_aud']:.4f}] | "
            f"{int(row['energy_cost_left_better_pairs'])}/"
            f"{int(row['energy_cost_right_better_pairs'])}/"
            f"{int(row['energy_cost_tied_pairs'])} | "
            f"{row['mean_per_profile_combined_objective_difference_aud']:.4f} | "
            f"{int(row['objective_left_better_pairs'])}/"
            f"{int(row['objective_right_better_pairs'])}/"
            f"{int(row['objective_tied_pairs'])} |"
        )
    lines.extend(
        [
            "",
            "Paired energy-cost differences by design factor (left minus right; negative favors "
            "the left strategy):",
            "",
            "| Factor | Level | Comparison | Mean difference (AUD) | Wins/losses/ties |",
            "|---|---|---|---:|---|",
        ]
    )
    for row in factor_pairs.itertuples():
        lines.append(
            f"| {row.factor} | {row.level} | {row.comparison} | "
            f"{row.mean_per_profile_energy_cost_difference_aud:.4f} | "
            f"{row.energy_cost_left_better_pairs}/"
            f"{row.energy_cost_right_better_pairs}/{row.energy_cost_tied_pairs} |"
        )
    lines.extend(
        [
            "",
            "## Factor-level outcomes",
            "",
            "Mean energy-charge reduction vs S0, descriptive averages across remaining factors:",
            "",
            "| Flexibility (h) | Greedy nominal | MILP nominal | "
            "MILP forecast | Perfect-info MILP |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    for flexibility, row in flex_ablation.iterrows():
        lines.append(
            f"| {flexibility} | {row['S1_greedy_nominal']:.3f} | "
            f"{row['S2_milp_nominal']:.3f} | {row['S2_milp_forecast']:.3f} | "
            f"{row['oracle_milp_perfect_information']:.3f} |"
        )
    lines.extend(
        [
            "",
            "Mean energy-charge reduction vs S0 by forecast-error factor:",
            "",
            "| Forecast-error factor | MILP nominal | MILP forecast |",
            "|---:|---:|---:|",
        ]
    )
    for factor, row in error_ablation.iterrows():
        lines.append(
            f"| {factor:g} | {row['S2_milp_nominal']:.3f} | {row['S2_milp_forecast']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Robustness checks",
            "",
            "| Case | Solver status | MILP energy charge (AUD) | Greedy energy charge (AUD) | "
            "MILP − greedy charge (AUD) | Error |",
            "|---|---|---:|---:|---:|---|",
        ]
    )
    for row in robustness.itertuples():
        candidate = (
            "—"
            if pd.isna(row.candidate_energy_cost_aud)
            else f"{row.candidate_energy_cost_aud:.3f}"
        )
        greedy = "—" if pd.isna(row.greedy_energy_cost_aud) else f"{row.greedy_energy_cost_aud:.3f}"
        gap = (
            "—"
            if pd.isna(row.greedy_energy_cost_gap_aud)
            else f"{row.greedy_energy_cost_gap_aud:.3f}"
        )
        lines.append(
            f"| {row.case} | {row.status} | {candidate} | {greedy} | {gap} | "
            f"{row.error_message or ''} |"
        )
    lines.extend(
        [
            "",
            "## Figures and audit files",
            "",
            "- `paired_s1_s2.png`: matched S1-versus-S2 nominal charges and objectives with "
            "identity lines.",
            "- `flexibility_forecast_error.png`: flexibility and forecast-error ablation.",
            "- `cost_inconvenience.png`: synthetic energy-cost versus inconvenience trade-off.",
            "- `equity_savings_distribution.png`: synthetic profile means by flexibility, "
            "with medians/IQRs, split by flat versus TOU tariff spread.",
            "- `paired_comparisons.csv` and `paired_summary.csv`: matched deltas, outcomes, "
            "win/loss/tie counts, profile-level summaries, and descriptive intervals.",
            "- `equity_summary.csv`: synthetic flexibility/appliance groups, technical input "
            "eligibility, technical non-completion counts, charge/savings distributions, "
            "inconvenience, "
            "and weighted-objective changes.",
            "- `equity_flexibility_sensitivity.csv`: matched 2-hour versus wider-window results.",
            "- `equity_provenance.csv`: metric definitions, sources, missing categories, and "
            "interpretation limits.",
            "- `equity_boundary_cases.csv`: constructed fixed-window, sub-penalty-benefit, and "
            "unavailable-appliance cases.",
            "- `robustness.csv`: infeasible windows/caps, greedy suboptimality, and injected "
            "solver-failure outcomes.",
            "- `interval_prices.csv` and `task_schedules.csv`: traces to replay every charge.",
            "",
            "## Limitations",
            "",
            "- Synthetic scenarios assume task compliance and are not estimates of actual "
            "participation or customer savings.",
            "- Energy charges alone do not establish superiority; the combined objective depends "
            "on an unvalidated inconvenience weight.",
            "- The one-day model excludes complete bills, supply/demand charges, tax/export "
            "treatment, PV/BESS, comfort constraints, device execution, and population diversity.",
            "- Results and price-error distributions are uncalibrated sensitivity cases only.",
            "",
            "## Equity and distributional evaluation",
            "",
            "These are software-pipeline and synthetic scenario results, not verified "
            "energy-equity outcomes. Software access is not measured: the experiment has no "
            "account access, device, connectivity, uptake, or accessibility audit data. The "
            "technically eligible input count only records generated cases whose advisory "
            "inputs were valid; it must not be interpreted as the number of people able to "
            "use the service.",
            "",
            "Technical feasibility means the optimizer returns a feasible schedule and all "
            "mandatory tasks complete. Economic worth is not classified because no acceptable "
            "minimum benefit or welfare threshold is declared. Practical actionability, user "
            "acceptance, and device execution are not measured. Benefits are absolute modeled "
            "energy-charge reductions versus matched S0 in AUD, reported alongside inconvenience "
            "and weighted-objective changes. Negative savings are retained as counterexamples. "
            "Uncertainty intervals and quantiles operate on the generated profile means; repeated "
            "scenario cells are not independent households.",
            "",
            f"In the executed forecast-MILP cases, {len(negative_forecast_savings)} of "
            f"{len(forecast_results)} had negative savings versus S0; the worst modeled "
            f"difference was "
            f"{negative_forecast_savings.min():.4f} AUD."
            if not negative_forecast_savings.empty
            else f"No negative forecast-MILP savings versus S0 occurred among "
            f"{len(forecast_results)} cases.",
            "",
            "Groups are synthetic flexibility-hour and appliance-mix categories only. No housing "
            "tenure, income, health, demographic, or protected-group information is inferred from "
            "consumption. Demographic groups and DER categories (no DER, PV, EV/BESS ownership) "
            "are missing/not estimable; EV charging in the mixed task profile is a modeled load, "
            "not evidence of DER ownership. No poverty-reduction or verified equity claim follows.",
            "",
            "| Synthetic grouping | Category | Strategy | Profile count | Scenario cells | "
            "Technically eligible input cases | Technical non-completion cells | "
            "Technical non-completion rate | Mean energy charge (AUD) | "
            "Charge p10–p90 (AUD) | Mean savings (AUD) | "
            "Profile 95% interval (AUD) | Savings p10–p90 (AUD) | Inconvenience (h) | "
            "Inconvenience p10–p90 (h) | Weighted-objective change (AUD) | "
            "Objective-change p10–p90 (AUD) |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in equity_summary.itertuples():
        lines.append(
            f"| {row.group_axis} | {row.group_label} | {row.strategy} | "
            f"{row.distinct_generated_profiles} | {row.scenario_cells} | "
            f"{row.technically_eligible_cells} | "
            f"{row.technically_incomplete_or_infeasible_cells} | "
            f"{row.technical_non_completion_rate:.1%} | "
            f"{row.mean_profile_energy_charge_aud:.3f} | "
            f"{row.profile_energy_charge_p10_aud:.3f}–"
            f"{row.profile_energy_charge_p90_aud:.3f} | "
            f"{row.mean_profile_savings_vs_s0_aud:.3f} | "
            f"[{row.profile_savings_95pct_ci_low_aud:.3f}, "
            f"{row.profile_savings_95pct_ci_high_aud:.3f}] | "
            f"{row.profile_savings_p10_aud:.3f}–{row.profile_savings_p90_aud:.3f} | "
            f"{row.mean_profile_inconvenience_hours:.2f} | "
            f"{row.profile_inconvenience_p10_hours:.2f}–"
            f"{row.profile_inconvenience_p90_hours:.2f} | "
            f"{row.mean_profile_weighted_objective_change_vs_s0_aud:.3f} | "
            f"{row.profile_objective_change_p10_aud:.3f}–"
            f"{row.profile_objective_change_p90_aud:.3f} |"
        )
    lines.extend(
        [
            "",
            "Limited-flexibility sensitivity compares each same profile/scenario at 2 hours "
            "against the wider listed window. Negative savings difference means the 2-hour "
            "window produces less modeled benefit. These are matched synthetic scenario changes, "
            "not evidence about groups of people.",
            "",
            "| Strategy | Comparison | Matched cells | Profiles | Mean savings difference (AUD) | "
            "Profile 95% interval (AUD) | Lower/equal/higher savings cells | "
            "Flat tariff ties/cases | TOU tariff ties/cases | "
            "Technical non-completion 2h / comparator | Inconvenience difference (h) |",
            "|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|",
        ]
    )
    for row in equity_flexibility.itertuples():
        lines.append(
            f"| {row.strategy} | {row.comparison} | {row.matched_scenario_cells} | "
            f"{row.distinct_generated_profiles} | "
            f"{row.mean_profile_savings_difference_aud:.4f} | "
            f"[{row.profile_savings_difference_95pct_ci_low_aud:.4f}, "
            f"{row.profile_savings_difference_95pct_ci_high_aud:.4f}] | "
            f"{row.limited_flexibility_lower_savings_cells}/"
            f"{row.tied_savings_cells}/{row.limited_flexibility_higher_savings_cells} | "
            f"{row.flat_tariff_tied_cells}/{row.flat_tariff_comparison_cells} | "
            f"{row.variable_tariff_tied_cells}/{row.variable_tariff_comparison_cells} | "
            f"{row.technically_incomplete_or_infeasible_at_limited_flexibility_cells}/"
            f"{row.technically_incomplete_or_infeasible_at_comparator_flexibility_cells} | "
            f"{row.mean_profile_inconvenience_difference_hours:.3f} |"
        )
    lines.extend(
        [
            "",
            "Constructed boundary cases are synthetic optimizer checks, not household groups. "
            "The unavailable-appliance row is explicitly not modeled because the v1 request "
            "requires at least one task and has no appliance-availability field.",
            "",
            "| Case | Status | Feasible | Available shift benefit (AUD) | "
            "Available shift penalty (AUD) | Realized energy saving (AUD) | "
            "Applied inconvenience penalty (AUD) | "
            "Weighted objective change (AUD) | Interpretation |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in equity_boundary_cases.itertuples():
        benefit = (
            "—"
            if pd.isna(row.available_shift_benefit_aud)
            else f"{row.available_shift_benefit_aud:.4f}"
        )
        available_penalty = (
            "—"
            if pd.isna(row.available_shift_inconvenience_penalty_aud)
            else f"{row.available_shift_inconvenience_penalty_aud:.4f}"
        )
        saving = (
            "—"
            if pd.isna(row.realized_energy_saving_vs_preferred_aud)
            else f"{row.realized_energy_saving_vs_preferred_aud:.4f}"
        )
        penalty = (
            "—"
            if pd.isna(row.inconvenience_penalty_aud)
            else f"{row.inconvenience_penalty_aud:.4f}"
        )
        objective_change = (
            "—"
            if pd.isna(row.weighted_objective_change_vs_preferred_aud)
            else f"{row.weighted_objective_change_vs_preferred_aud:.4f}"
        )
        feasible = "—" if pd.isna(row.feasible) else str(bool(row.feasible))
        lines.append(
            f"| {row.case} | {row.status} | {feasible} | {benefit} | "
            f"{available_penalty} | {saving} | {penalty} | {objective_change} | "
            f"{row.interpretation} |"
        )
    lines.extend(
        [
            "",
            "The machine-readable provenance ledger is `equity_provenance.csv`; it records source "
            "fields, definitions, missing categories, and interpretation boundaries.",
            "",
            "Missing categories and limitations:",
            "",
        ]
    )
    for row in equity_provenance.itertuples():
        if row.source_fields == "Not available" or row.source_fields == "Not measured":
            lines.append(f"- **{row.metric}:** {row.scope_and_limitations}")
    lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")
