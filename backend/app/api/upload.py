"""NEM12 file upload endpoints."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.meter import Meter
from app.models.reading import Reading
from app.models.user import User
from app.services.nem12_parser import NEM12Parser

router = APIRouter(prefix="/upload", tags=["Upload"])


class UploadResponse(BaseModel):
    """Response after successful NEM12 upload."""

    message: str
    meters_created: int
    meters_updated: int
    readings_imported: int
    warnings: list[str]
    errors: list[str]


@router.post("", response_model=UploadResponse)
async def upload_nem12(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UploadResponse:
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

    # Parse the file
    parser = NEM12Parser()
    result = parser.parse(content)

    if result.errors and not result.meters:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse NEM12 file: {'; '.join(result.errors[:5])}",
        )

    meters_created = 0
    meters_updated = 0
    readings_imported = 0

    # Process each meter found in the file
    for meter_data in result.meters:
        # Find or create meter
        existing_meter = (
            db.query(Meter)
            .filter(
                Meter.user_id == current_user.id,
                Meter.nmi == meter_data.nmi,
                Meter.suffix == meter_data.suffix,
            )
            .first()
        )

        if existing_meter:
            meter = existing_meter
            meters_updated += 1
        else:
            meter = Meter(
                user_id=current_user.id,
                nmi=meter_data.nmi,
                meter_serial=meter_data.meter_serial,
                suffix=meter_data.suffix,
                unit_of_measure=meter_data.unit_of_measure,
                interval_minutes=meter_data.interval_minutes,
                state="VIC",  # Default to Victoria
                name=f"Meter {meter_data.nmi[-4:]}",  # Last 4 digits as default name
            )
            db.add(meter)
            db.flush()  # Get the meter ID
            meters_created += 1

        # Determine register type - default to B (consumption/import) for household meters
        # Only treat as export if suffix explicitly contains "export" or is B-type
        suffix_lower = (meter_data.suffix or "").lower()
        register_type = "E" if "export" in suffix_lower else "B"

        # Import readings (bulk insert for efficiency)
        readings_to_add = []
        for reading_data in meter_data.readings:
            # Check for duplicate timestamp
            existing = (
                db.query(Reading)
                .filter(
                    Reading.meter_id == meter.id,
                    Reading.timestamp == reading_data.timestamp,
                )
                .first()
            )

            if not existing:
                readings_to_add.append(
                    Reading(
                        meter_id=meter.id,
                        timestamp=reading_data.timestamp,
                        value=reading_data.value,
                        quality=reading_data.quality,
                        register_type=register_type,
                    )
                )

        if readings_to_add:
            db.bulk_save_objects(readings_to_add)
            readings_imported += len(readings_to_add)

    db.commit()

    return UploadResponse(
        message="NEM12 file processed successfully",
        meters_created=meters_created,
        meters_updated=meters_updated,
        readings_imported=readings_imported,
        warnings=result.warnings[:10],  # Limit warnings returned
        errors=result.errors[:10],  # Limit errors returned
    )
