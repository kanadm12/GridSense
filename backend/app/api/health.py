"""Health check and operational endpoints."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from rq import Queue, Worker
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger(__name__)


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
        logger.error(
            "Readiness check failed",
            extra={"dependency": "database", "error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "database": "disconnected",
            },
        ) from exc


@router.get("/worker")
def worker_health(current_user: dict = Depends(get_current_user)) -> dict:
    """Check RQ worker status (requires authentication)."""
    try:
        from app.tasks import get_redis_conn

        redis = get_redis_conn()
        queue = Queue("default", connection=redis)

        workers = Worker.all(connection=redis, queue=queue)
        jobs_queued = queue.count
        failed_jobs = queue.failed_job_registry.count

        if not workers:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"status": "unavailable", "worker": "not_running", "workers": 0},
            )

        return {
            "status": "ok",
            "workers": len(workers),
            "jobs_queued": jobs_queued,
            "jobs_failed": failed_jobs,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Worker health check failed",
            extra={"dependency": "redis", "error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unavailable", "worker": "unreachable"},
        ) from exc
