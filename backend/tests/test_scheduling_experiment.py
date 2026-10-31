"""Tests for billing consistency and reproducibility in synthetic scheduling experiments."""

import json
from pathlib import Path

import pandas as pd
import pytest

from app.ml.scheduling_experiment import (
    ExperimentDesign,
    _make_request,
    audit_billing_reconciliation,
    equity_provenance_ledger,
    flexibility_equity_sensitivity,
    run_equity_boundary_cases,
    run_experiment,
    run_optimizer_for_robustness,
    run_robustness_cases,
    score_assignment,
    summarize_equity,
)


def _request():
    baseline = [0.5] * 48
    return _make_request(
        household_index=0,
        scenario_id="synthetic-test",
        flexibility_hours=2,
        mix="light",
        baseline_kw=baseline,
    )


def test_realized_billing_reconciles_baseline_and_task_interval_charges():
    request = _request()
    assignment = {task.task_id: task.preferred_start for task in request.tasks}
    prices = [0.2] * 48

    score = score_assignment(request, assignment, prices)

    baseline_kwh = sum(item.demand_kw for item in request.baseline_profile.intervals) * 0.5
    task_energy_kwh = sum(
        task.rated_power_kw * task.duration_minutes / 60 for task in request.tasks
    )
    expected_cost = (baseline_kwh + task_energy_kwh) * 0.2
    assert score.non_flexible_baseline_cost_aud == pytest.approx(baseline_kwh * 0.2)
    assert score.cost_aud == pytest.approx(expected_cost)
    assert score.completed_tasks == len(request.tasks)
    assert score.feasible is True


def test_score_rejects_missing_or_invalid_interval_prices():
    request = _request()

    with pytest.raises(ValueError, match="price is required"):
        score_assignment(request, {}, [0.2])
    with pytest.raises(ValueError, match="finite and nonnegative"):
        score_assignment(request, {}, [float("nan")] * 48)


def test_experiment_writes_repeatable_cases_and_summary(tmp_path: Path):
    design = ExperimentDesign(
        seed=17,
        household_count=1,
        flexibility_hours=(2,),
        forecast_error_spread_fractions=(0.0,),
        appliance_mixes=("light",),
        tariff_spread_factors=(0.0,),
    )
    output_paths = run_experiment(tmp_path, design)

    results = pd.read_csv(output_paths["results"])
    summary = pd.read_csv(output_paths["summary"])
    paired = pd.read_csv(output_paths["paired_comparisons"])
    paired_summary = pd.read_csv(output_paths["paired_summary"])
    equity_summary = pd.read_csv(output_paths["equity_summary"])
    equity_flexibility = pd.read_csv(output_paths["equity_flexibility_sensitivity"])
    equity_provenance = pd.read_csv(output_paths["equity_provenance"])
    equity_boundary_cases = pd.read_csv(output_paths["equity_boundary_cases"])
    interval_prices = pd.read_csv(output_paths["interval_prices"])
    schedules = pd.read_csv(output_paths["task_schedules"])
    config = json.loads(output_paths["config"].read_text())

    assert set(results["strategy"]) == {
        "S0_no_intervention",
        "S1_greedy_nominal",
        "S2_milp_nominal",
        "S2_milp_forecast",
        "oracle_milp_perfect_information",
        "oracle_milp_energy_only",
    }
    assert len(results) == 6
    assert len(summary) == 6
    assert (results["baseline_energy_cost_aud"] > 0).all()
    assert results["savings_vs_s0_percent"].notna().all()
    assert config["result_rows"] == 6
    assert len(interval_prices) == 48
    assert len(schedules) == 12
    assert len(paired) == 3
    assert {
        "left_energy_cost_aud",
        "right_energy_cost_aud",
        "left_combined_objective_aud",
        "right_combined_objective_aud",
    }.issubset(paired.columns)
    assert (paired_summary["distinct_generated_profiles"] == 1).all()
    assert len(equity_summary) == 6
    assert len(equity_boundary_cases) == 3
    assert (equity_summary["distinct_generated_profiles"] == 1).all()
    assert (equity_summary["no_actionable_recommendation_cells"] == 0).all()
    assert equity_summary["mean_profile_energy_charge_aud"].notna().all()
    assert equity_summary["profile_inconvenience_p10_hours"].notna().all()
    assert equity_flexibility.empty
    assert output_paths["equity_distribution_plot"].stat().st_size > 0
    assert {"demographic_groups", "der_comparison"}.issubset(set(equity_provenance["metric"]))
    assert all(path.exists() for path in output_paths.values())

    audit_billing_reconciliation(results, interval_prices, schedules)
    changed_results = results.copy()
    changed_results.loc[0, "realized_energy_cost_aud"] += 1e-4
    with pytest.raises(ValueError, match="Billing mismatch"):
        audit_billing_reconciliation(changed_results, interval_prices, schedules)


