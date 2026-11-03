"""Bill comparison endpoints."""

from collections import Counter
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.ownership import verify_meter_ownership
from app.database import get_db
from app.models.meter import Meter
from app.models.reading import Reading
from app.models.tariff import Tariff, TariffRevision
from app.models.user import User
from app.schemas.billing import (
    BillComparisonResponse,
    BillLineItem,
    BillPeriodBreakdown,
    PeriodComparison,
)
from app.services.interval_quality import (
    evaluate_interval,
    expected_interval_ends_utc,
)
from app.services.tariff import (
    DEFAULT_FLAT_RATE_CENTS,
    MARKET_TIME,
    local_interval_end_date,
    market_bounds_for_local_dates,
    market_interval_start_to_local,
    timezone_for_state,
)

router = APIRouter(prefix="/billing", tags=["Billing"])

# Scenario-only supply charge used only when illustrative_scenario=true.
DEFAULT_SUPPLY_CHARGE_CENTS = 100.0


def calculate_period_cost(
    db: Session, meter_id: int, start: date, end: date, tariff: Tariff | None
) -> tuple[float, float | None, int]:
    """Compatibility wrapper returning import kWh, available estimate, and days."""
    breakdown = calculate_period_breakdown(db, meter_id, start, end, tariff)
    return breakdown.import_kwh, breakdown.total_cost, (end - start).days + 1


def _money(value: float | Decimal) -> float:
    """Round a monetary component to cents using conventional half-up rounding."""
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _window_rate(tariff: Tariff, timestamp, interval_minutes: int, state: str):
    """Return a configured local-time window rate, or None when no window matches."""
    local_start = market_interval_start_to_local(timestamp, interval_minutes, state)
    minute = local_start.hour * 60 + local_start.minute
    matches = [
        period
        for period in (tariff.periods or [])
        if local_start.weekday() in period.get("days", range(7))
        and period.get("start_minute", 0) <= minute < period.get("end_minute", 0)
    ]
    if len(matches) > 1:
        raise ValueError("Configured tariff windows overlap for an imported interval")
    return matches[0] if matches else None


