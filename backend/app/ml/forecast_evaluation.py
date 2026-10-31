"""Reproducible, chronological evaluation of daily household-load forecasts."""

from __future__ import annotations

import hashlib
import json
import math
import random
import shutil
import time
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from datetime import time as datetime_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from prophet import Prophet

DATASET_URL = (
    "https://archive.ics.uci.edu/static/public/235/"
    "individual+household+electric+power+consumption.zip"
)
DATASET_FILENAME = "household_power_consumption.txt"
DATASET_TIMEZONE = "Europe/Paris"
HOUSEHOLD_ID = "uci_sceaux_household_1"
FORECAST_HORIZONS = (1, 7, 14)
ORIGIN_STEP_DAYS = 7
MINIMUM_DAILY_COVERAGE = 0.99
RANDOM_SEED = 42


@dataclass(frozen=True)
class ChronologicalSplit:
    train_end: date
    validation_start: date
    validation_end: date
    test_start: date
    test_end: date


def _expected_minutes(day: date, timezone_name: str) -> int:
    zone = ZoneInfo(timezone_name)
    start = datetime.combine(day, datetime_time.min, tzinfo=zone).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), datetime_time.min, tzinfo=zone).astimezone(
        timezone.utc
    )
    return int((end - start).total_seconds() // 60)


def daily_targets_from_frame(
    frame: pd.DataFrame,
    minimum_coverage: float = MINIMUM_DAILY_COVERAGE,
    timezone_name: str = DATASET_TIMEZONE,
) -> pd.DataFrame:
    """Convert minute-average kW samples to daily kWh without imputing missing values."""
    required = {"Date", "Time", "Global_active_power"}
    missing_columns = required.difference(frame.columns)
    if missing_columns:
        raise ValueError(f"Dataset is missing required columns: {sorted(missing_columns)}")
    if not 0 < minimum_coverage <= 1:
        raise ValueError("minimum_coverage must be greater than 0 and no more than 1")

    timestamps = pd.to_datetime(
        frame["Date"].astype(str) + " " + frame["Time"].astype(str),
        format="%d/%m/%Y %H:%M:%S",
        errors="coerce",
    )
    power_kw = pd.to_numeric(frame["Global_active_power"], errors="coerce")
    valid = timestamps.notna() & power_kw.notna() & power_kw.ge(0)
    if not valid.any():
        raise ValueError("Dataset contains no valid nonnegative active-power readings")

    rows = pd.DataFrame(
        {
            "date": timestamps.loc[valid].dt.date,
            "power_kw": power_kw.loc[valid].astype(float),
        }
    )
    grouped = rows.groupby("date")["power_kw"].agg(["sum", "count"])
    first_day = min(grouped.index)
    last_day = max(grouped.index)
    dates = pd.date_range(first_day, last_day, freq="D")
    result = pd.DataFrame(index=dates)
    result.index.name = "date"
    result["valid_minutes"] = [int(grouped["count"].get(day.date(), 0)) for day in dates]
    result["expected_minutes"] = [_expected_minutes(day.date(), timezone_name) for day in dates]
    result["coverage"] = result["valid_minutes"] / result["expected_minutes"]
    result["y_kwh"] = [float(grouped["sum"].get(day.date(), np.nan)) / 60.0 for day in dates]
    result.loc[result["coverage"] < minimum_coverage, "y_kwh"] = np.nan
    return result.reset_index()


def load_daily_targets(
    dataset_path: Path,
    minimum_coverage: float = MINIMUM_DAILY_COVERAGE,
) -> pd.DataFrame:
    frame = pd.read_csv(
        dataset_path,
        sep=";",
        usecols=["Date", "Time", "Global_active_power"],
        na_values=["?", ""],
        dtype={"Date": "string", "Time": "string", "Global_active_power": "string"},
    )
    return daily_targets_from_frame(frame, minimum_coverage=minimum_coverage)


def chronological_split(daily: pd.DataFrame) -> ChronologicalSplit:
    if daily.empty or "date" not in daily or "y_kwh" not in daily:
        raise ValueError("At least one dated observation with a daily target is required")
    parsed_dates = pd.to_datetime(daily["date"])
    if parsed_dates.duplicated().any():
        raise ValueError("Daily target dates must be unique")
    dates = pd.DatetimeIndex(parsed_dates.sort_values().unique())
    if len(dates) < 60:
        raise ValueError("At least 60 calendar days are required for chronological evaluation")
    if not dates.is_monotonic_increasing or dates.has_duplicates:
        raise ValueError("Daily target dates must be unique and chronologically sorted")
    train_position = math.floor(len(dates) * 0.70) - 1
    validation_position = math.floor(len(dates) * 0.85) - 1
    split = ChronologicalSplit(
        train_end=dates[train_position].date(),
        validation_start=(dates[train_position] + pd.Timedelta(days=1)).date(),
        validation_end=dates[validation_position].date(),
        test_start=(dates[validation_position] + pd.Timedelta(days=1)).date(),
        test_end=dates[-1].date(),
    )
    assert split.train_end < split.validation_start <= split.validation_end
    assert split.validation_end < split.test_start <= split.test_end
    return split


def _origins(start: date, end: date, horizons: tuple[int, ...]) -> list[date]:
    maximum_horizon = max(horizons)
    origin = start - timedelta(days=1)
    last_origin = end - timedelta(days=maximum_horizon)
    values = []
    while origin <= last_origin:
        values.append(origin)
        origin += timedelta(days=ORIGIN_STEP_DAYS)
    return values


def _season(day: date) -> str:
    if day.month in (12, 1, 2):
        return "DJF"
    if day.month in (3, 4, 5):
        return "MAM"
    if day.month in (6, 7, 8):
        return "JJA"
    return "SON"


def _baseline_predictions(
    history: pd.Series,
    future_dates: pd.DatetimeIndex,
) -> dict[str, np.ndarray]:
    observed = history.dropna().sort_index()
    if observed.empty:
        raise ValueError("Cannot forecast without valid training observations")
    persistence = float(observed.iloc[-1])
    predictions: dict[str, list[float]] = {
        "persistence": [],
        "weekday_mean_28d": [],
    }
    for future_date in future_dates:
        recent = observed.loc[
            (observed.index >= future_date - pd.Timedelta(days=28)) & (observed.index < future_date)
        ]
        same_weekday = recent.loc[recent.index.dayofweek == future_date.dayofweek]
        history_mean = (
            float(same_weekday.mean()) if not same_weekday.empty else float(observed.mean())
        )
        predictions["persistence"].append(persistence)
        predictions["weekday_mean_28d"].append(history_mean)
    return {name: np.asarray(values, dtype=float) for name, values in predictions.items()}


def _prophet_predictions(
    history: pd.Series,
    future_dates: pd.DatetimeIndex,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    train = history.dropna().rename("y").rename_axis("ds").reset_index()
    model = Prophet(uncertainty_samples=200)
    model.fit(train)
    forecast = model.predict(pd.DataFrame({"ds": future_dates}))
    return (
        forecast["yhat"].to_numpy(dtype=float),
        forecast["yhat_lower"].to_numpy(dtype=float),
        forecast["yhat_upper"].to_numpy(dtype=float),
    )


def evaluate_forecasts(
    daily: pd.DataFrame,
    split: ChronologicalSplit,
    horizons: tuple[int, ...] = FORECAST_HORIZONS,
) -> pd.DataFrame:
    """Run expanding-window forecasts; only data dated before each origin is fitted."""
    if not horizons or any(horizon < 1 for horizon in horizons):
        raise ValueError("Forecast horizons must be positive calendar-day counts")
    data = daily.copy()
    data["date"] = pd.to_datetime(data["date"]).dt.normalize()
    series = data.set_index("date")["y_kwh"].astype(float).sort_index()
    if series.index.has_duplicates:
        raise ValueError("Daily target dates must be unique")

    split_ranges = {
        "validation": (split.validation_start, split.validation_end),
        "test": (split.test_start, split.test_end),
    }
    rows: list[dict[str, Any]] = []
    np.random.seed(RANDOM_SEED)
    random.seed(RANDOM_SEED)

    for phase, (phase_start, phase_end) in split_ranges.items():
        for origin in _origins(phase_start, phase_end, horizons):
            origin_timestamp = pd.Timestamp(origin)
            future_dates = pd.date_range(
                origin_timestamp + pd.Timedelta(days=1),
                periods=max(horizons),
                freq="D",
            )
            history = series.loc[series.index <= origin_timestamp].dropna()
            if history.empty:
                continue
            actuals = series.reindex(future_dates)
            baseline = _baseline_predictions(history, future_dates)
            start_time = time.perf_counter()
            prophet_values, prophet_lower, prophet_upper = _prophet_predictions(
                history, future_dates
            )
            prophet_runtime_ms = (time.perf_counter() - start_time) * 1000
            model_values = {
                **baseline,
                "prophet": prophet_values,
            }

            for horizon in horizons:
                target_date = future_dates[horizon - 1]
                actual = actuals.iloc[horizon - 1]
                if pd.isna(actual):
                    continue
                for model_name, values in model_values.items():
                    lower = prophet_lower[horizon - 1] if model_name == "prophet" else np.nan
                    upper = prophet_upper[horizon - 1] if model_name == "prophet" else np.nan
                    prediction = float(values[horizon - 1])
                    rows.append(
                        {
                            "household": HOUSEHOLD_ID,
                            "phase": phase,
                            "origin_date": origin,
                            "target_date": target_date.date(),
                            "season": _season(target_date.date()),
                            "horizon_days": horizon,
                            "model": model_name,
                            "actual_kwh": float(actual),
                            "prediction_kwh": prediction,
                            "error_kwh": prediction - float(actual),
                            "absolute_error_kwh": abs(prediction - float(actual)),
                            "squared_error_kwh2": (prediction - float(actual)) ** 2,
                            "lower_80_kwh": lower,
                            "upper_80_kwh": upper,
                            "interval_covered": (
                                bool(lower <= float(actual) <= upper)
                                if model_name == "prophet"
                                else None
                            ),
                            "interval_width_kwh": (
                                float(upper - lower) if model_name == "prophet" else np.nan
                            ),
                            "fit_runtime_ms": (
                                prophet_runtime_ms if model_name == "prophet" else 0.0
                            ),
                        }
                    )

    if not rows:
        raise ValueError("No complete validation or test forecasts could be evaluated")
    result = pd.DataFrame(rows)
    if not (pd.to_datetime(result["origin_date"]) < pd.to_datetime(result["target_date"])).all():
        raise AssertionError("Forecast origin must precede every target date")
    if not result["phase"].isin(["validation", "test"]).all():
        raise AssertionError("Forecast predictions must belong to validation or test")
    return result


def summarize_predictions(predictions: pd.DataFrame) -> pd.DataFrame:
    group_keys = ["household", "phase", "model", "season", "horizon_days"]
    rows = []
    for season in ["ALL", *sorted(predictions["season"].unique())]:
        season_predictions = (
            predictions if season == "ALL" else predictions.loc[predictions["season"] == season]
        )
        keys = ["household", "phase", "model", "horizon_days"] if season == "ALL" else group_keys
        for values, group in season_predictions.groupby(keys, dropna=False, sort=True):
            errors = group["error_kwh"].to_numpy(dtype=float)
            actual = group["actual_kwh"].to_numpy(dtype=float)
            lower = group["lower_80_kwh"].to_numpy(dtype=float)
            upper = group["upper_80_kwh"].to_numpy(dtype=float)
            has_intervals = np.isfinite(lower) & np.isfinite(upper)
            row_keys = dict(zip(keys, values, strict=True))
            if season == "ALL":
                row_keys["season"] = season
            rows.append(
                {
                    **row_keys,
                    "n_forecasts": len(group),
                    "mae_kwh": float(np.mean(np.abs(errors))),
                    "rmse_kwh": float(np.sqrt(np.mean(np.square(errors)))),
                    "actual_mean_kwh": float(np.mean(actual)),
                    "interval_coverage_80": (
                        float(group.loc[has_intervals, "interval_covered"].astype(float).mean())
                        if has_intervals.any()
                        else np.nan
                    ),
                    "mean_interval_width_kwh": (
                        float(np.mean(upper[has_intervals] - lower[has_intervals]))
                        if has_intervals.any()
                        else np.nan
                    ),
                    "mean_prophet_fit_runtime_ms": (
                        float(group["fit_runtime_ms"].mean())
                        if (group["model"] == "prophet").any()
                        else 0.0
                    ),
                }
            )
    return pd.DataFrame(rows)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def acquire_dataset(cache_dir: Path) -> tuple[Path, Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = cache_dir / DATASET_FILENAME
    archive_path = cache_dir / "uci_household_power_consumption.zip"
    if dataset_path.exists():
        return dataset_path, archive_path

    temporary_archive = archive_path.with_suffix(".zip.download")
    request = urllib.request.Request(
        DATASET_URL,
        headers={"User-Agent": "GridSense-forecast-evaluation/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            with temporary_archive.open("wb") as target:
                shutil.copyfileobj(response, target)
        with zipfile.ZipFile(temporary_archive) as archive:
            member = next(
                (name for name in archive.namelist() if Path(name).name == DATASET_FILENAME),
                None,
            )
            if member is None:
                raise ValueError(f"UCI archive does not contain {DATASET_FILENAME}")
            with archive.open(member) as source, dataset_path.open("wb") as target:
                shutil.copyfileobj(source, target)
        temporary_archive.replace(archive_path)
    finally:
        temporary_archive.unlink(missing_ok=True)
    return dataset_path, archive_path


def write_report(
    output_dir: Path,
    split: ChronologicalSplit,
    daily: pd.DataFrame,
    metrics: pd.DataFrame,
    dataset_path: Path,
    archive_path: Path,
) -> None:
    test_overall = metrics.loc[
        (metrics["phase"] == "test") & (metrics["season"] == "ALL")
    ].sort_values(["horizon_days", "mae_kwh"])
    lines = [
        "# Forecast evaluation results",
        "",
        "This report evaluates daily active-energy consumption for one public research household. "
        "It is not a GridSense customer study, household bill estimate, or evidence of savings.",
        "",
        "## Protocol",
        "",
        f"- Household: `{HOUSEHOLD_ID}` (one home in Sceaux, France; no household-level "
        "generalization is possible).",
        "- Target: daily kWh derived from UCI `Global_active_power` (minute-average kW divided "
        "by 60 and summed). PV generation and behind-the-meter generation are not identified "
        "or separated by this target.",
        f"- Dataset interval: {daily['date'].min().date()} through {daily['date'].max().date()}; "
        f"{int(daily['y_kwh'].notna().sum())} daily targets retained at "
        f"{MINIMUM_DAILY_COVERAGE:.0%} or better minute coverage.",
        f"- Chronological split: train through {split.train_end}; validation "
        f"{split.validation_start}–{split.validation_end}; "
        f"test {split.test_start}–{split.test_end}.",
        f"- Rolling origins are spaced {ORIGIN_STEP_DAYS} days apart. Each forecast uses "
        "only nonmissing target values dated on or before its origin. Forecasts at a given "
        "horizon overlap across origins; counts are not independent samples.",
        "- Missing minute readings are not interpolated. Days below the 99% minute-coverage "
        "threshold are excluded as targets and training observations. Actual daily energy sums "
        "available valid minute-average power readings.",
        "- Baselines: previous valid daily value repeated (persistence) and mean of prior "
        "same-weekday values from the preceding 28 calendar days (fallback: prior-history mean).",
        "- ML comparator: the repository's Prophet implementation, fit independently at each "
        "origin; 200 predictive samples and nominal 80% intervals are used for tractable, "
        "repeatable interval evaluation.",
        f"- Source archive SHA-256: "
        f"`{_sha256(archive_path) if archive_path.exists() else 'not cached'}`.",
        f"- Source data SHA-256: `{_sha256(dataset_path)}`.",
        "",
        "## Test metrics",
        "",
        "| Model | Horizon | Forecasts | MAE (kWh) | RMSE (kWh) | "
        "80% interval coverage | Mean interval width (kWh) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in test_overall.iterrows():
        coverage = (
            f"{row['interval_coverage_80']:.1%}"
            if pd.notna(row["interval_coverage_80"])
            else "not provided"
        )
        width = (
            f"{row['mean_interval_width_kwh']:.3f}"
            if pd.notna(row["mean_interval_width_kwh"])
            else "not provided"
        )
        lines.append(
            f"| {row['model']} | {int(row['horizon_days'])} day(s) | "
            f"{int(row['n_forecasts'])} | {row['mae_kwh']:.3f} | {row['rmse_kwh']:.3f} | "
            f"{coverage} | {width} |"
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- The public benchmark represents one French household, not Australian households "
            "or GridSense users. Results are descriptive, not statistically representative.",
            "- The dataset has no verified PV/generation or NEM12 import/export classification; "
            "net demand and underlying load cannot be compared separately.",
            "- Forecast intervals are model-based uncertainty estimates, "
            "not calibrated guarantees. "
            "Baselines do not provide intervals.",
            "- Seasonal subgroup estimates can have small sample counts; inspect `metrics.csv` "
            "before interpreting those rows.",
            "- No tariff is applied. These kWh metrics cannot support bill or savings claims.",
            "- A single expanding-window split and public dataset do not establish deployment "
            "performance. Missingness and meter quality may differ in real data.",
            "",
            "## Artifacts",
            "",
            "- `predictions.csv`: per-origin, per-horizon observed and forecast values.",
            "- `metrics.csv`: MAE, RMSE, sample counts, and Prophet interval diagnostics by "
            "household, phase, season, and horizon.",
            "- `config.json`: dataset digest, split dates, model setup, seeds, "
            "and package versions.",
            "- `forecast_evaluation.png`: test MAE by forecast horizon and model.",
            "- `DATASET_README.md`: source, attribution, license, coverage, "
            "and preprocessing details.",
            "",
        ]
    )
    (output_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def plot_test_metrics(metrics: pd.DataFrame, output_path: Path) -> None:
    test = metrics.loc[(metrics["phase"] == "test") & (metrics["season"] == "ALL")]
    models = sorted(test["model"].unique())
    horizons = sorted(test["horizon_days"].unique())
    figure, axis = plt.subplots(figsize=(8, 4.5))
    positions = np.arange(len(horizons))
    width = 0.8 / max(len(models), 1)
    for index, model in enumerate(models):
        values = [
            test.loc[(test["model"] == model) & (test["horizon_days"] == horizon), "mae_kwh"].mean()
            for horizon in horizons
        ]
        axis.bar(positions + index * width, values, width=width, label=model)
    axis.set_xticks(positions + width * (len(models) - 1) / 2)
    axis.set_xticklabels([f"{horizon} day" for horizon in horizons])
    axis.set_ylabel("Mean absolute error (kWh)")
    axis.set_title("Chronological test MAE by forecast horizon")
    axis.legend()
    axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def run_evaluation(
    output_dir: Path,
    dataset_path: Path | None = None,
    cache_dir: Path | None = None,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir or (output_dir.parent / ".cache" / "forecast-evaluation")
    if dataset_path is None:
        dataset_path, archive_path = acquire_dataset(cache)
    else:
        archive_path = cache / "uci_household_power_consumption.zip"
    daily = load_daily_targets(dataset_path)
    split = chronological_split(daily)
    predictions = evaluate_forecasts(daily, split)
    metrics = summarize_predictions(predictions)

    predictions_path = output_dir / "predictions.csv"
    metrics_path = output_dir / "metrics.csv"
    config_path = output_dir / "config.json"
    plot_path = output_dir / "forecast_evaluation.png"
    predictions.to_csv(predictions_path, index=False)
    metrics.to_csv(metrics_path, index=False)
    plot_test_metrics(metrics, plot_path)
    dataset_readme = Path(__file__).resolve().parents[2] / "docs" / "forecast-evaluation-dataset.md"
    shutil.copyfile(dataset_readme, output_dir / "DATASET_README.md")

    import matplotlib as matplotlib_package
    import prophet
    import sklearn

    config = {
        "dataset_url": DATASET_URL,
        "dataset_file": dataset_path.name,
        "dataset_sha256": _sha256(dataset_path),
        "archive_sha256": _sha256(archive_path) if archive_path.exists() else None,
        "dataset_timezone": DATASET_TIMEZONE,
        "household_id": HOUSEHOLD_ID,
        "target": "daily_kwh_from_global_active_power",
        "minimum_daily_coverage": MINIMUM_DAILY_COVERAGE,
        "split": {key: value.isoformat() for key, value in asdict(split).items()},
        "forecast_horizons_days": list(FORECAST_HORIZONS),
        "rolling_origin_step_days": ORIGIN_STEP_DAYS,
        "random_seed": RANDOM_SEED,
        "prophet": {"implementation": prophet.__version__, "uncertainty_samples": 200},
        "versions": {
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "matplotlib": matplotlib_package.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "prediction_rows": len(predictions),
        "metrics_rows": len(metrics),
    }
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    write_report(
        output_dir,
        split,
        daily,
        metrics,
        dataset_path,
        archive_path,
    )
    return {
        "predictions": predictions_path,
        "metrics": metrics_path,
        "config": config_path,
        "plot": plot_path,
        "report": output_dir / "REPORT.md",
    }
