# Forecast evaluation results

This report evaluates daily active-energy consumption for one public research household. It is not a GridSense customer study, household bill estimate, or evidence of savings.

## Protocol

- Household: `uci_sceaux_household_1` (one home in Sceaux, France; no household-level generalization is possible).
- Target: daily kWh derived from UCI `Global_active_power` (minute-average kW divided by 60 and summed). PV generation and behind-the-meter generation are not identified or separated by this target.
- Dataset interval: 2006-12-16 through 2010-11-26; 1407 daily targets retained at 99% or better minute coverage.
- Chronological split: train through 2009-09-19; validation 2009-09-20–2010-04-23; test 2010-04-24–2010-11-26.
- Rolling origins are spaced 7 days apart. Each forecast uses only nonmissing target values dated on or before its origin. Forecasts at a given horizon overlap across origins; counts are not independent samples.
- Missing minute readings are not interpolated. Days below the 99% minute-coverage threshold are excluded as targets and training observations. Actual daily energy sums available valid minute-average power readings.
- Baselines: previous valid daily value repeated (persistence) and mean of prior same-weekday values from the preceding 28 calendar days (fallback: prior-history mean).
- ML comparator: the repository's Prophet implementation, fit independently at each origin; 200 predictive samples and nominal 80% intervals are used for tractable, repeatable interval evaluation.
- Source archive SHA-256: `9f84b46ade8a2d8e1286ec4b2b6c2987a45a755c59f263be3b3b3d10dfbda3ff`.
- Source data SHA-256: `4259c9d7ece5dbee9ab8d53682baac68d791c864f0f64a52b4043cb3b90894b7`.

## Test metrics

| Model | Horizon | Forecasts | MAE (kWh) | RMSE (kWh) | 80% interval coverage | Mean interval width (kWh) |
|---|---:|---:|---:|---:|---:|---:|
| persistence | 1 day(s) | 28 | 4.952 | 6.628 | not provided | not provided |
| prophet | 1 day(s) | 28 | 5.320 | 6.156 | 96.4% | 18.015 |
| weekday_mean_28d | 1 day(s) | 28 | 6.158 | 7.537 | not provided | not provided |
| prophet | 7 day(s) | 29 | 3.169 | 4.659 | 96.6% | 17.337 |
| persistence | 7 day(s) | 29 | 3.832 | 5.458 | not provided | not provided |
| weekday_mean_28d | 7 day(s) | 29 | 4.154 | 6.084 | not provided | not provided |
| prophet | 14 day(s) | 28 | 3.269 | 4.765 | 96.4% | 17.368 |
| weekday_mean_28d | 14 day(s) | 28 | 4.665 | 6.759 | not provided | not provided |
| persistence | 14 day(s) | 28 | 4.893 | 7.094 | not provided | not provided |

## Limitations

- The public benchmark represents one French household, not Australian households or GridSense users. Results are descriptive, not statistically representative.
- The dataset has no verified PV/generation or NEM12 import/export classification; net demand and underlying load cannot be compared separately.
- Forecast intervals are model-based uncertainty estimates, not calibrated guarantees. Baselines do not provide intervals.
- Seasonal subgroup estimates can have small sample counts; inspect `metrics.csv` before interpreting those rows.
- No tariff is applied. These kWh metrics cannot support bill or savings claims.
- A single expanding-window split and public dataset do not establish deployment performance. Missingness and meter quality may differ in real data.

## Artifacts

- `predictions.csv`: per-origin, per-horizon observed and forecast values.
- `metrics.csv`: MAE, RMSE, sample counts, and Prophet interval diagnostics by household, phase, season, and horizon.
- `config.json`: dataset digest, split dates, model setup, seeds, and package versions.
- `forecast_evaluation.png`: test MAE by forecast horizon and model.
- `DATASET_README.md`: source, attribution, license, coverage, and preprocessing details.
