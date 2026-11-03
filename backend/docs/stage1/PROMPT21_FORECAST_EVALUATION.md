# Prompt 21 — chronological forecast evaluation

**Disposition: PARTIAL — forecasting remains disabled for product advice.**

## Evidence and protocol

This assessment uses the repository's existing chronological evaluation
artifacts in `backend/reports/forecast_evaluation/`. The underlying UCI
minute-level dataset is not bundled in the workspace, so this Prompt 21 update
did not download the data or claim a fresh full model run. The existing
predictions, metrics, report, and configuration were inspected and retained.
The evaluation code and unit tests were extended to report MAE changes against
the best baseline for the same phase, season, and horizon.

The source is UCI's Individual Household Electric Power Consumption dataset,
one household in Sceaux, France. Its reported source-data SHA-256 is
`4259c9d7ece5dbee9ab8d53682baac68d791c864f0f64a52b4043cb3b90894b7`.
Valid minute-average active power was converted to daily kWh; days below 99%
minute coverage were excluded rather than imputed. The saved run retains
1,407 daily targets from 16 December 2006 through 26 November 2010. The
chronological split is train through 19 September 2009, validation from
20 September 2009 through 23 April 2010, and test from 24 April through
26 November 2010. Origins are spaced seven days apart, and each model is fit
using only observations dated on or before that origin.

Compared methods are persistence, a 28-day same-weekday mean (with historical
mean fallback), and Prophet. The forecast horizons and scored dates are
identical across models. The test samples are 28, 29, and 28 forecast records
for one-, seven-, and fourteen-day horizons. Overlapping rolling-origin
forecasts mean these are not independent samples.

## Held-out test results

The relative MAE is `(Prophet MAE / best baseline MAE - 1) × 100%`; negative is
lower error than the best baseline.

| Horizon | N | Best baseline MAE (kWh) | Prophet MAE (kWh) | Prophet RMSE (kWh) | MAE change vs best baseline | Prophet nominal 80% interval coverage |
|---:|---:|---:|---:|---:|---:|---:|
| 1 day | 28 | 4.952 (persistence) | 5.320 | 6.156 | +7.4% | 96.4% |
| 7 days | 29 | 3.832 (persistence) | 3.169 | 4.659 | -17.3% | 96.6% |
| 14 days | 28 | 4.665 (weekday mean) | 3.269 | 4.765 | -29.9% | 96.4% |

The new summary output adds `best_baseline_model`,
`best_baseline_mae_kwh`, and `mae_change_vs_best_baseline_percent` to the
metrics table. Existing code tests verify that this baseline-relative metric
is derived from matched phase/season/horizon samples.

## Interpretation and leakage boundary

- Prophet does not outperform the best baseline at every test horizon; its
  one-day MAE is 7.4% higher than persistence. At 14 days the best baseline is
  the weekday mean, not persistence. The longer-horizon improvements in this
  single-household test do not establish deployment superiority.
- The nominal 80% Prophet intervals cover about 96% of the test observations.
  This sample suggests over-coverage and does not establish calibrated
  uncertainty. Persistence and weekday baselines do not provide intervals.
- No weather features were used. The existing Open-Meteo data path does not
  provide verified historical issue-time evidence for these past forecast
  origins. No future realized weather was represented as a forecast known at
  an earlier time.
- No retailer tariff was applied, and the target has no validated
  import/export or PV separation. These results do not support bills, savings,
  Australian household performance, or customer-specific recommendations.
- No predeclared product acceptance threshold has been met. Forecast-derived
  advice remains unavailable pending a suitable chronological evaluation,
  calibrated uncertainty assessment, and issue-time-valid feature evidence.

The original run's detailed per-origin CSVs and environment configuration
remain in `backend/reports/forecast_evaluation/`; this report does not replace
those artifacts or claim the source dataset is available in this checkout.
