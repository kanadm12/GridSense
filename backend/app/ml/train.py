"""Training utilities for forecasting and anomaly detection models."""
from __future__ import annotations

import os
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from prophet import Prophet
from sklearn.ensemble import IsolationForest

from app.config import get_settings


MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
os.makedirs(MODEL_DIR, exist_ok=True)


def train_forecast(df: pd.DataFrame, meter_id: int, periods: int = 14) -> dict:
    """Train a Prophet forecasting model on `df` (ds,y). Saves model to disk.

    Returns a dict with a small report and path to saved model.
    """
    if df.empty or len(df) < 10:
        raise ValueError("Not enough data to train forecast model")

    m = Prophet()
    # Prophet expects ds as datetimes
    dfp = df.copy()
    dfp["ds"] = pd.to_datetime(dfp["ds"])
    m.fit(dfp)

    future = m.make_future_dataframe(periods=periods)
    forecast = m.predict(future)

    save_path = os.path.join(MODEL_DIR, f"meter_{meter_id}_forecast.pkl")
    joblib.dump(m, save_path)

    return {"model_path": save_path, "forecast_tail": forecast[["ds", "yhat"]].tail(periods).to_dict(orient="list")}


def train_anomaly_detector(df: pd.DataFrame, meter_id: int) -> dict:
    """Train an IsolationForest on daily kWh to flag anomalous days.

    Saves model and returns metrics.
    """
    if df.empty or len(df) < 20:
        raise ValueError("Not enough data to train anomaly detector")

    X = df[["y"]].to_numpy()
    clf = IsolationForest(n_estimators=100, contamination=0.01, random_state=42)
    clf.fit(X)

    preds = clf.predict(X)
    anomalies = int((preds == -1).sum())

    save_path = os.path.join(MODEL_DIR, f"meter_{meter_id}_anomaly.pkl")
    joblib.dump(clf, save_path)

    return {"model_path": save_path, "n_samples": len(X), "n_anomalies": anomalies}
