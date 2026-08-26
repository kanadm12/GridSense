"""Tests for ML module: ETL, training, and prediction."""

import pytest
from datetime import date, datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import get_db
from app.models.base import Base
from app.models.meter import Meter
from app.models.reading import Reading
from app.models.user import User
from app.models.aggregate import DailyAggregate
from app.ml.etl import extract_daily_series
from app.services.auth import AuthService


# Test database setup (shared in-memory)
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///file:tests_db_ml?mode=memory&cache=shared"
engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL, connect_args={"check_same_thread": False, "uri": True}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_with_data():
    """Create test DB with sample daily aggregate data."""
    db = TestingSessionLocal()
    
    # Create user and meter
    user = User(email="ml@test.com", hashed_password=AuthService.hash_password("pass"), full_name="ML Test")
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
    df = extract_daily_series(db_with_data, meter.id, start_date="2025-04-10", end_date="2025-04-20")
    
    assert len(df) == 11  # 10-20 inclusive
