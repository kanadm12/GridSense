ML training pipeline (development)
================================

This provides simple scripts to extract daily time-series from the database and train two baseline models per meter:

- `Prophet` forecasting model (daily kWh forecast)
- `IsolationForest` anomaly detector on daily kWh

Quick start (dev):

1. Ensure database exists and contains `daily_aggregates` data for meters.
2. Run training for a single meter:

```bash
python -m app.ml.cli train-meter --meter-id 1
```

Or train all meters:

```bash
python -m app.ml.cli train-all
```

Models are saved under `app/models/` as `meter_{id}_forecast.pkl` and `meter_{id}_anomaly.pkl`.

Notes:
- These are baseline implementations meant to be iterated on. Next steps: hyperparameter tuning, cross-validation, automated retraining, evaluation dashboards, and model registry.
