"""Tests for the versioned scheduling request and response contract."""

import copy
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import object_session, sessionmaker

from app.api.deps import get_current_user
from app.database import get_db
from app.main import app
from app.models.base import Base
from app.models.meter import Meter
from app.models.tariff import Tariff, TariffRevision
from app.models.user import User
from app.schemas.scheduling import SchedulingRequestV1
from app.services.scheduling_optimizer import interval_energy_rates_aud

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "scheduling_v1.json"


@pytest.fixture
def scheduling_api(tmp_path):
    database_url = URL.create(
        "sqlite",
        database=str(tmp_path / "scheduling.sqlite3"),
    )
    # Separate file-backed connections prevent fixture and TestClient sessions
    # from sharing StaticPool's single SQLite connection across threads.
    engine = create_engine(database_url)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = session_factory()

    user = User(email="schedule@example.com", hashed_password="x")
    other_user = User(email="other-schedule@example.com", hashed_password="x")
    db.add_all([user, other_user])
    db.flush()
    meter = Meter(user_id=user.id, nmi="1234567890", suffix="B1", state="VIC")
    other_meter = Meter(user_id=other_user.id, nmi="2234567890", suffix="B1", state="VIC")
    tariff = Tariff(
        user_id=user.id,
        tariff_type="flat",
        flat_rate_cents_kwh=28.0,
        is_preset=False,
        effective_from=date(2020, 1, 1),
    )
    other_tariff = Tariff(
        user_id=other_user.id,
        tariff_type="flat",
        flat_rate_cents_kwh=28.0,
        is_preset=False,
        effective_from=date(2020, 1, 1),
    )
    db.add_all([meter, other_meter, tariff, other_tariff])
    db.flush()
    db.add_all(
        [
            TariffRevision(
                tariff_id=item.id,
                revision_number=1,
                source_type="user_entered",
                confirmed_at=datetime.now(timezone.utc),
                effective_from=date(2020, 1, 1),
                tariff_type="flat",
                flat_rate_cents_kwh=28.0,
                daily_supply_charge_cents=100.0,
                rates_include_gst=True,
                unsupported_components=[],
                is_illustrative=False,
            )
            for item in (tariff, other_tariff)
        ]
    )
    db.commit()
    db.refresh(user)
    db.expunge(user)
    assert object_session(user) is None
    db.refresh(meter)
    db.refresh(other_meter)
    db.refresh(tariff)
    db.refresh(other_tariff)

    def override_get_db():
        request_db = session_factory()
        try:
            yield request_db
        finally:
            request_db.close()

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with TestClient(app) as client:
            yield SimpleNamespace(
                client=client,
                db=db,
                user=user,
                meter=meter,
                other_meter=other_meter,
                tariff=tariff,
                other_tariff=other_tariff,
            )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        db.close()
        try:
            # Every request session must be returned before schema teardown.
            assert engine.pool.checkedout() == 0, "connection leaked before drop_all"
            Base.metadata.drop_all(bind=engine)
        finally:
            engine.dispose()


def _request_payload() -> dict:
    return copy.deepcopy(json.loads(FIXTURE_PATH.read_text())["request"])


def _post_preview(client, payload: dict):
    return client.post("/api/v1/scheduling/v1/plans/preview", json=payload)


