"""
Tests for shrimp_journal — no Claude API, no Telegram, no DB calls.

Run with:
    cd ~/clawdception && python3 -m pytest tests/test_shrimp_journal.py -v
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# _as_list (regression: API returns string instead of array)
# ---------------------------------------------------------------------------

# Extract the function by running the module-level scope trick — since _as_list
# is nested inside run(), we replicate it here to test the same logic.
# The real test is the integration test below, which drives run() end-to-end.

def _as_list_impl(val):
    """Exact copy of _as_list from shrimp_journal/run.py."""
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val.strip()) or []
        except json.JSONDecodeError:
            return []
    return val or []


class TestAsListRobustness:
    def test_list_passthrough(self):
        assert _as_list_impl(["a", "b"]) == ["a", "b"]

    def test_empty_list(self):
        assert _as_list_impl([]) == []

    def test_none(self):
        assert _as_list_impl(None) == []

    def test_empty_string(self):
        assert _as_list_impl("") == []

    def test_newline_string(self):
        # Regression: API returned "\n" for an empty recommended_actions array,
        # which caused json.loads to raise JSONDecodeError and crash the journal.
        assert _as_list_impl("\n") == []

    def test_whitespace_string(self):
        assert _as_list_impl("   \n  ") == []

    def test_valid_json_array_string(self):
        assert _as_list_impl('["do water change", "check pH"]') == [
            "do water change", "check pH"
        ]

    def test_invalid_json_string(self):
        assert _as_list_impl("not json at all") == []


# ---------------------------------------------------------------------------
# Integration: run() handles string-valued array fields without crashing
# ---------------------------------------------------------------------------

FAKE_READING = {
    "temp_f": 76.5, "ph": 6.8, "tds_ppm": 190,
    "timestamp": "2026-04-18T12:00:00"
}

TOOL_RESULT_WITH_STRING_ARRAYS = {
    "narrative": "Tank stable. Shrimp active.",
    "key_observations": "\n",           # API bug: string instead of array
    "watch_list": [],
    "recommended_actions": "\n",        # API bug: the crash trigger
}

TOOL_RESULT_NORMAL = {
    "narrative": "Tank stable. Shrimp active.",
    "key_observations": ["Active grazing observed."],
    "watch_list": ["pH trend"],
    "recommended_actions": [],
}


FAKE_READINGS = [FAKE_READING] * 4


class TestRunDoesNotCrash:
    def _patches(self, tool_result):
        return {
            "fetch_readings": MagicMock(return_value=FAKE_READINGS),
            "read_decisions_since": MagicMock(return_value=[]),
            "fetch_events": MagicMock(return_value=[]),
            "fetch_notable_events": MagicMock(return_value=[]),
            "read_journal": MagicMock(return_value=""),
            "call_claude": MagicMock(return_value=tool_result),
            "write_journal_entry": MagicMock(return_value=Path("/tmp/fake.md")),
            "call_toby": MagicMock(),
            "send_document": MagicMock(),
        }

    def test_string_array_fields_do_not_crash(self):
        """Regression: string-valued array fields from API must not crash run()."""
        patches = self._patches(TOOL_RESULT_WITH_STRING_ARRAYS)
        with patch.multiple("skills.shrimp_journal.run", **patches):
            from skills.shrimp_journal.run import run
            run()  # must not raise

    def test_normal_result_writes_entry(self):
        patches = self._patches(TOOL_RESULT_NORMAL)
        with patch.multiple("skills.shrimp_journal.run", **patches):
            from skills.shrimp_journal.run import run
            run()
        patches["write_journal_entry"].assert_called_once()

    def test_string_array_fields_skip_telegram_actions(self):
        """Empty recommended_actions (from string '\n') should not trigger action Telegram."""
        patches = self._patches(TOOL_RESULT_WITH_STRING_ARRAYS)
        with patch.multiple("skills.shrimp_journal.run", **patches):
            from skills.shrimp_journal.run import run
            run()
        # call_toby called once (journal header) but NOT for action items
        calls = [str(c) for c in patches["call_toby"].call_args_list]
        assert not any("Action items" in c for c in calls)
