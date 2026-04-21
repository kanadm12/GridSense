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
    meter_serial: str | None = None
    suffix: str | None = None  # E1=Export, B1=Import, etc.
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

    # Quality flags
    QUALITY_ACTUAL = "A"
    QUALITY_ESTIMATED = "E"
    QUALITY_SUBSTITUTED = "S"

    # Register suffixes
    SUFFIX_IMPORT = "B"  # Consumption (buying from grid)
    SUFFIX_EXPORT = "E"  # Generation (selling to grid)

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
        current_meter_key: str | None = None
        current_interval_date: datetime | None = None
        current_interval_length: int = 30
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

                elif record_type == "300":
                    # Interval data - actual readings
                    if current_meter_key and current_meter_key in meters:
                        readings, interval_date = self._parse_interval_data(
                            row, line_num, current_interval_length
                        )
                        meters[current_meter_key].readings.extend(readings)
                        current_interval_date = interval_date
                        total_readings += len(readings)
                    else:
                        self.errors.append(f"Line {line_num}: Interval data without NMI context")

                elif record_type == "400":
                    # Interval event - quality flags (optional processing)
                    pass  # Quality already handled in 300 record

                elif record_type == "900":
                    # End of data
                    break

            except Exception as e:
                self.errors.append(f"Line {line_num}: Parse error - {str(e)}")

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
        suffix = row[4].strip() if len(row) > 4 else "E1"
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
                    f"Line {line_num}: Unusual interval length {interval_minutes}"
                )
        except ValueError:
            interval_minutes = 30
            self.warnings.append(f"Line {line_num}: Invalid interval length, defaulting to 30")

        key = f"{nmi}_{suffix}"

        return (
            NEM12MeterData(
                nmi=nmi,
                meter_serial=meter_serial,
                suffix=suffix,
                unit_of_measure=uom,
                interval_minutes=interval_minutes,
            ),
            key,
        )

    def _parse_interval_data(
        self, row: list[str], line_num: int, interval_minutes: int
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

        # Calculate number of intervals per day
        intervals_per_day = 1440 // interval_minutes  # 1440 minutes per day

        # Extract interval values
        # Values start at index 2, quality at the end
        values_end = 2 + intervals_per_day
        if len(row) < values_end:
            self.warnings.append(
                f"Line {line_num}: Expected {intervals_per_day} intervals, got {len(row) - 2}"
            )
            values_end = len(row)

        # Get quality flag (typically after the values)
        quality = self.QUALITY_ACTUAL
        if len(row) > values_end:
            quality_str = row[values_end].strip()
            if quality_str and quality_str[0] in ("A", "E", "S", "F", "N"):
                quality = quality_str[0]

        # Determine register type from suffix context (will be set by caller if needed)
        register_type = "B"  # Default to import/consumption

        # Parse each interval value
        for i, value_str in enumerate(row[2:values_end]):
            try:
                value = float(value_str.strip()) if value_str.strip() else 0.0

                # Calculate timestamp for this interval (end of interval)
                # First interval (i=0) ends at 00:30, second at 01:00, etc.
                interval_end = interval_date + timedelta(minutes=(i + 1) * interval_minutes)

                readings.append(
                    ReadingBulkCreate(
                        timestamp=interval_end,
                        value=value,
                        quality=quality,
                        register_type=register_type,
                    )
                )
            except ValueError:
                self.warnings.append(
                    f"Line {line_num}: Invalid value at interval {i + 1}: '{value_str}'"
                )

        return readings, interval_date

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
