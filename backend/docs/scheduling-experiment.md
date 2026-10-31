# Scheduling strategy experiment

## Reproduce the experiment

From `backend/`:

```powershell
python scripts/run_scheduling_experiment.py
```

By default, the script writes reproducible CSVs, configuration, a generated
`REPORT.md`, and three figures under `reports/scheduling_experiment/`. `--households`
and `--seed` change the number of generated profiles and random seed. The other
factor levels are defined in `app/ml/scheduling_experiment.py`. No customer data
or external data download is used.

## Strategies and information available at scheduling time

- **S0 — no intervention:** each task is run at its preferred start.
- **S1 — greedy nominal:** the deterministic greedy reference schedule returned by
  the scheduling optimizer using the nominal synthetic tariff.
- **S2 — MILP nominal:** the optimizer's MILP schedule using the same nominal
  interval-price vector as S1. The matched S2-minus-S1 comparison isolates
  algorithm outcomes under identical price information.
- **S2 — MILP forecast:** MILP schedule using a synthetic estimate perturbed around
  realized future prices. Compare it with nominal MILP to assess forecast-information
  sensitivity separately from algorithm differences.
- **Perfect-information MILP:** the MILP receives realized interval prices and
  optimizes realized energy charge plus the configured preference/inconvenience
  penalty. This is a perfect-information comparator, not an implementable
  scheduling strategy. The report includes both its energy charge and scored
  weighted objective.
- **Energy-only oracle:** the MILP receives realized interval prices and its
  optimization preference penalty is set to zero. It is an energy-charge lower
  bound only within this modeled feasible set; its realized inconvenience and
  common weighted-objective score are still reported.

At scheduling time, the synthetic nominal time-of-use periods and interval price
shape are assumed known. S1 and nominal S2 receive this same vector. The
forecast-informed strategy receives a noisy future-price estimate; realized prices
are used only to score schedules and for the explicitly labeled perfect-information
comparators.

## Billing, cost fields, and objective

The reported energy charge is recomputed from interval-level realized prices and
the sum of exported non-flexible baseline demand and task power at each scheduled
interval. The runner writes `results.csv`, `interval_prices.csv`, and
`task_schedules.csv`, reloads those exported files, and audits every feasible
strategy row against the exported traces. A mismatch greater than `1e-8 AUD`
raises an error and fails the run. Infeasible strategies must have no reported
realized energy charge.

`non_flexible_baseline_energy_cost_aud` is the cost of fixed baseline demand only.
The legacy `baseline_energy_cost_aud` export is retained as a compatibility alias
for that same fixed-demand value; neither field is the complete S0 charge.
`s0_reference_energy_cost_aud` is the full realized energy charge when all tasks
run at preferred starts.

The common weighted objective is the realized energy charge plus
`preference_penalty_aud_per_interval` multiplied by each task's absolute
start-time distance from its preferred time, measured in scheduling intervals.
The configured weight is `0.01 AUD` per interval. It is a modeling weight, not a
validated monetary valuation of comfort or inconvenience. Energy charge,
inconvenience hours and penalty, weighted-objective value, peak demand, and task
completion are reported separately so a lower bill is not presented as an
unqualified overall improvement.

## Synthetic design and price assumptions

The default design uses 30-minute intervals for one synthetic Melbourne day and
crosses flexibility windows of 2, 6, and 10 hours; tariff-spread factors 0 and 1;
forecast-error factors 0 and 0.5; and light and mixed appliance sets. Eight fixed
generated household profiles recur across the 192 design cells. These cells are
not 192 independent households. Paired profile-level intervals first average
repeated differences within each generated profile and are descriptive only; they
do not establish population-level inference.

The nominal synthetic energy-only time-of-use profile uses stylized prices:
off-peak/shoulder/peak values vary from 12/24/42 cents per kWh according to the
spread factor. Realized prices add Gaussian perturbations drawn with mean zero and
standard deviation `0.025 * tariff_spread_factor AUD/kWh`, then apply a
`0.01 AUD/kWh` floor. Forecast estimates add an independent Gaussian perturbation
drawn with mean zero and standard deviation
`0.25 * forecast_error_spread_fraction * tariff_spread_factor AUD/kWh`, then
apply the same floor. Clipping can shift resulting deviations away from zero mean.
These are uncalibrated sensitivity/stress assumptions, not observed Australian
retail tariffs or validated forecast-error distributions.

Baseline loads, appliance power and duration, task windows, and the 8 kW household
power limit are synthetic fixed assumptions. The model excludes retailer
supply/demand charges, tax, export credits, PV/battery behavior, multi-day
dependencies, customer behavior and task non-compliance, device control, and
validated comfort preferences.

## Matched statistics and figures

Paired comparisons include:

1. nominal MILP minus greedy nominal (algorithm comparison under identical nominal
   prices);
2. forecast MILP minus nominal MILP (forecast-information comparison);
3. forecast MILP minus greedy nominal (descriptive combined comparison).

Differences are left minus right, so a negative value favors the left strategy on
the named metric. CSV summaries include matched-cell win/loss/tie counts and
profile-level means with descriptive 95% t intervals. Tie classification uses a
`1e-8 AUD` numerical tolerance. Separate factor-level summaries are provided for
flexibility, forecast-error factor, tariff-spread factor, and appliance mix.
Repeated matched rows contribute to outcome counts, but uncertainty intervals use
the generated profile means, not the repeated rows as independent households.

