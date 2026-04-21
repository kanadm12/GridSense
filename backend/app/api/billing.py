"""Bill comparison endpoints."""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.meter import Meter
from app.models.reading import Reading
from app.models.tariff import Tariff
from app.models.user import User
from app.schemas.billing import BillComparisonResponse, PeriodComparison

router = APIRouter(prefix="/billing", tags=["Billing"])


def calculate_period_cost(
    db: Session, meter_id: int, start: date, end: date, tariff: Tariff | None
) -> tuple[float, float, int]:
    """Calculate total kWh and cost for a period."""
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())

    # Get total consumption
    result = (
        db.query(func.sum(Reading.value).label("total_kwh"))
        .filter(
            Reading.meter_id == meter_id,
            Reading.timestamp >= start_dt,
            Reading.timestamp <= end_dt,
            Reading.register_type == "B",  # Consumption only
        )
        .first()
    )

    total_kwh = result.total_kwh or 0.0
    days = (end - start).days + 1

    # Calculate cost
    if tariff:
        if tariff.tariff_type == "flat":
            rate = tariff.flat_rate_cents_kwh or 25.0
            cost = (total_kwh * rate) / 100
        else:
            # For TOU, we need to calculate by period
            # Simplified: assume 25% peak, 35% shoulder, 40% off-peak
            peak_kwh = total_kwh * 0.25
            shoulder_kwh = total_kwh * 0.35
            off_peak_kwh = total_kwh * 0.40

            peak_cost = (peak_kwh * (tariff.peak_rate_cents_kwh or 38)) / 100
            shoulder_cost = (shoulder_kwh * (tariff.shoulder_rate_cents_kwh or 25)) / 100
            off_peak_cost = (off_peak_kwh * (tariff.off_peak_rate_cents_kwh or 18)) / 100

            cost = peak_cost + shoulder_cost + off_peak_cost

        # Add supply charge
        cost += (tariff.daily_supply_charge_cents * days) / 100
    else:
        # Default flat rate
        cost = (total_kwh * 25) / 100 + (100 * days) / 100

    return total_kwh, cost, days


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

    # Get user's tariff
    tariff = db.query(Tariff).filter(Tariff.user_id == current_user.id).first()

    # Default previous period to same duration before current
    if not previous_start or not previous_end:
        duration = (current_end - current_start).days + 1
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=duration - 1)

    # Calculate both periods
    current_kwh, current_cost, current_days = calculate_period_cost(
        db, meter_id, current_start, current_end, tariff
    )
    previous_kwh, previous_cost, previous_days = calculate_period_cost(
        db, meter_id, previous_start, previous_end, tariff
    )

    # Avoid division by zero
    if previous_kwh == 0:
        previous_kwh = 0.001
    if previous_cost == 0:
        previous_cost = 0.001
    if previous_days == 0:
        previous_days = 1

    # Calculate changes
    kwh_change = current_kwh - previous_kwh
    kwh_change_percent = (kwh_change / previous_kwh) * 100
    cost_change = current_cost - previous_cost
    cost_change_percent = (cost_change / previous_cost) * 100

    current_daily_avg = current_kwh / current_days
    previous_daily_avg = previous_kwh / previous_days
    daily_avg_change_percent = ((current_daily_avg - previous_daily_avg) / previous_daily_avg) * 100

    # Determine trend
    if abs(kwh_change_percent) < 5:
        trend = "stable"
    elif kwh_change_percent < 0:
        trend = "down"
    else:
        trend = "up"

    # Generate insight
    if trend == "down":
        insight = f"Great job! You've reduced your usage by {abs(kwh_change_percent):.1f}% compared to last period."
    elif trend == "up":
        insight = f"Your usage increased by {kwh_change_percent:.1f}%. Check your peak hour consumption."
    else:
        insight = "Your usage is consistent with the previous period."

    # Generate recommendations
    recommendations = []
    if cost_change > 0:
        recommendations.append("Consider shifting heavy appliance usage to off-peak hours (10pm-7am).")
    if current_daily_avg > 15:
        recommendations.append("Your daily average is above typical households. Consider an energy audit.")
    if trend == "down":
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
        kwh_change_percent=round(kwh_change_percent, 1),
        cost_change=round(cost_change, 2),
        cost_change_percent=round(cost_change_percent, 1),
        daily_avg_change_percent=round(daily_avg_change_percent, 1),
        trend=trend,
        insight=insight,
    )

    return BillComparisonResponse(
        meter_id=meter_id,
        meter_name=meter.name,
        comparison=comparison,
        recommendations=recommendations,
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

    today = date.today()
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

        kwh, cost, days = calculate_period_cost(db, meter_id, month_start, month_end, tariff)

        summaries.append({
            "month": month_start.strftime("%B %Y"),
            "start_date": month_start.isoformat(),
            "end_date": month_end.isoformat(),
            "total_kwh": round(kwh, 2),
            "total_cost": round(cost, 2),
            "daily_avg_kwh": round(kwh / max(days, 1), 2),
        })

    return list(reversed(summaries))
