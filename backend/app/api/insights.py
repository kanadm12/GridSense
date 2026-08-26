"""Insights API endpoints for forecasting and anomaly detection."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.ownership import verify_meter_ownership
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
        return verify_meter_ownership(db, meter_id, user_id)

    # Get default active meter
    meter = db.query(Meter).filter(
        Meter.user_id == user_id,
        Meter.is_active.is_(True),
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

    # Get time-based greeting
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good morning!"
    elif hour < 17:
        greeting = "Good afternoon!"
    else:
        greeting = "Good evening!"

    # Get yesterday's usage
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
                    message=(
                        "Peak pricing starts at 3pm. Now is a good time to run "
                        "the dishwasher or laundry!"
                    ),
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
                message=(
                    "It's the weekend - all-day off-peak rates! Great time for "
                    "energy-intensive tasks."
                ),
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


@router.get("/ml-suggestions")
async def get_ml_suggestions(
    meter_id: int | None = Query(None, description="Specific meter ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get ML model-based suggestions: forecasts and anomaly detection.

    Returns:
    - Next 14 days forecast (kWh per day)
    - Recent anomalous days detected
    - Status of ML models (available/not trained)
    """
    from app.ml.etl import extract_daily_series
    from app.ml.predict import detect_anomalies, predict_forecast
    from app.models.ml_training import MLTrainingJob

    meter = _get_user_meter(db, current_user.id, meter_id)

    try:
        # Extract time-series data
        df = extract_daily_series(db, meter.id)
        latest_job = (
            db.query(MLTrainingJob)
            .filter(MLTrainingJob.meter_id == meter.id, MLTrainingJob.job_type == "all")
            .order_by(MLTrainingJob.created_at.desc())
            .first()
        )

        forecast = predict_forecast(meter.id, periods=14)
        anomalies = detect_anomalies(meter.id, df)

        response = {
            "meter_id": meter.id,
            "forecast": forecast or {"message": "Forecast model not trained yet"},
            "anomalies": anomalies or {"message": "Anomaly detector model not trained yet"},
            "model_status": {
                "days_available": len(df),
                "minimum_days": 20,
                "forecast": "trained" if forecast else "unavailable",
                "anomaly": "trained" if anomalies else "unavailable",
                "training_job": (
                    {
                        "id": latest_job.id,
                        "status": latest_job.status,
                        "created_at": latest_job.created_at,
                        "completed_at": latest_job.completed_at,
                        "error": latest_job.error_message,
                    }
                    if latest_job
                    else None
                ),
            },
        }

        if len(df) < 20:
            response["model_status"]["forecast"] = "insufficient_data"
            response["model_status"]["anomaly"] = "insufficient_data"
        elif latest_job and latest_job.status in ("pending", "running"):
            if not forecast:
                response["model_status"]["forecast"] = "training"
            if not anomalies:
                response["model_status"]["anomaly"] = "training"
            elif latest_job and latest_job.status == "failed":
                if not forecast:
                    response["model_status"]["forecast"] = "failed"
                if not anomalies:
                    response["model_status"]["anomaly"] = "failed"

        # Add helpful messages if models aren't trained
        if not forecast and len(df) < 20:
            response["forecast"]["suggestion"] = (
                "Upload more history to enable a personalized forecast"
            )
        if not anomalies and len(df) < 20:
            response["anomalies"]["suggestion"] = (
                "Upload more history to enable personalized anomaly detection"
            )

        return response
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate ML suggestions: {str(e)}"
        )
