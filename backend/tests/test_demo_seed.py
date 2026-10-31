"""Tests for the isolated synthetic demo database seed/reset workflow."""

from pydantic import EmailStr, TypeAdapter
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.meter import Meter
from app.models.reading import Reading
from app.models.tariff import Tariff
from app.models.user import User
from app.services.tariff import local_interval_end_date
from app.services.usage_analyzer import UsageAnalyzer
from scripts.demo_seed import (
    DEMO_DAY,
    DEMO_EMAIL,
    DEMO_SCHEDULING_EMAIL,
    seed_demo_database,
)


def test_demo_seed_is_repeatable_and_reset_is_scoped_to_named_sqlite_file(tmp_path, monkeypatch):
    database_path = tmp_path / "gridsense-demo.db"
    monkeypatch.setenv("GRIDSENSE_DEMO_PASSWORD", "synthetic-demo-password")

    seed_demo_database(database_path)
    seed_demo_database(database_path)

    email_type = TypeAdapter(EmailStr)
    assert email_type.validate_python(DEMO_EMAIL) == DEMO_EMAIL
    assert email_type.validate_python(DEMO_SCHEDULING_EMAIL) == DEMO_SCHEDULING_EMAIL

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with Session(engine) as db:
            user = db.query(User).filter(User.email == DEMO_EMAIL).one()
            meter = db.query(Meter).filter(Meter.user_id == user.id).one()
            readings = (
                db.query(Reading)
                .filter(Reading.meter_id == meter.id)
                .order_by(Reading.timestamp)
                .all()
            )
            assert len(readings) == 48
            assert {
                local_interval_end_date(reading.timestamp, meter.state) for reading in readings
            } == {DEMO_DAY}
            usage = UsageAnalyzer(db).get_usage_summary(
                meter.id, start_date=DEMO_DAY, end_date=DEMO_DAY
            )
            assert usage is not None
            assert usage.days_count == 1
            flat_tariff = db.query(Tariff).filter(Tariff.user_id == user.id).one()
            assert flat_tariff.tariff_type == "flat"
            assert flat_tariff.flat_rate_cents_kwh == 30.0

            scheduling_user = db.query(User).filter(User.email == DEMO_SCHEDULING_EMAIL).one()
            scheduling_meter = db.query(Meter).filter(Meter.user_id == scheduling_user.id).one()
            assert scheduling_meter.name == "Synthetic TOU scheduling meter"
            tou_tariff = db.query(Tariff).filter(Tariff.user_id == scheduling_user.id).one()
            assert tou_tariff.tariff_type == "tou"
            assert [period["rate_cents_kwh"] for period in tou_tariff.periods] == [
                10.0,
                25.0,
                55.0,
                10.0,
            ]
            assert db.query(Reading).filter(Reading.meter_id == scheduling_meter.id).count() == 0
            assert db.query(User).count() == 2
    finally:
        engine.dispose()

    seed_demo_database(database_path, reset=True)
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with Session(engine) as db:
            assert db.query(User).filter(User.email == DEMO_EMAIL).count() == 1
            assert db.query(User).filter(User.email == DEMO_SCHEDULING_EMAIL).count() == 1
            assert db.query(Reading).count() == 48
    finally:
        engine.dispose()
