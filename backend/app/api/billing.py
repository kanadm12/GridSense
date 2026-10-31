"""Bill comparison endpoints."""

from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.ownership import verify_meter_ownership
from app.database import get_db
from app.models.meter import Meter
from app.models.reading import Reading
from app.models.tariff import Tariff
from app.models.user import User
from app.schemas.billing import (
    BillComparisonResponse,
    BillLineItem,
    BillPeriodBreakdown,
    PeriodComparison,
)
from app.services.tariff import (
    DEFAULT_FLAT_RATE_CENTS,
    TouPeriod,
    classify_interval_tou_period,
    market_bounds_for_local_dates,
    market_interval_start_to_local,
    timezone_for_state,
)

router = APIRouter(prefix="/billing", tags=["Billing"])

# Fallback supply charge (cents/day) when the user has no configured tariff. Matches the
# Tariff model's own default so a configured-but-unmodified tariff and no tariff agree.
DEFAULT_SUPPLY_CHARGE_CENTS = 100.0


def calculate_period_cost(
    db: Session, meter_id: int, start: date, end: date, tariff: Tariff | None
) -> tuple[float, float, int]:
    """Compatibility wrapper returning import kWh, estimated total cost, and days."""
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
    db: Session, meter_id: int, start: date, end: date, tariff: Tariff | None
) -> BillPeriodBreakdown:
    """Build a cent-reconciled, explicitly estimated bill breakdown."""
    if end < start:
        raise ValueError("Billing period end cannot be before its start")
    meter = db.query(Meter).filter(Meter.id == meter_id).first()
    if meter is None:
        raise ValueError(f"Meter {meter_id} was not found; cannot determine billing timezone")
    market_start, market_end = market_bounds_for_local_dates(start, end, meter.state)
    requested_tariff = tariff
    tariff_status = "active"
    if tariff and (
        (tariff.effective_from is not None and start < tariff.effective_from)
        or (tariff.effective_to is not None and end > tariff.effective_to)
    ):
        tariff = None
        tariff_status = "outside_effective_dates"
    elif tariff is None:
        tariff_status = "illustrative_default"
    elif tariff.is_preset:
        tariff_status = "preset_illustrative"

    readings = (
        db.query(Reading)
        .filter(
            Reading.meter_id == meter_id,
            Reading.timestamp > market_start,
            Reading.timestamp <= market_end,
        )
        .all()
    )
    imports = [
        reading
        for reading in readings
        if reading.direction == "import"
        or (reading.direction is None and reading.register_type == "B")
    ]
    exports = [reading for reading in readings if reading.direction == "export"]
    unresolved = len(readings) - len(imports) - len(exports)
    interval_minutes = meter.interval_minutes
    if interval_minutes not in (5, 15, 30):
        raise ValueError(f"Unsupported meter interval length {interval_minutes}")
    expected_count = int((market_end - market_start).total_seconds() // (interval_minutes * 60))
    observed_count = len({reading.timestamp for reading in readings})
    missing_count = max(expected_count - observed_count, 0)
    days = (end - start).days + 1
    limitations: list[str] = []
    if requested_tariff is None:
        limitations.append("No configured tariff; indicative default rates are used.")
    elif requested_tariff.is_preset:
        limitations.append("Retailer preset rates are illustrative and may not match your current offer.")
    if tariff_status == "outside_effective_dates":
        limitations.append("Configured tariff does not cover the full requested date range.")
    if unresolved:
        limitations.append(
            f"{unresolved} reading(s) have unresolved direction and are excluded from energy charges."
        )
    if missing_count:
        limitations.append(
            f"{missing_count} expected interval(s) are absent; costs may be understated."
        )
    if any(reading.quality != "A" for reading in imports + exports):
        limitations.append("Some charged readings have non-actual or unresolved quality metadata.")
    if tariff and tariff.periods:
        limitations.append(
            "Custom periods use local weekday schedules; no public-holiday calendar is configured."
        )
    elif tariff and tariff.tariff_type in {"tou", "flexible", "demand"}:
        limitations.append(
            "Time-of-use windows use GridSense's default Victorian schedule, not retailer-specific holiday rules."
        )
    else:
        limitations.append("Demand charges and other retailer-specific bill adjustments may be omitted.")
    limitations.append(
        "Feed-in credits are applied at the configured rate without a separate GST adjustment."
    )
    if tariff is None:
        limitations.append("Illustrative default rates are assumed to include GST.")

    estimate_type = (
        "illustrative"
        if tariff is None or bool(tariff.is_preset)
        else "configured_tariff_estimate"
    )
    line_items: list[BillLineItem] = []
    buckets: dict[tuple[str, float], float] = {}
    unpriced_imports = 0
    import_kwh = sum(reading.value for reading in imports)
    export_kwh = sum(reading.value for reading in exports)
    for reading in imports:
        period_name = "flat"
        if tariff is None:
            rate = DEFAULT_FLAT_RATE_CENTS
        elif tariff.tariff_type == "flat":
            rate = tariff.flat_rate_cents_kwh
        elif tariff.periods:
            window = _window_rate(
                tariff, reading.timestamp, reading.interval_minutes, meter.state
            )
            period_name = window["name"] if window else "unpriced"
            rate = window["rate_cents_kwh"] if window else None
        else:
            period = classify_interval_tou_period(
                reading.timestamp, reading.interval_minutes, meter.state
            )
            period_name = period.value
            rate = {
                TouPeriod.PEAK.value: tariff.peak_rate_cents_kwh,
                TouPeriod.SHOULDER.value: tariff.shoulder_rate_cents_kwh,
                TouPeriod.OFF_PEAK.value: tariff.off_peak_rate_cents_kwh,
            }[period.value]
        if rate is None:
            unpriced_imports += 1
            continue
        key = (period_name, rate)
        buckets[key] = buckets.get(key, 0.0) + reading.value

    import_charge = 0.0
    for (period_name, rate), quantity in sorted(buckets.items()):
        amount = _money(quantity * rate / 100)
        import_charge += amount
        line_items.append(
            BillLineItem(
                label=f"{period_name.replace('_', ' ').title()} import energy",
                quantity_kwh=round(quantity, 4),
                rate_cents_kwh=rate,
                amount=amount,
            )
        )
    import_charge = _money(import_charge)

    feed_in_rate = tariff.feed_in_rate_cents_kwh if tariff else None
    export_credit = 0.0
    if exports and feed_in_rate is not None:
        export_credit = _money(-export_kwh * feed_in_rate / 100)
        line_items.append(
            BillLineItem(
                label="Export feed-in credit",
                quantity_kwh=round(export_kwh, 4),
                rate_cents_kwh=feed_in_rate,
                amount=export_credit,
            )
        )
    elif exports:
        limitations.append("Export readings are known but no feed-in rate is configured.")
    if unpriced_imports:
        limitations.append(
            f"{unpriced_imports} import interval(s) have no matching configured rate and are excluded."
        )
        tariff_status = "incomplete"

    supply_rate = tariff.daily_supply_charge_cents if tariff else DEFAULT_SUPPLY_CHARGE_CENTS
    supply_charge = _money(supply_rate * days / 100)
    line_items.append(
        BillLineItem(
            label=f"Daily supply charge ({days} days)",
            amount=supply_charge,
        )
    )

    demand_charge = 0.0
    if tariff and tariff.demand_charge_dollars_kw is not None:
        peak_kw = max(
            (
                reading.value * 60 / reading.interval_minutes
                for reading in imports
            ),
            default=0.0,
        )
        demand_charge = _money(peak_kw * tariff.demand_charge_dollars_kw)
        line_items.append(
            BillLineItem(
                label="Observed peak demand charge",
                amount=demand_charge,
            )
        )
        limitations.append(
            "Demand charge uses the highest observed import interval average; retailer demand-window rules may differ."
        )

    taxable_charges = _money(import_charge + supply_charge + demand_charge)
    gst_included = tariff is None or tariff.rates_include_gst is not False
    gst_amount = (
        _money(taxable_charges / 11)
        if gst_included
        else _money(taxable_charges * 0.10)
    )
    line_items.append(
        BillLineItem(
            label="GST component (included)" if gst_included else "GST (10%)",
            amount=gst_amount,
            included_in_total=not gst_included,
        )
    )
    total_cost = _money(
        sum(item.amount for item in line_items if item.included_in_total)
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
        gst_treatment=(
            "rates_include_gst"
            if gst_included
            else "GST added at 10%; tariff rates are treated as GST-exclusive"
        ),
        import_kwh=round(import_kwh, 4),
        export_kwh=round(export_kwh, 4),
        unresolved_reading_count=unresolved,
        expected_interval_count=expected_count,
        observed_interval_count=observed_count,
        missing_interval_count=missing_count,
        unpriced_interval_count=unpriced_imports,
        gst_amount=gst_amount,
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BillComparisonResponse:
    """Compare usage and costs between two billing periods."""
    meter = verify_meter_ownership(db, meter_id, current_user.id)

    # Get user's tariff
    tariff = db.query(Tariff).filter(Tariff.user_id == current_user.id).first()

    # Default previous period to same duration before current
    if not previous_start or not previous_end:
        duration = (current_end - current_start).days + 1
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=duration - 1)

    # Calculate both periods
    current_breakdown = calculate_period_breakdown(
        db, meter_id, current_start, current_end, tariff
    )
    previous_breakdown = calculate_period_breakdown(
        db, meter_id, previous_start, previous_end, tariff
    )
    current_kwh = current_breakdown.import_kwh
    current_cost = current_breakdown.total_cost
    current_days = (current_end - current_start).days + 1
    previous_kwh = previous_breakdown.import_kwh
    previous_cost = previous_breakdown.total_cost
    previous_days = (previous_end - previous_start).days + 1

    # Calculate absolute changes
    kwh_change = current_kwh - previous_kwh
    cost_change = current_cost - previous_cost
    current_daily_avg = current_kwh / current_days
    previous_daily_avg = previous_kwh / previous_days

    has_classifiable_usage = not any(
        breakdown.data_status == "no_readings"
        or (
            breakdown.import_kwh == 0
            and breakdown.unresolved_reading_count > 0
        )
        for breakdown in (current_breakdown, previous_breakdown)
    )

    def percent_change(current: float, previous: float) -> float | None:
        if previous == 0:
            return 0.0 if current == 0 else None
        return (current - previous) / previous * 100

    if not has_classifiable_usage:
        kwh_change_percent = None
        cost_change_percent = None
        daily_avg_change_percent = None
        trend = "unavailable"
        insight = (
            "A usage trend cannot be calculated because one or both periods "
            "have no classifiable import readings."
        )
    else:
        kwh_change_percent = percent_change(current_kwh, previous_kwh)
        cost_change_percent = percent_change(current_cost, previous_cost)
        daily_avg_change_percent = percent_change(current_daily_avg, previous_daily_avg)
        if kwh_change_percent is None:
            trend = "up" if kwh_change > 0 else "down"
            insight = (
                "Usage is present in this period, while the previous period was zero; "
                "a percentage change cannot be calculated."
            )
        elif abs(kwh_change_percent) < 5:
            trend = "stable"
            insight = "Your usage is consistent with the previous period."
        elif kwh_change_percent < 0:
            trend = "down"
            insight = (
                f"Great job! You've reduced your usage by "
                f"{abs(kwh_change_percent):.1f}% compared to last period."
            )
        else:
            trend = "up"
            insight = (
                f"Your usage increased by {kwh_change_percent:.1f}%. "
                "Check your peak hour consumption."
            )

    # Generate recommendations
    recommendations = []
    if has_classifiable_usage and cost_change > 0:
        recommendations.append("Consider shifting heavy appliance usage to off-peak hours (10pm-7am).")
    if has_classifiable_usage and current_daily_avg > 15:
        recommendations.append("Your daily average is above typical households. Consider an energy audit.")
    if has_classifiable_usage and trend == "down":
        recommendations.append("Keep up the good work! Your energy-saving habits are paying off.")

    comparison = PeriodComparison(
        current_start=current_start,
        current_end=current_end,
        current_kwh=round(current_kwh, 2),
        current_cost=round(current_cost, 2),
        current_days=current_days,
        current_daily_avg_kwh=round(current_daily_avg, 2),
        previous_start=previous_start,
        previous_end=previous_end,
        previous_kwh=round(previous_kwh, 2),
        previous_cost=round(previous_cost, 2),
        previous_days=previous_days,
        previous_daily_avg_kwh=round(previous_daily_avg, 2),
        kwh_change=round(kwh_change, 2),
        kwh_change_percent=(
            round(kwh_change_percent, 1)
            if kwh_change_percent is not None
            else None
        ),
        cost_change=round(cost_change, 2),
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

    tariff = db.query(Tariff).filter(Tariff.user_id == current_user.id).first()
    summaries = []

    today = datetime.now(timezone_for_state(meter.state)).date()
    for i in range(months):
        # Calculate month boundaries
        month_end = date(today.year, today.month, 1) - timedelta(days=1)
        month_end = month_end.replace(day=1) - timedelta(days=i * 30)
        month_end = (month_end.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        month_start = month_end.replace(day=1)

        if i > 0:
            offset = timedelta(days=30 * i)
            month_start = (today.replace(day=1) - offset).replace(day=1)
            month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

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
            "total_cost": round(cost, 2),
            "daily_avg_kwh": round(kwh / max(days, 1), 2),
            "estimate_type": breakdown.estimate_type,
            "data_status": breakdown.data_status,
            "limitations": breakdown.limitations,
        })

    return list(reversed(summaries))
