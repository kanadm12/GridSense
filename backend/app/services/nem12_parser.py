"""NEM12 file parser for Australian smart meter data.

NEM12 is a CSV-based format used in Australia's National Electricity Market (NEM).
File structure:
- Record 100: Header (version info)
- Record 200: NMI Data Details (meter info)
- Record 300: Interval Data (actual readings)
- Record 400: Interval Event (quality flags)
- Record 500: B2B Details (not used for consumption)
- Record 900: End of data

Reference: AEMO MDFF Specification

NEM12 timestamps are preserved as naive fixed-market-time (UTC+10) interval ends.
Local civil-time consumers convert them explicitly using the associated meter timezone.

Timezone contract
-----------------
The parser preserves record 300 interval-end wall-clock values in fixed market time
(AEST, UTC+10), represented as naive datetimes. It does not adjust them for local DST.
Consumers convert these source timestamps to the meter's IANA timezone explicitly.
Each parsed reading also stores its interval length for exact boundary calculations.
"""

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import BinaryIO, TextIO

from app.schemas.reading import ReadingBulkCreate


@dataclass
class NEM12MeterData:
    """Parsed meter data from NEM12 file."""

    nmi: str
    register_id: str | None = None
    meter_serial: str | None = None
    suffix: str | None = None
    unit_of_measure: str = "kWh"
    interval_minutes: int = 30
    readings: list[ReadingBulkCreate] = field(default_factory=list)


@dataclass
class NEM12ParseResult:
    """Result of parsing a NEM12 file."""

    meters: list[NEM12MeterData]
    errors: list[str]
    warnings: list[str]
    total_readings: int


