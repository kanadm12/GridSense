"""Tests for the anomaly detection service.

Every detector reads ``reading.value``; a regression to the old ``r.kwh`` attribute would
raise ``AttributeError`` in these paths. Peak classification is delegated to the shared
weekday-aware ToU classifier, so weekend afternoons are never counted as peak.
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.meter import Meter
from app.models.reading import Reading
from app.models.user import User
from app.services.anomaly_detector import AnomalyDetector, AnomalyType
from app.services.interval_quality import expected_interval_ends_utc
from app.services.tariff import is_peak

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
    user = User(email="an@example.com", hashed_password="x", full_name="AN")
    db.add(user)
    db.commit()
    db.refresh(user)

    meter = Meter(user_id=user.id, nmi="1234567890", suffix="B1", state="VIC", name="AN Meter")
    db.add(meter)
    db.commit()
    db.refresh(meter)
    return meter


def _add(db, meter_id, ts, value):
    db.add(
        Reading(
            meter_id=meter_id,
            timestamp=ts,
            value=value,
            source_value=value,
            source_unit="kWh",
            provenance_kind="measured",
            source_time_basis="fixed_utc_plus_10",
            quality="A",
            register_type="B",
            direction="import",
        )
    )


def _add_complete_day(db, meter, day, value_for_start):
    fixed_market_time = timezone(timedelta(hours=10))
    melbourne = ZoneInfo("Australia/Melbourne")
    for interval_end_utc in expected_interval_ends_utc(
        day, meter.state, meter.interval_minutes
    ):
        interval_start_local = (
            interval_end_utc - timedelta(minutes=meter.interval_minutes)
        ).astimezone(melbourne)
        timestamp = interval_end_utc.astimezone(fixed_market_time).replace(tzinfo=None)
        _add(
            db,
            meter.id,
            timestamp,
            value_for_start(interval_start_local),
        )


class TestOvernightUsage:
    def test_flags_high_overnight_rate(self, db, test_meter):
        # Five complete days with an elevated measured overnight average.
        for day_offset in range(1, 6):
            day = date.today() - timedelta(days=day_offset)
            _add_complete_day(
                db,
                test_meter,
                day,
                lambda start: 0.6 if start.hour < 6 else 0.1,
            )
        db.commit()

        anomalies = AnomalyDetector(db).detect_overnight_usage(test_meter.id)

        assert len(anomalies) >= 1
        assert all(a["type"] == AnomalyType.OVERNIGHT_USAGE for a in anomalies)
        assert all(a["hourly_rate_kwh"] > 0.5 for a in anomalies)

    def test_quiet_nights_not_flagged(self, db, test_meter):
        for day_offset in range(1, 6):
            day = date.today() - timedelta(days=day_offset)
            _add_complete_day(db, test_meter, day, lambda start: 0.05)
        db.commit()

        assert AnomalyDetector(db).detect_overnight_usage(test_meter.id) == []


class TestPeakHeavyUsage:
    def test_flags_peak_dominated_weekday(self, db, test_meter):
        # Seed the previous 7 days; each contains >=5 weekdays. Peak hours dominate.
        for day_offset in range(1, 8):
            day = date.today() - timedelta(days=day_offset)
            _add_complete_day(
                db,
                test_meter,
                day,
                lambda start: 2.0 if 15 <= start.hour < 21 else 0.1,
            )
        db.commit()

        anomalies = AnomalyDetector(db).detect_peak_heavy_usage(test_meter.id)

        # At least the weekdays in the window flag; weekends never do (peak=0 on weekends).
        assert len(anomalies) >= 1
        assert all(a["type"] == AnomalyType.PEAK_HEAVY for a in anomalies)
        for a in anomalies:
            flagged_day = date.fromisoformat(a["date"])
            assert flagged_day.weekday() < 5  # weekday only
            assert a["peak_ratio"] > 0.6
            assert a["extra_cost"] is None
            assert "tariff" in a["message"]

    def test_weekend_peak_window_not_flagged(self, db, test_meter):
        # Find the most recent Saturday within the lookback window and load its 3-9pm block.
        saturday = None
        for day_offset in range(1, 8):
            day = date.today() - timedelta(days=day_offset)
            if day.weekday() == 5:
                saturday = day
                break

        if saturday is None:
            pytest.skip("No Saturday in the 7-day lookback window on this run date")

        for hour in range(15, 21):
            for minute in (0, 30):
                ts = datetime.combine(
                    saturday, datetime.min.time().replace(hour=hour, minute=minute)
                ) + timedelta(minutes=30)
                _add(db, test_meter.id, ts, 5.0)
        db.commit()

        # Sanity: the shared classifier agrees this window is off-peak on a weekend.
        assert not is_peak(
            datetime.combine(saturday, datetime.min.time().replace(hour=18))
            + timedelta(minutes=30)
        )

        flagged = AnomalyDetector(db).detect_peak_heavy_usage(test_meter.id)
        assert all(date.fromisoformat(a["date"]) != saturday for a in flagged)


class TestAllAnomalies:
    def test_report_structure(self, db, test_meter):
        for day_offset in range(1, 31):
            day = date.today() - timedelta(days=day_offset)
            _add_complete_day(
                db,
                test_meter,
                day,
                lambda start: 2.0 if 15 <= start.hour < 21 else 0.1,
            )
        db.commit()

        report = AnomalyDetector(db).get_all_anomalies(test_meter.id)

        assert report["meter_id"] == test_meter.id
        assert report["total_anomalies"] == len(report["anomalies"])
        counts = (
            report["high_severity_count"]
            + report["medium_severity_count"]
            + report["low_severity_count"]
        )
        assert counts == report["total_anomalies"]
