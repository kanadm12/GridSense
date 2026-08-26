"""Tests for the bill forecasting service.

These guard two things that previously broke at runtime:
- Cost is derived from ``reading.value`` (the model has no ``kwh`` attribute), so a
  regression back to ``r.kwh`` would raise ``AttributeError`` here.
- Interval costs are priced through the shared Victorian ToU classifier, not a flat rate.
"""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.meter import Meter
from app.models.reading import Reading
from app.models.user import User
from app.services.forecasting import BillForecaster
from app.services.tariff import DEFAULT_SUPPLY_CHARGE

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_meter(db):
    user = User(email="fc@example.com", hashed_password="x", full_name="FC")
    db.add(user)
    db.commit()
    db.refresh(user)

    meter = Meter(user_id=user.id, nmi="1234567890", suffix="B1", state="VIC", name="FC Meter")
    db.add(meter)
    db.commit()
    db.refresh(meter)
    return meter


def _seed_month_to_date(db, meter_id: int) -> None:
    """Seed constant half-hourly readings from the 1st of this month through today.

    A flat 1.0 kWh across all 48 half-hours means every day contains peak, shoulder and
    off-peak intervals, so the ToU cost path is fully exercised.
    """
    first_day = date.today().replace(day=1)
    day = first_day
    while day <= date.today():
        for half_hour in range(48):
            ts = datetime.combine(day, datetime.min.time()) + timedelta(minutes=30 * half_hour)
            db.add(Reading(meter_id=meter_id, timestamp=ts, value=1.0, quality="A", register_type="B"))
        day += timedelta(days=1)
    db.commit()


class TestForecastMonthlyBill:
    def test_forecast_has_positive_usage_and_cost(self, db, test_meter):
        forecaster = BillForecaster(db)
        result = forecaster.forecast_monthly_bill(test_meter.id)

        assert result["meter_id"] == test_meter.id
        # No readings seeded yet -> zero usage, but the supply charge still applies.
        assert result["usage_so_far_kwh"] == 0.0

        _seed_month_to_date(db, test_meter.id)
        result = forecaster.forecast_monthly_bill(test_meter.id)

        # Exercises the r.value summation path that used to crash as r.kwh.
        assert result["usage_so_far_kwh"] > 0
        assert result["cost_so_far"] > 0
        assert result["projected_total_kwh"] >= result["usage_so_far_kwh"]
        assert result["projected_total_cost"] > 0
        assert result["projected_cost_high"] >= result["projected_cost_low"]
        assert result["confidence_level"] == 0.95

    def test_tou_pricing_beats_pure_supply_charge(self, db, test_meter):
        """A day of usage must cost more than the supply charge alone."""
        _seed_month_to_date(db, test_meter.id)
        forecaster = BillForecaster(db)
        result = forecaster.forecast_monthly_bill(test_meter.id)

        days_elapsed = result["days_elapsed"]
        # If cost were flat/zero-rated, cost_so_far would equal just the supply charges.
        assert result["cost_so_far"] > DEFAULT_SUPPLY_CHARGE * days_elapsed


class TestBillTrend:
    def test_trend_returns_month_with_usage(self, db, test_meter):
        _seed_month_to_date(db, test_meter.id)
        forecaster = BillForecaster(db)
        trend = forecaster.get_bill_trend(test_meter.id, months=3)

        assert isinstance(trend, list)
        assert len(trend) >= 1
        current = trend[-1]
        assert current["total_kwh"] > 0
        assert current["total_cost"] > 0
        assert current["days_with_data"] >= 1

    def test_trend_empty_for_meter_without_readings(self, db, test_meter):
        forecaster = BillForecaster(db)
        assert forecaster.get_bill_trend(test_meter.id, months=3) == []
