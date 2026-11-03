"""PostgreSQL integration: confirmed tariffs, billing reconciliation and owner scoping.

Data is seeded directly through the ORM with deterministic, quality-A measured
readings so that expected totals can be recomputed independently in the test.
Each test starts from a truncated schema (see ``pg_db`` in conftest).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.models.meter import Meter
from app.models.reading import Reading
from app.models.tariff import Tariff, TariffRevision
from app.models.user import User
from app.services.interval_quality import expected_interval_ends_utc

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery"  # noqa: S105 - disposable test credential
BILL_DAY = date(2025, 4, 1)  # AEDT (+11) in Victoria; DST changes on 2025-04-06
RATE_CENTS = 30.0
SUPPLY_CENTS = 100.0


def _register_and_login(client, email: str) -> dict[str, str]:
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Integration User"},
    )
    assert reg.status_code == 201, reg.text
    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _seed_meter_and_confirmed_tariff(
    session_factory: sessionmaker[Session], email: str
) -> tuple[int, int]:
    with session_factory() as db:
        user = db.query(User).filter(User.email == email).one()
        meter = Meter(
            user_id=user.id, nmi="VAAA123456", suffix="E1", state="VIC", interval_minutes=30
        )
        tariff = Tariff(
            user_id=user.id,
            tariff_type="flat",
            flat_rate_cents_kwh=RATE_CENTS,
            daily_supply_charge_cents=SUPPLY_CENTS,
            rates_include_gst=True,
            is_preset=False,
            effective_from=date(2025, 1, 1),
        )
        db.add_all([meter, tariff])
        db.flush()
        db.add(
            TariffRevision(
                tariff_id=tariff.id,
                revision_number=1,
                source_type="user_entered",
                confirmed_at=datetime.now(UTC),
                effective_from=date(2025, 1, 1),
                tariff_type="flat",
                flat_rate_cents_kwh=RATE_CENTS,
                daily_supply_charge_cents=SUPPLY_CENTS,
                rates_include_gst=True,
                unsupported_components=[],
                is_illustrative=False,
            )
        )
        db.commit()
        return meter.id, tariff.id


def _reading(meter_id: int, end_utc: datetime, *, value: float = 0.5, **overrides) -> Reading:
    fields = {
        "meter_id": meter_id,
        "timestamp": end_utc,
        "interval_minutes": 30,
        "value": value,
        "source_value": value,
        "source_unit": "kWh",
        "provenance_kind": "measured",
        "source_time_basis": "UTC",
        "quality": "A",
        "register_type": "B",
        "direction": "import",
    }
    fields.update(overrides)
    return Reading(**fields)


def _seed_bill_day(session_factory: sessionmaker[Session], meter_id: int) -> list[datetime]:
    """Return the expected UTC interval ends for ``BILL_DAY`` after inserting clean readings."""
    ends = list(expected_interval_ends_utc(BILL_DAY, "VIC", 30))
    assert len(ends) == 48
    with session_factory() as db:
        db.add_all([_reading(meter_id, end) for end in ends])
        db.commit()
    return ends


def _breakdown(client, headers, meter_id: int, start: date, end: date) -> dict:
    response = client.get(
        f"/api/v1/billing/comparison/{meter_id}",
        params={"current_start": start.isoformat(), "current_end": end.isoformat()},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["current_breakdown"]


def test_confirmed_tariff_revisions_are_owner_scoped(client, pg_db, pg_session_factory):
    owner = _register_and_login(client, "tariff-owner@example.com")
    other = _register_and_login(client, "tariff-other@example.com")
    _seed_meter_and_confirmed_tariff(pg_session_factory, "tariff-owner@example.com")

    own = client.get("/api/v1/tariffs/revisions", headers=owner)
    assert own.status_code == 200, own.text
    revisions = own.json()
    assert len(revisions) == 1
    assert revisions[0]["revision_number"] == 1
    assert revisions[0]["confirmed_at"] is not None

    stranger = client.get("/api/v1/tariffs/revisions", headers=other)
    assert stranger.status_code == 200, stranger.text
    assert stranger.json() == []


def test_billing_reconciles_independently_recomputed_totals(client, pg_db, pg_session_factory):
    headers = _register_and_login(client, "bill-owner@example.com")
    meter_id, _ = _seed_meter_and_confirmed_tariff(pg_session_factory, "bill-owner@example.com")
    _seed_bill_day(pg_session_factory, meter_id)

    breakdown = _breakdown(client, headers, meter_id, BILL_DAY, BILL_DAY)

    # Independent recomputation: 48 x 0.5 kWh at 30 c/kWh plus one 100 c daily supply charge.
    expected_kwh = 48 * 0.5
    expected_import = round(expected_kwh * RATE_CENTS / 100, 2)
    expected_total = round(expected_import + SUPPLY_CENTS / 100, 2)
    assert breakdown["data_status"] == "complete"
    assert breakdown["import_kwh"] == pytest.approx(expected_kwh)
    assert breakdown["coverage_fraction"] == pytest.approx(1.0)
    assert breakdown["customer_estimate_available"] is True
    assert breakdown["full_bill_available"] is True
    assert breakdown["total_cost"] == pytest.approx(expected_total, abs=0.005)
    # Rates include GST, so the GST component is total / 11 (rounded to cents).
    assert breakdown["gst_amount"] == pytest.approx(round(expected_total / 11, 2), abs=0.005)

    # Line items must reconcile to the stated total when the GST-inclusive component is excluded.
    included = [item for item in breakdown["line_items"] if item.get("included_in_total", True)]
    assert sum(item["amount"] for item in included) == pytest.approx(expected_total, abs=0.01)


def test_billing_excludes_unqualified_and_unknown_direction_intervals(
    client, pg_db, pg_session_factory
):
    headers = _register_and_login(client, "bill-excl@example.com")
    meter_id, _ = _seed_meter_and_confirmed_tariff(pg_session_factory, "bill-excl@example.com")
    ends = list(expected_interval_ends_utc(BILL_DAY, "VIC", 30))
    with pg_session_factory() as db:
        db.add_all(_reading(meter_id, end) for end in ends[:40])
        # Estimated/substituted quality is not headline-billable.
        db.add_all(_reading(meter_id, end, quality="V") for end in ends[40:44])
        # Unknown direction must never be billed as import.
        db.add_all(
            _reading(meter_id, end, direction="unknown", register_type="B")
            for end in ends[44:48]
        )
        db.commit()

    breakdown = _breakdown(client, headers, meter_id, BILL_DAY, BILL_DAY)

    assert breakdown["import_kwh"] == pytest.approx(40 * 0.5)
    assert breakdown["excluded_quality_count"] == 4
    assert breakdown["unresolved_reading_count"] == 8
    assert breakdown["data_status"] == "partial"
    assert breakdown["full_bill_available"] is False
    assert breakdown["coverage_fraction"] == pytest.approx(40 / 48)
    expected_total = round(20 * RATE_CENTS / 100 + 1.0, 2)
    assert breakdown["total_cost"] == pytest.approx(expected_total, abs=0.005)


def test_billing_without_confirmed_tariff_produces_no_estimate(client, pg_db, pg_session_factory):
    headers = _register_and_login(client, "bill-none@example.com")
    with pg_session_factory() as db:
        user = db.query(User).filter(User.email == "bill-none@example.com").one()
        meter = Meter(
            user_id=user.id, nmi="VAAA999999", suffix="E1", state="VIC", interval_minutes=30
        )
        db.add(meter)
        db.commit()
        meter_id = meter.id
    _seed_bill_day(pg_session_factory, meter_id)

    breakdown = _breakdown(client, headers, meter_id, BILL_DAY, BILL_DAY)

    assert breakdown["customer_estimate_available"] is False
    assert breakdown["full_bill_available"] is False
    assert breakdown["total_cost"] is None


def test_billing_and_recommendations_enforce_meter_ownership(client, pg_db, pg_session_factory):
    owner = _register_and_login(client, "meter-owner@example.com")
    other = _register_and_login(client, "meter-other@example.com")
    meter_id, _ = _seed_meter_and_confirmed_tariff(pg_session_factory, "meter-owner@example.com")
    window = {
        "current_start": BILL_DAY.isoformat(),
        "current_end": BILL_DAY.isoformat(),
    }

    billing_url = f"/api/v1/billing/comparison/{meter_id}"
    assert client.get(billing_url, params=window, headers=other).status_code == 404
    assert (
        client.get(f"/api/v1/recommendations/{meter_id}", headers=other).status_code == 404
    )
    assert (
        client.get(f"/api/v1/recommendations/{meter_id}", headers=owner).status_code == 200
    )