def test_scheduling_fixture_validates_and_openapi_exposes_v1(scheduling_api):
    fixture = json.loads(FIXTURE_PATH.read_text())
    request = _request_payload()
    request["meter_id"] = scheduling_api.meter.id
    request["tariff_id"] = scheduling_api.tariff.id
    validated = SchedulingRequestV1.model_validate(request)
    assert validated.schema_version == "1.0"

    response = _post_preview(scheduling_api.client, request)
    assert response.status_code == 200, response.text
    expected_response = copy.deepcopy(fixture["response"])
    expected_response["meter_id"] = scheduling_api.meter.id
    expected_response["tariff"]["tariff_id"] = scheduling_api.tariff.id
    response_body = response.json()
    assert response_body["calculation_evidence"]["status"] == "illustrative"
    assert response_body["calculation_evidence"]["owner_user_id"] == scheduling_api.user.id
    assert response_body["calculation_evidence"]["meter_id"] == scheduling_api.meter.id
    assert response_body["calculation_evidence"]["expires_at"] > response_body[
        "calculation_evidence"
    ]["created_at"]
    assert response_body["calculation_evidence"]["task_set_digest_sha256"]
    assert response_body["calculation_evidence"]["tariff_revision_ids"]
    assert response_body["baseline_eligibility"]["eligible_for_costed_preview"] is True
    response_body.pop("calculation_evidence")
    assert response_body == expected_response

    openapi = app.openapi()
    endpoint = openapi["paths"]["/api/v1/scheduling/v1/plans/preview"]["post"]
    request_schema = openapi["components"]["schemas"]["SchedulingRequestV1"]
    response_schema = openapi["components"]["schemas"]["SchedulingResponseV1"]
    assert request_schema["properties"]["schema_version"]["const"] == "1.0"
    assert response_schema["properties"]["schema_version"]["const"] == "1.0"
    assert endpoint["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/SchedulingRequestV1"
    )
    assert request_schema["examples"] == [fixture["request"]]
    response_example = response_schema["examples"][0]
    assert response_example["preferred_schedule"]["method"] == "preferred"
    assert response_example["baseline_eligibility"]["status"] == "eligible_synthetic"
    assert "calculation_evidence" in response_schema["properties"]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: payload["tasks"][0].update(duration_minutes=45),
            "multiple of interval_minutes",
        ),
        (
            lambda payload: payload["tasks"][0].update(deadline="2026-11-03T08:30:00+11:00"),
            "does not fit within its available window",
        ),
        (lambda payload: payload.update(currency="USD"), "Input should be 'AUD'"),
        (
            lambda payload: payload.update(timezone="Mars/Olympus"),
            "valid IANA timezone",
        ),
        (
            lambda payload: payload["tasks"][0].update(earliest_start="2026-11-03T08:00:00+10:00"),
            "UTC offset does not match",
        ),
        (
            lambda payload: payload["baseline_profile"].update(intervals=[]),
            "at least 1 item",
        ),
        (
            lambda payload: payload["baseline_profile"].update(
                source="independently_measured", scenario_id=None
            ),
            "require a supported measurement_method",
        ),
        (
            lambda payload: payload["baseline_profile"]["intervals"][1].update(
                interval_start="2026-11-03T08:00:00+11:00"
            ),
            "without overlaps",
        ),
        (
            lambda payload: payload["baseline_profile"].update(source="raw_net_meter"),
            "Input should be 'independently_measured' or 'synthetic'",
        ),
    ],
)
def test_invalid_scheduling_contract_inputs_are_rejected(mutate, message):
    payload = _request_payload()
    mutate(payload)

    with pytest.raises(ValidationError, match=message):
        SchedulingRequestV1.model_validate(payload)


