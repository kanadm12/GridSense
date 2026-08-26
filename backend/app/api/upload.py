"""NEM12 file upload endpoints."""

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status, BackgroundTasks
import hashlib
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.rate_limit import limiter
from app.database import get_db
from app.models.meter import Meter
from app.models.reading import Reading
from app.models.user import User
from app.services.nem12_parser import NEM12Parser
from app.services.nem12_importer import NEM12Importer
from app.models.upload import NEM12Upload
from app.schemas.reading import ReadingBulkCreate
from typing import Optional

router = APIRouter(prefix="/upload", tags=["Upload"])


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
        content = await file.read()
        if len(content) > 50 * 1024 * 1024:  # 50MB limit
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File too large (max 50MB)",
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error reading file: {str(e)}",
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
        .filter(NEM12Upload.user_id == current_user.id, NEM12Upload.file_hash == file_hash, NEM12Upload.status == "completed")
        .first()
    )
    if existing:
        return UploadAccepted(upload_id=existing.id, message="File already imported previously")

    # Create upload record in DB (pending) and schedule background import
    upload = NEM12Upload(user_id=current_user.id, filename=file.filename, status="pending", file_hash=file_hash)
    db.add(upload)
    db.commit()
    db.refresh(upload)

    importer = NEM12Importer()

    # Try to enqueue via RQ; if Redis isn't available, fallback to BackgroundTasks
    try:
        from app.tasks import enqueue_import

        job_id = enqueue_import(content, current_user.id, file.filename, upload.id)
        # store job id on upload for tracking
        upload.rq_job_id = job_id
        db.add(upload)
        db.commit()
    except Exception:
        # fallback to in-process background task
        background_tasks.add_task(importer.import_file, db, current_user.id, content, file.filename, upload.id)

    return UploadAccepted(upload_id=upload.id, message="Upload accepted and processing started")


@router.get("/{upload_id}")
async def get_upload_status(upload_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict:
    """Get the status of a previously uploaded NEM12 file."""
    upload = db.query(NEM12Upload).filter(NEM12Upload.id == upload_id, NEM12Upload.user_id == current_user.id).first()
    if not upload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")

    # Attempt to fetch job status from Redis if present
    job_id: Optional[str] = getattr(upload, "rq_job_id", None)
    job_status: Optional[str] = None
    if job_id:
        try:
            from app.tasks import get_job_status

            job_status = get_job_status(job_id)
        except Exception:
            job_status = None

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
