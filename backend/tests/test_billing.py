"""Tests for billing period-cost calculation.

The previous implementation split every period's kWh by a fixed 25/35/40 peak/shoulder/
off-peak ratio regardless of when energy was actually used. These tests pin the corrected
behaviour: each interval is bucketed into its real Victorian ToU period and priced at that
period's rate, so identical kWh consumed at different times of day costs different amounts.
"""

from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.billing import DEFAULT_SUPPLY_CHARGE_CENTS, calculate_period_cost
from app.models.base import Base
from app.models.meter import Meter
from app.models.reading import Reading
from app.models.tariff import Tariff
from app.models.user import User
from app.services.tariff import DEFAULT_FLAT_RATE_CENTS

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 2024-06-05 is a Wednesday; 2024-06-08 is a Saturday.
WED = date(2024, 6, 5)
SAT = date(2024, 6, 8)


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
def user(db):
    u = User(email="bill@example.com", hashed_password="x", full_name="Bill")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def meter(db, user):
    m = Meter(user_id=user.id, nmi="1234567890", suffix="B1", state="VIC", name="Bill Meter")
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def _tou_tariff(user_id: int) -> Tariff:
    return Tariff(
        user_id=user_id,
        tariff_type="tou",
        peak_rate_cents_kwh=40.0,
        shoulder_rate_cents_kwh=20.0,
        off_peak_rate_cents_kwh=10.0,
        daily_supply_charge_cents=100.0,
    )


def _seed_hours(db, meter_id, day, hours, value=1.0, register_type="B"):
    for hour in hours:
        ts = datetime.combine(day, datetime.min.time().replace(hour=hour))
        db.add(Reading(meter_id=meter_id, timestamp=ts, value=value, quality="A", register_type=register_type))
    db.commit()


class TestTouBucketing:
    def test_peak_only_priced_at_peak_rate(self, db, user, meter):
        # 6 kWh, all inside the weekday 3-9pm peak window.
        _seed_hours(db, meter.id, WED, range(15, 21), value=1.0)
        tariff = _tou_tariff(user.id)

        total_kwh, cost, days = calculate_period_cost(db, meter.id, WED, WED, tariff)

        assert total_kwh == pytest.approx(6.0)
        assert days == 1
        # 6 * 0.40 + 1.00 supply = 3.40. The old fixed-split code produced 2.26 here.
        assert cost == pytest.approx(3.40)

    def test_weekend_afternoon_priced_at_off_peak_rate(self, db, user, meter):
        # Same 3-9pm block, but on a Saturday it is entirely off-peak.
        _seed_hours(db, meter.id, SAT, range(15, 21), value=1.0)
        tariff = _tou_tariff(user.id)

        total_kwh, cost, days = calculate_period_cost(db, meter.id, SAT, SAT, tariff)

        assert total_kwh == pytest.approx(6.0)
        # 6 * 0.10 + 1.00 supply = 1.60 (vs 3.40 if it were wrongly treated as peak).
        assert cost == pytest.approx(1.60)

    def test_weekday_morning_priced_at_shoulder_rate(self, db, user, meter):
        _seed_hours(db, meter.id, WED, [8, 9, 10, 11], value=1.0)  # 4 kWh shoulder
        tariff = _tou_tariff(user.id)

        total_kwh, cost, days = calculate_period_cost(db, meter.id, WED, WED, tariff)

        assert total_kwh == pytest.approx(4.0)
        # 4 * 0.20 + 1.00 supply = 1.80
        assert cost == pytest.approx(1.80)

    def test_export_readings_excluded(self, db, user, meter):
        _seed_hours(db, meter.id, WED, range(15, 21), value=1.0, register_type="B")
        # An "E" (export/generation) reading must not be billed as consumption.
        _seed_hours(db, meter.id, WED, [16], value=100.0, register_type="E")
        tariff = _tou_tariff(user.id)

        total_kwh, cost, days = calculate_period_cost(db, meter.id, WED, WED, tariff)

        assert total_kwh == pytest.approx(6.0)  # the 100 kWh export is ignored


class TestFlatAndNoTariff:
    def test_flat_tariff(self, db, user, meter):
        _seed_hours(db, meter.id, WED, range(0, 10), value=1.0)  # 10 kWh
        tariff = Tariff(
            user_id=user.id,
            tariff_type="flat",
            flat_rate_cents_kwh=30.0,
            daily_supply_charge_cents=100.0,
        )

        total_kwh, cost, days = calculate_period_cost(db, meter.id, WED, WED, tariff)

        assert total_kwh == pytest.approx(10.0)
        # 10 * 0.30 + 1.00 supply = 4.00
        assert cost == pytest.approx(4.00)

    def test_no_tariff_uses_defaults(self, db, meter):
        _seed_hours(db, meter.id, WED, range(0, 10), value=1.0)  # 10 kWh

        total_kwh, cost, days = calculate_period_cost(db, meter.id, WED, WED, None)

        assert total_kwh == pytest.approx(10.0)
        expected = (10.0 * DEFAULT_FLAT_RATE_CENTS) / 100 + (DEFAULT_SUPPLY_CHARGE_CENTS * 1) / 100
        assert cost == pytest.approx(expected)

    def test_empty_period_is_supply_charge_only(self, db, meter):
        total_kwh, cost, days = calculate_period_cost(db, meter.id, WED, WED, None)

        assert total_kwh == 0.0
        assert cost == pytest.approx(DEFAULT_SUPPLY_CHARGE_CENTS / 100)
