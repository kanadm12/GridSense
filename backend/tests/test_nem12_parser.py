"""Tests for NEM12 parser."""

import pytest
from pathlib import Path

from app.services.nem12_parser import NEM12Parser


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
