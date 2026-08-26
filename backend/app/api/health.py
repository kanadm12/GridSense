"""Health check and operational endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from rq import Queue
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def liveness() -> dict:
    """Kubernetes/Docker liveness probe - API is running."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/ready")
def readiness(db: Session = Depends(get_db)) -> dict:
    """Kubernetes/Docker readiness probe - API can handle requests."""
    try:
        # Check database connection
        db.execute(text("SELECT 1"))
        return {
            "status": "ready",
            "database": "connected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        return {
            "status": "not_ready",
            "database": "disconnected",
            "error": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@router.get("/worker")
def worker_health(current_user: dict = Depends(get_current_user)) -> dict:
    """Check RQ worker status (requires authentication)."""
    try:
        from app.worker import get_redis_conn

        redis = get_redis_conn()
        queue = Queue("default", connection=redis)

        workers = queue.workers
        jobs_queued = queue.count
        failed_jobs = queue.failed_job_registry.count

        return {
            "status": "ok",
            "workers": len(workers),
            "jobs_queued": jobs_queued,
            "jobs_failed": failed_jobs,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
