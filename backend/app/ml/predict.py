"""Prediction utilities to load saved models and generate suggestions."""
from __future__ import annotations

import os
from typing import Optional

import joblib
import pandas as pd


MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")


def load_forecast_model(meter_id: int):
    """Load Prophet forecast model for a meter, or return None if not found."""
    path = os.path.join(MODEL_DIR, f"meter_{meter_id}_forecast.pkl")
    if os.path.exists(path):
        return joblib.load(path)
    return None


def load_anomaly_model(meter_id: int):
    """Load IsolationForest anomaly model for a meter, or return None if not found."""
    path = os.path.join(MODEL_DIR, f"meter_{meter_id}_anomaly.pkl")
    if os.path.exists(path):
        return joblib.load(path)
    return None


def predict_forecast(meter_id: int, periods: int = 14) -> Optional[dict]:
    """Predict next `periods` days of kWh using Prophet model.

    Returns dict with `forecast_dates` and `forecast_kwh` lists, or None if model not available.
    """
    m = load_forecast_model(meter_id)
    if m is None:
        return None
    try:
        future = m.make_future_dataframe(periods=periods)
        forecast = m.predict(future)
        # Return only future dates
        tail = forecast.tail(periods)
        return {
            "forecast_dates": tail["ds"].dt.strftime("%Y-%m-%d").tolist(),
            "forecast_kwh": tail["yhat"].round(2).tolist(),
        }
    except Exception:
        return None


def detect_anomalies(meter_id: int, df: pd.DataFrame) -> Optional[dict]:
    """Detect anomalous days in the data using trained IsolationForest.

    Returns dict with `anomaly_dates` and `anomaly_values` lists, or None if model not available.
    """
    clf = load_anomaly_model(meter_id)
    if clf is None or df.empty:
        return None
    try:
        X = df[["y"]].to_numpy()
        preds = clf.predict(X)
        anomaly_indices = [i for i, p in enumerate(preds) if p == -1]
        return {
            "anomaly_dates": df.iloc[anomaly_indices]["ds"].astype(str).tolist(),
            "anomaly_values": df.iloc[anomaly_indices]["y"].round(2).tolist(),
        }
    except Exception:
        return None
