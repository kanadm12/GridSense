"""Unit checks for leakage-safe forecast evaluation helpers."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.ml.forecast_evaluation import (
    ChronologicalSplit,
    chronological_split,
    daily_targets_from_frame,
    evaluate_forecasts,
    summarize_predictions,
)


def test_daily_targets_exclude_low_coverage_without_imputation():
    first_day = pd.date_range("2024-01-01", periods=1440, freq="min")
    frame = pd.DataFrame(
        {
            "Date": first_day.strftime("%d/%m/%Y"),
            "Time": first_day.strftime("%H:%M:%S"),
            "Global_active_power": ["1.0"] * len(first_day),
        }
    )
    frame.loc[1, "Global_active_power"] = "?"
    partial_day = pd.DataFrame(
        {
            "Date": ["02/01/2024"] * 2,
            "Time": ["00:00:00", "00:01:00"],
            "Global_active_power": ["2.0", "4.0"],
        }
    )
    frame = pd.concat([frame, partial_day], ignore_index=True)

    daily = daily_targets_from_frame(frame, minimum_coverage=0.99)

    assert daily.loc[0, "valid_minutes"] == 1439
    assert daily.loc[0, "y_kwh"] == pytest.approx(1439 / 60)
    assert daily.loc[1, "valid_minutes"] == 2
    assert pd.isna(daily.loc[1, "y_kwh"])


def test_chronological_split_is_disjoint_and_ordered():
    dates = pd.date_range("2020-01-01", periods=100, freq="D")
    daily = pd.DataFrame({"date": dates, "y_kwh": np.arange(len(dates), dtype=float)})

    split = chronological_split(daily)

    assert split.train_end < split.validation_start
    assert split.validation_end < split.test_start
    assert split.test_end == dates[-1].date()


def test_evaluation_training_history_never_reaches_forecast_target(monkeypatch):
    start = date(2020, 1, 1)
    dates = pd.date_range(start, periods=140, freq="D")
    daily = pd.DataFrame({"date": dates, "y_kwh": np.arange(len(dates), dtype=float)})
    split = ChronologicalSplit(
        train_end=(dates[69]).date(),
        validation_start=(dates[70]).date(),
        validation_end=(dates[84]).date(),
        test_start=(dates[85]).date(),
        test_end=(dates[-1]).date(),
    )
    seen_training_dates: list[pd.Timestamp] = []

    def fake_prophet(history, future_dates):
        assert history.index.max() < future_dates.min()
        seen_training_dates.append(history.index.max())
        values = np.full(len(future_dates), float(history.iloc[-1]))
        return values, values - 1, values + 1

    monkeypatch.setattr("app.ml.forecast_evaluation._prophet_predictions", fake_prophet)
    results = evaluate_forecasts(daily, split, horizons=(1, 7, 14))

    assert not results.empty
    assert (pd.to_datetime(results["origin_date"]) < pd.to_datetime(results["target_date"])).all()
    assert results["phase"].isin(["validation", "test"]).all()
    assert seen_training_dates
    assert max(seen_training_dates) < pd.to_datetime(split.test_end)


def test_evaluation_rejects_nonpositive_horizon():
    dates = pd.date_range("2020-01-01", periods=100, freq="D")
    daily = pd.DataFrame({"date": dates, "y_kwh": np.arange(len(dates), dtype=float)})
    split = chronological_split(daily)

    with pytest.raises(ValueError, match="positive calendar-day"):
        evaluate_forecasts(daily, split, horizons=(0,))


def test_chronological_split_requires_sufficient_days():
    dates = pd.date_range("2020-01-01", periods=59, freq="D")
    daily = pd.DataFrame({"date": dates, "y_kwh": np.arange(len(dates), dtype=float)})

    with pytest.raises(ValueError, match="60 calendar days"):
        chronological_split(daily)


def test_summary_has_one_overall_row_per_model_and_horizon():
    predictions = pd.DataFrame(
        [
            {
                "household": "home",
                "phase": "test",
                "model": model,
                "season": season,
                "horizon_days": 1,
                "actual_kwh": actual,
                "error_kwh": error,
                "lower_80_kwh": np.nan,
                "upper_80_kwh": np.nan,
                "interval_covered": None,
                "fit_runtime_ms": 0.0,
            }
            for model in ["persistence", "prophet"]
            for season, actual, error in [("DJF", 10.0, 2.0), ("MAM", 20.0, -4.0)]
        ]
    )

    metrics = summarize_predictions(predictions)
    overall = metrics.loc[metrics["season"] == "ALL"]

    assert len(overall) == 2
    assert set(overall["model"]) == {"persistence", "prophet"}
    assert (overall["n_forecasts"] == 2).all()
    assert (overall["mae_kwh"] == 3.0).all()
    prophet_row = overall.loc[overall["model"] == "prophet"].iloc[0]
    assert prophet_row["best_baseline_model"] == "persistence"
    assert prophet_row["mae_change_vs_best_baseline_percent"] == pytest.approx(0.0)
