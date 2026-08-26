"""Services to import parsed NEM12 data into the database and generate aggregates."""

from datetime import datetime
from typing import Callable, Optional
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.services.nem12_parser import NEM12Parser, NEM12ParseResult, NEM12MeterData
from app.models import Meter, Reading, NEM12Upload, DailyAggregate
from app.schemas.reading import ReadingBulkCreate


logger = logging.getLogger(__name__)


class NEM12Importer:
    """Import NEM12 parsed data into DB and compute aggregates."""

    CHUNK_SIZE = 5000  # Insert readings in chunks for large files

    def __init__(self, parser: Optional[NEM12Parser] = None):
        self.parser = parser or NEM12Parser()

    def import_file(
        self,
        db: Session,
        user_id: int,
        file_content: str | bytes,
        filename: str | None = None,
        upload_id: int | None = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> NEM12ParseResult:
        """Parse NEM12 content, persist upload record, meters, and readings.

        If `upload_id` is provided, update that upload record; otherwise create a new one.
        
        Args:
            db: Database session
            user_id: User ID for ownership
            file_content: NEM12 file content
            filename: Original filename
            upload_id: Existing upload record ID (optional)
            progress_callback: Optional callback(current, total) for progress updates

        Returns the parse result for reporting.
        """
        # Create or load upload record
        if upload_id is not None:
            upload = db.query(NEM12Upload).filter(NEM12Upload.id == upload_id).first()
            if upload is None:
                upload = NEM12Upload(user_id=user_id, filename=filename, status="processing")
                db.add(upload)
                db.flush()
            else:
                upload.status = "processing"
                upload.processed_at = None
                upload.errors = None
                upload.warnings = None
                db.add(upload)
                db.flush()
        else:
            upload = NEM12Upload(
                user_id=user_id,
                filename=filename,
                status="processing",
                processed_at=None,
            )
            db.add(upload)
            db.flush()

        # Parse file
        result = self.parser.parse(file_content)

        # Save parsed data
        total_inserted = 0
        errors_text = "\n".join(result.errors) if result.errors else None
        warnings_text = "\n".join(result.warnings) if result.warnings else None

        try:
            for meter_data in result.meters:
                meter = self._get_or_create_meter(db, user_id, meter_data)

                # Prepare Reading objects
                reading_objs = []
                for r in meter_data.readings:
                    # Expect ReadingBulkCreate-like objects
                    if isinstance(r, ReadingBulkCreate):
                        reading_objs.append(
                            Reading(
                                meter_id=meter.id,
                                timestamp=r.timestamp,
                                value=r.value,
                                quality=r.quality,
                                register_type=r.register_type,
                            )
                        )
                    else:
                        # fallback dict-like
                        reading_objs.append(
                            Reading(
                                meter_id=meter.id,
                                timestamp=r["timestamp"],
                                value=r["value"],
                                quality=r.get("quality", "A"),
                                register_type=r.get("register_type", "B"),
                            )
                        )

                # Insert readings in chunks for large files
                if reading_objs:
                    total_readings = len(reading_objs)
                    logger.info(
                        f"Inserting {total_readings} readings for meter {meter.nmi}"
                    )

                    for i in range(0, total_readings, self.CHUNK_SIZE):
                        chunk = reading_objs[i : i + self.CHUNK_SIZE]
                        db.bulk_save_objects(chunk)
                        db.commit()  # Commit each chunk
                        total_inserted += len(chunk)

                        # Update progress in upload record
                        if upload:
                            progress = int((total_inserted / total_readings) * 100)
                            upload.progress_percent = progress
                            db.add(upload)
                            db.commit()

                        # Report progress if callback provided
                        if progress_callback:
                            progress_callback(total_inserted, total_readings)

                        logger.debug(
                            f"Inserted chunk {i // self.CHUNK_SIZE + 1}, "
                            f"total: {total_inserted}/{total_readings}"
                        )

            # Update upload record
            upload.status = "completed"
            upload.total_readings = total_inserted
            upload.errors = errors_text
            upload.warnings = warnings_text
            upload.processed_at = datetime.utcnow()
            db.add(upload)
            db.commit()

            # Generate aggregates for affected meters
            for meter_data in result.meters:
                meter = db.query(Meter).filter(Meter.nmi == meter_data.nmi, Meter.suffix == meter_data.suffix, Meter.user_id == user_id).first()
                if meter:
                    self.generate_daily_aggregates(db, meter.id)

        except Exception:
            db.rollback()
            upload.status = "failed"
            upload.errors = (upload.errors or "") + "\nImport failure"
            db.add(upload)
            db.commit()
            raise

        return result

    def _get_or_create_meter(self, db: Session, user_id: int, meter_data: NEM12MeterData) -> Meter:
        meter = (
            db.query(Meter)
            .filter(Meter.nmi == meter_data.nmi, Meter.suffix == (meter_data.suffix or ""), Meter.user_id == user_id)
            .first()
        )
        if meter:
            return meter

        meter = Meter(
            user_id=user_id,
            nmi=meter_data.nmi,
            meter_serial=meter_data.meter_serial,
            suffix=meter_data.suffix,
            unit_of_measure=meter_data.unit_of_measure,
            interval_minutes=meter_data.interval_minutes,
            name=None,
        )
        db.add(meter)
        db.flush()
        return meter

    def generate_daily_aggregates(self, db: Session, meter_id: int) -> None:
        """Generate/update daily aggregates for a meter from its readings."""
        # Aggregate readings by date
        reading_date = func.date(Reading.timestamp)
        stmt = (
            db.query(reading_date.label("day"), func.sum(Reading.value).label("total_kwh"))
            .filter(Reading.meter_id == meter_id)
            .group_by(reading_date)
        )

        for row in stmt:
            day = row[0]
            # func.date may return a string YYYY-MM-DD on some DBs (SQLite), convert to date
            if isinstance(day, str):
                try:
                    from datetime import date as _date

                    day = _date.fromisoformat(day)
                except Exception:
                    # fallback: attempt parse via datetime
                    from datetime import datetime as _dt

                    day = _dt.strptime(day, "%Y-%m-%d").date()
            total_kwh = float(row[1] or 0.0)

            agg = (
                db.query(DailyAggregate)
                .filter(DailyAggregate.meter_id == meter_id, DailyAggregate.date == day)
                .first()
            )
            if not agg:
                agg = DailyAggregate(meter_id=meter_id, date=day, total_kwh=total_kwh, peak_kwh=0.0, offpeak_kwh=0.0)
                db.add(agg)
            else:
                agg.total_kwh = total_kwh
            db.flush()

        db.commit()
