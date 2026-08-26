"""Simple CLI to run training jobs from the project root.

Usage:
    python -m app.ml.cli train-all
    python -m app.ml.cli train-meter --meter-id 1
"""
import argparse
from datetime import date

from app.database import SessionLocal
from app.ml.etl import extract_daily_series
from app.ml.train import train_forecast, train_anomaly_detector


def train_all():
    db = SessionLocal()
    try:
        meters = db.execute("SELECT id FROM meters").fetchall()
        for (mid,) in meters:
            print(f"Training for meter {mid}")
            df = extract_daily_series(db, mid)
            if df.empty:
                print("  no data, skipping")
                continue
            try:
                f = train_forecast(df, mid)
                a = train_anomaly_detector(df, mid)
                print("  forecast:", f["model_path"])
                print("  anomaly:", a["model_path"])
            except Exception as e:
                print("  failed:", e)
    finally:
        db.close()


def train_meter(meter_id: int):
    db = SessionLocal()
    try:
        df = extract_daily_series(db, meter_id)
        print(train_forecast(df, meter_id))
        print(train_anomaly_detector(df, meter_id))
    finally:
        db.close()


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("train-all")
    pm = sub.add_parser("train-meter")
    pm.add_argument("--meter-id", type=int, required=True)
    args = p.parse_args()
    if args.cmd == "train-all":
        train_all()
    elif args.cmd == "train-meter":
        train_meter(args.meter_id)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
