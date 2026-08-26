"""Background tasks for RQ worker processing."""
import asyncio
from datetime import datetime, timezone
from typing import Optional

from redis import Redis
from rq import Queue

from app.config import get_settings
from app.database import SessionLocal
from app.models.aggregate import DailyAggregate
from app.models.automation import Automation as AutomationModel
from app.models.automation import DeviceSchedule, SmartDevice
from app.models.meter import Meter
from app.models.upload import NEM12Upload
from app.services.alert_service import publish_after_import
from app.services.automation_provider import AutomationProviderError, get_automation_provider
from app.services.nem12_importer import NEM12Importer

settings = get_settings()


def get_redis_conn() -> Redis:
    return Redis.from_url(getattr(settings, "redis_url", "redis://localhost:6379/0"))


def enqueue_import(content: bytes, user_id: int, filename: Optional[str], upload_id: int) -> str:
    """Enqueue an import job and return job id."""
    q = Queue("default", connection=get_redis_conn())
    # RQ will serialize arguments; send bytes as is
    job = q.enqueue("app.tasks.import_nem12_task", upload_id, user_id, content, filename)
    return job.id


def get_job_status(job_id: str) -> Optional[str]:
    """Return RQ job status string, or None if not found/Redis unavailable."""
    try:
        from rq.job import Job

        conn = get_redis_conn()
        job = Job.fetch(job_id, connection=conn)
        return job.get_status()
    except Exception:
        return None


def enqueue_automation_rule(rule_id: int) -> str:
    """Enqueue a manual automation rule execution."""
    q = Queue("default", connection=get_redis_conn())
    job = q.enqueue("app.tasks.execute_automation_rule_task", rule_id)
    return job.id


def execute_automation_rule_task(rule_id: int) -> dict:
    """Execute one enabled automation rule through its configured provider."""
    db = SessionLocal()
    try:
        rule = (
            db.query(AutomationModel)
            .join(SmartDevice)
            .filter(AutomationModel.id == rule_id)
            .first()
        )
        if rule is None:
            return {"status": "not_found", "rule_id": rule_id}
        if not rule.is_enabled or not rule.device.is_enabled:
            return {"status": "skipped", "reason": "disabled", "rule_id": rule_id}

        now = datetime.now(timezone.utc)
        provider = get_automation_provider(rule.device, settings)
        command = rule.action.get("command", rule.action.get("action", ""))
        new_state = asyncio.run(provider.execute(rule.device, command, rule.action.get("params")))
        rule.device.current_state = new_state
        rule.device.last_seen = now
        rule.last_triggered = now
        rule.trigger_count = (rule.trigger_count or 0) + 1
        db.commit()
        return {"status": "completed", "rule_id": rule_id, "new_state": new_state}
    except AutomationProviderError as exc:
        db.rollback()
        return {"status": "failed", "rule_id": rule_id, "error": str(exc)}
    finally:
        db.close()


def execute_due_schedules_task() -> dict:
    """Execute enabled schedules due in the current UTC minute.

    A scheduler or cron process can enqueue this task once per minute.
    """
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    executed = 0
    skipped = 0
    failed = 0
    try:
        schedules = (
            db.query(DeviceSchedule)
            .join(SmartDevice)
            .filter(DeviceSchedule.is_enabled.is_(True), SmartDevice.is_enabled.is_(True))
            .all()
        )
        for schedule in schedules:
            if now.weekday() not in (schedule.days_of_week or []):
                continue
            if schedule.start_time != now.strftime("%H:%M"):
                continue
            if schedule.last_executed_at:
                last = schedule.last_executed_at
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                if (now - last).total_seconds() < 60:
                    skipped += 1
                    continue

            try:
                provider = get_automation_provider(schedule.device, settings)
                new_state = asyncio.run(
                    provider.execute(schedule.device, schedule.action, schedule.action_params)
                )
                schedule.device.current_state = new_state
                schedule.device.last_seen = now
                schedule.last_executed_at = now
                db.commit()
                executed += 1
            except AutomationProviderError:
                db.rollback()
                failed += 1
        return {"status": "completed", "executed": executed, "skipped": skipped, "failed": failed}
    finally:
        db.close()


def enqueue_ml_training(meter_id: int) -> Optional[str]:
    """Create and enqueue a meter training job when enough data exists."""
    db = SessionLocal()
    try:
        from app.services.ml_training_service import MINIMUM_TRAINING_DAYS, MLTrainingService

        days_available = (
            db.query(DailyAggregate)
            .filter(DailyAggregate.meter_id == meter_id)
            .count()
        )
        if days_available < MINIMUM_TRAINING_DAYS:
            return None

        service = MLTrainingService(db)
        active_job = service.get_active_job(meter_id, "all")
        if active_job:
            return active_job.rq_job_id

        job = service.create_job(meter_id, "all")
        queue = Queue("default", connection=get_redis_conn())
        rq_job = queue.enqueue("app.tasks.train_meter_models_task", job.id, meter_id, "all")
        job.rq_job_id = rq_job.id
        db.commit()
        return job.rq_job_id
    finally:
        db.close()


