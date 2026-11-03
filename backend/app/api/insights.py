"""Insights API endpoints for forecasting and anomaly detection."""

from datetime import date, datetime, timedelta

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
    # Get time-based greeting
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good morning!"
    elif hour < 17:
        greeting = "Good afternoon!"
    else:
        greeting = "Good evening!"

    # Compare complete days only, matching yesterday to the same weekday.
    yesterday = date.today() - timedelta(days=1)

    try:
        yesterday_rows = analyzer.get_daily_usage(
            meter_id=meter.id,
            start_date=yesterday,
            end_date=yesterday,
            limit=1,
        )
        yesterday_row = yesterday_rows[0] if yesterday_rows else None
        yesterday_eligible = bool(
            yesterday_row is not None
            and yesterday_row.coverage_status == "complete"
            and yesterday_row.provenance_status == "measured"
            and yesterday_row.unresolved_direction_count == 0
            and yesterday_row.legacy_direction_unverified_count == 0
        )
        yesterday_kwh = yesterday_row.observed_eligible_kwh if yesterday_eligible else None
        yesterday_cost = (
            yesterday_row.estimated_cost
            if yesterday_eligible and yesterday_row is not None
            else None
        )

        prior_same_weekdays = analyzer.get_daily_usage(
            meter_id=meter.id,
            start_date=yesterday - timedelta(days=28),
            end_date=yesterday - timedelta(days=7),
            limit=28,
        )
        weekday_baseline = [
            row
            for row in prior_same_weekdays
            if row.date.weekday() == yesterday.weekday()
            and row.coverage_status == "complete"
            and row.provenance_status == "measured"
            and row.unresolved_direction_count == 0
            and row.legacy_direction_unverified_count == 0
        ]
        comparison = None
        if yesterday_kwh is not None and len(weekday_baseline) == 4:
            baseline_average = sum(row.observed_eligible_kwh for row in weekday_baseline) / 4
            if baseline_average > 0:
                comparison = (yesterday_kwh - baseline_average) / baseline_average * 100

        # Generate insights
        insights = []

        # Descriptive comparison only; it does not explain why usage changed.
        if comparison is not None and comparison < -10:
            insights.append(Insight(
                type=InsightType.USAGE_PATTERN,
                title="Lower use than matched weekdays",
                message=(
                    f"Yesterday's eligible import was {abs(comparison):.0f}% below "
                    "the average of four complete prior same-weekday observations."
                ),
                icon="trending-down",
            ))
        elif comparison is not None and comparison > 20:
            insights.append(Insight(
                type=InsightType.USAGE_PATTERN,
                title="Higher use than matched weekdays",
                message=(
                    f"Yesterday's eligible import was {comparison:.0f}% above "
                    "the average of four complete prior same-weekday observations. "
                    "This does not identify a cause."
                ),
                action=(
                    "Compare the interval record with your own notes; aggregate "
                    "readings do not identify appliances."
                ),
                icon="trending-up",
            ))
        else:
            insights.append(Insight(
                type=InsightType.USAGE_PATTERN,
                title="Weekday comparison unavailable",
                message=(
                    "A comparison needs a fully covered measured day yesterday "
                    "and four fully covered measured observations from the same weekday."
                ),
                icon="information-circle",
            ))

        insights.append(Insight(
            type=InsightType.TIP,
            title="Check your confirmed tariff",
            message=(
                "Retailer time windows differ. Review your confirmed tariff and "
                "the appliance's requirements before deciding whether to shift a task."
            ),
            icon="information-circle",
        ))

        return DailyBrief(
            date=str(date.today()),
            greeting=greeting,
            yesterday_usage_kwh=(
                round(yesterday_kwh, 3) if yesterday_kwh is not None else None
            ),
            yesterday_cost=(
                round(yesterday_cost, 2) if yesterday_cost is not None else None
            ),
            comparison_to_average=round(comparison, 1) if comparison is not None else None,
            insights=insights,
            forecast_message=(
                "Forecast-dependent advice is unavailable until chronological "
                "held-out evaluation meets its acceptance criteria."
            ),
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
