"""
Tests for telegram_listener — no Telegram API, no Claude API calls.

Run with:
    cd ~/clawdception && python3 -m pytest tests/test_telegram_listener.py -v
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.telegram_listener.run import answer_question
from utils import format_recent_events


FAKE_READING = {"temp_f": 75.2, "ph": 7.1, "tds_ppm": 210, "timestamp": "2026-04-15T12:00:00"}

FAKE_NOTABLE = [
    {"event_type": "water_test",  "timestamp": "2026-04-14T10:00:00", "notes": "", "data": {"ammonia": 0, "nitrite": 0}},
    {"event_type": "owner_photo", "timestamp": "2026-04-14T11:00:00", "notes": "shrimp near filter", "data": {}},
    {"event_type": "water_change","timestamp": "2026-04-13T09:00:00", "notes": "20%", "data": {"percent": 20}},
]


class TestAnswerQuestion:
    def _patch_context(self, notable=None, claude_reply="Tank looks stable."):
        return {
            "fetch_latest_reading": MagicMock(return_value=FAKE_READING),
            "fetch_events": MagicMock(return_value=[]),
            "fetch_notable_events": MagicMock(return_value=notable or []),
            "read_journal": MagicMock(return_value=""),
            "read_agent_state": MagicMock(return_value=""),
            "call_claude": MagicMock(return_value=claude_reply),
        }

    def test_returns_claude_reply(self):
        patches = self._patch_context(claude_reply="pH is good.")
        with patch.multiple("skills.telegram_listener.run", **patches):
            result = answer_question("How's the pH?")
        assert result == "pH is good."

    def test_question_text_in_prompt(self):
        patches = self._patch_context()
        with patch.multiple("skills.telegram_listener.run", **patches):
            answer_question("Is the temperature safe?")
        prompt = patches["call_claude"].call_args.kwargs["messages"][0]["content"]
        assert "Is the temperature safe?" in prompt

    def test_current_reading_in_prompt(self):
        patches = self._patch_context()
        with patch.multiple("skills.telegram_listener.run", **patches):
            answer_question("Status?")
        prompt = patches["call_claude"].call_args.kwargs["messages"][0]["content"]
        assert "75.2" in prompt
        assert "7.1" in prompt
        assert "210" in prompt

    def test_owner_photo_excluded_from_notable(self):
        patches = self._patch_context(notable=FAKE_NOTABLE)
        with patch.multiple("skills.telegram_listener.run", **patches):
            answer_question("Any recent water tests?")
        prompt = patches["call_claude"].call_args.kwargs["messages"][0]["content"]
        assert "water_test" in prompt
        assert "water_change" in prompt
        assert "owner_photo" not in prompt

    def test_returns_none_on_claude_failure(self):
        patches = self._patch_context()
        patches["call_claude"].side_effect = Exception("API error")
        with patch.multiple("skills.telegram_listener.run", **patches):
            result = answer_question("Status?")
        assert result is None


class TestFormatRecentEventsTruncation:
    def test_long_data_truncated(self):
        events = [{"timestamp": "2026-04-15T10:00:00", "event_type": "owner_photo",
                   "notes": "", "data": {"narrative": "x" * 300, "source": "telegram"}}]
        line = format_recent_events(events)
        assert len(line) < 300

    def test_notes_preferred_over_data(self):
        events = [{"timestamp": "2026-04-15T10:00:00", "event_type": "observation",
                   "notes": "shrimp active", "data": {"source": "telegram"}}]
        line = format_recent_events(events)
        assert "shrimp active" in line
        assert "source" not in line

    def test_empty_returns_none_string(self):
        assert format_recent_events([]) == "None in past 24 hours."
