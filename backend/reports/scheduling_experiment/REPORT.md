# Synthetic scheduling strategy experiment

## Findings and limitations

This is a synthetic sensitivity study using 8 generated household profiles repeatedly across 192 household/configuration cells. It is not measured customer behavior, an Australian tariff study, or evidence of real bill savings. No population-level inference is supported.

## Equity metric definitions (specified before group outcomes)

- **Software access:** Not measured; technically complete synthetic advisory inputs are a pipeline-eligibility proxy only and do not establish that a person can access or use the software.
- **Actionability:** Technical feasibility/completion only: the schedule is feasible and all mandatory tasks complete. Practical user actionability is not measured.
- **Benefit distribution:** Absolute modeled energy-charge reduction from the same case's S0, in AUD; not a full bill or verified household saving. Sum of absolute task start-time displacements from preferred starts, in hours.
- **Permitted groups:** Only generated scenario categories (flexibility hours and appliance mix) are used; no demographic or socioeconomic groups are inferred.
- **DER comparison:** Not estimable: source profiles do not encode PV generation, battery storage, or a verified DER-ownership category. EV charging is only a modeled load task.
- Group sizes and descriptive uncertainty use generated-profile means; repeated factorial cells are not independent households.

## Strategies and price information

- **S0:** execute tasks at their preferred starts.
- **S1 greedy nominal:** greedy reference using nominal tariff information.
- **S2 MILP nominal:** MILP using the identical nominal price vector as S1. This matched comparison separates algorithm differences from price-information effects.
- **S2 MILP forecast:** MILP using noisy future-price estimates; compare with S2 nominal to isolate forecast-information sensitivity.
- **Perfect-information MILP:** realized prices supplied to MILP, optimizing energy charge plus the configured inconvenience penalty.
- **Energy-only oracle:** realized prices supplied to MILP with the preference penalty set to zero; an energy-charge lower bound only within this modeled feasible set.

The nominal time-of-use schedule and price shape are assumed known at scheduling time. Realized prices are nominal prices plus Gaussian perturbations drawn with mean zero and standard deviation $0.025/kWh times the spread factor, before a $0.01/kWh price floor. Forecast estimates add independent Gaussian perturbations drawn with mean zero and standard deviation $0.25 times the forecast-error factor times the spread factor, before the same floor; clipping can shift the resulting deviations away from zero mean. These uncalibrated stress parameters are not observed Australian retail prices or validated forecast-error distributions.

## Design and assumptions

- 192 household/configuration cells, 1152 strategy rows, 8 fixed generated profiles.
- Factorial dimensions: flexibility hours [2, 6, 10], tariff-spread factors [0.0, 1.0], forecast-error factors [0.0, 0.5], and appliance mixes [light, mixed]; one synthetic Melbourne day at 30-minute resolution.
- Profiles contain no measured DER, PV, EV ownership, demographics, or customer data. Tariffs are energy-only; supply/demand charges, tax, export credits, and retailer rules are excluded.
- The same 8 generated profile IDs recur. The 192 cells are not independent households. Paired profile-level intervals average repeated cell differences within profile before calculating intervals from the 8 profile means.
- The combined objective is realized energy charge plus $0.01 per interval of absolute start-time displacement. This preference weight is a modeling assumption, not a validated monetary value of inconvenience.
- `baseline_energy_cost_aud` remains as a compatibility alias for `non_flexible_baseline_energy_cost_aud`; neither is the complete S0 charge. `s0_reference_energy_cost_aud` is the complete preferred-start charge.

## Aggregate descriptive results

| Strategy | Rows | Energy charge (AUD) | Weighted objective (AUD) | Change vs S0 (AUD) | Completion | Peak (kW) | Inconvenience (h) | Infeasible |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| S0_no_intervention | 192 | 7.359 | 7.359 | 0.000 | 100.0% | 3.836 | 0.00 | 0 |
| S1_greedy_nominal | 192 | 6.887 | 6.927 | 0.472 | 100.0% | 3.748 | 1.98 | 0 |
| S2_milp_nominal | 192 | 6.886 | 6.926 | 0.473 | 100.0% | 3.771 | 1.98 | 0 |
| S2_milp_forecast | 192 | 6.896 | 6.947 | 0.464 | 100.0% | 3.769 | 2.57 | 0 |
| oracle_milp_perfect_information | 192 | 6.862 | 6.912 | 0.498 | 100.0% | 3.754 | 2.53 | 0 |
| oracle_milp_energy_only | 192 | 6.858 | 6.985 | 0.501 | 100.0% | 3.619 | 6.38 | 0 |

