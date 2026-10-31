"""Download the documented UCI household dataset and evaluate daily forecasts."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.ml.forecast_evaluation import run_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/forecast_evaluation"),
        help="Directory for CSV, JSON, report, and plot outputs.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        help="Use an already downloaded household_power_consumption.txt file.",
    )
    args = parser.parse_args()
    outputs = run_evaluation(args.output_dir, dataset_path=args.dataset)
    for label, path in outputs.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()
