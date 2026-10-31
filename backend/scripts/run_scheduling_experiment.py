"""Run the synthetic scheduling strategy comparison."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.ml.scheduling_experiment import ExperimentDesign, run_experiment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/scheduling_experiment"),
        help="Directory for result CSVs, config, report, and plot.",
    )
    parser.add_argument("--households", type=int, default=ExperimentDesign().household_count)
    parser.add_argument("--seed", type=int, default=ExperimentDesign().seed)
    args = parser.parse_args()
    outputs = run_experiment(
        args.output_dir,
        ExperimentDesign(household_count=args.households, seed=args.seed),
    )
    for label, path in outputs.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()