## Matched comparisons

Differences are left minus right; negative favors the left strategy. Win/loss/tie counts use matched cells and a 1e-08 AUD numerical tie tolerance. Profile-level 95% t intervals are descriptive and use 8 generated profile means, not 192 independent households.

| Comparison | Paired cells | Profiles | Mean energy Δ (AUD) | 95% profile t interval | Energy wins/losses/ties | Mean objective Δ (AUD) | Objective wins/losses/ties |
|---|---:|---:|---:|---:|---|---:|---|
| forecast_milp_minus_greedy | 192 | 8 | 0.0083 | [-0.0086, 0.0251] | 63/31/98 | 0.0200 | 55/39/98 |
| forecast_minus_nominal_milp | 192 | 8 | 0.0094 | [-0.0060, 0.0247] | 62/32/98 | 0.0211 | 54/40/98 |
| nominal_milp_minus_greedy | 192 | 8 | -0.0011 | [-0.0039, 0.0016] | 4/2/186 | -0.0011 | 4/2/186 |

Paired energy-cost differences by design factor (left minus right; negative favors the left strategy):

| Factor | Level | Comparison | Mean difference (AUD) | Wins/losses/ties |
|---|---|---|---:|---|
| flexibility_hours | 2 | forecast_milp_minus_greedy | 0.0204 | 19/11/34 |
| flexibility_hours | 6 | forecast_milp_minus_greedy | 0.0084 | 22/10/32 |
| flexibility_hours | 10 | forecast_milp_minus_greedy | -0.0040 | 22/10/32 |
| flexibility_hours | 2 | forecast_minus_nominal_milp | 0.0204 | 19/11/34 |
| flexibility_hours | 6 | forecast_minus_nominal_milp | 0.0118 | 21/11/32 |
| flexibility_hours | 10 | forecast_minus_nominal_milp | -0.0040 | 22/10/32 |
| flexibility_hours | 2 | nominal_milp_minus_greedy | 0.0000 | 0/0/64 |
| flexibility_hours | 6 | nominal_milp_minus_greedy | -0.0034 | 4/2/58 |
| flexibility_hours | 10 | nominal_milp_minus_greedy | 0.0000 | 0/0/64 |
| forecast_error_spread_fraction | 0.0 | forecast_milp_minus_greedy | -0.0257 | 46/0/50 |
| forecast_error_spread_fraction | 0.5 | forecast_milp_minus_greedy | 0.0422 | 17/31/48 |
| forecast_error_spread_fraction | 0.0 | forecast_minus_nominal_milp | -0.0246 | 46/0/50 |
| forecast_error_spread_fraction | 0.5 | forecast_minus_nominal_milp | 0.0433 | 16/32/48 |
| forecast_error_spread_fraction | 0.0 | nominal_milp_minus_greedy | -0.0011 | 2/1/93 |
| forecast_error_spread_fraction | 0.5 | nominal_milp_minus_greedy | -0.0011 | 2/1/93 |
| tariff_spread_factor | 0.0 | forecast_milp_minus_greedy | 0.0000 | 0/0/96 |
| tariff_spread_factor | 1.0 | forecast_milp_minus_greedy | 0.0165 | 63/31/2 |
| tariff_spread_factor | 0.0 | forecast_minus_nominal_milp | 0.0000 | 0/0/96 |
| tariff_spread_factor | 1.0 | forecast_minus_nominal_milp | 0.0188 | 62/32/2 |
| tariff_spread_factor | 0.0 | nominal_milp_minus_greedy | 0.0000 | 0/0/96 |
| tariff_spread_factor | 1.0 | nominal_milp_minus_greedy | -0.0023 | 4/2/90 |
| appliance_mix | light | forecast_milp_minus_greedy | -0.0015 | 32/15/49 |
| appliance_mix | mixed | forecast_milp_minus_greedy | 0.0180 | 31/16/49 |
| appliance_mix | light | forecast_minus_nominal_milp | -0.0015 | 32/15/49 |
| appliance_mix | mixed | forecast_minus_nominal_milp | 0.0203 | 30/17/49 |
| appliance_mix | light | nominal_milp_minus_greedy | 0.0000 | 0/0/96 |
| appliance_mix | mixed | nominal_milp_minus_greedy | -0.0023 | 4/2/90 |

