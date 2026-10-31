# Synthetic scheduling strategy experiment

This is a deterministic research simulation over generated household profiles, appliance tasks, and tariffs. It is not measured customer behavior, a validated retailer bill, or evidence of realized household savings.

## Strategy definitions

- **S0 — no intervention:** each task runs at its original preferred start.
- **S1 — rule-based:** the existing deterministic greedy reference schedules tasks against the announced synthetic tariff periods.
- **S2 — forecast-informed MILP:** the existing scheduling MILP uses noisy day-ahead estimates of realized interval prices.
- **Oracle — perfect information:** the same MILP is given realized interval prices. It is an upper-bound comparator, not an implementable forecast.

Every strategy shares the same generated baseline, task mix, tariff period schedule, and realized interval prices within each household/configuration. All energy costs are recomputed with the same realized-price billing function; planning costs are not scored.

## Design and assumptions

- 24 household/configuration cases and 96 strategy rows; 1 fixed generated profiles are reused across cases.
- Factorial ablations vary flexibility (2/6/10 hours), tariff spread (flat/wide), forecast error (0/0.5 of the spread scale), and appliance mix (light/mixed).
- Profiles use 30-minute intervals for a synthetic Melbourne day and contain no measured DER, PV, EV ownership, demographics, or customer data.
- Tariffs are synthetic energy-only AUD rates; supply charges, demand charges, tax structures, export credits, and retailer-specific rules are excluded.
- Appliance powers/durations, baseline shape, 8 kW household cap, preference penalty, and price-noise assumptions are explicit in `config.json`.
- Runtime is hardware-dependent. Case-level results include absolute AUD and the change relative to that same synthetic case's S0 charge; percentage differences are only defined for positive S0 charges.

## Results by strategy

| Strategy | Cases | Mean energy charge (AUD) | Mean change vs S0 (AUD) | Task completion | Mean inconvenience (hours) | Infeasible cases |
|---|---:|---:|---:|---:|---:|---:|
| S0_no_intervention | 24 | 6.712 | 0.000 | 100.0% | 0.00 | 0 |
| S1_rule_based | 24 | 6.171 | 0.542 | 100.0% | 1.75 | 0 |
| S2_forecast_milp | 24 | 6.213 | 0.500 | 100.0% | 2.46 | 0 |
| oracle | 24 | 6.135 | 0.577 | 100.0% | 2.33 | 0 |

## Interpretation limits

- These outcomes are simulated conditional on the declared synthetic profiles and schedule compliance. They do not predict customer participation or realized savings.
- S1 and S2 may perform differently across tariff spread, flexibility, appliance mix, and forecast error; use `summary.csv` to inspect each factorial cell.
- Oracle performance assumes perfect knowledge of realized interval prices and is not a deployable service.
- The benchmark compares energy charges only and does not model complete bills, comfort/health constraints, stochastic task completion, device communication, PV/battery behavior, or diverse customer populations.
- `results.csv` contains per-household absolute values, feasibility, task completion, peak demand, inconvenience, runtime, and savings relative to S0. `summary.csv` contains factorial-cell aggregates.
