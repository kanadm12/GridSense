"""PostgreSQL integration: scheduling, tariff confirmation, recommendations and NEM12 exclusions.

Every expected value is either taken from the canonical ``scheduling_v1.json``
fixture or recomputed by hand in the test. Source-quality rules are never
relaxed to produce positive usage or cost.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.models.meter import Meter
from app.models.tariff import Tariff, TariffRevision
from app.models.user import User
from app.services.interval_quality import expected_interval_ends_utc
from tests.integration.test_tariffs_billing import (
    BILL_DAY,
    _breakdown,
    _reading,
    _register_and_login,
)

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "scheduling_v1.json"
PREVIEW = "/api/v1/scheduling/v1/plans/preview"
SCHEDULE_RATE_CENTS = 28.0


def _seed_owner_meter_and_tariff(
    session_factory: sessionmaker[Session], email: str, *, rate_cents: float = SCHEDULE_RATE_CENTS
) -> tuple[int, int]:
    """Create a VIC meter and a confirmed flat tariff owned by ``email``."""
    with session_factory() as db:
        user = db.query(User).filter(User.email == email).one()
        meter = Meter(user_id=user.id, nmi="VBBB987654", suffix="E1", state="VIC")
        tariff = Tariff(
            user_id=user.id,
            tariff_type="flat",
            flat_rate_cents_kwh=rate_cents,
            daily_supply_charge_cents=100.0,
            rates_include_gst=True,
            is_preset=False,
            effective_from=date(2020, 1, 1),
        )
        db.add_all([meter, tariff])
        db.flush()
        db.add(
            TariffRevision(
                tariff_id=tariff.id,
                revision_number=1,
                source_type="user_entered",
                confirmed_at=datetime.now(UTC),
                effective_from=date(2020, 1, 1),
                tariff_type="flat",
                flat_rate_cents_kwh=rate_cents,
                daily_supply_charge_cents=100.0,
                rates_include_gst=True,
                unsupported_components=[],
                is_illustrative=False,
            )
        )
        db.commit()
        return meter.id, tariff.id


def _schedule_payload(meter_id: int, tariff_id: int) -> dict:
    payload = copy.deepcopy(json.loads(FIXTURE.read_text())["request"])
    payload["meter_id"] = meter_id
    payload["tariff_id"] = tariff_id
    return payload


@pytest.fixture
def scheduling_owner(client, pg_db, pg_session_factory):
    email = "schedule-owner@example.com"
    headers = _register_and_login(client, email)
    meter_id, tariff_id = _seed_owner_meter_and_tariff(pg_session_factory, email)
    return {"headers": headers, "meter_id": meter_id, "tariff_id": tariff_id}


def test_preview_reconciles_preferred_greedy_and_milp_to_fixture(client, scheduling_owner):
    fixture_response = json.loads(FIXTURE.read_text())["response"]
    payload = _schedule_payload(scheduling_owner["meter_id"], scheduling_owner["tariff_id"])

    response = client.post(PREVIEW, json=payload, headers=scheduling_owner["headers"])
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == "feasible"
    assert body["candidate_schedule"]["method"] == "milp"
    assert body["reference_schedule"]["method"] == "deterministic_greedy"

    breakdown = body["objective_breakdown"]
    expected = fixture_response["objective_breakdown"]
    # Independent check: baseline 4 x 0.4 kWh = 1.6 kWh; task 2.4 kW x 1 h = 2.4 kWh.
    assert 1.6 * SCHEDULE_RATE_CENTS / 100 == pytest.approx(expected["baseline_energy_cost_aud"])
    assert 4.0 * SCHEDULE_RATE_CENTS / 100 == pytest.approx(expected["candidate_energy_cost_aud"])
    assert breakdown["baseline_energy_cost_aud"] == pytest.approx(0.448)
    assert breakdown["candidate_energy_cost_aud"] == pytest.approx(1.12)
    assert breakdown["reference_energy_cost_aud"] == pytest.approx(1.12)
    assert breakdown["preferred_energy_cost_aud"] == pytest.approx(1.12)
    assert breakdown["preference_penalty_aud"] == pytest.approx(0.0)
    assert breakdown["milp_vs_preferred_energy_cost_delta_aud"] == pytest.approx(0.0)
    assert breakdown["greedy_vs_preferred_energy_cost_delta_aud"] == pytest.approx(0.0)

    task = body["candidate_schedule"]["tasks"][0]
    assert task["task_id"] == "water-heater-1"
    assert task["omitted"] is False
    assert task["start"].startswith("2026-11-03T08:30:00")
    assert body["candidate_schedule"]["total_energy_kwh"] == pytest.approx(4.0)


def test_zero_benefit_schedule_on_flat_tariff_reports_no_energy_saving(
    client, scheduling_owner
):
    payload = _schedule_payload(scheduling_owner["meter_id"], scheduling_owner["tariff_id"])
    payload["tasks"][0]["preferred_start"] = payload["tasks"][0]["earliest_start"]

    response = client.post(PREVIEW, json=payload, headers=scheduling_owner["headers"])
    assert response.status_code == 200, response.text
    breakdown = response.json()["objective_breakdown"]
    # A flat tariff prices every start identically, so moving the task yields no saving.
    assert breakdown["energy_cost_delta_aud"] == pytest.approx(0.0)
    assert breakdown["preference_penalty_aud"] == pytest.approx(0.0)


def test_infeasible_power_limit_returns_no_candidate_schedule(client, scheduling_owner):
    payload = _schedule_payload(scheduling_owner["meter_id"], scheduling_owner["tariff_id"])
    # Baseline 0.8 kW plus the 2.4 kW task is 3.2 kW, which exceeds the 3.0 kW limit.
    payload["grid_power_limit_kw"] = 3.0

    response = client.post(PREVIEW, json=payload, headers=scheduling_owner["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "infeasible"
    assert body.get("candidate_schedule") is None
    assert body["reference_schedule"]["status"] == "not_found"
    assert body["blockers"]


def test_unconfirmed_tariff_creation_is_rejected_and_appends_no_revision(
    client, pg_db, pg_session_factory
):
    headers = _register_and_login(client, "unconfirmed-tariff@example.com")
    response = client.post(
        "/api/v1/tariffs",
        json={
            "tariff_type": "flat",
            "flat_rate_cents_kwh": 30.0,
            "effective_from": "2025-01-01",
            "confirmed": False,
        },
        headers=headers,
    )
    assert response.status_code == 422, response.text
    revisions = client.get("/api/v1/tariffs/revisions", headers=headers)
    assert revisions.status_code == 200, revisions.text
    assert revisions.json() == []


def test_confirmed_revisions_are_immutable_after_later_change(client, pg_db, pg_session_factory):
    headers = _register_and_login(client, "immutable-tariff@example.com")
    first = {
        "tariff_type": "flat",
        "flat_rate_cents_kwh": 30.0,
        "effective_from": "2025-01-01",
        "confirmed": True,
        "unmodeled_components_confirmed_absent": True,
    }
    assert client.post("/api/v1/tariffs", json=first, headers=headers).status_code == 201
    second = {**first, "flat_rate_cents_kwh": 45.0, "effective_from": "2025-07-01"}
    assert client.post("/api/v1/tariffs", json=second, headers=headers).status_code == 201

    revisions = client.get("/api/v1/tariffs/revisions", headers=headers).json()
    assert len(revisions) == 2
    by_number = {item["revision_number"]: item for item in revisions}
    assert by_number[1]["flat_rate_cents_kwh"] == pytest.approx(30.0)
    assert by_number[2]["flat_rate_cents_kwh"] == pytest.approx(45.0)


def test_illustrative_preset_tariff_cannot_be_scheduled(client, pg_db, pg_session_factory):
    headers = _register_and_login(client, "preset-schedule@example.com")
    presets = client.get("/api/v1/tariffs/presets", headers=headers)
    assert presets.status_code == 200, presets.text
    preset_id = presets.json()[0]["id"]
    applied = client.post(f"/api/v1/tariffs/from-preset/{preset_id}", headers=headers)
    assert applied.status_code == 200, applied.text
    tariff_id = applied.json()["id"]

    # The schema allows one tariff row per user, so the preset tariff is the user's
    # tariff and only a meter is seeded alongside it.
    with pg_session_factory() as db:
        owner = db.query(User).filter(User.email == "preset-schedule@example.com").one()
        meter = Meter(user_id=owner.id, nmi="VBBB987655", suffix="E1", state="VIC")
        db.add(meter)
        db.commit()
        meter_id = meter.id
    payload = _schedule_payload(meter_id, tariff_id)
    response = client.post(PREVIEW, json=payload, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "blocked"
    assert body.get("candidate_schedule") is None
    assert body["blockers"]


def test_foreign_and_missing_resources_return_indistinguishable_404(
    client, scheduling_owner, pg_session_factory
):
    stranger = _register_and_login(client, "stranger-404@example.com")
    missing_id = 987654

    foreign_meter = client.get(
        f"/api/v1/meters/{scheduling_owner['meter_id']}", headers=stranger
    )
    missing_meter = client.get(f"/api/v1/meters/{missing_id}", headers=stranger)
    assert foreign_meter.status_code == missing_meter.status_code == 404
    assert foreign_meter.json()["detail"].replace(
        str(scheduling_owner["meter_id"]), "<id>"
    ) == missing_meter.json()["detail"].replace(str(missing_id), "<id>")

    foreign_schedule = client.post(
        PREVIEW,
        json=_schedule_payload(scheduling_owner["meter_id"], scheduling_owner["tariff_id"]),
        headers=stranger,
    )
    missing_schedule = client.post(
        PREVIEW,
        json=_schedule_payload(missing_id, scheduling_owner["tariff_id"]),
        headers=stranger,
    )
    assert foreign_schedule.status_code == missing_schedule.status_code == 404
    assert foreign_schedule.json()["detail"].replace(
        str(scheduling_owner["meter_id"]), "<id>"
    ) == missing_schedule.json()["detail"].replace(str(missing_id), "<id>")


def test_recommendations_without_evidence_are_unquantified(client, pg_db, pg_session_factory):
    email = "no-evidence@example.com"
    headers = _register_and_login(client, email)
    meter_id, _ = _seed_owner_meter_and_tariff(pg_session_factory, email)

    response = client.get(f"/api/v1/recommendations/{meter_id}", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_potential_savings"] in (None, 0, 0.0)
    for item in body["recommendations"]:
        assert item["potential_savings_dollars"] in (None, 0, 0.0), item["id"]
        assert item["estimate_status"] == "unquantified", item["id"]


def test_unverified_time_basis_intervals_are_excluded_from_billing(
    client, pg_db, pg_session_factory
):
    email = "time-basis@example.com"
    headers = _register_and_login(client, email)
    meter_id, _ = _seed_owner_meter_and_tariff(pg_session_factory, email)
    ends = list(expected_interval_ends_utc(BILL_DAY, "VIC", 30))
    unverified = set(ends[:8])
    with pg_session_factory() as db:
        for end in ends:
            basis = "unverified_clock" if end in unverified else "UTC"
            db.add(_reading(meter_id, end, source_time_basis=basis))
        db.commit()

    breakdown = _breakdown(client, headers, meter_id, BILL_DAY, BILL_DAY)
    # Eight intervals with an unverified clock must not be billed as consumption.
    assert breakdown["import_kwh"] == pytest.approx(40 * 0.5)
    assert breakdown["data_status"] == "partial"
    assert breakdown["full_bill_available"] is False