## Factor-level outcomes

Mean energy-charge reduction vs S0, descriptive averages across remaining factors:

| Flexibility (h) | Greedy nominal | MILP nominal | MILP forecast | Perfect-info MILP |
|---:|---:|---:|---:|---:|
| 2 | 0.149 | 0.149 | 0.129 | 0.171 |
| 6 | 0.553 | 0.556 | 0.545 | 0.579 |
| 10 | 0.713 | 0.713 | 0.717 | 0.742 |

Mean energy-charge reduction vs S0 by forecast-error factor:

| Forecast-error factor | MILP nominal | MILP forecast |
|---:|---:|---:|
| 0 | 0.473 | 0.498 |
| 0.5 | 0.473 | 0.430 |

## Robustness checks

| Case | Solver status | MILP energy charge (AUD) | Greedy energy charge (AUD) | MILP − greedy charge (AUD) | Error |
|---|---|---:|---:|---:|---|
| single_slot_window_cap_conflict | infeasible | — | — | — | nan |
| power_cap_conflict | infeasible | — | — | — | nan |
| baseline_over_cap | infeasible | — | — | — | nan |
| greedy_suboptimal | feasible | 5.100 | 10.050 | -4.950 | nan |
| injected_solver_failure | solver_error | — | — | — | RuntimeError: Injected solver failure for fault-containment test |

## Figures and audit files

- `paired_s1_s2.png`: matched S1-versus-S2 nominal charges and objectives with identity lines.
- `flexibility_forecast_error.png`: flexibility and forecast-error ablation.
- `cost_inconvenience.png`: synthetic energy-cost versus inconvenience trade-off.
- `equity_savings_distribution.png`: synthetic profile means by flexibility, with medians/IQRs, split by flat versus TOU tariff spread.
- `paired_comparisons.csv` and `paired_summary.csv`: matched deltas, outcomes, win/loss/tie counts, profile-level summaries, and descriptive intervals.
- `equity_summary.csv`: synthetic flexibility/appliance groups, technical input eligibility, technical non-completion counts, charge/savings distributions, inconvenience, and weighted-objective changes.
- `equity_flexibility_sensitivity.csv`: matched 2-hour versus wider-window results.
- `equity_provenance.csv`: metric definitions, sources, missing categories, and interpretation limits.
- `equity_boundary_cases.csv`: constructed fixed-window, sub-penalty-benefit, and unavailable-appliance cases.
- `robustness.csv`: infeasible windows/caps, greedy suboptimality, and injected solver-failure outcomes.
- `interval_prices.csv` and `task_schedules.csv`: traces to replay every charge.

## Limitations

- Synthetic scenarios assume task compliance and are not estimates of actual participation or customer savings.
- Energy charges alone do not establish superiority; the combined objective depends on an unvalidated inconvenience weight.
- The one-day model excludes complete bills, supply/demand charges, tax/export treatment, PV/BESS, comfort constraints, device execution, and population diversity.
- Results and price-error distributions are uncalibrated sensitivity cases only.

## Equity and distributional evaluation

These are software-pipeline and synthetic scenario results, not verified energy-equity outcomes. Software access is not measured: the experiment has no account access, device, connectivity, uptake, or accessibility audit data. The technically eligible input count only records generated cases whose advisory inputs were valid; it must not be interpreted as the number of people able to use the service.

Technical feasibility means the optimizer returns a feasible schedule and all mandatory tasks complete. Economic worth is not classified because no acceptable minimum benefit or welfare threshold is declared. Practical actionability, user acceptance, and device execution are not measured. Benefits are absolute modeled energy-charge reductions versus matched S0 in AUD, reported alongside inconvenience and weighted-objective changes. Negative savings are retained as counterexamples. Uncertainty intervals and quantiles operate on the generated profile means; repeated scenario cells are not independent households.

In the executed forecast-MILP cases, 3 of 192 had negative savings versus S0; the worst modeled difference was -0.1889 AUD.

