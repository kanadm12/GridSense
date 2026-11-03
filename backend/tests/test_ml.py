"""Tests for ML module: ETL, training, and prediction."""

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.ml.etl import extract_daily_series
from app.models.aggregate import DailyAggregate
from app.models.base import Base
from app.models.meter import Meter
from app.models.user import User
from app.services.auth import AuthService

engine: Engine
testing_session_local: sessionmaker[Session]


@pytest.fixture(autouse=True)
def setup_database(tmp_path):
    global engine, testing_session_local
    engine = create_engine(f"sqlite:///{tmp_path / 'ml.sqlite3'}")
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        Base.metadata.create_all(bind=engine)
        yield
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def db_with_data():
    """Create test DB with sample daily aggregate data."""
    db = testing_session_local()

    # Create user and meter
    user = User(
        email="ml@test.com", hashed_password=AuthService.hash_password("pass"), full_name="ML Test"
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    meter = Meter(
        user_id=user.id,
        nmi="1234567890",
        meter_serial="ABC123",
        state="VIC",
    )
    db.add(meter)
    db.commit()
    db.refresh(meter)

    # Add sample daily aggregates (30 days)
    base_date = date(2025, 4, 1)
    for i in range(30):
        agg = DailyAggregate(
            meter_id=meter.id,
            date=base_date + timedelta(days=i),
            total_kwh=20.0 + (i % 7) * 2,  # Vary between 20-34 kWh
            peak_kwh=10.0 + (i % 7),
            offpeak_kwh=10.0 + (i % 7),
        )
        db.add(agg)
    db.commit()

    yield db
    db.close()


def test_extract_daily_series(db_with_data):
    """Test ETL extraction of daily time-series."""
    meter = db_with_data.query(Meter).first()
    df = extract_daily_series(db_with_data, meter.id)

    assert not df.empty
    assert len(df) == 30
    assert "ds" in df.columns
    assert "y" in df.columns
    assert all(df["y"] > 0)


def test_extract_daily_series_with_date_filter(db_with_data):
    """Test extraction with date filtering."""
    meter = db_with_data.query(Meter).first()
    df = extract_daily_series(
        db_with_data, meter.id, start_date="2025-04-10", end_date="2025-04-20"
    )

    assert len(df) == 11  # 10-20 inclusive