def test_robustness_cases_cover_infeasible_caps_and_greedy_gap():
    cases = run_robustness_cases().set_index("case")

    assert cases.loc["single_slot_window_cap_conflict", "status"] == "infeasible"
    assert cases.loc["power_cap_conflict", "status"] == "infeasible"
    assert cases.loc["baseline_over_cap", "status"] == "infeasible"
    assert cases.loc["greedy_suboptimal", "status"] == "feasible"
    assert cases.loc["greedy_suboptimal", "greedy_energy_cost_gap_aud"] < -1.0
    assert cases.loc["injected_solver_failure", "status"] == "solver_error"
    assert "Injected solver failure" in cases.loc["injected_solver_failure", "error_message"]


def test_solver_failure_is_reported_not_converted_to_a_feasible_fallback():
    def fail_solver(*args, **kwargs):
        raise RuntimeError("forced failure")

    result, error = run_optimizer_for_robustness(_request(), [0.2] * 48, fail_solver)

    assert result is None
    assert error == "RuntimeError: forced failure"


def test_equity_summary_preserves_negative_savings_and_no_actionability_counterexample():
    rows = []
    for household_id, savings, feasible in (
        ("synthetic-household-1", -2.0, True),
        ("synthetic-household-2", 3.0, False),
    ):
        rows.append(
            {
                "scenario_key": f"case-{household_id}",
                "household_id": household_id,
                "strategy": "S1_greedy_nominal",
                "flexibility_hours": 2,
                "appliance_mix": "light",
                "realized_energy_cost_aud": 5.0 - savings,
                "savings_vs_s0_aud": savings,
                "inconvenience_hours": 1.0,
                "weighted_objective_change_vs_s0_aud": -1.0,
                "feasible": feasible,
                "task_completion_fraction": 1.0 if feasible else 0.5,
            }
        )

    summary = summarize_equity(pd.DataFrame(rows)).iloc[0]

    assert summary["distinct_generated_profiles"] == 2
    assert summary["technically_incomplete_or_infeasible_cells"] == 1
    assert summary["technical_non_completion_rate"] == pytest.approx(0.5)
    assert summary["no_actionable_recommendation_cells"] == 1
    assert summary["no_actionable_recommendation_rate"] == pytest.approx(0.5)
    assert summary["mean_profile_savings_vs_s0_aud"] == pytest.approx(0.5)
    assert summary["profile_savings_p10_aud"] < 0


