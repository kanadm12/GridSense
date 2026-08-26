"""Tests for the anomaly detection service.

Every detector reads ``reading.value``; a regression to the old ``r.kwh`` attribute would
raise ``AttributeError`` in these paths. Peak classification is delegated to the shared
weekday-aware ToU classifier, so weekend afternoons are never counted as peak.
"""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.meter import Meter
from app.models.reading import Reading
from app.models.user import User
from app.services.anomaly_detector import AnomalyDetector, AnomalyType
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
    db.add(Reading(meter_id=meter_id, timestamp=ts, value=value, quality="A", register_type="B"))


class TestOvernightUsage:
    def test_flags_high_overnight_rate(self, db, test_meter):
        # Five recent nights with sustained midnight-6am draw (~1.2 kWh/h > 0.5 threshold).
        for day_offset in range(1, 6):
            day = date.today() - timedelta(days=day_offset)
            for half_hour in range(12):  # 00:00 .. 05:30
                ts = datetime.combine(day, datetime.min.time()) + timedelta(minutes=30 * half_hour)
                _add(db, test_meter.id, ts, 0.6)
        db.commit()

        anomalies = AnomalyDetector(db).detect_overnight_usage(test_meter.id)

        assert len(anomalies) >= 1
        assert all(a["type"] == AnomalyType.OVERNIGHT_USAGE for a in anomalies)
        assert all(a["hourly_rate_kwh"] > 0.5 for a in anomalies)

    def test_quiet_nights_not_flagged(self, db, test_meter):
        for day_offset in range(1, 6):
            day = date.today() - timedelta(days=day_offset)
            for half_hour in range(12):
                ts = datetime.combine(day, datetime.min.time()) + timedelta(minutes=30 * half_hour)
                _add(db, test_meter.id, ts, 0.05)  # ~0.1 kWh/h, well under threshold
        db.commit()

        assert AnomalyDetector(db).detect_overnight_usage(test_meter.id) == []


class TestPeakHeavyUsage:
    def test_flags_peak_dominated_weekday(self, db, test_meter):
        # Seed the previous 7 days; each contains >=5 weekdays. Peak hours dominate.
        for day_offset in range(1, 8):
            day = date.today() - timedelta(days=day_offset)
            for half_hour in range(48):
                ts = datetime.combine(day, datetime.min.time()) + timedelta(minutes=30 * half_hour)
                value = 2.0 if 15 <= ts.hour < 21 else 0.1
                _add(db, test_meter.id, ts, value)
        db.commit()

        anomalies = AnomalyDetector(db).detect_peak_heavy_usage(test_meter.id)

        # At least the weekdays in the window flag; weekends never do (peak=0 on weekends).
        assert len(anomalies) >= 1
        assert all(a["type"] == AnomalyType.PEAK_HEAVY for a in anomalies)
        for a in anomalies:
            flagged_day = date.fromisoformat(a["date"])
            assert flagged_day.weekday() < 5  # weekday only
            assert a["peak_ratio"] > 0.6
            assert a["extra_cost"] >= 0

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
            ts = datetime.combine(saturday, datetime.min.time().replace(hour=hour))
            _add(db, test_meter.id, ts, 5.0)
        db.commit()

        # Sanity: the shared classifier agrees this window is off-peak on a weekend.
        assert not is_peak(datetime.combine(saturday, datetime.min.time().replace(hour=18)))

        flagged = AnomalyDetector(db).detect_peak_heavy_usage(test_meter.id)
        assert all(date.fromisoformat(a["date"]) != saturday for a in flagged)


class TestAllAnomalies:
    def test_report_structure(self, db, test_meter):
        for day_offset in range(1, 31):
            day = date.today() - timedelta(days=day_offset)
            for half_hour in range(48):
                ts = datetime.combine(day, datetime.min.time()) + timedelta(minutes=30 * half_hour)
                value = 2.0 if 15 <= ts.hour < 21 else 0.1
                _add(db, test_meter.id, ts, value)
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
