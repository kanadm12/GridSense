"""Golden tests for schedule optimization and the deterministic reference."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.schemas.scheduling import SchedulingRequestV1, SchedulingStatus
from app.services.scheduling_optimizer import (
    interval_energy_rates_aud,
    optimize_schedule_v1,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "scheduling_v1.json"


def _request_payload() -> dict:
    return copy.deepcopy(json.loads(FIXTURE_PATH.read_text())["request"])


def _request(payload: dict | None = None) -> SchedulingRequestV1:
    return SchedulingRequestV1.model_validate(payload or _request_payload())


def _scheduled_start(result, task_id: str = "water-heater-1"):
    assert result.candidate_schedule is not None
    task = next(item for item in result.candidate_schedule.tasks if item.task_id == task_id)
    return task.start


def test_golden_case_chooses_lowest_energy_cost_start():
    request = _request()

    result = optimize_schedule_v1(request, [0.50, 0.50, 0.10, 0.10])

    assert result.status == SchedulingStatus.FEASIBLE
    assert _scheduled_start(result).isoformat() == "2026-11-03T09:00:00+11:00"
    assert result.reference_schedule.status == "feasible"
    assert result.objective_breakdown.total_objective_aud == pytest.approx(0.73)
    assert result.objective_breakdown.candidate_energy_cost_aud == pytest.approx(0.72)
    assert result.objective_breakdown.reference_energy_cost_aud == pytest.approx(0.72)
    assert result.objective_breakdown.total_objective_aud == pytest.approx(0.73)
    assert result.objective_breakdown.reference_objective_aud == pytest.approx(0.73)


def test_fixed_baseline_is_counted_once_in_schedule_cost():
    result = optimize_schedule_v1(_request(), [0.28] * 4)

    assert result.objective_breakdown.baseline_energy_cost_aud == pytest.approx(0.448)
    assert result.objective_breakdown.candidate_energy_cost_aud == pytest.approx(1.12)
    assert result.objective_breakdown.energy_cost_delta_aud == pytest.approx(0.0)
    assert result.candidate_schedule.total_energy_kwh == pytest.approx(4.0)
    assert result.candidate_schedule.total_cost_aud == pytest.approx(1.12)


def test_flat_tariff_ties_are_repeatable():
    payload = _request_payload()
    payload["tasks"][0]["preferred_start"] = None
    request = _request(payload)

    first = optimize_schedule_v1(request, [0.28] * 4)
    repeated = optimize_schedule_v1(request, [0.28] * 4)

    assert first.status == repeated.status == SchedulingStatus.FEASIBLE
    assert _scheduled_start(first) == _scheduled_start(repeated)
    assert first.candidate_schedule.total_cost_aud == repeated.candidate_schedule.total_cost_aud
    assert first.objective_breakdown.total_objective_aud == pytest.approx(1.12)


def test_milp_beats_greedy_when_task_priority_changes_the_global_assignment():
    payload = _request_payload()
    payload["baseline_profile"]["intervals"] = [
        {"interval_start": "2026-11-03T08:00:00+11:00", "demand_kw": 0.0},
        {"interval_start": "2026-11-03T08:30:00+11:00", "demand_kw": 0.0},
    ]
    payload["tasks"] = [
        {
            "task_id": "a-small",
            "appliance": "Small task",
            "rated_power_kw": 1.0,
            "duration_minutes": 30,
            "earliest_start": "2026-11-03T08:00:00+11:00",
            "deadline": "2026-11-03T09:00:00+11:00",
            "preferred_start": None,
            "mandatory": True,
        },
        {
            "task_id": "b-large",
            "appliance": "Large task",
            "rated_power_kw": 2.0,
            "duration_minutes": 30,
            "earliest_start": "2026-11-03T08:00:00+11:00",
            "deadline": "2026-11-03T09:00:00+11:00",
            "preferred_start": None,
            "mandatory": True,
        },
    ]
    payload["household_power_limit_kw"] = 2.0
    result = optimize_schedule_v1(_request(payload), [0.10, 10.0])

    candidate_starts = {
        task.task_id: task.start.isoformat() for task in result.candidate_schedule.tasks
    }
    reference_starts = {
        task.task_id: task.start.isoformat() for task in result.reference_schedule.tasks
    }
    assert candidate_starts == {
        "a-small": "2026-11-03T08:30:00+11:00",
        "b-large": "2026-11-03T08:00:00+11:00",
    }
    assert reference_starts == {
        "a-small": "2026-11-03T08:00:00+11:00",
        "b-large": "2026-11-03T08:30:00+11:00",
    }
    assert result.objective_breakdown.candidate_energy_cost_aud == pytest.approx(5.1)
    assert result.objective_breakdown.reference_energy_cost_aud == pytest.approx(10.05)
    assert result.objective_breakdown.total_objective_aud < (
        result.objective_breakdown.reference_objective_aud
    )


def test_preference_penalty_can_justify_a_higher_energy_cost():
    payload = _request_payload()
    payload["tasks"][0]["preferred_start"] = "2026-11-03T09:00:00+11:00"
    payload["preference_penalty_aud_per_interval"] = 0.25
    request = _request(payload)

    result = optimize_schedule_v1(request, [0.10, 0.20, 0.30, 0.40])

    assert _scheduled_start(result).isoformat() == "2026-11-03T09:00:00+11:00"
    assert result.objective_breakdown.preference_penalty_aud == pytest.approx(0.0)
    assert result.objective_breakdown.candidate_energy_cost_aud == pytest.approx(1.24)
    assert result.objective_breakdown.total_objective_aud == pytest.approx(1.24)


@pytest.mark.parametrize(
    ("omission_penalty", "expected_omitted"),
    [(0.20, True), (1.00, False)],
)
def test_optional_tasks_use_explicit_omission_penalty(omission_penalty, expected_omitted):
    payload = _request_payload()
    payload["tasks"][0]["mandatory"] = False
    payload["tasks"][0]["omission_penalty_aud"] = omission_penalty

    result = optimize_schedule_v1(_request(payload), [0.28] * 4)

    assert result.status == SchedulingStatus.FEASIBLE
    assert result.candidate_schedule.tasks[0].omitted is expected_omitted
    if expected_omitted:
        assert result.candidate_schedule.tasks[0].start is None
        assert result.objective_breakdown.omission_penalty_aud == pytest.approx(0.20)
    else:
        assert result.candidate_schedule.tasks[0].start is not None
        assert result.objective_breakdown.omission_penalty_aud == pytest.approx(0.0)


def test_optional_tasks_without_penalty_use_no_savings_treatment():
    payload = _request_payload()
    payload["tasks"][0]["mandatory"] = False

    result = optimize_schedule_v1(_request(payload), [0.0] * 4)

    assert result.candidate_schedule.tasks[0].omitted is True
    assert result.objective_breakdown.omission_penalty_aud == pytest.approx(0.0)


def test_power_limit_can_make_required_task_infeasible():
    payload = _request_payload()
    payload["grid_power_limit_kw"] = 3.0
    request = _request(payload)

    result = optimize_schedule_v1(request, [0.28] * 4)

    assert result.status == SchedulingStatus.INFEASIBLE
    assert result.candidate_schedule is None
    assert result.reference_schedule.status == "not_found"


def test_dst_transition_uses_contiguous_utc_intervals_and_local_offsets():
    payload = _request_payload()
    payload["baseline_profile"]["intervals"] = [
        {"interval_start": timestamp, "demand_kw": 0.2}
        for timestamp in (
            "2026-10-04T01:00:00+10:00",
            "2026-10-04T01:30:00+10:00",
            "2026-10-04T03:00:00+11:00",
            "2026-10-04T03:30:00+11:00",
            "2026-10-04T04:00:00+11:00",
        )
    ]
    task = payload["tasks"][0]
    task["earliest_start"] = "2026-10-04T01:30:00+10:00"
    task["deadline"] = "2026-10-04T04:00:00+11:00"
    task["preferred_start"] = None
    request = _request(payload)

    result = optimize_schedule_v1(request, [0.5, 0.5, 0.1, 0.1, 0.1])

    scheduled = result.candidate_schedule.tasks[0]
    assert scheduled.start.isoformat() == "2026-10-04T03:00:00+11:00"
    assert scheduled.end.isoformat() == "2026-10-04T04:00:00+11:00"


def test_tariff_periods_resolve_each_interval_rate_without_default_fallbacks():
    request = _request()
    tariff = SimpleNamespace(
        rates_include_gst=True,
        tariff_type="tou",
        periods=[
            {
                "start_minute": 480,
                "end_minute": 540,
                "days": [1],
                "rate_cents_kwh": 10.0,
            },
            {
                "start_minute": 540,
                "end_minute": 600,
                "days": [1],
                "rate_cents_kwh": 20.0,
            },
        ],
    )

    assert interval_energy_rates_aud(tariff, request, "VIC") == pytest.approx(
        [0.10, 0.10, 0.20, 0.20]
    )


def test_solver_timeout_does_not_return_a_candidate_fallback(monkeypatch):
    import app.services.scheduling_optimizer as optimizer

    monkeypatch.setattr(
        optimizer,
        "milp",
        lambda **kwargs: SimpleNamespace(status=1, message="time limit", x=None),
    )

    result = optimizer.optimize_schedule_v1(_request(), [0.28] * 4)

    assert result.status == SchedulingStatus.TIMEOUT
    assert result.candidate_schedule is None
    assert result.reference_schedule.status == "feasible"
    assert "time limit" in result.blockers[0]


def test_invalid_interval_prices_fail_explicitly():
    with pytest.raises(ValueError, match="finite and nonnegative"):
        optimize_schedule_v1(_request(), [0.28, float("nan"), 0.28, 0.28])
