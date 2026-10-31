"""Tests for transparent, non-invented recommendation opportunities."""

import asyncio
from datetime import date, datetime, timedelta

import pytest

from app.api.automation import get_automation_suggestions
from app.models.meter import Meter
from app.models.reading import Reading
from app.models.tariff import Tariff
from app.models.user import User
from app.schemas.recommendation import RecommendationEstimateStatus, RecommendationTariffStatus
from app.services.ai_assistant import SYSTEM_PROMPT, AIAssistant
from app.services.recommendation_engine import RecommendationEngine, UsagePattern


@pytest.fixture
def recommendation_meter(test_db):
    user = User(email="recommendations@example.com", hashed_password="x")
    test_db.add(user)
    test_db.flush()
    meter = Meter(user_id=user.id, nmi="1234567890", suffix="B1", state="VIC")
    test_db.add(meter)
    test_db.commit()
    return user, meter


def _pattern(**overrides) -> UsagePattern:
    values = {
        "avg_daily_kwh": 10.0,
        "peak_hour": 18,
        "peak_avg_kwh": 0.5,
        "evening_ratio": 0.5,
        "night_ratio": 0.1,
        "daytime_ratio": 0.25,
        "weekend_vs_weekday": 1.0,
        "total_kwh": 100.0,
        "days_analyzed": 10,
    }
    values.update(overrides)
    return UsagePattern(**values)


def _generate_for_pattern(test_db, monkeypatch, meter, pattern=None):
    engine = RecommendationEngine(test_db)
    monkeypatch.setattr(
        engine,
        "analyze_patterns",
        lambda requested_meter_id: (
            pattern or _pattern() if requested_meter_id == meter.id else None
        ),
    )
    return engine.generate_recommendations(meter.id)


def test_no_tariff_and_missing_appliance_are_explicitly_unquantified(
    test_db, recommendation_meter, monkeypatch
):
    _, meter = recommendation_meter

    response = _generate_for_pattern(test_db, monkeypatch, meter)

    shift = next(rec for rec in response.recommendations if rec.id == "shift_evening_load")
    assert response.tariff_status == RecommendationTariffStatus.MISSING
    assert response.total_potential_savings is None
    assert shift.potential_savings_kwh is None
    assert shift.potential_savings_dollars is None
    assert shift.estimate_status == RecommendationEstimateStatus.UNQUANTIFIED
    assert "User-declared appliance" in shift.data_requirements
    assert "rated power or energy demand" in shift.conditional_opportunity
    assert shift.rate_difference_cents_kwh is None


def test_flat_tariff_has_no_time_of_use_rate_spread(test_db, recommendation_meter, monkeypatch):
    user, meter = recommendation_meter
    test_db.add(
        Tariff(
            user_id=user.id,
            tariff_type="flat",
            flat_rate_cents_kwh=29.0,
            is_preset=False,
        )
    )
    test_db.commit()

    response = _generate_for_pattern(test_db, monkeypatch, meter)

    shift = next(rec for rec in response.recommendations if rec.id == "shift_evening_load")
    assert response.tariff_status == RecommendationTariffStatus.CONFIGURED
    assert shift.rate_difference_cents_kwh == 0
    assert shift.potential_savings_dollars is None


def test_tou_rate_difference_uses_configured_tariff_without_claiming_savings(
    test_db, recommendation_meter, monkeypatch
):
    user, meter = recommendation_meter
    test_db.add(
        Tariff(
            user_id=user.id,
            tariff_type="tou",
            peak_rate_cents_kwh=40.0,
            shoulder_rate_cents_kwh=20.0,
            off_peak_rate_cents_kwh=10.0,
            is_preset=False,
        )
    )
    test_db.commit()

    response = _generate_for_pattern(test_db, monkeypatch, meter)

    shift = next(rec for rec in response.recommendations if rec.id == "shift_evening_load")
    assert shift.rate_difference_cents_kwh == 30.0
    assert shift.potential_savings_dollars is None
    assert "not a savings estimate" not in shift.conditional_opportunity.lower()
    assert "Not quantified" in shift.conditional_opportunity


