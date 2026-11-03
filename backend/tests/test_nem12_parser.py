"""Tests for NEM12 parser."""

import csv
import io
import json
from datetime import date
from pathlib import Path

import pytest

from app.services.interval_quality import expected_interval_ends_utc, interval_bounds_utc
from app.services.nem12_parser import NEM12Parser

FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "metering"
    / "aemo_mdff_v2_7_interval_records.json"
)


class TestNEM12Parser:
    """Test cases for NEM12Parser."""

    def test_parse_valid_file(self):
        """Test parsing a valid NEM12 file."""
        # Load sample file
        sample_path = Path(__file__).parent / "sample_nem12.csv"
        with open(sample_path) as f:
            content = f.read()

        parser = NEM12Parser()
        result = parser.parse(content)

        # Should have one meter
        assert len(result.meters) == 1
        assert result.meters[0].nmi == "VAAA123456"
        assert result.meters[0].suffix == "E1"
        assert result.meters[0].interval_minutes == 30

        # Should have readings (7 days * 48 intervals)
        assert result.total_readings == 7 * 48 == len(result.meters[0].readings)

        # Should have no errors
        assert len(result.errors) == 0

    def test_validate_valid_file(self):
        """Test validation of valid NEM12 file."""
        content = """100,NEM12,202504011200,TEST,AEMO
200,1234567890,E1,E1,E1,N1,12345678,kWh,30,
300,20250401,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0,1.1,1.2,1.3,1.4,1.5,1.6,1.7,1.8,1.9,2.0,2.1,2.2,2.3,2.4,2.5,2.6,2.7,2.8,2.9,3.0,3.1,3.2,3.3,3.4,3.5,3.6,3.7,3.8,3.9,4.0,4.1,4.2,4.3,4.4,4.5,4.6,4.7,4.8,A,,,
900"""

        is_valid, error = NEM12Parser.validate_file(content)
        assert is_valid is True
        assert error == ""

    def test_validate_missing_header(self):
        """Test validation fails without header."""
        content = """200,1234567890,E1,E1,E1,N1,12345678,kWh,30,
900"""

        is_valid, error = NEM12Parser.validate_file(content)
        assert is_valid is False
        assert "header" in error.lower()

    def test_validate_missing_footer(self):
        """Test validation fails without footer."""
        content = """100,NEM12,202504011200,TEST,AEMO
200,1234567890,E1,E1,E1,N1,12345678,kWh,30,"""

        is_valid, error = NEM12Parser.validate_file(content)
        assert is_valid is False
        assert "footer" in error.lower()

    def test_parse_interval_values(self):
        """Test that interval values are correctly parsed."""
        content = """100,NEM12,202504011200,TEST,AEMO
200,1234567890,E1,E1,E1,N1,12345678,kWh,30,
300,20250401,1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0,10.0,11.0,12.0,13.0,14.0,15.0,16.0,17.0,18.0,19.0,20.0,21.0,22.0,23.0,24.0,25.0,26.0,27.0,28.0,29.0,30.0,31.0,32.0,33.0,34.0,35.0,36.0,37.0,38.0,39.0,40.0,41.0,42.0,43.0,44.0,45.0,46.0,47.0,48.0,A,,,
900"""

        parser = NEM12Parser()
        result = parser.parse(content)

        readings = result.meters[0].readings
        assert len(readings) == 48

        # Check first and last values
        assert readings[0].value == 1.0
        assert readings[47].value == 48.0

        # Check timestamps (30-min intervals starting at 00:30)
        assert readings[0].timestamp.hour == 0
        assert readings[0].timestamp.minute == 30
        assert readings[47].timestamp.hour == 0
        assert readings[47].timestamp.minute == 0  # Next day 00:00

    def test_parse_quality_flags(self):
        """Test quality flags are correctly parsed."""
        content = """100,NEM12,202504011200,TEST,AEMO
200,1234567890,E1,E1,E1,N1,12345678,kWh,30,
300,20250401,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,E,,,
900"""

        parser = NEM12Parser()
        result = parser.parse(content)

        # All readings should have estimated quality
        for reading in result.meters[0].readings:
            assert reading.quality == "E"

    def test_multiple_registers_and_interval_quality_events(self):
        values = ["1.0"] * 48
        values[0] = ""
        interval_values = ",".join(values)
        content = (
            "100,NEM12,202504011200,TEST,AEMO\n"
            "200,1234567890,E1,1,E1,N1,SERIAL1,kWh,30,\n"
            f"300,20250401,{interval_values},V,,,\n"
            "400,1,24,A,,\n"
            "400,25,48,S53,9,Substituted interval\n"
            "200,1234567890,E1,2,B1,N2,SERIAL2,kWh,30,\n"
            f"300,20250401,{','.join(['2.0'] * 48)},A,,,\n"
            "900\n"
        )

        result = NEM12Parser().parse(content)

        assert not result.errors
        assert len(result.meters) == 2
        first_register, second_register = result.meters
        assert first_register.register_id == "1"
        assert second_register.register_id == "2"
        assert len(first_register.readings) == 47
        assert first_register.readings[0].timestamp.hour == 1
        assert first_register.readings[0].quality == "A"
        assert first_register.readings[24].quality_method == "S53"
        assert first_register.readings[24].reason_code == "9"
        assert first_register.readings[24].reason_description == "Substituted interval"
        assert first_register.readings[-1].quality == "S"
        assert second_register.readings[0].value == 2.0
        assert all(
            reading.direction == "unknown"
            for meter in result.meters
            for reading in meter.readings
        )
        assert all(
            reading.register_type == "U"
            for meter in result.meters
            for reading in meter.readings
        )
        assert any("Direction is unresolved" in warning for warning in result.warnings)

    def test_short_interval_record_and_invalid_value_are_reported(self):
        content = """100,NEM12,202504011200,TEST,AEMO
200,1234567890,E1,1,E1,N1,SERIAL1,kWh,30,
300,20250401,1.0,,not-a-number
900"""

        result = NEM12Parser().parse(content)

        assert len(result.meters[0].readings) == 1
        assert result.meters[0].readings[0].value == 1.0
        assert any("Expected 48 intervals" in warning for warning in result.warnings)
        assert any("Missing value at interval 2" in warning for warning in result.warnings)
        assert any("Invalid value at interval 3" in warning for warning in result.warnings)
        assert result.meters[0].readings[0].quality == "U"

    def test_shortened_interval_record_keeps_trailing_quality_metadata(self):
        values = ",".join(["0.5"] * 47)
        content = (
            "100,NEM12,202504011200,TEST,AEMO\n"
            "200,1234567890,E1,1,E1,N1,SERIAL1,kWh,30,\n"
            f"300,20250401,{values},E52,9,Estimated replacement,,\n"
            "900\n"
        )

        result = NEM12Parser().parse(content)

        assert len(result.meters[0].readings) == 47
        assert result.meters[0].readings[-1].quality_method == "E52"
        assert result.meters[0].readings[-1].reason_code == "9"
        assert any("Expected 48 intervals, got 47" in warning for warning in result.warnings)

    def test_missing_daily_record_is_reported_as_coverage_gap(self):
        values = ",".join(["0.5"] * 48)
        content = (
            "100,NEM12,202504011200,TEST,AEMO\n"
            "200,1234567890,E1,1,E1,N1,SERIAL1,kWh,30,\n"
            f"300,20250401,{values},A,,,\n"
            f"300,20250403,{values},A,,,\n"
            "900\n"
        )

        result = NEM12Parser().parse(content)

        assert any("1 missing daily interval record" in warning for warning in result.warnings)

    def test_wh_values_are_converted_and_unsupported_units_are_preserved_for_audit(self):
        values = ",".join(["1000"] * 48)
        content = (
            "100,NEM12,202504011200,TEST,AEMO\n"
            "200,1234567890,E1,1,E1,N1,SERIAL1,Wh,30,\n"
            f"300,20250401,{values},A,,,\n"
            "200,1234567890,E1,2,E2,N2,SERIAL2,kW,30,\n"
            f"300,20250401,{values},A,,,\n"
            "900\n"
        )

        result = NEM12Parser().parse(content)

        assert result.meters[0].readings[0].value == 1.0
        assert len(result.meters[1].readings) == 48
        assert result.meters[1].readings[0].source_unit == "kW"
        assert result.meters[1].readings[0].source_value == 1000.0
        assert result.meters[1].readings[0].value == 1000.0
        assert any("Unsupported UOM 'kW'" in warning for warning in result.warnings)

    def test_aemo_mdff_v27_fixture_preserves_channels_and_resolves_400_quality_per_interval(self):
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(["100", "NEM12", "202512021200", "TEST-FIXTURE", "AEMO"])
        for channel in fixture["channels"]:
            writer.writerow(
                [
                    "200",
                    channel["nmi"],
                    channel["nmi_configuration"],
                    channel["register_id"],
                    channel["nmi_suffix"],
                    channel["mdm_data_stream_identifier"],
                    channel["meter_serial"],
                    channel["unit_of_measure"],
                    fixture["interval_minutes"],
                    "",
                ]
            )
            writer.writerow(
                [
                    "300",
                    fixture["interval_date"],
                    *([channel["value_text"]] * 48),
                    channel["record_300_quality_method"],
                    channel["record_300_reason_code"],
                    "",
                    "",
                    "",
                ]
            )
            for event in channel["record_400"]:
                writer.writerow(
                    [
                        "400",
                        event["start_interval"],
                        event["end_interval"],
                        event["quality_method"],
                        event["reason_code"],
                        event["reason_description"],
                    ]
                )
        writer.writerow(["900"])

        result = NEM12Parser().parse(output.getvalue())

        assert not result.errors
        assert len(result.meters) == 2
        first_channel, second_channel = result.meters
        assert first_channel.mdm_data_stream_identifier == "N1"
        assert second_channel.mdm_data_stream_identifier == "N2"
        assert first_channel.suffix == "E1"
        assert second_channel.suffix == "B1"
        assert [reading.quality for reading in first_channel.readings].count("A") == 24
        assert [reading.quality for reading in first_channel.readings].count("S") == 12
        assert [reading.quality for reading in first_channel.readings].count("E") == 12
        assert first_channel.readings[24].quality_method == "S53"
        assert first_channel.readings[24].reason_code == "9"
        assert first_channel.readings[24].source_record_quality_method == "V"
        assert first_channel.readings[0].source_interval_date == date(2025, 12, 1)
        assert first_channel.readings[0].source_interval_number == 1
        assert first_channel.readings[0].source_nmi_configuration == "E1B1"
        assert first_channel.readings[0].source_time_basis == "unverified_nem12_clock_basis"
        assert first_channel.readings[0].timestamp.isoformat() == "2025-12-01T00:30:00"
        assert first_channel.readings[-1].timestamp.isoformat() == "2025-12-02T00:00:00"
        assert first_channel.readings[0].source_value == 1000.0
        assert first_channel.readings[0].value == 1.0
        assert all(
            reading.direction == "unknown"
            for meter in result.meters
            for reading in meter.readings
        )

    @pytest.mark.parametrize(
        ("interval_date", "expected_local_slots"),
        [("20250406", 50), ("20251005", 46)],
    )
    def test_mdff_daily_count_does_not_imply_melbourne_dst_utc_mapping(
        self, interval_date, expected_local_slots
    ):
        values = ",".join(["0.5"] * 48)
        content = (
            "100,NEM12,202511011200,TEST,AEMO\n"
            "200,1234567890,E1,B1,E1,N1,SERIAL,kWh,30,\n"
            f"300,{interval_date},{values},A,,,\n"
            "900\n"
        )

        result = NEM12Parser().parse(content)
        readings = result.meters[0].readings
        local_day = date.fromisoformat(
            f"{interval_date[:4]}-{interval_date[4:6]}-{interval_date[6:]}"
        )
        expected_ends = expected_interval_ends_utc(local_day, "VIC", 30)

        assert len(readings) == 48
        assert len(expected_ends) == expected_local_slots
        assert interval_bounds_utc(
            readings[0].timestamp, 30, readings[0].source_time_basis
        ) is None

    @pytest.mark.parametrize(
        ("quality_method", "reason_code", "expected_quality"),
        [
            ("A", "", "A"),
            ("E52", "", "E"),
            ("F53", "", "F"),
            ("S53", "9", "S"),
        ],
    )
    def test_mdff_uniform_300_quality_methods(
        self, quality_method, reason_code, expected_quality
    ):
        values = ",".join(["0.5"] * 48)
        content = (
            "100,NEM12,202512021200,TEST,AEMO\n"
            "200,1234567890,E1,B1,E1,N1,SERIAL,kWh,30,\n"
            f"300,20251201,{values},{quality_method},{reason_code},"
            f"{'Test reason' if reason_code else ''}\n"
            "900\n"
        )

        result = NEM12Parser().parse(content)

        assert not result.errors
        assert {reading.quality for reading in result.meters[0].readings} == {
            expected_quality
        }

    def test_variable_300_with_incomplete_400_ranges_is_unresolved(self):
        values = ",".join(["0.5"] * 48)
        content = (
            "100,NEM12,202512021200,TEST,AEMO\n"
            "200,1234567890,E1,B1,E1,N1,SERIAL,kWh,30,\n"
            f"300,20251201,{values},V,,,\n"
            "400,1,24,A,,\n"
            "400,26,48,S53,9,Substituted interval\n"
            "900\n"
        )

        result = NEM12Parser().parse(content)

        assert any(reading.quality == "U" for reading in result.meters[0].readings)
        assert all(reading.quality_method is None for reading in result.meters[0].readings)
        assert any("contiguous" in error for error in result.errors)

    def test_variable_300_without_400_events_is_unresolved(self):
        values = ",".join(["0.5"] * 48)
        content = (
            "100,NEM12,202512021200,TEST,AEMO\n"
            "200,1234567890,E1,B1,E1,N1,SERIAL,kWh,30,\n"
            f"300,20251201,{values},V,,,\n"
            "900\n"
        )

        result = NEM12Parser().parse(content)

        assert {reading.quality for reading in result.meters[0].readings} == {"U"}
        assert any("without required 400 records" in warning for warning in result.warnings)

    @pytest.mark.parametrize(
        "event_rows",
        [
            ["400,1,25,A,,", "400,25,48,S53,9,Substituted interval"],
            ["400,25,48,S53,9,Substituted interval", "400,1,24,A,,"],
            ["400,1,48,V,,"],
        ],
    )
    def test_overlapping_out_of_order_or_variable_400_ranges_are_unresolved(
        self, event_rows
    ):
        values = ",".join(["0.5"] * 48)
        content = "\n".join(
            [
                "100,NEM12,202512021200,TEST,AEMO",
                "200,1234567890,E1,B1,E1,N1,SERIAL,kWh,30,",
                f"300,20251201,{values},V,,,",
                *event_rows,
                "900",
            ]
        )

        result = NEM12Parser().parse(content)

        assert {reading.quality for reading in result.meters[0].readings} == {"U"}
        assert all(reading.quality_method is None for reading in result.meters[0].readings)
        assert result.errors

    def test_invalid_interval_length_is_not_silently_defaulted(self):
        content = """100,NEM12,202512021200,TEST,AEMO
200,1234567890,E1,1,E1,N1,SERIAL,kWh,10,
300,20251201,1.0,A,,,
900"""

        result = NEM12Parser().parse(content)

        assert result.meters == []
        assert result.total_readings == 0
        assert any("Unsupported interval length 10" in error for error in result.errors)

    @pytest.mark.parametrize("interval_minutes", [5, 15, 30])
    def test_interval_count_matches_declared_length(self, interval_minutes):
        interval_count = 1440 // interval_minutes
        values = ",".join(["0.25"] * interval_count)
        content = (
            "100,NEM12,202504011200,TEST,AEMO\n"
            f"200,1234567890,E1,1,E1,N1,SERIAL1,kWh,{interval_minutes},\n"
            f"300,20250401,{values},A,,,\n"
            "900\n"
        )

        result = NEM12Parser().parse(content)

        readings = result.meters[0].readings
        assert len(readings) == interval_count
        assert sum(reading.value for reading in readings) == pytest.approx(interval_count * 0.25)
        assert readings[-1].timestamp.date().isoformat() == "2025-04-02"
        assert readings[-1].timestamp.time().isoformat() == "00:00:00"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