def test_missing_tariff_is_explicitly_blocked(scheduling_api):
    payload = _request_payload()
    payload["meter_id"] = scheduling_api.meter.id
    payload["tariff_id"] = None
    scheduling_api.tariff.archived_at = datetime.now(timezone.utc)
    scheduling_api.db.commit()

    response = _post_preview(scheduling_api.client, payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "blocked"
    assert body["tariff"]["status"] == "missing"
    assert body.get("candidate_schedule") is None
    assert body.get("objective_breakdown") is None


def test_user_declared_measured_baseline_is_not_treated_as_verified(scheduling_api):
    payload = _request_payload()
    payload["meter_id"] = scheduling_api.meter.id
    payload["tariff_id"] = scheduling_api.tariff.id
    payload["baseline_profile"].update(
        source="independently_measured",
        scenario_id=None,
        measurement_method="submeter",
    )

    response = _post_preview(scheduling_api.client, payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "blocked"
    assert body["baseline_eligibility"]["status"] == "unavailable"
    assert body["baseline_eligibility"]["eligible_for_costed_preview"] is False
    assert body.get("objective_breakdown") is None
    assert body["calculation_evidence"]["status"] == "unavailable"
    assert "user declaration" in body["blockers"][0]


def test_scheduling_prices_from_revision_not_mutable_projection(scheduling_api):
    payload = _request_payload()
    payload["meter_id"] = scheduling_api.meter.id
    payload["tariff_id"] = scheduling_api.tariff.id
    scheduling_api.tariff.effective_from = None
    scheduling_api.tariff.flat_rate_cents_kwh = None
    scheduling_api.db.commit()

    response = _post_preview(scheduling_api.client, payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tariff"]["status"] == "configured"
    assert body["status"] == "feasible"


def test_synthetic_tou_demo_uses_cheaper_start_and_reports_real_tradeoff(scheduling_api):
    payload = _request_payload()
    payload["meter_id"] = scheduling_api.meter.id
    payload["tariff_id"] = scheduling_api.tariff.id
    payload["scenario_id"] = "synthetic-tou-demo"
    payload["preference_penalty_aud_per_interval"] = 0.01
    payload["tasks"][0].update(
        earliest_start="2026-11-03T06:00:00+11:00",
        deadline="2026-11-03T10:00:00+11:00",
        preferred_start="2026-11-03T09:00:00+11:00",
    )
    baseline_start = datetime.fromisoformat("2026-11-03T06:00:00+11:00")
    payload["baseline_profile"]["scenario_id"] = "synthetic-tou-demo"
    payload["baseline_profile"]["intervals"] = [
        {
            "interval_start": (baseline_start + timedelta(minutes=30 * index)).isoformat(),
            "demand_kw": 0.8,
        }
        for index in range(8)
    ]
    tou_periods = [
        {
            "name": "Off-peak",
            "start_minute": 0,
            "end_minute": 420,
            "rate_cents_kwh": 10.0,
            "days": list(range(7)),
        },
        {
            "name": "Shoulder",
            "start_minute": 420,
            "end_minute": 960,
            "rate_cents_kwh": 25.0,
            "days": list(range(7)),
        },
        {
            "name": "Peak",
            "start_minute": 960,
            "end_minute": 1260,
            "rate_cents_kwh": 55.0,
            "days": list(range(7)),
        },
        {
            "name": "Off-peak late",
            "start_minute": 1260,
            "end_minute": 1440,
            "rate_cents_kwh": 10.0,
            "days": list(range(7)),
        },
    ]
    previous_revision = (
        scheduling_api.db.query(TariffRevision)
        .filter(TariffRevision.tariff_id == scheduling_api.tariff.id)
        .one()
    )
    previous_revision.effective_to = date(2026, 11, 2)
    scheduling_api.db.add(
        TariffRevision(
            tariff_id=scheduling_api.tariff.id,
            revision_number=2,
            source_type="user_entered",
            confirmed_at=datetime.now(timezone.utc),
            effective_from=date(2026, 11, 3),
            tariff_type="tou",
            periods=tou_periods,
            daily_supply_charge_cents=100.0,
            rates_include_gst=True,
            unsupported_components=[],
            is_illustrative=False,
        )
    )
    scheduling_api.db.commit()

    response = _post_preview(scheduling_api.client, payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "feasible"
    assert body["candidate_schedule"]["tasks"][0]["start"] == ("2026-11-03T06:00:00+11:00")
    assert body["reference_schedule"]["tasks"][0]["start"] == ("2026-11-03T06:00:00+11:00")
    breakdown = body["objective_breakdown"]
    assert breakdown["baseline_energy_cost_aud"] == pytest.approx(0.68)
    assert breakdown["candidate_energy_cost_aud"] == pytest.approx(0.92)
    assert breakdown["reference_energy_cost_aud"] == pytest.approx(0.92)
    assert breakdown["energy_cost_delta_aud"] == pytest.approx(0.0)
    assert breakdown["preference_penalty_aud"] == pytest.approx(0.06)
    assert breakdown["total_objective_aud"] == pytest.approx(0.98)
    assert breakdown["reference_objective_aud"] == pytest.approx(0.98)
    assert breakdown["preferred_energy_cost_aud"] == pytest.approx(1.28)
    assert breakdown["milp_vs_preferred_energy_cost_delta_aud"] == pytest.approx(-0.36)
    assert breakdown["greedy_vs_preferred_energy_cost_delta_aud"] == pytest.approx(-0.36)

    revision = (
        scheduling_api.db.query(TariffRevision)
        .filter(TariffRevision.tariff_id == scheduling_api.tariff.id)
        .order_by(TariffRevision.revision_number.desc())
        .first()
    )
    rates = interval_energy_rates_aud(
        revision, SchedulingRequestV1.model_validate(payload), "VIC"
    )
    assert rates is not None
    preferred_task_charge = 2.4 * 0.5 * sum(rates[6:8])
    proposed_task_charge = (
        breakdown["candidate_energy_cost_aud"] - breakdown["baseline_energy_cost_aud"]
    )
    assert preferred_task_charge == pytest.approx(0.60)
    assert proposed_task_charge == pytest.approx(0.24)
    assert proposed_task_charge - preferred_task_charge == pytest.approx(-0.36)


def test_tariff_effective_dates_cover_the_full_baseline_cost_horizon(scheduling_api):
    payload = _request_payload()
    payload["meter_id"] = scheduling_api.meter.id
    payload["tariff_id"] = scheduling_api.tariff.id
    baseline_start = datetime.fromisoformat("2026-11-02T23:30:00+11:00")
    payload["baseline_profile"]["intervals"] = [
        {
            "interval_start": (baseline_start + timedelta(minutes=30 * index)).isoformat(),
            "demand_kw": 0.8,
        }
        for index in range(21)
    ]
    revision = (
        scheduling_api.db.query(TariffRevision)
        .filter(TariffRevision.tariff_id == scheduling_api.tariff.id)
        .one()
    )
    revision.effective_from = datetime(2026, 11, 3).date()
    revision.effective_to = datetime(2026, 11, 3).date()
    scheduling_api.db.commit()

    response = _post_preview(scheduling_api.client, payload)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "blocked"
    assert response.json()["tariff"]["status"] == "outside_effective_dates"


def test_scheduling_blocks_when_horizon_crosses_tariff_revision_boundary(scheduling_api):
    payload = _request_payload()
    payload["meter_id"] = scheduling_api.meter.id
    payload["tariff_id"] = scheduling_api.tariff.id
    baseline_start = datetime.fromisoformat("2026-11-02T23:30:00+11:00")
    payload["baseline_profile"]["intervals"] = [
        {
            "interval_start": (baseline_start + timedelta(minutes=30 * index)).isoformat(),
            "demand_kw": 0.8,
        }
        for index in range(52)
    ]
    previous_revision = (
        scheduling_api.db.query(TariffRevision)
        .filter(TariffRevision.tariff_id == scheduling_api.tariff.id)
        .one()
    )
    previous_revision.effective_to = date(2026, 11, 2)
    scheduling_api.db.add(
        TariffRevision(
            tariff_id=scheduling_api.tariff.id,
            revision_number=2,
            source_type="user_entered",
            confirmed_at=datetime.now(timezone.utc),
            effective_from=date(2026, 11, 3),
            tariff_type="flat",
            flat_rate_cents_kwh=28.0,
            daily_supply_charge_cents=100.0,
            rates_include_gst=True,
            unsupported_components=[],
            is_illustrative=False,
        )
    )
    scheduling_api.db.commit()

    response = _post_preview(scheduling_api.client, payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "blocked"
    assert body["tariff"]["status"] == "missing"
    assert any("revision boundary" in blocker for blocker in body["blockers"])


def test_infeasible_power_limit_is_explicit_in_api_response(scheduling_api):
    payload = _request_payload()
    payload["meter_id"] = scheduling_api.meter.id
    payload["tariff_id"] = scheduling_api.tariff.id
    payload["grid_power_limit_kw"] = 3.0

    response = _post_preview(scheduling_api.client, payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "infeasible"
    assert "candidate_schedule" not in body
    assert body["reference_schedule"]["status"] == "not_found"
    assert body["blockers"]


def test_invalid_contract_request_is_rejected_by_api(scheduling_api):
    payload = _request_payload()
    payload["meter_id"] = scheduling_api.meter.id
    payload["tariff_id"] = scheduling_api.tariff.id
    payload["tasks"][0]["duration_minutes"] = 45

    response = _post_preview(scheduling_api.client, payload)

    assert response.status_code == 422


def test_foreign_meter_is_rejected(scheduling_api):
    payload = _request_payload()
    payload["meter_id"] = scheduling_api.other_meter.id
    payload["tariff_id"] = scheduling_api.tariff.id

    response = _post_preview(scheduling_api.client, payload)

    assert response.status_code == 404


def test_foreign_tariff_is_rejected(scheduling_api):
    payload = _request_payload()
    payload["meter_id"] = scheduling_api.meter.id
    payload["tariff_id"] = scheduling_api.other_tariff.id

    response = _post_preview(scheduling_api.client, payload)

    assert response.status_code == 404
    assert response.json()["detail"] == "Tariff not found"
