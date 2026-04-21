"""Recommendation endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.meter import Meter
from app.models.user import User
from app.schemas.recommendation import RecommendationsResponse
from app.services.recommendation_engine import RecommendationEngine

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


@router.get("/{meter_id}", response_model=RecommendationsResponse)
async def get_recommendations(
    meter_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RecommendationsResponse:
    """Get personalized energy recommendations for a meter.

    Analyzes usage patterns and provides actionable recommendations
    to reduce energy costs and improve efficiency.
    """
    # Verify meter ownership
    meter = (
        db.query(Meter)
        .filter(Meter.id == meter_id, Meter.user_id == current_user.id)
        .first()
    )

    if not meter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meter not found",
        )

    engine = RecommendationEngine(db)
    return engine.generate_recommendations(meter_id)


@router.get("", response_model=RecommendationsResponse)
async def get_all_recommendations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RecommendationsResponse:
    """Get recommendations for all user's meters combined.

    Returns a consolidated list of recommendations across all meters.
    """
    meters = db.query(Meter).filter(Meter.user_id == current_user.id).all()

    if not meters:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No meters found. Please upload NEM12 data first.",
        )

    engine = RecommendationEngine(db)

    # Get recommendations for the primary meter (first one)
    # In a more complete implementation, we'd aggregate across all meters
    return engine.generate_recommendations(meters[0].id)
