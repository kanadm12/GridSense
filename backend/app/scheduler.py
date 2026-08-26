"""Minute-based scheduler for due automation rules."""

import time
from datetime import datetime, timezone

from redis import Redis
from rq import Queue

from app.config import get_settings

LOCK_KEY = "gridsense:automation:scheduler-minute"
ML_LOCK_KEY = "gridsense:ml:weekly-retrain"
SUMMARY_LOCK_KEY = "gridsense:notifications:weekly-summary"
FORECAST_LOCK_KEY = "gridsense:notifications:forecast-check"


def run() -> None:
    """Enqueue due schedule evaluation once per UTC minute."""
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    queue = Queue("default", connection=redis)

    while True:
        now = datetime.now(timezone.utc)
        minute_key = now.strftime("%Y-%m-%dT%H:%M")

        # Automation schedules: every minute
        if redis.set(LOCK_KEY, minute_key, nx=True, ex=55):
            queue.enqueue("app.tasks.execute_due_schedules_task")

        # ML retraining: Sunday 3am UTC weekly
        if now.weekday() == 6 and now.hour == 3 and now.minute == 0:
            if redis.set(ML_LOCK_KEY, minute_key, nx=True, ex=7 * 24 * 60 * 60):
                queue.enqueue("app.tasks.retrain_all_meters_task")

        # Weekly summaries: Sunday 8am UTC (after training completes)
        if now.weekday() == 6 and now.hour == 8 and now.minute == 0:
            if redis.set(SUMMARY_LOCK_KEY, minute_key, nx=True, ex=7 * 24 * 60 * 60):
                queue.enqueue("app.tasks.send_weekly_summaries_task")

        # Forecast checks: Daily 6pm UTC
        if now.hour == 18 and now.minute == 0:
            daily_key = now.strftime("%Y-%m-%d")
            if redis.set(FORECAST_LOCK_KEY, daily_key, nx=True, ex=24 * 60 * 60):
                queue.enqueue("app.tasks.check_all_forecasts_task")

        time.sleep(10)


if __name__ == "__main__":
    run()
