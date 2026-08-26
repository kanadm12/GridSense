"""ML training job management and scheduling."""

import json
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.ml.etl import extract_daily_series
from app.ml.train import train_anomaly_detector, train_forecast
from app.models.meter import Meter
from app.models.ml_training import MLTrainingJob

MINIMUM_TRAINING_DAYS = 20


class MLTrainingService:
    """Service for managing ML model training jobs."""

    def __init__(self, db: Session):
        self.db = db

    def create_job(
        self, meter_id: int, job_type: str, rq_job_id: Optional[str] = None
    ) -> MLTrainingJob:
        """Create a new training job record."""
        job = MLTrainingJob(
            meter_id=meter_id,
            job_type=job_type,
            rq_job_id=rq_job_id,
            status="pending",
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def update_job_status(
        self, job_id: int, status: str, error_message: Optional[str] = None
    ) -> bool:
        """Update job status."""
        job = self.db.query(MLTrainingJob).get(job_id)
        if job:
            job.status = status
            if status == "running" and not job.started_at:
                job.started_at = datetime.now()
            if status == "completed":
                job.completed_at = datetime.now()
            if error_message:
                job.error_message = error_message
            self.db.add(job)
            self.db.commit()
            return True
        return False

    def record_metrics(self, job_id: int, metrics: dict) -> bool:
        """Record training metrics."""
        job = self.db.query(MLTrainingJob).get(job_id)
        if job:
            job.metrics = json.dumps(metrics)
            self.db.add(job)
            self.db.commit()
            return True
        return False

    def get_job(self, job_id: int) -> Optional[MLTrainingJob]:
        """Get a training job by ID."""
        return self.db.query(MLTrainingJob).get(job_id)

    def list_jobs(self, meter_id: int, limit: int = 10) -> list[MLTrainingJob]:
        """List training jobs for a meter."""
        return (
            self.db.query(MLTrainingJob)
            .filter(MLTrainingJob.meter_id == meter_id)
            .order_by(MLTrainingJob.created_at.desc())
            .limit(limit)
            .all()
        )

    def train_meter_models(self, meter_id: int, job_type: str = "all") -> dict:
        """Train models for a meter (forecast, anomaly, or both).

        Returns dict with training results and metrics.
        """
        # Extract time-series data
        df = extract_daily_series(self.db, meter_id)
        if df.empty or len(df) < MINIMUM_TRAINING_DAYS:
            return {
                "status": "insufficient_data",
                "days_available": len(df),
                "minimum_days": MINIMUM_TRAINING_DAYS,
            }

        results = {}

        # Train forecast model
        if job_type in ("all", "forecast"):
            try:
                forecast_result = train_forecast(df, meter_id)
                results["forecast"] = {
                    "status": "success",
                    "model_path": forecast_result["model_path"],
                }
            except Exception as e:
                results["forecast"] = {"status": "failed", "error": str(e)}

        # Train anomaly detector
        if job_type in ("all", "anomaly"):
            try:
                anomaly_result = train_anomaly_detector(df, meter_id)
                results["anomaly"] = {
                    "status": "success",
                    "model_path": anomaly_result["model_path"],
                    "n_anomalies": anomaly_result["n_anomalies"],
                }
            except Exception as e:
                results["anomaly"] = {"status": "failed", "error": str(e)}

        return results

    def get_active_job(self, meter_id: int, job_type: str = "all") -> Optional[MLTrainingJob]:
        """Return a pending or running job, if one exists for the meter."""
        return (
            self.db.query(MLTrainingJob)
            .filter(
                MLTrainingJob.meter_id == meter_id,
                MLTrainingJob.job_type == job_type,
                MLTrainingJob.status.in_(["pending", "running"]),
            )
            .order_by(MLTrainingJob.created_at.desc())
            .first()
        )

    def get_latest_job_by_type(self, meter_id: int, job_type: str) -> Optional[MLTrainingJob]:
        """Get the most recent training job of a specific type."""
        return (
            self.db.query(MLTrainingJob)
            .filter(MLTrainingJob.meter_id == meter_id, MLTrainingJob.job_type == job_type)
            .order_by(MLTrainingJob.created_at.desc())
            .first()
        )

    def schedule_retrain_all_meters(self) -> list[MLTrainingJob]:
        """Schedule retraining for all active meters. Returns list of created jobs."""
        meters = self.db.query(Meter).all()
        jobs = []
        for meter in meters:
            job = self.create_job(meter.id, "all")
            jobs.append(job)
        return jobs
