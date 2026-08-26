"""ETL helpers to build time-series datasets from DB models."""
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from app.models.aggregate import DailyAggregate


def extract_daily_series(db: Session, meter_id: int, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
    """Return a DataFrame with columns `ds` (date) and `y` (kWh) suitable for forecasting.

    Dates are returned as pandas datetime and sorted ascending.
    """
    query = db.query(DailyAggregate).filter(DailyAggregate.meter_id == meter_id)
    if start_date:
        query = query.filter(DailyAggregate.date >= start_date)
    if end_date:
        query = query.filter(DailyAggregate.date <= end_date)

    rows = query.order_by(DailyAggregate.date.asc()).all()
    if not rows:
        return pd.DataFrame(columns=["ds", "y"])

    data = [(r.date, float(r.total_kwh or 0.0)) for r in rows]
    df = pd.DataFrame(data, columns=["ds", "y"])
    df["ds"] = pd.to_datetime(df["ds"]).dt.date
    df = df.sort_values("ds").reset_index(drop=True)
    return df