def calculate_period_breakdown(
    db: Session,
    meter_id: int,
    start: date,
    end: date,
    tariff: Tariff | None,
    *,
    allow_illustrative: bool = False,
) -> BillPeriodBreakdown:
    """Price only intervals covered by a confirmed revision or explicit scenario."""
    if end < start:
        raise ValueError("Billing period end cannot be before its start")
    meter = db.query(Meter).filter(Meter.id == meter_id).first()
    if meter is None:
        raise ValueError(f"Meter {meter_id} was not found; cannot determine billing timezone")
    market_start, market_end = market_bounds_for_local_dates(start, end, meter.state)
    revision_rows: list[TariffRevision] = []
    if tariff is not None and tariff.id is not None:
        revision_rows = (
            db.query(TariffRevision)
            .filter(
                TariffRevision.tariff_id == tariff.id,
                TariffRevision.confirmed_at.is_not(None),
                TariffRevision.is_illustrative.is_(False),
            )
            .order_by(TariffRevision.revision_number)
            .all()
        )
    if allow_illustrative and tariff is None:
        revision_rows = [
            SimpleNamespace(
                id=None,
                revision_number=0,
                source_type="illustrative_scenario",
                confirmed_at=None,
                effective_from=start,
                effective_to=end,
                tariff_type="flat",
                retailer_name="Illustrative scenario",
                flat_rate_cents_kwh=DEFAULT_FLAT_RATE_CENTS,
                peak_rate_cents_kwh=None,
                off_peak_rate_cents_kwh=None,
                shoulder_rate_cents_kwh=None,
                feed_in_rate_cents_kwh=None,
                periods=None,
                rates_include_gst=True,
                demand_charge_dollars_kw=None,
                daily_supply_charge_cents=DEFAULT_SUPPLY_CHARGE_CENTS,
                unsupported_components=["all non-modeled plan terms"],
                is_illustrative=True,
            )
        ]
    days = (end - start).days + 1
    revision_by_day: dict[date, TariffRevision] = {}
    unpriced_days = 0
    overlapping_revisions = False
    for day_offset in range(days):
        day = start + timedelta(days=day_offset)
        applicable = [
            revision
            for revision in revision_rows
            if revision.effective_from is not None
            and revision.effective_from <= day
            and (revision.effective_to is None or day <= revision.effective_to)
        ]
        if len(applicable) == 1:
            revision_by_day[day] = applicable[0]
        else:
            unpriced_days += 1
            if len(applicable) > 1:
                overlapping_revisions = True
    if allow_illustrative and tariff is not None and tariff.is_preset:
        revision_by_day = {
            start + timedelta(days=offset): revision
            for offset in range(days)
            for revision in revision_rows
            if revision.is_illustrative
            and revision.effective_from is not None
            and revision.effective_from <= start + timedelta(days=offset)
            and (
                revision.effective_to is None
                or start + timedelta(days=offset) <= revision.effective_to
            )
        }
        unpriced_days = days - len(revision_by_day)
    if allow_illustrative and not revision_by_day and tariff is not None and tariff.is_preset:
        revision_by_day = {
            start + timedelta(days=offset): SimpleNamespace(
                id=None,
                revision_number=0,
                source_type="illustrative_preset",
                confirmed_at=None,
                effective_from=start,
                effective_to=end,
                tariff_type=tariff.tariff_type,
                retailer_name=tariff.retailer_name,
                flat_rate_cents_kwh=tariff.flat_rate_cents_kwh,
                peak_rate_cents_kwh=tariff.peak_rate_cents_kwh,
                off_peak_rate_cents_kwh=tariff.off_peak_rate_cents_kwh,
                shoulder_rate_cents_kwh=tariff.shoulder_rate_cents_kwh,
                feed_in_rate_cents_kwh=tariff.feed_in_rate_cents_kwh,
                periods=tariff.periods,
                rates_include_gst=tariff.rates_include_gst,
                demand_charge_dollars_kw=None,
                daily_supply_charge_cents=tariff.daily_supply_charge_cents,
                unsupported_components=["customer-specific contract terms"],
                is_illustrative=True,
            )
            for offset in range(days)
        }
        unpriced_days = 0

    readings = (
        db.query(Reading)
        .filter(
            Reading.meter_id == meter_id,
            Reading.timestamp >= market_start - timedelta(days=1),
            Reading.timestamp <= market_end + timedelta(days=1),
        )
        .all()
    )
    interval_minutes = meter.interval_minutes
    if interval_minutes not in (5, 15, 30):
        raise ValueError(f"Unsupported meter interval length {interval_minutes}")
    expected_ends = {
        end_utc
        for day_offset in range(days)
        for end_utc in expected_interval_ends_utc(
            start + timedelta(days=day_offset), meter.state, interval_minutes
        )
    }
    expected_count = len(expected_ends)
    slot_rows: dict[tuple[datetime, str | None], list[tuple[Reading, object]]] = {}
    unresolved_time_basis_count = 0
    invalid_reading_count = 0
    for reading in readings:
        decision = evaluate_interval(
            reading,
            source_unit=reading.source_unit,
            source_time_basis=reading.source_time_basis,
            provenance_kind=reading.provenance_kind,
            required_direction=(
                reading.direction if reading.direction in {"import", "export"} else "import"
            ),
        )
        if decision.reason == "unresolved_time_basis":
            raw_timestamp = reading.timestamp
            if raw_timestamp.tzinfo is not None:
                raw_timestamp = raw_timestamp.astimezone(MARKET_TIME).replace(
                    tzinfo=None
                )
            if market_start <= raw_timestamp <= market_end:
                unresolved_time_basis_count += 1
        elif decision.end_utc in expected_ends:
            slot_rows.setdefault(
                (decision.end_utc, reading.direction), []
            ).append((reading, decision))
        elif decision.end_utc is None:
            invalid_reading_count += 1

    imports: list[Reading] = []
    exports: list[Reading] = []
    excluded_quality_count = 0
    legacy_direction_unverified_count = 0
    unresolved_direction_count = 0
    duplicate_count = 0
    observed_slots = {end_utc for end_utc, _ in slot_rows}
    for rows in slot_rows.values():
        if len(rows) > 1:
            duplicate_count += len(rows) - 1
            continue
        reading, decision = rows[0]
        if decision.reason == "excluded_quality":
            excluded_quality_count += 1
        elif decision.reason == "legacy_direction_unverified":
            legacy_direction_unverified_count += 1
        elif decision.reason == "unresolved_direction":
            unresolved_direction_count += 1
        elif decision.eligible:
            if reading.direction == "import":
                imports.append(reading)
            elif reading.direction == "export":
                exports.append(reading)
    unresolved = sum(
        1
        for rows in slot_rows.values()
        if len(rows) == 1 and not rows[0][1].eligible
    ) + unresolved_time_basis_count
    provenance_kinds = {
        reading.provenance_kind
        for rows in slot_rows.values()
        for reading, _ in rows
    }
    if provenance_kinds == {"measured"}:
        provenance_status = "measured"
    elif provenance_kinds == {"synthetic"}:
        provenance_status = "synthetic"
    elif provenance_kinds:
        provenance_status = "mixed"
    else:
        provenance_status = "unavailable"
    observed_count = len(observed_slots)
    eligible_import_count = len(
        {
            end_utc
            for end_utc, direction in slot_rows
            if direction == "import"
            and len(slot_rows[(end_utc, direction)]) == 1
            and slot_rows[(end_utc, direction)][0][1].eligible
        }
    )
    coverage_fraction = (
        eligible_import_count / expected_count if expected_count else 0.0
    )
    missing_count = max(expected_count - eligible_import_count, 0)
    limitations: list[str] = [
        "This is a calculation from confirmed user-entered rates, not a retailer-issued bill."
    ]
    if not revision_by_day:
        limitations.append(
            "No confirmed tariff revision with an evidenced effective date covers this period."
        )
    if overlapping_revisions:
        limitations.append(
            "Multiple confirmed tariff revisions overlap; affected days are left unpriced."
        )
    if unpriced_days:
        limitations.append(
            f"{unpriced_days} day(s) have no uniquely applicable confirmed tariff revision."
        )
    if unresolved:
        limitations.append(
            f"{unresolved} interval record(s) are excluded for unresolved direction, "
            "quality, provenance, unit, or time basis."
        )
    if legacy_direction_unverified_count:
        limitations.append(
            f"{legacy_direction_unverified_count} legacy null/B record(s) have "
            "unverified direction and are excluded."
        )
    if excluded_quality_count:
        limitations.append(
            f"{excluded_quality_count} non-quality-A interval(s) are excluded from "
            "headline billing energy under the conservative policy."
        )
    if duplicate_count:
        limitations.append(
            f"{duplicate_count} duplicate interval record(s) were excluded; "
            "conflicting slot values are not selected."
        )
    if unresolved_time_basis_count:
        limitations.append(
            f"{unresolved_time_basis_count} interval(s) have an unverified "
            "timestamp basis and are excluded."
        )
    if missing_count:
        limitations.append(
            f"{missing_count} expected import interval(s) are absent; energy "
            "charges may be understated."
        )
    if tariff and tariff.periods:
        limitations.append(
            "Custom periods use local weekday schedules; no public-holiday calendar is configured."
        )
    if tariff and tariff.tariff_type in {"tou", "flexible", "demand"} and not tariff.periods:
        limitations.append(
            "TOU rates without user-confirmed time windows are left unpriced; "
            "no generic schedule is assumed."
        )

    line_items: list[BillLineItem] = []
    buckets: dict[tuple[str, float, int | None, bool], float] = {}
    unpriced_imports = 0
    unpriced_kwh = 0.0
    import_kwh = sum(reading.value for reading in imports)
    export_kwh = sum(reading.value for reading in exports)
    for reading in imports:
        local_day = local_interval_end_date(
            reading.timestamp, meter.state
        )
        revision = revision_by_day.get(local_day)
        if revision is None:
            unpriced_imports += 1
            unpriced_kwh += reading.value
            continue
        period_name = "flat"
        if revision.tariff_type == "flat":
            rate = revision.flat_rate_cents_kwh
        elif revision.periods:
            window = _window_rate(
                revision, reading.timestamp, reading.interval_minutes, meter.state
            )
            period_name = window["name"] if window else "unpriced"
            rate = window["rate_cents_kwh"] if window else None
        else:
            rate = None
        if rate is None:
            unpriced_imports += 1
            unpriced_kwh += reading.value
            continue
        key = (
            period_name,
            rate,
            revision.id,
            revision.rates_include_gst,
        )
        buckets[key] = buckets.get(key, 0.0) + reading.value

    import_charge = 0.0
    gst_included_charge = 0.0
    gst_exclusive_charge = 0.0
    used_revision_ids: set[int] = set()
    for (period_name, rate, revision_id, rates_include_gst), quantity in sorted(
        buckets.items()
    ):
        amount = _money(quantity * rate / 100)
        import_charge += amount
        if rates_include_gst:
            gst_included_charge += amount
        else:
            gst_exclusive_charge += amount
        if revision_id is not None:
            used_revision_ids.add(revision_id)
        line_items.append(
            BillLineItem(
                label=f"{period_name.replace('_', ' ').title()} import energy",
                quantity_kwh=round(quantity, 4),
                rate_cents_kwh=rate,
                amount=amount,
            )
        )
    import_charge = _money(import_charge)

    export_credit = 0.0
    export_credit_by_rate: dict[tuple[float, int | None], float] = {}
    unpriced_export_kwh = 0.0
    for reading in exports:
        local_day = local_interval_end_date(reading.timestamp, meter.state)
        revision = revision_by_day.get(local_day)
        feed_in_rate = revision.feed_in_rate_cents_kwh if revision else None
        if feed_in_rate is None:
            unpriced_export_kwh += reading.value
            continue
        key = (feed_in_rate, revision.id)
        export_credit_by_rate[key] = export_credit_by_rate.get(key, 0.0) + reading.value
    for (feed_in_rate, revision_id), quantity in export_credit_by_rate.items():
        export_credit += _money(-quantity * feed_in_rate / 100)
        if revision_id is not None:
            used_revision_ids.add(revision_id)
        line_items.append(
            BillLineItem(
                label="Export feed-in credit",
                quantity_kwh=round(quantity, 4),
                rate_cents_kwh=feed_in_rate,
                amount=_money(-quantity * feed_in_rate / 100),
            )
        )
    if unpriced_export_kwh:
        limitations.append(
            f"{unpriced_export_kwh:.4f} kWh export has no applicable feed-in "
            "rate and is not credited."
        )
    if unpriced_imports:
        limitations.append(
            f"{unpriced_imports} import interval(s) ({unpriced_kwh:.4f} kWh) "
            "have no applicable confirmed rate and are not priced."
        )
    supply_charge = 0.0
    for day, revision in revision_by_day.items():
        supply_rate = revision.daily_supply_charge_cents
        if supply_rate is None:
            unpriced_days += 1
            continue
        daily_amount = _money(supply_rate / 100)
        supply_charge += daily_amount
        if revision.rates_include_gst:
            gst_included_charge += daily_amount
        else:
            gst_exclusive_charge += daily_amount
        if revision.id is not None:
            used_revision_ids.add(revision.id)
    if supply_charge:
        line_items.append(
            BillLineItem(
                label="Daily supply charge (priced effective days)",
                amount=_money(supply_charge),
            )
        )
    gst_amount = _money(
        gst_included_charge / 11 + gst_exclusive_charge * 0.10
    )
    included_gst_component = _money(gst_included_charge / 11)
    gst_added_amount = _money(gst_exclusive_charge * 0.10)
    if included_gst_component:
        line_items.append(
            BillLineItem(
                label="GST component included in modeled charges",
                amount=included_gst_component,
                included_in_total=False,
            )
        )
    if gst_added_amount:
        line_items.append(
            BillLineItem(
                label="GST added to modeled exclusive charges",
                amount=gst_added_amount,
            )
        )
    estimate_total = _money(
        import_charge
        + supply_charge
        + export_credit
        + (gst_exclusive_charge * 0.10)
    )
    any_priced_charge = bool(buckets or supply_charge or export_credit_by_rate)
    all_customer_revisions = all(
        not getattr(revision, "is_illustrative", False)
        for revision in revision_by_day.values()
    )
    customer_estimate_available = (
        any_priced_charge
        and bool(revision_by_day)
        and provenance_status not in {"synthetic", "mixed"}
        and all_customer_revisions
    )
    explicit_scenario_available = (
        allow_illustrative and any_priced_charge and bool(revision_by_day)
    )
    total_cost = estimate_total if customer_estimate_available else None
    if explicit_scenario_available:
        total_cost = estimate_total
    unsupported_components = sorted(
        {
            component
            for revision in revision_by_day.values()
            for component in revision.unsupported_components
        }
    )
    full_bill_available = (
        customer_estimate_available
        and not unsupported_components
        and not missing_count
        and not unresolved
        and not unpriced_imports
        and not unpriced_days
    )
    if unsupported_components:
        limitations.append(
            "Unsupported or unverified tariff components: "
            + ", ".join(unsupported_components)
            + "."
        )
    if not full_bill_available:
        limitations.append(
            "Only modeled components are estimated; this is not a complete bill."
        )
    illustrative_tariff_used = (
        allow_illustrative
        and tariff is None
    ) or any(
        getattr(revision, "is_illustrative", False)
        for revision in revision_by_day.values()
    )
    illustrative_inputs_used = (
        provenance_status in {"synthetic", "mixed"}
        or illustrative_tariff_used
    )
    if illustrative_inputs_used:
        estimate_type = "illustrative"
        if illustrative_tariff_used:
            tariff_status = "illustrative_scenario"
        if provenance_status in {"synthetic", "mixed"}:
            tariff_status = "illustrative_data"
        limitations.append(
            "At least one calculation input is illustrative; this is not a "
            "customer-specific estimate."
        )
    elif not customer_estimate_available:
        estimate_type = "unavailable"
        if tariff is None or not revision_rows:
            tariff_status = "no_confirmed_tariff"
        else:
            tariff_status = "outside_effective_dates"
        limitations.append(
            "No customer-specific estimate is available without a confirmed, "
            "effective tariff revision."
        )
    elif unpriced_imports or unpriced_days:
        estimate_type = "partial_estimate"
        tariff_status = "partially_priced"
    else:
        estimate_type = "partial_estimate"
        tariff_status = "active"
    gst_flags = {revision.rates_include_gst for revision in revision_by_day.values()}
    gst_treatment = (
        "unavailable"
        if not gst_flags
        else "mixed treatment by tariff revision"
        if len(gst_flags) > 1
        else "rates include GST"
        if True in gst_flags
        else "GST added at 10% to modeled exclusive charges"
    )
    data_status = (
        "no_readings"
        if not readings
        else "partial"
        if missing_count
        else "unresolved_direction"
        if unresolved and not imports and not exports
        else "partial"
        if unresolved
        else "complete"
    )
    return BillPeriodBreakdown(
        start_date=start,
        end_date=end,
        estimate_type=estimate_type,
        tariff_status=tariff_status,
        data_status=data_status,
        provenance_status=provenance_status,
        gst_treatment=gst_treatment,
        import_kwh=round(import_kwh, 4),
        export_kwh=round(export_kwh, 4),
        unresolved_reading_count=unresolved,
        excluded_quality_count=excluded_quality_count,
        legacy_direction_unverified_count=legacy_direction_unverified_count,
        duplicate_interval_count=duplicate_count,
        unresolved_time_basis_count=unresolved_time_basis_count,
        expected_interval_count=expected_count,
        observed_interval_count=observed_count,
        missing_interval_count=missing_count,
        unpriced_interval_count=unpriced_imports,
        unpriced_kwh=round(unpriced_kwh, 4),
        unpriced_days=unpriced_days,
        coverage_fraction=round(coverage_fraction, 6),
        customer_estimate_available=customer_estimate_available,
        full_bill_available=full_bill_available,
        tariff_revision_ids=sorted(used_revision_ids),
        gst_amount=gst_amount if customer_estimate_available else None,
        total_cost=total_cost,
        line_items=line_items,
        limitations=list(dict.fromkeys(limitations)),
    )