Groups are synthetic flexibility-hour and appliance-mix categories only. No housing tenure, income, health, demographic, or protected-group information is inferred from consumption. Demographic groups and DER categories (no DER, PV, EV/BESS ownership) are missing/not estimable; EV charging in the mixed task profile is a modeled load, not evidence of DER ownership. No poverty-reduction or verified equity claim follows.

| Synthetic grouping | Category | Strategy | Profile count | Scenario cells | Technically eligible input cases | Technical non-completion cells | Technical non-completion rate | Mean energy charge (AUD) | Charge p10–p90 (AUD) | Mean savings (AUD) | Profile 95% interval (AUD) | Savings p10–p90 (AUD) | Inconvenience (h) | Inconvenience p10–p90 (h) | Weighted-objective change (AUD) | Objective-change p10–p90 (AUD) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| flexibility_hours | 2 | S1_greedy_nominal | 8 | 64 | 64 | 0 | 0.0% | 7.210 | 6.435–8.035 | 0.149 | [0.076, 0.222] | 0.058–0.250 | 0.67 | 0.43–1.00 | -0.136 | -0.230–-0.052 |
| flexibility_hours | 2 | S2_milp_forecast | 8 | 64 | 64 | 0 | 0.0% | 7.230 | 6.481–8.032 | 0.129 | [0.054, 0.203] | 0.035–0.240 | 1.12 | 0.94–1.27 | -0.106 | -0.216–-0.015 |
| flexibility_hours | 2 | S2_milp_nominal | 8 | 64 | 64 | 0 | 0.0% | 7.210 | 6.435–8.035 | 0.149 | [0.076, 0.222] | 0.058–0.250 | 0.67 | 0.43–1.00 | -0.136 | -0.230–-0.052 |
| flexibility_hours | 6 | S1_greedy_nominal | 8 | 64 | 64 | 0 | 0.0% | 6.806 | 6.044–7.583 | 0.553 | [0.521, 0.585] | 0.518–0.590 | 2.31 | 1.96–2.58 | -0.507 | -0.545–-0.473 |
| flexibility_hours | 6 | S2_milp_forecast | 8 | 64 | 64 | 0 | 0.0% | 6.814 | 6.121–7.569 | 0.545 | [0.520, 0.569] | 0.513–0.574 | 2.84 | 2.38–3.24 | -0.488 | -0.520–-0.460 |
| flexibility_hours | 6 | S2_milp_nominal | 8 | 64 | 64 | 0 | 0.0% | 6.803 | 6.044–7.563 | 0.556 | [0.527, 0.586] | 0.529–0.590 | 2.31 | 1.96–2.58 | -0.510 | -0.545–-0.479 |
| flexibility_hours | 10 | S1_greedy_nominal | 8 | 64 | 64 | 0 | 0.0% | 6.646 | 5.935–7.393 | 0.713 | [0.647, 0.780] | 0.633–0.803 | 2.95 | 2.51–3.29 | -0.654 | -0.738–-0.571 |
| flexibility_hours | 10 | S2_milp_forecast | 8 | 64 | 64 | 0 | 0.0% | 6.642 | 5.915–7.370 | 0.717 | [0.639, 0.796] | 0.618–0.796 | 3.73 | 3.24–4.20 | -0.643 | -0.725–-0.547 |
| flexibility_hours | 10 | S2_milp_nominal | 8 | 64 | 64 | 0 | 0.0% | 6.646 | 5.935–7.393 | 0.713 | [0.647, 0.780] | 0.633–0.803 | 2.95 | 2.51–3.29 | -0.654 | -0.738–-0.571 |
| appliance_mix | light | S1_greedy_nominal | 8 | 96 | 96 | 0 | 0.0% | 5.892 | 5.195–6.624 | 0.140 | [0.103, 0.176] | 0.090–0.189 | 1.05 | 0.83–1.33 | -0.119 | -0.162–-0.073 |
| appliance_mix | light | S2_milp_forecast | 8 | 96 | 96 | 0 | 0.0% | 5.890 | 5.184–6.618 | 0.141 | [0.108, 0.175] | 0.092–0.180 | 1.44 | 1.17–1.63 | -0.112 | -0.149–-0.069 |
| appliance_mix | light | S2_milp_nominal | 8 | 96 | 96 | 0 | 0.0% | 5.892 | 5.195–6.624 | 0.140 | [0.103, 0.176] | 0.090–0.189 | 1.05 | 0.83–1.33 | -0.119 | -0.162–-0.073 |
| appliance_mix | mixed | S1_greedy_nominal | 8 | 96 | 96 | 0 | 0.0% | 7.883 | 7.081–8.716 | 0.804 | [0.738, 0.870] | 0.732–0.892 | 2.91 | 2.67–3.17 | -0.746 | -0.835–-0.671 |
| appliance_mix | mixed | S2_milp_forecast | 8 | 96 | 96 | 0 | 0.0% | 7.901 | 7.161–8.696 | 0.786 | [0.741, 0.831] | 0.729–0.845 | 3.69 | 3.33–4.08 | -0.712 | -0.770–-0.653 |
| appliance_mix | mixed | S2_milp_nominal | 8 | 96 | 96 | 0 | 0.0% | 7.881 | 7.081–8.703 | 0.806 | [0.743, 0.870] | 0.737–0.892 | 2.91 | 2.67–3.17 | -0.748 | -0.835–-0.680 |

