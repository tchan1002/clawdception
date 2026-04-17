"""
Tests for pure utility functions in utils.py.
No hardware, no Flask server, no API calls required.

Run with:
    cd ~/clawdception && python3 -m pytest tests/ -v
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import compute_stats, is_reading_stale, parse_json_response, NOTABLE_EVENT_TYPES


# ---------------------------------------------------------------------------
# compute_stats
# ---------------------------------------------------------------------------

class TestComputeStats:
    # Readings are expected newest-first (matches API response order)
    READINGS = [
        {"temp_f": 75.0, "ph": 7.0},
        {"temp_f": 76.0, "ph": 6.8},
        {"temp_f": 74.0, "ph": 7.2},
    ]

    def test_min_max_mean(self):
        stats = compute_stats(self.READINGS, "temp_f")
        assert stats["min"] == 74.0
        assert stats["max"] == 76.0
        assert stats["mean"] == 75.0

    def test_first_is_oldest_last_is_newest(self):
        # list is newest-first, so index 0 = most recent = "last"
        stats = compute_stats(self.READINGS, "temp_f")
        assert stats["last"] == 75.0   # index 0 — most recent
        assert stats["first"] == 74.0  # index -1 — oldest

    def test_count(self):
        assert compute_stats(self.READINGS, "temp_f")["count"] == 3

    def test_missing_field_skipped(self):
        readings = [{"temp_f": 75.0}, {"ph": 7.0}, {"temp_f": 76.0}]
        stats = compute_stats(readings, "temp_f")
        assert stats["count"] == 2

    def test_none_value_skipped(self):
        readings = [{"temp_f": 75.0}, {"temp_f": None}, {"temp_f": 74.0}]
        stats = compute_stats(readings, "temp_f")
        assert stats["count"] == 2

    def test_empty_list_returns_none(self):
        assert compute_stats([], "temp_f") is None

    def test_no_matching_field_returns_none(self):
        assert compute_stats([{"ph": 7.0}], "temp_f") is None

    def test_single_reading(self):
        stats = compute_stats([{"ph": 7.0}], "ph")
        assert stats["min"] == stats["max"] == stats["mean"] == stats["first"] == stats["last"] == 7.0
        assert stats["count"] == 1

    def test_rounding(self):
        readings = [{"ph": 7.123456}]
        stats = compute_stats(readings, "ph")
        assert stats["mean"] == 7.123  # rounds to 3 decimal places


# ---------------------------------------------------------------------------
# parse_json_response
# ---------------------------------------------------------------------------

class TestParseJsonResponse:
    def test_plain_json(self):
        result = parse_json_response('{"risk_level": "green"}')
        assert result["risk_level"] == "green"

    def test_markdown_json_fence(self):
        text = '```json\n{"risk_level": "green"}\n```'
        result = parse_json_response(text)
        assert result["risk_level"] == "green"

    def test_plain_code_fence(self):
        text = '```\n{"risk_level": "yellow"}\n```'
        result = parse_json_response(text)
        assert result["risk_level"] == "yellow"

    def test_leading_trailing_whitespace(self):
        result = parse_json_response('  {"key": "value"}  ')
        assert result["key"] == "value"

    def test_nested_object(self):
        payload = '{"parameter_status": {"temperature": {"value": 75.0, "status": "green"}}}'
        result = parse_json_response(payload)
        assert result["parameter_status"]["temperature"]["value"] == 75.0

    def test_array_value(self):
        result = parse_json_response('{"actions": ["check pH", "monitor temp"]}')
        assert len(result["actions"]) == 2

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            parse_json_response("not valid json")

    def test_empty_fence_raises(self):
        with pytest.raises(json.JSONDecodeError):
            parse_json_response("```json\n```")


# ---------------------------------------------------------------------------
# is_reading_stale
# ---------------------------------------------------------------------------

class TestIsReadingStale:
    def test_none_is_stale(self):
        assert is_reading_stale(None) is True

    def test_missing_timestamp_is_stale(self):
        assert is_reading_stale({"temp_f": 75.0}) is True

    def test_null_timestamp_is_stale(self):
        assert is_reading_stale({"timestamp": None}) is True

    def test_fresh_reading_not_stale(self):
        ts = datetime.now().isoformat()
        assert is_reading_stale({"timestamp": ts}) is False

    def test_old_reading_is_stale(self):
        ts = (datetime.now() - timedelta(hours=2)).isoformat()
        assert is_reading_stale({"timestamp": ts}) is True

    def test_just_under_threshold_not_stale(self):
        # 29 minutes old — threshold is 30
        ts = (datetime.now() - timedelta(minutes=29)).isoformat()
        assert is_reading_stale({"timestamp": ts}) is False

    def test_just_over_threshold_is_stale(self):
        ts = (datetime.now() - timedelta(minutes=31)).isoformat()
        assert is_reading_stale({"timestamp": ts}) is True

    def test_invalid_timestamp_is_stale(self):
        assert is_reading_stale({"timestamp": "not-a-date"}) is True

    def test_extra_fields_ignored(self):
        ts = datetime.now().isoformat()
        reading = {"timestamp": ts, "temp_f": 75.0, "ph": 7.0, "tds_ppm": 200}
        assert is_reading_stale(reading) is False


# ---------------------------------------------------------------------------
# NOTABLE_EVENT_TYPES — correction membership
# ---------------------------------------------------------------------------

class TestNotableEventTypes:
    def test_correction_in_notable(self):
        assert "correction" in NOTABLE_EVENT_TYPES

    def test_core_types_present(self):
        for t in ("water_change", "water_test", "owner_photo", "maintenance"):
            assert t in NOTABLE_EVENT_TYPES