def test_limited_flexibility_sensitivity_is_matched_and_provenance_discloses_missing_groups():
    rows = []
    for household_index, (limited_savings, wider_savings, spread_factor) in enumerate(
        ((1.0, 1.0, 0.0), (1.0, 3.0, 1.0), (-1.0, 0.0, 1.0)), start=1
    ):
        for strategy in ("S1_greedy_nominal", "S2_milp_nominal", "S2_milp_forecast"):
            for flexibility, savings, inconvenience in (
                (2, limited_savings, 1.0),
                (6, wider_savings, 0.5),
            ):
                rows.append(
                    {
                        "scenario_key": f"scenario-{household_index}",
                        "household_id": f"synthetic-household-{household_index}",
                        "forecast_error_spread_fraction": 0.0,
                        "appliance_mix": "light",
                        "tariff_spread_factor": spread_factor,
                        "strategy": strategy,
                        "flexibility_hours": flexibility,
                        "savings_vs_s0_aud": savings,
                        "inconvenience_hours": inconvenience,
                        "feasible": True,
                        "task_completion_fraction": 1.0,
                    }
                )

    sensitivity = flexibility_equity_sensitivity(pd.DataFrame(rows))
    greedy = sensitivity.loc[sensitivity["strategy"] == "S1_greedy_nominal"].iloc[0]
    ledger = equity_provenance_ledger().set_index("metric")

    assert len(sensitivity) == 3
    assert greedy["comparison"] == "2h_minus_6h"
    assert greedy["mean_profile_savings_difference_aud"] == pytest.approx(-1.0)
    assert greedy["limited_flexibility_lower_savings_cells"] == 2
    assert greedy["no_actionable_at_limited_flexibility_cells"] == 0
    assert greedy["flat_tariff_tied_cells"] == 1
    assert greedy["flat_tariff_comparison_cells"] == 1
    assert greedy["variable_tariff_tied_cells"] == 0
    assert greedy["variable_tariff_comparison_cells"] == 2
    assert greedy["technically_incomplete_or_infeasible_at_limited_flexibility_cells"] == 0
    assert ledger.loc["demographic_groups", "source_fields"] == "Not available"
    assert "not estimable" in ledger.loc["der_comparison", "definition"].lower()


def test_equity_boundary_cases_separate_technical_and_economic_actionability():
    cases = run_equity_boundary_cases().set_index("case")

    fixed = cases.loc["zero_flexibility_fixed_mandatory_task"]
    low_benefit = cases.loc["benefit_below_inconvenience_penalty"]
    unavailable = cases.loc["appliance_unavailable"]

    assert fixed["status"] == "feasible"
    assert bool(fixed["feasible"])
    assert fixed["available_shift_benefit_aud"] == pytest.approx(0.0)
    assert fixed["realized_energy_saving_vs_preferred_aud"] == pytest.approx(0.0)
    assert low_benefit["available_shift_benefit_aud"] == pytest.approx(0.005)
    assert low_benefit["available_shift_inconvenience_penalty_aud"] == pytest.approx(0.01)
    assert low_benefit["inconvenience_penalty_aud"] == pytest.approx(0.0)
    assert low_benefit["realized_energy_saving_vs_preferred_aud"] == pytest.approx(0.0)
    assert low_benefit["weighted_objective_change_vs_preferred_aud"] == pytest.approx(0.0)
    assert unavailable["status"] == "not_representable"
    assert pd.isna(unavailable["feasible"])


def test_report_discloses_synthetic_scope_and_perfect_information_limit(tmp_path: Path):
    design = ExperimentDesign(
        household_count=1,
        flexibility_hours=(2,),
        forecast_error_spread_fractions=(0.0,),
        appliance_mixes=("light",),
        tariff_spread_factors=(0.0,),
    )

    paths = run_experiment(tmp_path, design)

    report = paths["report"].read_text()
    assert "not measured customer behavior" in report
    assert "Perfect-information MILP" in report
    assert "identical nominal price vector as S1" in report
    assert "baseline_energy_cost_aud" in report
    assert "Equity metric definitions (specified before group outcomes)" in report
    assert "no negative forecast-milp savings" in report.lower()
    assert (
        "Practical actionability, user acceptance, and device execution are not measured." in report
    )
    assert "Flat tariff ties/cases" in report
    assert "appliance_unavailable" in report