class NEM12Parser:
    """Parser for NEM12 format smart meter data files."""

    QUALITY_UNKNOWN = "U"

    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def parse(self, file_content: str | bytes | TextIO | BinaryIO) -> NEM12ParseResult:
        """Parse a NEM12 file and return structured meter data.

        Args:
            file_content: File content as string, bytes, or file-like object

        Returns:
            NEM12ParseResult with parsed meter data
        """
        self.errors = []
        self.warnings = []
        meters: dict[str, NEM12MeterData] = {}  # keyed by NMI+suffix
        interval_dates: dict[str, list[datetime]] = {}
        current_meter_key: str | None = None
        current_interval_length: int = 30
        current_interval_readings: list[ReadingBulkCreate] = []
        total_readings = 0

        # Handle different input types
        if isinstance(file_content, bytes):
            file_content = file_content.decode("utf-8", errors="replace")
        if isinstance(file_content, str):
            file_content = io.StringIO(file_content)

        reader = csv.reader(file_content)

        for line_num, row in enumerate(reader, start=1):
            if not row:
                continue

            record_type = row[0].strip()

            try:
                if record_type == "100":
                    # Header record - validate format
                    self._parse_header(row, line_num)

                elif record_type == "200":
                    # NMI data details - meter info
                    meter_data, key = self._parse_nmi_details(row, line_num)
                    if meter_data:
                        meters[key] = meter_data
                        current_meter_key = key
                        current_interval_length = meter_data.interval_minutes
                        current_interval_readings = []
                        if meter_data.unit_of_measure.casefold() not in {"kwh", "wh"}:
                            self.warnings.append(
                                f"Line {line_num}: Unsupported UOM '{meter_data.unit_of_measure}' "
                                "for kWh analytics; interval values will be omitted"
                            )

                elif record_type == "300":
                    # Interval data - actual readings
                    if current_meter_key and current_meter_key in meters:
                        readings, interval_date = self._parse_interval_data(
                            row,
                            line_num,
                            current_interval_length,
                            meters[current_meter_key].unit_of_measure,
                        )
                        if interval_date is not None:
                            interval_dates.setdefault(current_meter_key, []).append(interval_date)
                        meters[current_meter_key].readings.extend(readings)
                        current_interval_readings = readings
                        total_readings += len(readings)
                    else:
                        self.errors.append(f"Line {line_num}: Interval data without NMI context")

                elif record_type == "400":
                    if current_meter_key and current_meter_key in meters:
                        self._parse_interval_event(
                            row,
                            line_num,
                            current_interval_length,
                            current_interval_readings,
                        )

                elif record_type == "900":
                    # End of data
                    break

            except Exception as e:
                self.errors.append(f"Line {line_num}: Parse error - {str(e)}")

        for key, dates in interval_dates.items():
            days = sorted({interval_date.date() for interval_date in dates})
            missing_days = sum(
                (current - previous).days - 1
                for previous, current in zip(days, days[1:])
            )
            if missing_days:
                meter = meters[key]
                self.warnings.append(
                    f"NMI '{meter.nmi}' RegisterID '{meter.register_id}' has "
                    f"{missing_days} missing daily interval record(s)"
                )

        for meter in meters.values():
            unresolved_quality = sum(
                reading.quality in {"V", self.QUALITY_UNKNOWN}
                for reading in meter.readings
            )
            if unresolved_quality:
                self.warnings.append(
                    f"NMI '{meter.nmi}' RegisterID '{meter.register_id}' has "
                    f"{unresolved_quality} interval(s) with unresolved quality metadata"
                )

        return NEM12ParseResult(
            meters=list(meters.values()),
            errors=self.errors,
            warnings=self.warnings,
            total_readings=total_readings,
        )

    def _parse_header(self, row: list[str], line_num: int) -> None:
        """Parse record 100 (header)."""
        if len(row) < 3:
            self.errors.append(f"Line {line_num}: Invalid header record")
            return

        version = row[1] if len(row) > 1 else ""
        if version not in ("NEM12", "NEM13"):
            self.warnings.append(f"Line {line_num}: Unexpected version {version}")

    def _parse_nmi_details(
        self, row: list[str], line_num: int
    ) -> tuple[NEM12MeterData | None, str]:
        """Parse record 200 (NMI data details).

        Format: 200,NMI,NMIConfiguration,RegisterID,NMISuffix,MDMDataStreamIdentifier,
                MeterSerialNumber,UOM,IntervalLength,...
        """
        if len(row) < 9:
            self.errors.append(f"Line {line_num}: Invalid NMI details record")
            return None, ""

        nmi = row[1].strip()
        register_id = row[3].strip() if len(row) > 3 else ""
        suffix = row[4].strip() if len(row) > 4 else ""
        meter_serial = row[6].strip() if len(row) > 6 else None
        uom = row[7].strip() if len(row) > 7 else "kWh"
        interval_str = row[8].strip() if len(row) > 8 else "30"

        # Validate NMI (should be 10 characters)
        if len(nmi) != 10:
            self.warnings.append(f"Line {line_num}: NMI '{nmi}' is not 10 characters")

        # Parse interval length
        try:
            interval_minutes = int(interval_str)
            if interval_minutes not in (5, 15, 30):
                self.warnings.append(
                    f"Line {line_num}: Unsupported interval length {interval_minutes}, "
                    "defaulting to 30"
                )
                interval_minutes = 30
        except ValueError:
            interval_minutes = 30
            self.warnings.append(f"Line {line_num}: Invalid interval length, defaulting to 30")

        key = f"{nmi}_{register_id}_{suffix}"
        self.warnings.append(
            f"Line {line_num}: Direction is unresolved for RegisterID '{register_id}' "
            f"and NMISuffix '{suffix}'"
        )

        return (
            NEM12MeterData(
                nmi=nmi,
                register_id=register_id or None,
                meter_serial=meter_serial,
                suffix=suffix,
                unit_of_measure=uom,
                interval_minutes=interval_minutes,
            ),
            key,
        )

    def _parse_interval_data(
        self,
        row: list[str],
        line_num: int,
        interval_minutes: int,
        unit_of_measure: str = "kWh",
    ) -> tuple[list[ReadingBulkCreate], datetime | None]:
        """Parse record 300 (interval data).

        Format: 300,IntervalDate,IntervalValue1,IntervalValue2,...,QualityMethod,
                ReasonCode,ReasonDescription,UpdateDateTime,MSATSLoadDateTime
        """
        readings: list[ReadingBulkCreate] = []

        if len(row) < 3:
            self.errors.append(f"Line {line_num}: Invalid interval data record")
            return readings, None

        # Parse date (YYYYMMDD format)
        date_str = row[1].strip()
        try:
            interval_date = datetime.strptime(date_str, "%Y%m%d")
        except ValueError:
            self.errors.append(f"Line {line_num}: Invalid date format '{date_str}'")
            return readings, None
        if unit_of_measure.casefold() not in {"kwh", "wh"}:
            return readings, interval_date

        # Calculate number of intervals per day
        intervals_per_day = 1440 // interval_minutes  # 1440 minutes per day

        # Extract interval values
        # Values start at index 2, quality at the end
        values_end = 2 + intervals_per_day
        expected_quality_index = values_end
        quality_index = None
        if len(row) > expected_quality_index:
            candidate = row[expected_quality_index].strip()
            if candidate and candidate[0] in ("A", "E", "F", "S", "V") and len(candidate) <= 3:
                quality_index = expected_quality_index
        if quality_index is None:
            for index in range(2, min(len(row), expected_quality_index)):
                candidate = row[index].strip()
                if candidate and candidate[0] in ("A", "E", "F", "S", "V") and len(candidate) <= 3:
                    quality_index = index
                    break

        if quality_index is not None and quality_index < expected_quality_index:
            values_end = quality_index
        elif len(row) < values_end:
            values_end = len(row)
        if values_end - 2 != intervals_per_day:
            self.warnings.append(
                f"Line {line_num}: Expected {intervals_per_day} intervals, "
                f"got {values_end - 2}"
            )

        quality_method = None
        reason_code = None
        reason_description = None
        quality = self.QUALITY_UNKNOWN
        if quality_index is not None:
            quality_method = row[quality_index].strip() or None
            reason_code = row[quality_index + 1].strip() or None if len(row) > quality_index + 1 else None
            reason_description = (
                row[quality_index + 2].strip() or None if len(row) > quality_index + 2 else None
            )
            quality = quality_method[0] if quality_method else self.QUALITY_UNKNOWN
        else:
            self.warnings.append(
                f"Line {line_num}: Missing or invalid QualityMethod; quality marked unresolved"
            )

        # Parse each interval value
        for i, value_str in enumerate(row[2:values_end]):
            if not value_str.strip():
                self.warnings.append(
                    f"Line {line_num}: Missing value at interval {i + 1}; interval skipped"
                )
                continue
            try:
                value = float(value_str.strip())
                if unit_of_measure.casefold() == "wh":
                    value /= 1000

                # Preserve the interval end in fixed NEM market time (naive UTC+10).
                # First interval (i=0) ends at 00:30, second at 01:00, etc.
                interval_end = interval_date + timedelta(minutes=(i + 1) * interval_minutes)

                readings.append(
                    ReadingBulkCreate(
                        timestamp=interval_end,
                        interval_minutes=interval_minutes,
                        value=value,
                        quality=quality,
                        register_type="U",
                        direction="unknown",
                        quality_method=quality_method,
                        reason_code=reason_code,
                        reason_description=reason_description,
                    )
                )
            except ValueError:
                self.warnings.append(
                    f"Line {line_num}: Invalid value at interval {i + 1}: '{value_str}'"
                )

        return readings, interval_date

    def _parse_interval_event(
        self,
        row: list[str],
        line_num: int,
        interval_minutes: int,
        readings: list[ReadingBulkCreate],
    ) -> None:
        """Apply a 400-record quality event to its 1-based interval range."""
        if len(row) < 4:
            self.errors.append(f"Line {line_num}: Invalid interval event record")
            return
        try:
            start_interval = int(row[1])
            end_interval = int(row[2])
        except ValueError:
            self.errors.append(f"Line {line_num}: Invalid interval event range")
            return
        quality_method = row[3].strip() or None
        reason_code = row[4].strip() or None if len(row) > 4 else None
        reason_description = row[5].strip() or None if len(row) > 5 else None
        if (
            start_interval < 1
            or end_interval < start_interval
            or end_interval > 1440 // interval_minutes
        ):
            self.errors.append(f"Line {line_num}: Interval event range is out of bounds")
            return

        for reading in readings:
            interval_number = (
                (reading.timestamp.hour * 60 + reading.timestamp.minute) // interval_minutes
                or 1440 // interval_minutes
            )
            if start_interval <= interval_number <= end_interval:
                reading.quality_method = quality_method
                reading.quality = (
                    quality_method[0]
                    if quality_method and quality_method[0] in {"A", "E", "F", "S", "V"}
                    else self.QUALITY_UNKNOWN
                )
                reading.reason_code = reason_code
                reading.reason_description = reason_description

    @staticmethod
    def validate_file(file_content: str | bytes) -> tuple[bool, str]:
        """Quick validation of NEM12 file format.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if isinstance(file_content, bytes):
            file_content = file_content.decode("utf-8", errors="replace")

        lines = file_content.strip().split("\n")

        if not lines:
            return False, "File is empty"

        # Check header
        first_line = lines[0].strip()
        if not first_line.startswith("100,"):
            return False, "File does not start with NEM12 header (100 record)"

        # Check for NEM12 version
        parts = first_line.split(",")
        if len(parts) < 2 or parts[1] not in ("NEM12", "NEM13"):
            return False, "Invalid NEM12 version identifier"

        # Check footer
        last_line = lines[-1].strip()
        if not last_line.startswith("900"):
            return False, "File does not end with NEM12 footer (900 record)"

        return True, ""