@router.get("/comparison/{meter_id}", response_model=BillComparisonResponse)
async def get_bill_comparison(
    meter_id: int,
    current_start: date = Query(..., description="Start of current period"),
    current_end: date = Query(..., description="End of current period"),
    previous_start: date | None = Query(None, description="Start of previous period"),
    previous_end: date | None = Query(None, description="End of previous period"),
    illustrative_scenario: bool = Query(
        False,
        description="Use a clearly labelled hypothetical rate scenario; never a customer tariff.",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BillComparisonResponse:
    """Compare usage and costs between two billing periods."""
    meter = verify_meter_ownership(db, meter_id, current_user.id)

    # Get user's tariff
    tariff = (
        db.query(Tariff)
        .filter(
            Tariff.user_id == current_user.id,
            Tariff.archived_at.is_(None),
        )
        .first()
    )

    # Default previous period to same duration before current
    if not previous_start or not previous_end:
        duration = (current_end - current_start).days + 1
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=duration - 1)

    # Calculate both periods
    current_breakdown = calculate_period_breakdown(
        db,
        meter_id,
        current_start,
        current_end,
        tariff,
        allow_illustrative=illustrative_scenario,
    )
    previous_breakdown = calculate_period_breakdown(
        db,
        meter_id,
        previous_start,
        previous_end,
        tariff,
        allow_illustrative=illustrative_scenario,
    )
    current_kwh = current_breakdown.import_kwh
    current_cost = current_breakdown.total_cost
    current_days = (current_end - current_start).days + 1
    previous_kwh = previous_breakdown.import_kwh
    previous_cost = previous_breakdown.total_cost
    previous_days = (previous_end - previous_start).days + 1

    def weekday_counts(period_start: date, period_end: date) -> Counter[int]:
        return Counter(
            (period_start + timedelta(days=offset)).weekday()
            for offset in range((period_end - period_start).days + 1)
        )

    comparable_periods = (
        current_days >= 7
        and previous_days >= 7
        and weekday_counts(current_start, current_end)
        == weekday_counts(previous_start, previous_end)
        and all(
            breakdown.data_status == "complete"
            and breakdown.coverage_fraction == 1
            and breakdown.provenance_status == "measured"
            and breakdown.unresolved_reading_count == 0
            and breakdown.unresolved_time_basis_count == 0
            for breakdown in (current_breakdown, previous_breakdown)
        )
    )

    def percent_change(current: float, previous: float) -> float | None:
        if previous == 0:
            return 0.0 if current == 0 else None
        return (current - previous) / previous * 100

    if not comparable_periods:
        kwh_change = None
        kwh_change_percent = None
        current_daily_avg = None
        previous_daily_avg = None
        cost_change_percent = None
        daily_avg_change_percent = None
        cost_change = None
        trend = "unavailable"
        insight = (
            "A period comparison requires at least seven fully covered measured "
            "days in each period with matching weekday coverage."
        )
    else:
        kwh_change = current_kwh - previous_kwh
        current_daily_avg = current_kwh / current_days
        previous_daily_avg = previous_kwh / previous_days
        kwh_change_percent = percent_change(current_kwh, previous_kwh)
        cost_comparable = (
            current_breakdown.full_bill_available
            and previous_breakdown.full_bill_available
            and current_breakdown.customer_estimate_available
            and previous_breakdown.customer_estimate_available
            and current_cost is not None
            and previous_cost is not None
        )
        cost_change = current_cost - previous_cost if cost_comparable else None
        cost_change_percent = (
            percent_change(current_cost, previous_cost)
            if cost_comparable and current_cost is not None and previous_cost is not None
            else None
        )
        daily_avg_change_percent = percent_change(current_daily_avg, previous_daily_avg)
        if kwh_change_percent is None:
            trend = "up" if kwh_change > 0 else "down" if kwh_change < 0 else "stable"
            insight = (
                "The previous period had no eligible import, so a percentage "
                "change cannot be calculated."
            )
        elif abs(kwh_change_percent) < 5:
            trend = "stable"
            insight = (
                "Observed eligible import is within 5% of the matched, fully "
                "covered measured period; this comparison does not explain why."
            )
        elif kwh_change_percent < 0:
            trend = "down"
            insight = (
                f"Observed eligible import was {abs(kwh_change_percent):.1f}% "
                "lower than in the matched, fully covered measured period. "
                "This does not identify a cause."
            )
        else:
            trend = "up"
            insight = (
                f"Observed eligible import was {kwh_change_percent:.1f}% higher "
                "than in the matched, fully covered measured period. "
                "This does not identify a cause."
            )

    # Period observations do not establish appliance ownership, causation, or
    # a defensible schedule change.
    recommendations: list[str] = []

    comparison = PeriodComparison(
        current_start=current_start,
        current_end=current_end,
        current_kwh=round(current_kwh, 2),
        current_cost=round(current_cost, 2) if current_cost is not None else None,
        current_days=current_days,
        current_daily_avg_kwh=(
            round(current_daily_avg, 2) if current_daily_avg is not None else None
        ),
        previous_start=previous_start,
        previous_end=previous_end,
        previous_kwh=round(previous_kwh, 2),
        previous_cost=round(previous_cost, 2) if previous_cost is not None else None,
        previous_days=previous_days,
        previous_daily_avg_kwh=(
            round(previous_daily_avg, 2) if previous_daily_avg is not None else None
        ),
        kwh_change=round(kwh_change, 2) if kwh_change is not None else None,
        kwh_change_percent=(
            round(kwh_change_percent, 1)
            if kwh_change_percent is not None
            else None
        ),
        cost_change=round(cost_change, 2) if cost_change is not None else None,
        cost_change_percent=(
            round(cost_change_percent, 1)
            if cost_change_percent is not None
            else None
        ),
        daily_avg_change_percent=(
            round(daily_avg_change_percent, 1)
            if daily_avg_change_percent is not None
            else None
        ),
        trend=trend,
        insight=insight,
    )

    return BillComparisonResponse(
        meter_id=meter_id,
        meter_name=meter.name,
        comparison=comparison,
        recommendations=recommendations,
        current_breakdown=current_breakdown,
        previous_breakdown=previous_breakdown,
    )


@router.get("/monthly-summary/{meter_id}")
async def get_monthly_summary(
    meter_id: int,
    months: int = Query(6, ge=1, le=24, description="Number of months to include"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Get monthly usage summary for trend analysis."""
    # Verify meter ownership
    meter = (
        db.query(Meter)
        .filter(Meter.id == meter_id, Meter.user_id == current_user.id)
        .first()
    )
    if not meter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meter not found.",
        )

    tariff = (
        db.query(Tariff)
        .filter(
            Tariff.user_id == current_user.id,
            Tariff.archived_at.is_(None),
        )
        .first()
    )
    summaries = []

    today = datetime.now(timezone_for_state(meter.state)).date()
    for i in range(months):
        # Calculate month boundaries
        month_end = date(today.year, today.month, 1) - timedelta(days=1)
        month_end = month_end.replace(day=1) - timedelta(days=i * 30)
        month_end = (
            (month_end.replace(day=28) + timedelta(days=4)).replace(day=1)
            - timedelta(days=1)
        )
        month_start = month_end.replace(day=1)

        if i > 0:
            offset = timedelta(days=30 * i)
            month_start = (today.replace(day=1) - offset).replace(day=1)
            month_end = (
                (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
                - timedelta(days=1)
            )

        breakdown = calculate_period_breakdown(
            db, meter_id, month_start, month_end, tariff
        )
        kwh = breakdown.import_kwh
        cost = breakdown.total_cost
        days = (month_end - month_start).days + 1

        summaries.append({
            "month": month_start.strftime("%B %Y"),
            "start_date": month_start.isoformat(),
            "end_date": month_end.isoformat(),
            "total_kwh": round(kwh, 2),
            "total_cost": round(cost, 2) if cost is not None else None,
            "daily_avg_kwh": round(kwh / max(days, 1), 2),
            "estimate_type": breakdown.estimate_type,
            "data_status": breakdown.data_status,
            "limitations": breakdown.limitations,
        })

    return list(reversed(summaries))
