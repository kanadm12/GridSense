"""NEM12 file parser for Australian smart meter data.

NEM12 is a CSV-based format used in Australia's National Electricity Market (NEM).
File structure:
- Record 100: Header (version info)
- Record 200: NMI Data Details (meter info)
- Record 300: Interval Data (quality may be actual, estimated, substituted, or variable)
- Record 400: Interval Event (quality flags)
- Record 500: B2B Details (not used for consumption)
- Record 900: End of data

Reference: AEMO MDFF NEM12/NEM13 v2.7, effective 1 December 2025. Verified
format clauses and remaining procedure blockers are in
backend/docs/stage1/AEMO_NEM12_COMPLIANCE_MATRIX.md.

The parser preserves the interval date/position as a naive nominal interval end
and records NMI configuration and data-stream identifiers. MDFF v2.7 verifies
the nominal position; the source clock basis remains unverified.

Timezone contract
-----------------
The parser preserves record 300's source IntervalDate and 1-based position,
deriving a naive nominal interval-end coordinate. It does not claim that the
coordinate is UTC or has a verified timezone/DST realization. Each reading
stores its source unit/value and an unverified clock-basis marker; consumers
must withhold UTC-dependent metrics until related procedures are confirmed.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import BinaryIO, TextIO

from app.schemas.reading import ReadingBulkCreate


@dataclass
class NEM12MeterData:
    """Parsed meter data from NEM12 file."""

    nmi: str
    nmi_configuration: str | None = None
    register_id: str | None = None
    meter_serial: str | None = None
    suffix: str | None = None
    mdm_data_stream_identifier: str | None = None
    unit_of_measure: str = "kWh"
    interval_minutes: int = 30
    readings: list[ReadingBulkCreate] = field(default_factory=list)


@dataclass(frozen=True)
class IntervalQualityEvent:
    """Parsed 400-record quality range."""

    start_interval: int
    end_interval: int
    quality_method: str
    reason_code: str | None
    reason_description: str | None
    line_num: int


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
    SOURCE_TIME_BASIS_UNVERIFIED = "unverified_nem12_clock_basis"

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
        meters: dict[tuple[str, ...], NEM12MeterData] = {}
        interval_dates: dict[tuple[str, ...], list[datetime]] = {}
        current_meter_key: tuple[str, ...] | None = None
        current_nmi_configuration: str | None = None
        current_unit_of_measure = "kWh"
        current_interval_length: int = 30
        current_interval_readings: list[ReadingBulkCreate] = []
        current_interval_events: list[IntervalQualityEvent] = []
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
            if current_interval_readings and record_type != "400":
                self._apply_interval_events(
                    current_interval_readings,
                    current_interval_events,
                    current_interval_length,
                )
                current_interval_readings = []
                current_interval_events = []

            try:
                if record_type == "100":
                    # Header record - validate format
                    self._parse_header(row, line_num)

                elif record_type == "200":
                    # NMI data details - meter info
                    current_meter_key = None
                    meter_data, key = self._parse_nmi_details(row, line_num)
                    if meter_data:
                        meters.setdefault(key, meter_data)
                        current_meter_key = key
                        current_nmi_configuration = meter_data.nmi_configuration
                        current_unit_of_measure = meter_data.unit_of_measure
                        current_interval_length = meter_data.interval_minutes
                        if current_unit_of_measure.casefold() not in {"kwh", "wh"}:
                            self.warnings.append(
                                f"Line {line_num}: Unsupported UOM "
                                f"'{current_unit_of_measure}' for kWh analytics; "
                                "interval values will be retained but ineligible"
                            )

                elif record_type == "300":
                    # Interval data - actual readings
                    if current_meter_key and current_meter_key in meters:
                        readings, interval_date = self._parse_interval_data(
                            row,
                            line_num,
                            current_interval_length,
                            current_unit_of_measure,
                            current_nmi_configuration,
                        )
                        if interval_date is not None:
                            interval_dates.setdefault(current_meter_key, []).append(interval_date)
                        meters[current_meter_key].readings.extend(readings)
                        current_interval_readings = readings
                        current_interval_events = []
                        total_readings += len(readings)
                    else:
                        self.errors.append(f"Line {line_num}: Interval data without NMI context")

                elif record_type == "400":
                    if current_meter_key and current_meter_key in meters:
                        event = self._parse_interval_event(
                            row,
                            line_num,
                            current_interval_length,
                        )
                        if event is not None:
                            current_interval_events.append(event)
                    else:
                        self.errors.append(
                            f"Line {line_num}: Interval event without a preceding interval record"
                        )

                elif record_type == "900":
                    if current_interval_readings:
                        self._apply_interval_events(
                            current_interval_readings,
                            current_interval_events,
                            current_interval_length,
                        )
                        current_interval_readings = []
                    # End of data
                    break

            except Exception as e:
                self.errors.append(f"Line {line_num}: Parse error - {str(e)}")

        if current_interval_readings:
            self._apply_interval_events(
                current_interval_readings,
                current_interval_events,
                current_interval_length,
            )

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
    ) -> tuple[NEM12MeterData | None, tuple[str, ...]]:
        """Parse record 200 (NMI data details).

        Format: 200,NMI,NMIConfiguration,RegisterID,NMISuffix,MDMDataStreamIdentifier,
                MeterSerialNumber,UOM,IntervalLength,...
        """
        if len(row) < 9:
            self.errors.append(f"Line {line_num}: Invalid NMI details record")
            return None, ""

        nmi = row[1].strip()
        nmi_configuration = row[2].strip() if len(row) > 2 else ""
        register_id = row[3].strip() if len(row) > 3 else ""
        suffix = row[4].strip() if len(row) > 4 else ""
        mdm_data_stream_identifier = row[5].strip() if len(row) > 5 else ""
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
                self.errors.append(
                    f"Line {line_num}: Unsupported interval length {interval_minutes}; "
                    "record not parsed"
                )
                return None, ()
        except ValueError:
            self.errors.append(
                f"Line {line_num}: Missing or invalid interval length; record not parsed"
            )
            return None, ()

        key = (
            nmi,
            register_id,
            suffix,
            mdm_data_stream_identifier,
        )
        self.warnings.append(
            f"Line {line_num}: Direction is unresolved for NMIConfiguration "
            f"'{nmi_configuration}', RegisterID '{register_id}', NMISuffix '{suffix}', "
            f"and MDMDataStreamIdentifier '{mdm_data_stream_identifier}'"
        )

        return (
            NEM12MeterData(
                nmi=nmi,
                nmi_configuration=nmi_configuration or None,
                register_id=register_id or None,
                meter_serial=meter_serial,
                suffix=suffix,
                mdm_data_stream_identifier=mdm_data_stream_identifier or None,
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
        nmi_configuration: str | None = None,
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
            reason_code = (
                row[quality_index + 1].strip() or None
                if len(row) > quality_index + 1
                else None
            )
            reason_description = (
                row[quality_index + 2].strip() or None if len(row) > quality_index + 2 else None
            )
            quality = (
                quality_method[0]
                if quality_method and quality_method[0] != "V"
                else self.QUALITY_UNKNOWN
            )
            if quality_method == "V" and (reason_code or reason_description):
                self.warnings.append(
                    f"Line {line_num}: Variable 300 QualityMethod must not include "
                    "a reason code or description"
                )
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
                source_value = float(value_str.strip())
                value = (
                    source_value / 1000
                    if unit_of_measure.casefold() == "wh"
                    else source_value
                )

                # MDFF v2.7 defines nominal interval-end positions relative to
                # IntervalDate; the source clock basis remains unverified.
                interval_end = interval_date + timedelta(minutes=(i + 1) * interval_minutes)

                readings.append(
                    ReadingBulkCreate(
                        timestamp=interval_end,
                        source_interval_date=interval_date.date(),
                        source_interval_number=i + 1,
                        interval_minutes=interval_minutes,
                        value=value,
                        source_value=source_value,
                        source_unit=unit_of_measure,
                        provenance_kind="measured",
                        source_time_basis=self.SOURCE_TIME_BASIS_UNVERIFIED,
                        source_nmi_configuration=nmi_configuration,
                        source_record_quality_method=quality_method,
                        quality=quality,
                        register_type="U",
                        direction="unknown",
                        quality_method=None if quality_method == "V" else quality_method,
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
    ) -> IntervalQualityEvent | None:
        """Parse one 400-record range without applying unverified partial data."""
        if len(row) < 4:
            self.errors.append(f"Line {line_num}: Invalid interval event record")
            return None
        try:
            start_interval = int(row[1])
            end_interval = int(row[2])
        except ValueError:
            self.errors.append(f"Line {line_num}: Invalid interval event range")
            return None
        quality_method = row[3].strip() or None
        reason_code = row[4].strip() or None if len(row) > 4 else None
        reason_description = row[5].strip() or None if len(row) > 5 else None
        if (
            start_interval < 1
            or end_interval < start_interval
            or end_interval > 1440 // interval_minutes
        ):
            self.errors.append(f"Line {line_num}: Interval event range is out of bounds")
            return None
        if not quality_method:
            self.errors.append(f"Line {line_num}: Missing interval-event QualityMethod")
            return None

        return IntervalQualityEvent(
            start_interval=start_interval,
            end_interval=end_interval,
            quality_method=quality_method,
            reason_code=reason_code,
            reason_description=reason_description,
            line_num=line_num,
        )

    def _apply_interval_events(
        self,
        readings: list[ReadingBulkCreate],
        events: list[IntervalQualityEvent],
        interval_minutes: int,
    ) -> None:
        """Apply 400 ranges only when they form a valid full-day partition."""
        expected_count = 1440 // interval_minutes
        summary_method = readings[0].source_record_quality_method if readings else None
        summary_is_variable = summary_method == "V"
        summary_reason_code = readings[0].reason_code if readings else None
        summary_reason_description = readings[0].reason_description if readings else None

        if summary_method is None or not self._quality_method_is_valid(
            summary_method, allow_variable=True
        ):
            self._mark_interval_quality_unresolved(readings)
            return
        if not self._reason_fields_are_valid(
            summary_method, summary_reason_code, summary_reason_description
        ):
            self.warnings.append("Record 300 contains invalid reason fields")
            self._mark_interval_quality_unresolved(readings)
            return

        if not events:
            if summary_is_variable:
                self.warnings.append(
                    "Record 300 uses variable QualityMethod V without required 400 records"
                )
                self._mark_interval_quality_unresolved(readings)
            return

        next_expected_interval = 1
        valid = True
        for event in events:
            if event.start_interval != next_expected_interval:
                valid = False
                self.errors.append(
                    f"Line {event.line_num}: 400 ranges must be ascending, contiguous, "
                    "and non-overlapping"
                )
            if not self._quality_method_is_valid(event.quality_method):
                valid = False
                self.errors.append(
                    f"Line {event.line_num}: Invalid interval-event QualityMethod"
                )
            if not self._reason_fields_are_valid(
                event.quality_method,
                event.reason_code,
                event.reason_description,
            ):
                valid = False
                self.errors.append(
                    f"Line {event.line_num}: Invalid reason fields for interval-event "
                    "QualityMethod"
                )
            next_expected_interval = event.end_interval + 1

        if next_expected_interval != expected_count + 1:
            valid = False
            self.errors.append(
                "400 ranges must cover every interval in the associated 300 record"
            )

        if not valid:
            self._mark_interval_quality_unresolved(readings)
            return

        if summary_is_variable:
            for event in events:
                for reading in readings:
                    interval_number = reading.source_interval_number
                    if (
                        interval_number is not None
                        and event.start_interval <= interval_number <= event.end_interval
                    ):
                        reading.quality = event.quality_method[0]
                        reading.quality_method = event.quality_method
                        reading.reason_code = event.reason_code
                        reading.reason_description = event.reason_description
            return

        self.warnings.append(
            "400 ranges accompany a non-variable 300 QualityMethod; interval qualities "
            "were retained as unresolved"
        )
        self._mark_interval_quality_unresolved(readings)

    def _quality_method_is_valid(
        self, quality_method: str, *, allow_variable: bool = False
    ) -> bool:
        """Validate the MDFF QMM field shape, not the referenced Part B method."""
        if not re.fullmatch(r"[AEFSV](?:\d{2})?", quality_method):
            return False
        quality = quality_method[0]
        has_method = len(quality_method) == 3
        if quality in {"A", "V"} and has_method:
            return False
        if quality in {"F", "S"} and not has_method:
            return False
        if quality == "V" and not allow_variable:
            return False
        return True

    @staticmethod
    def _reason_fields_are_valid(
        quality_method: str,
        reason_code: str | None,
        reason_description: str | None,
    ) -> bool:
        quality = quality_method[0]
        if reason_code is not None and not re.fullmatch(r"\d{1,3}", reason_code):
            return False
        if reason_description is not None and reason_code is None:
            return False
        if quality == "F" and (
            reason_code is not None or reason_description is not None
        ):
            return False
        if quality == "S" and reason_code is None:
            return False
        if reason_code is not None and int(reason_code) == 0 and not reason_description:
            return False
        if quality == "V" and (reason_code is not None or reason_description is not None):
            return False
        return True

    @staticmethod
    def _mark_interval_quality_unresolved(
        readings: list[ReadingBulkCreate],
    ) -> None:
        for reading in readings:
            reading.quality = NEM12Parser.QUALITY_UNKNOWN
            reading.quality_method = None
            reading.reason_code = None
            reading.reason_description = None

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
