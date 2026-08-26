"""Notification orchestration for usage alerts."""

import asyncio
import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationType
from app.services.anomaly_detector import AnomalyDetector
from app.services.forecasting import BillForecaster
from app.services.notification_service import NotificationService
from app.services.recommendation_engine import RecommendationEngine


class AlertService:
    """Generate user alerts from usage analysis and deliver them once."""

    def __init__(self, db: Session):
        self.db = db
        self.notifications = NotificationService(db)
        self.anomalies = AnomalyDetector(db)
        self.recommendations = RecommendationEngine(db)
        self.forecaster = BillForecaster(db)

    def _already_published(
        self, user_id: int, notification_type: NotificationType, key: str
    ) -> bool:
        """Check recent notification metadata for a deduplication key."""
        recent = (
            self.db.query(Notification)
            .filter(
                Notification.user_id == user_id,
                Notification.notification_type == notification_type,
            )
            .order_by(Notification.created_at.desc())
            .limit(100)
            .all()
        )
        for notification in recent:
            if not notification.data:
                continue
            try:
                if json.loads(notification.data).get("dedupe_key") == key:
                    return True
            except (TypeError, json.JSONDecodeError):
                continue
        return False

    async def _publish(
        self,
        user_id: int,
        notification_type: NotificationType,
        title: str,
        message: str,
        data: dict[str, Any],
    ) -> bool:
        """Publish an alert unless the same event was already recorded."""
        key = str(data["dedupe_key"])
        if self._already_published(user_id, notification_type, key):
            return False
        return await self.notifications.send_push_notification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            data=data,
        )

    async def publish_after_import(self, user_id: int, meter_id: int) -> int:
        """Generate alerts after a successful meter import."""
        published = 0
        for anomaly in self.anomalies.get_all_anomalies(meter_id).get("anomalies", []):
            anomaly_type = str(
                anomaly["type"].value
                if hasattr(anomaly["type"], "value")
                else anomaly["type"]
            )
            data = {
                "meter_id": meter_id,
                "anomaly_type": anomaly_type,
                "date": anomaly["date"],
                "dedupe_key": f"{meter_id}:anomaly:{anomaly_type}:{anomaly['date']}",
            }
            if await self._publish(
                user_id,
                NotificationType.ANOMALY_ALERT,
                "Unusual energy usage detected",
                anomaly["message"],
                data,
            ):
                published += 1

        recommendations = self.recommendations.generate_recommendations(meter_id)
        for recommendation in recommendations.recommendations:
            if recommendation.priority.value != "high":
                continue
            data = {
                "meter_id": meter_id,
                "recommendation_id": recommendation.id,
                "dedupe_key": f"{meter_id}:recommendation:{recommendation.id}",
            }
            if await self._publish(
                user_id,
                NotificationType.RECOMMENDATION,
                recommendation.title,
                recommendation.description,
                data,
            ):
                published += 1
        return published


    async def check_high_bill_forecast(self, user_id: int, meter_id: int) -> int:
        """Alert if monthly bill forecast exceeds threshold."""
        published = 0
        try:
            forecast = self.forecaster.forecast_monthly_bill(meter_id)
            projected_cost = forecast.get("projected_total_cost", 0)
            # Alert if projected cost is >$300 or >20% above average
            if projected_cost > 300 or (
                forecast.get("days_elapsed", 1) > 7
                and projected_cost > forecast.get("cost_so_far", 0) * 1.4
            ):
                data = {
                    "meter_id": meter_id,
                    "projected_cost": projected_cost,
                    "dedupe_key": f"{meter_id}:forecast:{forecast['month']}",
                }
                if await self._publish(
                    user_id,
                    NotificationType.FORECAST_UPDATE,
                    "High bill forecast",
                    f"Your projected bill for {forecast['month']} is ${projected_cost:.0f}.",
                    data,
                ):
                    published += 1
        except Exception:
            pass  # Forecast unavailable, skip silently
        return published

    async def notify_training_completion(
        self, user_id: int, meter_id: int, success: bool, models: list[str]
    ) -> bool:
        """Notify user when ML models finish training."""
        if success:
            title = "Energy models updated"
            message = f"Your personalized {', '.join(models)} models are ready."
        else:
            title = "Model training needs attention"
            message = "We need more data to create personalized forecasts."

        data = {
            "meter_id": meter_id,
            "success": success,
            "models": models,
            "dedupe_key": f"{meter_id}:training:{success}:{'_'.join(sorted(models))}",
        }
        return await self._publish(
            user_id, NotificationType.FORECAST_UPDATE, title, message, data
        )

    async def generate_weekly_summary(self, user_id: int, meter_id: int) -> int:
        """Generate and send weekly energy usage summary."""
        published = 0
        try:
            # Get 7-day usage stats
            from datetime import date, timedelta

            from app.models.aggregate import DailyAggregate

            end_date = date.today()
            start_date = end_date - timedelta(days=7)
            week_data = (
                self.db.query(DailyAggregate)
                .filter(
                    DailyAggregate.meter_id == meter_id,
                    DailyAggregate.date >= start_date,
                    DailyAggregate.date < end_date,
                )
                .all()
            )

            if not week_data:
                return 0

            total_kwh = sum(d.total_kwh or 0 for d in week_data)
            avg_daily = total_kwh / len(week_data) if week_data else 0
            estimated_cost = total_kwh * 0.27  # Average rate

            message = (
                f"This week: {total_kwh:.1f} kWh (avg {avg_daily:.1f} kWh/day). "
                f"Estimated cost: ${estimated_cost:.2f}."
            )

            data = {
                "meter_id": meter_id,
                "week_start": str(start_date),
                "week_end": str(end_date),
                "total_kwh": total_kwh,
                "avg_daily_kwh": avg_daily,
                "estimated_cost": estimated_cost,
                "dedupe_key": f"{meter_id}:weekly:{start_date}",
            }

            if await self._publish(
                user_id,
                NotificationType.WEEKLY_SUMMARY,
                "Your weekly energy summary",
                message,
                data,
            ):
                published += 1
        except Exception:
            pass
        return published


def publish_after_import(db: Session, user_id: int, meter_id: int) -> int:
    """Synchronous worker entry point for post-import alert generation."""
    return asyncio.run(AlertService(db).publish_after_import(user_id, meter_id))


def check_high_bill_forecast(db: Session, user_id: int, meter_id: int) -> int:
    """Check and alert on high bill forecasts."""
    return asyncio.run(AlertService(db).check_high_bill_forecast(user_id, meter_id))


def notify_training_completion(
    db: Session, user_id: int, meter_id: int, success: bool, models: list[str]
) -> bool:
    """Notify user of ML training completion."""
    return asyncio.run(
        AlertService(db).notify_training_completion(user_id, meter_id, success, models)
    )


def generate_weekly_summary(db: Session, user_id: int, meter_id: int) -> int:
    """Generate weekly summary for a meter."""
    return asyncio.run(AlertService(db).generate_weekly_summary(user_id, meter_id))
