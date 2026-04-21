"""Insights API endpoints for forecasting and anomaly detection."""

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.meter import Meter
from app.models.user import User
from app.schemas.insights import (
    AnomalyReport,
    BillForecast,
    BillTrend,
    BillTrendItem,
    DailyBrief,
    Insight,
    InsightType,
)
from app.services.anomaly_detector import get_anomaly_detector
from app.services.forecasting import get_forecaster
from app.services.usage_analyzer import UsageAnalyzer

router = APIRouter(prefix="/insights", tags=["insights"])


def _get_user_meter(db: Session, user_id: int, meter_id: int | None = None) -> Meter:
    """Get the user's meter, validating ownership."""
    if meter_id:
        meter = db.query(Meter).filter(
            Meter.id == meter_id,
            Meter.user_id == user_id,
        ).first()
        if not meter:
            raise HTTPException(status_code=404, detail="Meter not found")
        return meter
    
    # Get default active meter
    meter = db.query(Meter).filter(
        Meter.user_id == user_id,
        Meter.is_active == True,
    ).first()
    
    if not meter:
        raise HTTPException(
            status_code=404,
            detail="No active meter found. Please upload your NEM12 file first."
        )
    return meter


@router.get("/forecast", response_model=BillForecast)
async def get_bill_forecast(
    meter_id: int | None = Query(None, description="Specific meter ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BillForecast:
    """Get bill forecast for the current month.

    Predicts end-of-month bill based on:
    - Current month's usage so far
    - Historical usage patterns
    - Victorian TOU rates
    """
    meter = _get_user_meter(db, current_user.id, meter_id)
    forecaster = get_forecaster(db)
    
    try:
        forecast = forecaster.forecast_monthly_bill(meter.id)
        return BillForecast(**forecast)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate forecast: {str(e)}"
        )


@router.get("/trend", response_model=BillTrend)
async def get_bill_trend(
    meter_id: int | None = Query(None, description="Specific meter ID"),
    months: int = Query(6, ge=1, le=12, description="Months of history"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BillTrend:
    """Get historical bill trend for the past N months."""
    meter = _get_user_meter(db, current_user.id, meter_id)
    forecaster = get_forecaster(db)
    
    try:
        trend_data = forecaster.get_bill_trend(meter.id, months)
        return BillTrend(
            meter_id=meter.id,
            months=[BillTrendItem(**item) for item in trend_data],
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get bill trend: {str(e)}"
        )


@router.get("/anomalies", response_model=AnomalyReport)
async def get_anomalies(
    meter_id: int | None = Query(None, description="Specific meter ID"),
    days: int = Query(30, ge=7, le=90, description="Days to analyze"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnomalyReport:
    """Detect anomalies in energy usage.

    Checks for:
    - Daily usage spikes (unusual high consumption)
    - High overnight usage (appliance left on?)
    - Peak-heavy days (expensive usage patterns)
    """
    meter = _get_user_meter(db, current_user.id, meter_id)
    detector = get_anomaly_detector(db)
    
    try:
        report = detector.get_all_anomalies(meter.id, days)
        return AnomalyReport(**report)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to detect anomalies: {str(e)}"
        )


@router.get("/daily-brief", response_model=DailyBrief)
async def get_daily_brief(
    meter_id: int | None = Query(None, description="Specific meter ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DailyBrief:
    """Get personalized daily energy brief.

    Returns:
    - Yesterday's usage and cost
    - Comparison to your average
    - Actionable insights for today
    """
    meter = _get_user_meter(db, current_user.id, meter_id)
    analyzer = UsageAnalyzer(db)
    forecaster = get_forecaster(db)
    detector = get_anomaly_detector(db)
    
    # Get time-based greeting
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good morning!"
    elif hour < 17:
        greeting = "Good afternoon!"
    else:
        greeting = "Good evening!"

    # Get yesterday's usage
    yesterday = date.today() - datetime.timedelta(days=1) if hasattr(datetime, 'timedelta') else date.today()
    from datetime import timedelta
    yesterday = date.today() - timedelta(days=1)
    
    try:
        daily_usage = analyzer.get_daily_usage(
            meter_id=meter.id,
            start_date=yesterday,
            end_date=yesterday,
            limit=1,
        )
        
        if daily_usage:
            yesterday_kwh = daily_usage[0].total_kwh
            yesterday_cost = daily_usage[0].estimated_cost
        else:
            yesterday_kwh = 0.0
            yesterday_cost = 0.0

        # Get 30-day average for comparison
        thirty_days_ago = date.today() - timedelta(days=30)
        monthly_usage = analyzer.get_daily_usage(
            meter_id=meter.id,
            start_date=thirty_days_ago,
            end_date=date.today() - timedelta(days=1),
            limit=30,
        )
        
        if monthly_usage:
            avg_daily = sum(d.total_kwh for d in monthly_usage) / len(monthly_usage)
            comparison = ((yesterday_kwh - avg_daily) / avg_daily * 100) if avg_daily > 0 else 0
        else:
            avg_daily = yesterday_kwh
            comparison = 0.0

        # Generate insights
        insights = []
        
        # Usage comparison insight
        if comparison < -10:
            insights.append(Insight(
                type=InsightType.ACHIEVEMENT,
                title="Great job!",
                message=f"Yesterday's usage was {abs(comparison):.0f}% below your average!",
                icon="trophy",
            ))
        elif comparison > 20:
            insights.append(Insight(
                type=InsightType.COST_ALERT,
                title="High usage detected",
                message=f"Yesterday was {comparison:.0f}% above your average.",
                action="Check if any appliances were left on",
                icon="alert-triangle",
            ))

        # Time-based tip
        weekday = datetime.now().weekday()
        if weekday < 5:  # Weekday
            if hour < 15:
                insights.append(Insight(
                    type=InsightType.TIP,
                    title="Off-peak opportunity",
                    message="Peak pricing starts at 3pm. Now is a good time to run the dishwasher or laundry!",
                    impact_dollars=0.20,
                    icon="clock",
                ))
            elif 15 <= hour < 21:
                insights.append(Insight(
                    type=InsightType.TIP,
                    title="Peak hours now",
                    message="You're in peak pricing (3-9pm). Delay heavy appliances if possible.",
                    icon="zap",
                ))
        else:
            insights.append(Insight(
                type=InsightType.SAVINGS_OPPORTUNITY,
                title="Weekend off-peak",
                message="It's the weekend - all-day off-peak rates! Great time for energy-intensive tasks.",
                icon="sun",
            ))

        # Get forecast message
        try:
            forecast = forecaster.forecast_monthly_bill(meter.id)
            forecast_msg = f"Projected bill this month: ${forecast['projected_total_cost']:.0f}"
        except Exception:
            forecast_msg = None

        return DailyBrief(
            date=str(date.today()),
            greeting=greeting,
            yesterday_usage_kwh=round(yesterday_kwh, 2),
            yesterday_cost=round(yesterday_cost, 2),
            comparison_to_average=round(comparison, 1),
            insights=insights,
            forecast_message=forecast_msg,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate daily brief: {str(e)}"
        )
