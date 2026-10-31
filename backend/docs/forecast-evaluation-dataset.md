# Forecast evaluation dataset

## Selected dataset and permitted use

The evaluation uses the **Individual Household Electric Power Consumption** dataset from the UCI Machine Learning Repository:

- Citation: Georges Hebrail and Alice Berard (2006), *Individual Household Electric Power Consumption*, UCI Machine Learning Repository, DOI [10.24432/C58K54](https://doi.org/10.24432/C58K54).
- Dataset page and download: <https://archive.ics.uci.edu/dataset/235/individual+household+electric+power+consumption>
- License: Creative Commons Attribution 4.0 International (CC BY 4.0), as stated on the UCI dataset page. Any redistribution or adaptation must retain attribution and the license terms.
- Coverage: 2,075,259 minute-level records from one household in Sceaux, France, from December 2006 through November 2010. The archive reports roughly 1.25% missing measurement rows/values.

The dataset is public research data and is **not** GridSense customer data. It represents one French household only. The repository does not bundle the 126.8 MB uncompressed source. The evaluation command downloads and caches the UCI ZIP archive; alternatively, pass the extracted text file with `--dataset`.

## Forecast target and preparation

The target is daily household active energy in kWh. `Global_active_power` is minute-average kW; valid nonnegative values are divided by 60 and summed by local calendar day. Source timestamps are interpreted in `Europe/Paris` solely to calculate expected minutes on daylight-saving transition days. Empty/invalid power values are not interpolated. Days with less than 99% of expected valid minute samples are marked missing and excluded from both fitting and scored targets.

The data does not document a verified PV generation channel or provide an import/export direction classification. Therefore this experiment evaluates the published active-power consumption target only; it does not claim to separate grid net demand from behind-the-meter generation or estimate an underlying-load counterfactual.

## Leakage controls and split

The calendar is divided chronologically into 70% training, 15% validation, and 15% test ranges. Validation and test forecasts use seven-day-spaced expanding origins. At each origin, only valid daily observations dated on or before that origin are used. Predictions are scored at calendar horizons 1, 7, and 14 days. Origins are partially overlapping, so repeated forecasts of a date are not independent observations. Validation results are reported separately and are not used to tune model settings; the test period is held out from model development.

## Metrics and limitations

The run compares persistence, a 28-day historical weekday mean, and the repository's Prophet model. It exports MAE and RMSE in kWh, sample counts, Prophet nominal 80% interval coverage and width, and results by season, horizon, and split. This single-household benchmark is descriptive only. Small seasonal samples, forecast-interval calibration, source quality, and geographic transferability limit interpretation. No tariff is applied; these results support no bill or savings claim.

Run from `backend/`:

```powershell
python scripts/evaluate_forecasting.py
```

Outputs are written to `backend/reports/forecast_evaluation/`. Dataset metadata, archive/source SHA-256 digests, split dates, model parameters, random seed, and library versions are recorded in the generated configuration.
