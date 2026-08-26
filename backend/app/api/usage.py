"""Usage data endpoints."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.ownership import verify_meter_ownership
from app.database import get_db
from app.models.meter import Meter
from app.models.user import User
from app.schemas.usage import DailyUsage, HourlyUsage, UsageSummary, WeeklyUsage
from app.services.usage_analyzer import UsageAnalyzer

router = APIRouter(prefix="/usage", tags=["Usage"])


@router.get("/summary/{meter_id}", response_model=UsageSummary)
async def get_usage_summary(
    meter_id: int,
    start_date: date | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UsageSummary:
    """Get comprehensive usage summary for a meter."""
    verify_meter_ownership(db, meter_id, current_user.id)

    analyzer = UsageAnalyzer(db)
    summary = analyzer.get_usage_summary(meter_id, start_date, end_date)

    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No usage data found for the specified period",
        )

    return summary


@router.get("/daily/{meter_id}", response_model=list[DailyUsage])
async def get_daily_usage(
    meter_id: int,
    start_date: date | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(30, ge=1, le=365, description="Number of days to return"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DailyUsage]:
    """Get daily usage breakdown for a meter."""
    verify_meter_ownership(db, meter_id, current_user.id)

    analyzer = UsageAnalyzer(db)
    return analyzer.get_daily_usage(meter_id, start_date, end_date, limit)


@router.get("/hourly/{meter_id}", response_model=list[HourlyUsage])
async def get_hourly_usage(
    meter_id: int,
    start_date: date | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[HourlyUsage]:
    """Get average hourly usage pattern.

    Returns the average consumption for each hour of the day (0-23),
    useful for identifying peak usage times.
    """
    verify_meter_ownership(db, meter_id, current_user.id)

    analyzer = UsageAnalyzer(db)
    return analyzer.get_hourly_usage(meter_id, start_date, end_date)


@router.get("/weekly/{meter_id}", response_model=list[WeeklyUsage])
async def get_weekly_usage(
    meter_id: int,
    start_date: date | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[WeeklyUsage]:
    """Get average usage by day of week.

    Returns the average consumption for each day of the week,
    useful for identifying weekday vs weekend patterns.
    """
    verify_meter_ownership(db, meter_id, current_user.id)

    analyzer = UsageAnalyzer(db)
    return analyzer.get_weekly_usage(meter_id, start_date, end_date)