Limited-flexibility sensitivity compares each same profile/scenario at 2 hours against the wider listed window. Negative savings difference means the 2-hour window produces less modeled benefit. These are matched synthetic scenario changes, not evidence about groups of people.

| Strategy | Comparison | Matched cells | Profiles | Mean savings difference (AUD) | Profile 95% interval (AUD) | Lower/equal/higher savings cells | Flat tariff ties/cases | TOU tariff ties/cases | Technical non-completion 2h / comparator | Inconvenience difference (h) |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|
| S1_greedy_nominal | 2h_minus_6h | 64 | 8 | -0.4040 | [-0.4774, -0.3306] | 32/32/0 | 32/32 | 0/32 | 0/0 | -1.641 |
| S2_milp_nominal | 2h_minus_6h | 64 | 8 | -0.4074 | [-0.4827, -0.3321] | 32/32/0 | 32/32 | 0/32 | 0/0 | -1.641 |
| S2_milp_forecast | 2h_minus_6h | 64 | 8 | -0.4160 | [-0.5036, -0.3285] | 32/32/0 | 32/32 | 0/32 | 0/0 | -1.727 |
| S1_greedy_nominal | 2h_minus_10h | 64 | 8 | -0.5642 | [-0.6897, -0.4387] | 32/32/0 | 32/32 | 0/32 | 0/0 | -2.281 |
| S2_milp_nominal | 2h_minus_10h | 64 | 8 | -0.5642 | [-0.6897, -0.4387] | 32/32/0 | 32/32 | 0/32 | 0/0 | -2.281 |
| S2_milp_forecast | 2h_minus_10h | 64 | 8 | -0.5887 | [-0.7256, -0.4517] | 32/32/0 | 32/32 | 0/32 | 0/0 | -2.617 |

Constructed boundary cases are synthetic optimizer checks, not household groups. The unavailable-appliance row is explicitly not modeled because the v1 request requires at least one task and has no appliance-availability field.

| Case | Status | Feasible | Available shift benefit (AUD) | Available shift penalty (AUD) | Realized energy saving (AUD) | Applied inconvenience penalty (AUD) | Weighted objective change (AUD) | Interpretation |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| zero_flexibility_fixed_mandatory_task | feasible | True | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | One feasible mandatory task has a single allowed start; it cannot shift. |
| benefit_below_inconvenience_penalty | feasible | True | 0.0050 | 0.0100 | 0.0000 | 0.0000 | 0.0000 | A 0.005 AUD possible energy-charge reduction is below the 0.01 AUD one-interval preference penalty; MILP retains the preferred start. |
| appliance_unavailable | not_representable | — | — | — | — | — | — | The v1 request requires at least one task and has no appliance availability field; unavailable appliances are not simulated as eligible tasks. |

The machine-readable provenance ledger is `equity_provenance.csv`; it records source fields, definitions, missing categories, and interpretation boundaries.

Missing categories and limitations:

- **software_access:** No account, device, connectivity, uptake, or accessibility audit data.
- **practical_actionability_and_acceptance:** Technical feasibility does not establish practical actionability or adoption.
- **device_execution:** No device execution telemetry is included.
- **demographic_groups:** No consented demographic data, collection purpose, or provenance documentation exists.
- **der_comparison:** No PV/BESS/generation/DER ownership fields; EV is modeled as a flexible load.
