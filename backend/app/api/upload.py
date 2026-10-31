"""NEM12 file upload endpoints."""

import hashlib
import logging

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import SessionLocal, get_db
from app.models.upload import NEM12Upload
from app.models.user import User
from app.rate_limit import limiter
from app.services.nem12_importer import NEM12Importer
from app.services.nem12_parser import NEM12Parser

router = APIRouter(prefix="/upload", tags=["Upload"])
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024
logger = logging.getLogger(__name__)


def import_nem12_in_process(
    upload_id: int,
    user_id: int,
    content: bytes,
    filename: str | None,
) -> None:
    """Run the non-durable Redis fallback with a task-owned database session."""
    db = SessionLocal()
    try:
        NEM12Importer().import_file(
            db,
            user_id,
            content,
            filename=filename,
            upload_id=upload_id,
        )
    except Exception as exc:
        logger.error(
            "In-process NEM12 import failed",
            extra={"upload_id": upload_id, "error_type": type(exc).__name__},
        )
        raise
    finally:
        db.close()


class UploadResponse(BaseModel):
    """Response after successful NEM12 upload."""

    message: str
    meters_created: int
    meters_updated: int
    readings_imported: int
    warnings: list[str]
    errors: list[str]


class UploadAccepted(BaseModel):
    upload_id: int
    message: str


@router.post("", response_model=UploadAccepted)
@limiter.limit("5/minute")
async def upload_nem12(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UploadAccepted:
    """Upload and process a NEM12 file.

    The file should be a valid NEM12 format CSV file from your energy retailer
    or distribution network.
    """
    # Validate file type
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided",
        )

    if not file.filename.lower().endswith((".csv", ".nem12", ".nem")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV or NEM12 file",
        )

    # Read file content
    try:
        content = await file.read(MAX_UPLOAD_SIZE_BYTES + 1)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to read the uploaded file.",
        ) from exc
    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large (max 50MB)",
        )

    # Validate NEM12 format
    is_valid, error_msg = NEM12Parser.validate_file(content)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid NEM12 file: {error_msg}",
        )
    # Compute file hash for deduplication
    file_hash = hashlib.sha256(content).hexdigest()

    # If this exact file was already imported for this user, return existing upload
    existing = (
        db.query(NEM12Upload)
        .filter(
            NEM12Upload.user_id == current_user.id,
            NEM12Upload.file_hash == file_hash,
        )
        .with_for_update()
        .first()
    )
    if existing is not None:
        if existing.status == "completed":
            return UploadAccepted(
                upload_id=existing.id,
                message="File already imported previously",
            )
        if existing.status in {"pending", "processing"}:
            if existing.rq_job_id:
                from app.tasks import get_job_status

                queue_status = get_job_status(existing.rq_job_id)
                if (
                    queue_status in {"failed", "stopped", "canceled", "finished"}
                    or queue_status is None
                ):
                    logger.info(
                        "Retrying a failed NEM12 queue job",
                        extra={"upload_id": existing.id, "rq_job_status": queue_status},
                    )
                else:
                    return UploadAccepted(
                        upload_id=existing.id,
                        message="An upload with this content is already pending or processing",
                    )
            else:
                return UploadAccepted(
                    upload_id=existing.id,
                    message="An upload with this content is already pending or processing",
                )
        existing.status = "pending"
        existing.progress_percent = 0
        existing.errors = None
        existing.warnings = None
        existing.rq_job_id = None
        upload = existing
    else:
        upload = NEM12Upload(
            user_id=current_user.id,
            filename=file.filename,
            status="pending",
            file_hash=file_hash,
        )
        db.add(upload)
    try:
        db.commit()
        db.refresh(upload)
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(NEM12Upload)
            .filter(
                NEM12Upload.user_id == current_user.id,
                NEM12Upload.file_hash == file_hash,
            )
            .first()
        )
        if existing is None:
            raise
        return UploadAccepted(
            upload_id=existing.id,
            message="An upload with this content already exists",
        )

    # Try to enqueue via RQ; if Redis isn't available, fallback to BackgroundTasks
    try:
        from app.tasks import enqueue_import

        job_id = enqueue_import(content, current_user.id, file.filename, upload.id)
        upload.rq_job_id = job_id
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning(
            "NEM12 queue unavailable; using in-process fallback",
            extra={"upload_id": upload.id, "error_type": type(exc).__name__},
        )
        background_tasks.add_task(
            import_nem12_in_process,
            upload.id,
            current_user.id,
            content,
            file.filename,
        )

    return UploadAccepted(
        upload_id=upload.id,
        message="Upload accepted and processing started",
    )


@router.get("/{upload_id}")
async def get_upload_status(
    upload_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get the status of a previously uploaded NEM12 file."""
    upload = (
        db.query(NEM12Upload)
        .filter(NEM12Upload.id == upload_id, NEM12Upload.user_id == current_user.id)
        .first()
    )
    if not upload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")

    # Attempt to fetch job status from Redis if present
    job_id = upload.rq_job_id
    job_status = "unavailable" if job_id else None
    if job_id:
        try:
            from app.tasks import get_job_status

            job_status = get_job_status(job_id)
        except Exception as exc:
            logger.warning(
                "Unable to retrieve upload job status",
                extra={"upload_id": upload.id, "error_type": type(exc).__name__},
            )

    return {
        "id": upload.id,
        "status": upload.status,
        "progress_percent": upload.progress_percent or 0,
        "rq_job_id": job_id,
        "rq_job_status": job_status,
        "total_readings": upload.total_readings,
        "errors": (upload.errors or "").split("\n") if upload.errors else [],
        "warnings": (upload.warnings or "").split("\n") if upload.warnings else [],
        "processed_at": upload.processed_at,
    }
