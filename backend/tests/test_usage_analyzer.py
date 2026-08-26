"""Tests for usage analyzer service."""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.meter import Meter
from app.models.reading import Reading
from app.models.user import User
from app.services.usage_analyzer import UsageAnalyzer, _ensure_date


# Test database setup
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Fixed reference dates for weekday-aware Time-of-Use assertions (AEST wall-clock).
# Pinned so the tests are deterministic regardless of what day they run on.
WEEKDAY_DATE = date(2024, 6, 5)  # Wednesday
WEEKEND_DATE = date(2024, 6, 8)  # Saturday


@pytest.fixture
def db():
    """Create test database session."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_user(db):
    """Create a test user."""
    user = User(
        email="test@example.com",
        hashed_password="hashed_password",
        full_name="Test User",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_meter(db, test_user):
    """Create a test meter."""
    meter = Meter(
        user_id=test_user.id,
        nmi="1234567890",
        suffix="B1",
        unit_of_measure="kWh",
        interval_minutes=30,
        state="VIC",
        name="Test Meter",
    )
    db.add(meter)
    db.commit()
    db.refresh(meter)
    return meter


@pytest.fixture
def test_readings(db, test_meter):
    """Create test readings for 7 days."""
    readings = []
    base_date = date.today() - timedelta(days=7)
    
    for day_offset in range(7):
        current_date = base_date + timedelta(days=day_offset)
        # Create 48 half-hour readings per day
        for half_hour in range(48):
            timestamp = datetime.combine(
                current_date,
                datetime.min.time()
            ) + timedelta(minutes=30 * half_hour)
            
            # Vary consumption by hour (higher during peak)
            hour = timestamp.hour
            if 15 <= hour < 21:  # Peak hours
                value = 0.8 + (half_hour % 4) * 0.1
            elif hour >= 22 or hour < 7:  # Off-peak
                value = 0.2 + (half_hour % 3) * 0.05
            else:  # Shoulder
                value = 0.4 + (half_hour % 3) * 0.1
            
            reading = Reading(
                meter_id=test_meter.id,
                timestamp=timestamp,
                value=value,
                quality="A",
                register_type="B",
            )
            readings.append(reading)
    
    db.add_all(readings)
    db.commit()
    return readings


class TestEnsureDate:
    """Tests for _ensure_date helper function."""

    def test_date_passthrough(self):
        """Test that date objects pass through unchanged."""
        d = date(2024, 1, 15)
        result = _ensure_date(d)
        assert result == d
        assert isinstance(result, date)

    def test_string_conversion(self):
        """Test that date strings are converted to date objects."""
        date_str = "2024-01-15"
        result = _ensure_date(date_str)
        assert result == date(2024, 1, 15)
        assert isinstance(result, date)

    def test_iso_format_string(self):
        """Test various ISO format strings."""
        assert _ensure_date("2024-12-31") == date(2024, 12, 31)
        assert _ensure_date("2020-01-01") == date(2020, 1, 1)


class TestUsageAnalyzerDailyUsage:
    """Tests for daily usage calculations."""

    def test_get_daily_usage(self, db, test_meter, test_readings):
        """Test getting daily usage data."""
        analyzer = UsageAnalyzer(db)
        daily = analyzer.get_daily_usage(test_meter.id, limit=7)
        
        assert len(daily) == 7
        for day in daily:
            assert day.total_kwh > 0
            assert day.peak_kwh >= 0
            assert day.off_peak_kwh >= 0
            assert day.shoulder_kwh >= 0
            # Total should equal sum of TOU periods
            total_tou = day.peak_kwh + day.off_peak_kwh + day.shoulder_kwh
            assert abs(day.total_kwh - total_tou) < 0.01  # Allow small floating point diff
            assert day.estimated_cost > 0

    def test_get_daily_usage_empty_meter(self, db, test_meter):
        """Test getting daily usage for meter with no readings."""
        analyzer = UsageAnalyzer(db)
        daily = analyzer.get_daily_usage(test_meter.id)
        
        assert daily == []

    def test_get_daily_usage_with_date_range(self, db, test_meter, test_readings):
        """Test getting daily usage with specific date range."""
        analyzer = UsageAnalyzer(db)
        end_date = date.today()
        start_date = end_date - timedelta(days=3)
        
        daily = analyzer.get_daily_usage(
            test_meter.id,
            start_date=start_date,
            end_date=end_date,
        )
        
        # Should only return days within range
        for day in daily:
            assert start_date <= day.date <= end_date


class TestUsageAnalyzerHourlyUsage:
    """Tests for hourly usage calculations."""

    def test_get_hourly_usage(self, db, test_meter, test_readings):
        """Test getting hourly usage pattern."""
        analyzer = UsageAnalyzer(db)
        hourly = analyzer.get_hourly_usage(test_meter.id)
        
        assert len(hourly) == 24  # All hours represented
        hours = [h.hour for h in hourly]
        assert sorted(hours) == list(range(24))
        
        for hour_data in hourly:
            assert hour_data.avg_kwh >= 0
            assert hour_data.total_kwh >= 0
            assert hour_data.reading_count > 0

    def test_hourly_usage_peak_hours_higher(self, db, test_meter, test_readings):
        """Test that peak hours have higher average consumption."""
        analyzer = UsageAnalyzer(db)
        hourly = analyzer.get_hourly_usage(test_meter.id)
        
        peak_hours = [h for h in hourly if 15 <= h.hour < 21]
        off_peak_hours = [h for h in hourly if h.hour >= 22 or h.hour < 7]
        
        avg_peak = sum(h.avg_kwh for h in peak_hours) / len(peak_hours)
        avg_off_peak = sum(h.avg_kwh for h in off_peak_hours) / len(off_peak_hours)
        
        # Peak hours should generally have higher consumption
        assert avg_peak > avg_off_peak


class TestUsageAnalyzerSummary:
    """Tests for usage summary calculations."""

    def test_get_usage_summary(self, db, test_meter, test_readings):
        """Test getting usage summary."""
        analyzer = UsageAnalyzer(db)
        summary = analyzer.get_usage_summary(test_meter.id)
        
        assert summary is not None
        assert summary.meter_id == test_meter.id
        assert summary.nmi == test_meter.nmi
        assert summary.total_kwh > 0
        assert summary.avg_daily_kwh > 0
        assert summary.max_daily_kwh >= summary.avg_daily_kwh
        assert summary.min_daily_kwh <= summary.avg_daily_kwh
        assert 0 <= summary.peak_hour < 24
        assert 0 <= summary.off_peak_percentage <= 100
        assert summary.estimated_total_cost > 0
        assert summary.estimated_daily_cost > 0

    def test_get_usage_summary_no_readings(self, db, test_meter):
        """Test getting summary for meter with no readings."""
        analyzer = UsageAnalyzer(db)
        summary = analyzer.get_usage_summary(test_meter.id)
        
        assert summary is None

    def test_get_usage_summary_nonexistent_meter(self, db):
        """Test getting summary for nonexistent meter."""
        analyzer = UsageAnalyzer(db)
        summary = analyzer.get_usage_summary(meter_id=99999)
        
        assert summary is None


class TestUsageAnalyzerTOUBreakdown:
    """Tests for Time-of-Use breakdown calculations."""

    def test_tou_breakdown_peak_hours(self, db, test_meter):
        """Test that peak hours (3pm-9pm) on a weekday are categorized correctly."""
        # Create readings only during peak hours (on a known weekday)
        readings = []
        test_date = WEEKDAY_DATE
        
        for hour in range(15, 21):  # 3pm to 9pm
            timestamp = datetime.combine(test_date, datetime.min.time().replace(hour=hour))
            readings.append(Reading(
                meter_id=test_meter.id,
                timestamp=timestamp,
                value=1.0,
                quality="A",
                register_type="B",
            ))
        
        db.add_all(readings)
        db.commit()
        
        analyzer = UsageAnalyzer(db)
        tou = analyzer._get_tou_breakdown(test_meter.id, test_date)
        
        assert tou["peak"] == 6.0  # 6 hours * 1.0 kWh
        assert tou["off_peak"] == 0.0
        assert tou["shoulder"] == 0.0

    def test_tou_breakdown_off_peak_hours(self, db, test_meter):
        """Test that off-peak hours (10pm-7am) are categorized correctly."""
        readings = []
        test_date = WEEKDAY_DATE

        # Off-peak: 10pm-midnight and midnight-7am
        for hour in [22, 23, 0, 1, 2, 3, 4, 5, 6]:
            timestamp = datetime.combine(test_date, datetime.min.time().replace(hour=hour))
            readings.append(Reading(
                meter_id=test_meter.id,
                timestamp=timestamp,
                value=1.0,
                quality="A",
                register_type="B",
            ))
        
        db.add_all(readings)
        db.commit()
        
        analyzer = UsageAnalyzer(db)
        tou = analyzer._get_tou_breakdown(test_meter.id, test_date)
        
        assert tou["off_peak"] == 9.0  # 9 hours * 1.0 kWh
        assert tou["peak"] == 0.0
        assert tou["shoulder"] == 0.0

    def test_tou_breakdown_with_string_date(self, db, test_meter):
        """Test TOU breakdown handles string dates (from SQLite)."""
        test_date = WEEKDAY_DATE
        timestamp = datetime.combine(test_date, datetime.min.time().replace(hour=10))
        
        db.add(Reading(
            meter_id=test_meter.id,
            timestamp=timestamp,
            value=1.0,
            quality="A",
            register_type="B",
        ))
        db.commit()
        
        analyzer = UsageAnalyzer(db)
        # Pass string date like SQLite would return
        tou = analyzer._get_tou_breakdown(test_meter.id, str(test_date))

        assert tou["shoulder"] == 1.0  # 10am is shoulder time

    def test_tou_breakdown_weekend_is_off_peak(self, db, test_meter):
        """Weekends are entirely off-peak under the Victorian ToU convention.

        The same 3pm-9pm window that is 'peak' on a weekday must be classified as
        off-peak on a Saturday/Sunday. This guards against the earlier hour-only logic
        that ignored the day of week.
        """
        readings = []
        for hour in range(15, 21):  # 3pm-9pm — would be peak on a weekday
            timestamp = datetime.combine(WEEKEND_DATE, datetime.min.time().replace(hour=hour))
            readings.append(Reading(
                meter_id=test_meter.id,
                timestamp=timestamp,
                value=1.0,
                quality="A",
                register_type="B",
            ))

        db.add_all(readings)
        db.commit()

        analyzer = UsageAnalyzer(db)
        tou = analyzer._get_tou_breakdown(test_meter.id, WEEKEND_DATE)

        assert tou["off_peak"] == 6.0  # weekend afternoon is off-peak
        assert tou["peak"] == 0.0
        assert tou["shoulder"] == 0.0


class TestBatchTOUBreakdown:
    """Tests for batch TOU breakdown optimization."""

    def test_batch_tou_breakdown(self, db, test_meter, test_readings):
        """Test batch TOU breakdown returns same results as individual calls."""
        analyzer = UsageAnalyzer(db)
        
        # Get batch results
        batch_results = analyzer._batch_tou_breakdown(test_readings)
        
        # Compare with individual results for each day
        dates = set(r.timestamp.date() for r in test_readings)
        
        for day in dates:
            individual = analyzer._get_tou_breakdown(test_meter.id, day)
            batch = batch_results.get(day, {"peak": 0.0, "off_peak": 0.0, "shoulder": 0.0})
            
            assert abs(individual["peak"] - batch["peak"]) < 0.01
            assert abs(individual["off_peak"] - batch["off_peak"]) < 0.01
            assert abs(individual["shoulder"] - batch["shoulder"]) < 0.01

    def test_batch_tou_breakdown_empty(self, db, test_meter):
        """Test batch TOU breakdown with empty readings list."""
        analyzer = UsageAnalyzer(db)
        result = analyzer._batch_tou_breakdown([])
        
        assert result == {}