def test_equal_tou_rates_produce_zero_spread_and_no_savings(
    test_db, recommendation_meter, monkeypatch
):
    user, meter = recommendation_meter
    test_db.add(
        Tariff(
            user_id=user.id,
            tariff_type="tou",
            peak_rate_cents_kwh=20.0,
            shoulder_rate_cents_kwh=20.0,
            off_peak_rate_cents_kwh=20.0,
            is_preset=False,
        )
    )
    test_db.commit()

    response = _generate_for_pattern(test_db, monkeypatch, meter)

    shift = next(rec for rec in response.recommendations if rec.id == "shift_evening_load")
    assert shift.rate_difference_cents_kwh == 0
    assert shift.potential_savings_dollars is None
    assert response.total_potential_savings is None


def test_overnight_observation_uses_imports_and_excludes_export_readings(
    test_db, recommendation_meter
):
    _, meter = recommendation_meter
    today = date.today()
    timestamps = [
        datetime.combine(today, datetime.min.time()) + timedelta(hours=5, minutes=30),
        datetime.combine(today, datetime.min.time()) + timedelta(hours=22, minutes=30),
        datetime.combine(today, datetime.min.time()) + timedelta(hours=11, minutes=30),
    ]
    test_db.add_all(
        [
            Reading(
                meter_id=meter.id,
                timestamp=timestamps[0],
                value=1.0,
                direction="import",
                register_type="U",
                quality="A",
            ),
            Reading(
                meter_id=meter.id,
                timestamp=timestamps[1],
                value=1.0,
                direction="import",
                register_type="U",
                quality="A",
            ),
            Reading(
                meter_id=meter.id,
                timestamp=timestamps[2],
                value=1.0,
                direction="import",
                register_type="U",
                quality="A",
            ),
            Reading(
                meter_id=meter.id,
                timestamp=datetime.combine(today, datetime.min.time())
                + timedelta(hours=1, minutes=30),
                value=50.0,
                direction="export",
                register_type="U",
                quality="A",
            ),
        ]
    )
    test_db.commit()

    response = RecommendationEngine(test_db).generate_recommendations(meter.id)

    overnight = next(rec for rec in response.recommendations if rec.id == "overnight_load_review")
    assert "67%" in overnight.observed_fact
    assert "not established" in overnight.reason
    assert overnight.potential_savings_kwh is None
    assert overnight.potential_savings_dollars is None


def test_illustrative_tariff_is_not_used_as_a_verified_rate(
    test_db, recommendation_meter, monkeypatch
):
    user, meter = recommendation_meter
    test_db.add(
        Tariff(
            user_id=user.id,
            tariff_type="tou",
            peak_rate_cents_kwh=40.0,
            off_peak_rate_cents_kwh=10.0,
            is_preset=True,
        )
    )
    test_db.commit()

    response = _generate_for_pattern(test_db, monkeypatch, meter)

    shift = next(rec for rec in response.recommendations if rec.id == "shift_evening_load")
    assert response.tariff_status == RecommendationTariffStatus.ILLUSTRATIVE
    assert shift.rate_difference_cents_kwh is None


def test_automation_suggestions_are_examples_without_fixed_savings():
    suggestions = asyncio.run(get_automation_suggestions(db=None, current_user=None))

    assert suggestions
    assert all(suggestion.potential_savings_dollars is None for suggestion in suggestions)
    assert all(suggestion.potential_savings_kwh is None for suggestion in suggestions)
    assert all(suggestion.confidence is None for suggestion in suggestions)
    assert all("Example only" in suggestion.description for suggestion in suggestions)


def test_ai_fallback_does_not_assert_rates_or_specific_bill_savings():
    assistant = AIAssistant.__new__(AIAssistant)

    class _Rag:
        @staticmethod
        def get_savings_tips(category):
            return ["Review flexible energy use."] if category == "general" else []

    assistant.rag_engine = _Rag()
    response = assistant._generate_fallback_response(
        "How can I lower my bill?", "Observed imports: 5 kWh.", []
    )

    assert "not a bill calculation" in response
    assert "38c/kWh" not in SYSTEM_PROMPT
    assert "38c/kWh" not in response
    assert "$" not in response


def test_openai_dependency_and_credentials_are_optional(monkeypatch):
    assistant = AIAssistant.__new__(AIAssistant)
    assistant._client = None
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("app.services.ai_assistant.HAS_OPENAI", False)

    assert assistant._get_client() is None