def train_meter_models_task(training_job_id: int, meter_id: int, job_type: str = "all") -> dict:
    """Train models for one meter and persist job status and safe metrics."""
    db = SessionLocal()
    service = None
    try:
        from app.services.ml_training_service import MLTrainingService

        service = MLTrainingService(db)
        service.update_job_status(training_job_id, "running")
        results = service.train_meter_models(meter_id, job_type)
        if results.get("status") == "insufficient_data":
            service.record_metrics(training_job_id, results)
            service.update_job_status(training_job_id, "failed", "Insufficient data for training")
            return results

        safe_results = {}
        successful = 0
        successful_models = []
        for model_type, result in results.items():
            safe_result = {key: value for key, value in result.items() if key != "model_path"}
            safe_results[model_type] = safe_result
            if result.get("status") == "success":
                successful += 1
                successful_models.append(model_type)

        service.record_metrics(training_job_id, safe_results)
        if successful:
            service.update_job_status(training_job_id, "completed")
            # Notify user of successful training
            try:
                from app.services.alert_service import notify_training_completion
                meter = db.query(Meter).get(meter_id)
                if meter:
                    notify_training_completion(db, meter.user_id, meter_id, True, successful_models)
            except Exception:
                pass  # Don't fail task if notification fails
            return {"status": "completed", "results": safe_results}

        service.update_job_status(training_job_id, "failed", "No model completed successfully")
        return {"status": "failed", "results": safe_results}
    except Exception as exc:
        if service:
            service.update_job_status(training_job_id, "failed", str(exc))
        raise
    finally:
        db.close()


def retrain_all_meters_task() -> dict:
    """Queue training for every meter with sufficient data."""
    db = SessionLocal()
    queued = 0
    try:
        meter_ids = [meter.id for meter in db.query(Meter).all()]
    finally:
        db.close()

    for meter_id in meter_ids:
        if enqueue_ml_training(meter_id):
            queued += 1
    return {"status": "completed", "queued": queued}


def check_all_forecasts_task() -> dict:
    """Check bill forecasts for all meters and alert on high bills."""
    db = SessionLocal()
    alerted = 0
    try:
        from app.services.alert_service import check_high_bill_forecast

        meters = db.query(Meter).all()
        for meter in meters:
            try:
                alerted += check_high_bill_forecast(db, meter.user_id, meter.id)
            except Exception:
                continue
    finally:
        db.close()
    return {"status": "completed", "alerted": alerted}


def send_weekly_summaries_task() -> dict:
    """Send weekly energy summaries to all users."""
    db = SessionLocal()
    sent = 0
    try:
        from app.services.alert_service import generate_weekly_summary

        meters = db.query(Meter).all()
        for meter in meters:
            try:
                sent += generate_weekly_summary(db, meter.user_id, meter.id)
            except Exception:
                continue
    finally:
        db.close()
    return {"status": "completed", "sent": sent}


def import_nem12_task(
    upload_id: int, user_id: int, content: bytes, filename: Optional[str]
) -> dict:
    """Task executed by worker to import a NEM12 file.

    This function creates its own DB session and updates the upload record status.
    """
    db = SessionLocal()
    try:
        upload = db.query(NEM12Upload).get(upload_id)
        if upload:
            upload.status = "processing"
            db.add(upload)
            db.commit()

        importer = NEM12Importer()
        result = importer.import_file(db, user_id, content, filename=filename, upload_id=upload_id)

        if upload:
            upload.status = "completed"
            upload.total_readings = result.total_readings
            db.add(upload)
            db.commit()

        alerts_published = 0
        for meter_data in result.meters:
            meter = (
                db.query(Meter)
                .filter(
                    Meter.user_id == user_id,
                    Meter.nmi == meter_data.nmi,
                    Meter.suffix == (meter_data.suffix or ""),
                )
                .first()
            )
            if meter:
                alerts_published += publish_after_import(db, user_id, meter.id)

                # Training is optional and only starts once enough daily data exists.
                enqueue_ml_training(meter.id)

        return {
            "status": "completed",
            "readings": result.total_readings,
            "alerts_published": alerts_published,
        }
    except Exception as exc:
        if upload:
            upload.status = "failed"
            upload.errors = str(exc)
            db.add(upload)
            db.commit()
        raise
    finally:
        db.close()