All figures label the experiment synthetic:

- `paired_s1_s2.png` plots matched S1-versus-S2 nominal energy charges and
  weighted objectives against identity lines.
- `flexibility_forecast_error.png` shows flexibility and forecast-error
  sensitivity.
- `cost_inconvenience.png` plots realized energy charge against start-time
  inconvenience.
- `equity_savings_distribution.png` shows per-generated-profile mean S2 nominal
  charge reductions by flexibility window, with the median and interquartile
  range, faceted into flat-price and TOU synthetic tariff cases. The plotted
  profile means average repeated configurations; the dots are not additional
  independent households.

## Equity and distributional evaluation

The evaluation definitions are fixed before interpreting the generated group
outcomes and are also embedded in `config.json` and `equity_provenance.csv`:

- **Software access:** not measured. Complete synthetic inputs indicate only
  technical eligibility for the pipeline, not that a person can access or use the
  app or advisory service. Account reachability, device/connectivity access,
  accessibility needs, uptake, and user testing are absent.
- **Technical feasibility/completion:** a schedule is technically complete if it
  is feasible and completes all mandatory tasks. Economic worth
  is not classified because no minimum-benefit or welfare threshold is declared.
  Practical actionability, user confirmation/acceptance, and device execution are
  not measured.
- **Benefit distribution:** absolute modeled energy-charge reduction against the
  same case's S0, in AUD, with negative values retained; report alongside
  realized energy-charge levels, inconvenience in hours, and weighted-objective
  change. These are not verified household savings, complete bills, or validated
  welfare outcomes.
- **Uncertainty and size:** summarize at the generated-profile level after
  averaging repeated cells per profile. Include profile count, cell count, and
  descriptive 95% t intervals/10th–90th profile quantiles; do not treat repeated
  configurations as independent households.
- **Permitted grouping:** flexibility hours and appliance mix are synthetic
  scenario labels only. No tenure, income, health, demographic, or protected
  category is inferred from consumption. No consented demographic dataset or
  provenance is present.
- **DER comparisons:** not estimable. Profiles contain no verified PV, BESS,
  generation, or DER ownership dimensions. An EV task in the mixed appliance
  scenario is only a flexible load, not evidence that the household owns DER.
- **Limited-flexibility sensitivity:** pair the same generated profile, tariff
  spread, forecast-error factor, appliance mix, and strategy at a 2-hour window
  against each wider configured window. Report benefit and inconvenience deltas,
  profile-level intervals, win/tie/loss counts, and non-actionable cases.

The generated `equity_summary.csv` groups model outcomes by flexibility and
appliance mix, including energy-charge and savings distributions plus inconvenience
and objective distributions. `equity_flexibility_sensitivity.csv` contains the matched
limited-flexibility analysis, including tariff-spread-specific tie counts. In the
flat-price cases, the model has no energy-price signal to reward shifting; ties
in those cases are not evidence of equivalent performance under TOU tariffs.
`equity_boundary_cases.csv` includes a feasible mandatory task with one allowed
start, a constructed case where a 0.005 AUD potential energy-charge reduction is
smaller than the configured 0.01 AUD preference penalty, and an unavailable-
appliance case marked not representable by the v1 request (which requires a
task and has no appliance-availability field). These are optimizer checks, not
simulated customer groups or user behavior.
In `equity_summary.csv` and `equity_flexibility_sensitivity.csv`, fields prefixed
with `technically_incomplete_or_infeasible` are the explicit technical metrics.
Legacy `no_actionable_*` fields are retained as aliases and must not be read as
user acceptance or practical actionability.
`equity_provenance.csv` records the source fields,
metric definitions, missing categories, and interpretation boundaries. These
summaries distinguish technical pipeline eligibility from software access and
software output from verified energy-equity outcomes; they do not justify poverty
reduction, demographic fairness, or observed customer-benefit claims.

## Robustness cases

`robustness.csv` records:

- a single-slot appliance window made infeasible by the household power cap;
- two individually schedulable single-slot tasks whose combined power violates
  the cap;
- baseline demand already above the cap;
- a measured greedy-suboptimal case, including the MILP-minus-greedy energy-charge
  difference; and
- an injected solver `RuntimeError`, reported explicitly as `solver_error` rather
  than converted to a feasible fallback.

The invalid task-window shape that fails request-schema validation is not passed
to the optimizer; the reported window robustness case is valid under the API
contract but impossible under its physical power-cap constraint.

## Generated files and limitations

The output directory contains:

- `results.csv`, `summary.csv`
- `paired_comparisons.csv`, `paired_summary.csv`
- `equity_summary.csv`, `equity_flexibility_sensitivity.csv`,
  `equity_provenance.csv`, `equity_boundary_cases.csv`
- `interval_prices.csv`, `task_schedules.csv`
- `robustness.csv`, `config.json`, `REPORT.md`
- `paired_s1_s2.png`, `flexibility_forecast_error.png`,
  `cost_inconvenience.png`
  `equity_savings_distribution.png`

The configuration captures the seed, design, simulation date, assumptions,
solver/library versions, platform, and output row counts. Every input profile,
tariff, price deviation, appliance, and outcome is synthetic. Reported AUD values
are modeled energy charges, not complete bills, observed retail prices, customer
savings, or measured behavior. Results should not be generalized beyond these
scenarios.
