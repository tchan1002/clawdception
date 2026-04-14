"""
Tests for skills/shrimp_vision/run.py.
No API calls — call_claude is mocked.

Run with:
    cd ~/clawdception && python3 -m pytest tests/test_shrimp_vision.py -v
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.shrimp_vision.run import analyze_snapshot, log_entry, process_photo

FAKE_ANALYSIS = {
    "shrimp_count_estimate": 2,
    "water_clarity": "clear",
    "visible_algae": True,
    "algae_description": "Green biofilm on sponge filter.",
    "substrate_condition": "clean",
    "plant_health": "thriving",
    "concerns": ["Only 2 shrimp visible — may be sheltering."],
    "narrative": "Two shrimp grazing on sponge filter. Tank looks healthy.",
}

FAKE_JPEG = b"\xff\xd8\xff" + b"\x00" * 100  # minimal fake JPEG bytes


class TestAnalyzeSnapshot:
    def test_returns_analysis_dict(self):
        with patch("skills.shrimp_vision.run.call_claude", return_value=FAKE_ANALYSIS):
            result = analyze_snapshot(FAKE_JPEG)
        assert result == FAKE_ANALYSIS

    def test_passes_image_bytes_as_base64(self):
        import base64
        captured = {}

        def capture_call(**kwargs):
            captured["messages"] = kwargs["messages"]
            return FAKE_ANALYSIS

        with patch("skills.shrimp_vision.run.call_claude", side_effect=capture_call):
            analyze_snapshot(FAKE_JPEG)

        image_block = captured["messages"][0]["content"][0]
        assert image_block["type"] == "image"
        assert image_block["source"]["type"] == "base64"
        assert image_block["source"]["data"] == base64.standard_b64encode(FAKE_JPEG).decode()

    def test_passes_correct_tool(self):
        captured = {}

        def capture_call(**kwargs):
            captured["tool_name"] = kwargs["tool_name"]
            return FAKE_ANALYSIS

        with patch("skills.shrimp_vision.run.call_claude", side_effect=capture_call):
            analyze_snapshot(FAKE_JPEG)

        assert captured["tool_name"] == "analyze_tank_image"


class TestLogEntry:
    def test_writes_jsonl(self, tmp_path):
        with patch("skills.shrimp_vision.run.PATHS", {"vision_logs": tmp_path}):
            ts = "2026-04-14T11:08:04"
            entry = {**FAKE_ANALYSIS, "timestamp": ts, "filename": "test.jpg",
                     "owner_comment": "molting behavior", "status": "success", "source": "telegram"}
            log_entry(entry)

        log_file = tmp_path / "2026-04-14.jsonl"
        assert log_file.exists()
        written = json.loads(log_file.read_text().strip())
        assert written["filename"] == "test.jpg"
        assert written["shrimp_count_estimate"] == 2
        assert written["owner_comment"] == "molting behavior"
        assert written["status"] == "success"

    def test_appends_multiple_entries(self, tmp_path):
        with patch("skills.shrimp_vision.run.PATHS", {"vision_logs": tmp_path}):
            for i in range(3):
                log_entry({**FAKE_ANALYSIS, "timestamp": f"2026-04-14T11:0{i}:00",
                            "filename": f"photo_{i}.jpg", "status": "success", "source": "test"})

        lines = (tmp_path / "2026-04-14.jsonl").read_text().strip().splitlines()
        assert len(lines) == 3

    def test_owner_comment_preserved(self, tmp_path):
        with patch("skills.shrimp_vision.run.PATHS", {"vision_logs": tmp_path}):
            log_entry({**FAKE_ANALYSIS, "timestamp": "2026-04-14T12:00:00",
                       "filename": "x.jpg", "owner_comment": "little guys near sponges",
                       "status": "success", "source": "telegram"})

        written = json.loads((tmp_path / "2026-04-14.jsonl").read_text().strip())
        assert written["owner_comment"] == "little guys near sponges"


class TestProcessPhoto:
    def test_returns_analysis(self):
        with patch("skills.shrimp_vision.run.analyze_snapshot", return_value=FAKE_ANALYSIS), \
             patch("skills.shrimp_vision.run.log_entry"), \
             patch("skills.shrimp_vision.run.post_event"):
            result = process_photo(FAKE_JPEG, "photo.jpg", caption="hi", source="telegram")
        assert result == FAKE_ANALYSIS

    def test_vision_fields_in_event_data(self):
        with patch("skills.shrimp_vision.run.analyze_snapshot", return_value=FAKE_ANALYSIS), \
             patch("skills.shrimp_vision.run.log_entry"), \
             patch("skills.shrimp_vision.run.post_event") as mock_post:
            process_photo(FAKE_JPEG, "photo.jpg", caption="molting", source="telegram")

        data = mock_post.call_args.kwargs["data"]
        assert data["shrimp_count_estimate"] == 2
        assert data["water_clarity"] == "clear"
        assert data["filename"] == "photo.jpg"
        assert data["source"] == "telegram"
        assert data["narrative"] == FAKE_ANALYSIS["narrative"]

    def test_log_entry_called_with_vision_fields(self, tmp_path):
        with patch("skills.shrimp_vision.run.analyze_snapshot", return_value=FAKE_ANALYSIS), \
             patch("skills.shrimp_vision.run.PATHS", {"vision_logs": tmp_path}), \
             patch("skills.shrimp_vision.run.post_event"):
            process_photo(FAKE_JPEG, "photo.jpg", caption="molting", source="telegram")

        lines = (tmp_path / f"{datetime.now().date()}.jsonl").read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["filename"] == "photo.jpg"
        assert entry["source"] == "telegram"
        assert entry["owner_comment"] == "molting"
        assert entry["shrimp_count_estimate"] == 2
        assert entry["status"] == "success"

    def test_event_posted_even_when_analysis_fails(self):
        with patch("skills.shrimp_vision.run.analyze_snapshot", return_value=None), \
             patch("skills.shrimp_vision.run.post_event") as mock_post:
            result = process_photo(FAKE_JPEG, "photo.jpg", source="telegram")

        assert result is None
        mock_post.assert_called_once()
        data = mock_post.call_args.kwargs["data"]
        assert data["filename"] == "photo.jpg"
        assert "shrimp_count_estimate" not in data

    def test_no_log_entry_when_analysis_fails(self):
        with patch("skills.shrimp_vision.run.analyze_snapshot", return_value=None), \
             patch("skills.shrimp_vision.run.post_event"), \
             patch("skills.shrimp_vision.run.log_entry") as mock_log:
            process_photo(FAKE_JPEG, "photo.jpg")

        mock_log.assert_not_called()
