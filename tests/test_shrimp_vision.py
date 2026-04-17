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
    "tank_visible": True,
    "shrimp_count_visible": 2,
    "water_clarity": "clear",
    "visible_algae": True,
    "algae_description": "Green biofilm on sponge filter.",
    "substrate_condition": "clean",
    "plant_health": "thriving",
    "concerns": [],
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
        today = datetime.now().date()
        with patch("skills.shrimp_vision.run.PATHS", {"vision_logs": tmp_path}):
            entry = {**FAKE_ANALYSIS, "timestamp": datetime.now().isoformat(), "filename": "test.jpg",
                     "owner_comment": "molting behavior", "status": "success", "source": "telegram"}
            log_entry(entry)

        log_file = tmp_path / f"{today}.jsonl"
        assert log_file.exists()
        written = json.loads(log_file.read_text().strip())
        assert written["filename"] == "test.jpg"
        assert written["shrimp_count_visible"] == 2
        assert written["owner_comment"] == "molting behavior"
        assert written["status"] == "success"

    def test_appends_multiple_entries(self, tmp_path):
        today = datetime.now().date()
        with patch("skills.shrimp_vision.run.PATHS", {"vision_logs": tmp_path}):
            for i in range(3):
                log_entry({**FAKE_ANALYSIS, "timestamp": datetime.now().isoformat(),
                            "filename": f"photo_{i}.jpg", "status": "success", "source": "test"})

        lines = (tmp_path / f"{today}.jsonl").read_text().strip().splitlines()
        assert len(lines) == 3

    def test_owner_comment_preserved(self, tmp_path):
        today = datetime.now().date()
        with patch("skills.shrimp_vision.run.PATHS", {"vision_logs": tmp_path}):
            log_entry({**FAKE_ANALYSIS, "timestamp": datetime.now().isoformat(),
                       "filename": "x.jpg", "owner_comment": "little guys near sponges",
                       "status": "success", "source": "telegram"})

        written = json.loads((tmp_path / f"{today}.jsonl").read_text().strip())
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
        assert data["shrimp_count_visible"] == 2
        assert data["water_clarity"] == "clear"
        assert data["filename"] == "photo.jpg"
        assert data["source"] == "telegram"
        assert data["tank_visible"] is True

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
        assert entry["shrimp_count_visible"] == 2
        assert entry["status"] == "success"

    def test_no_event_when_analysis_fails(self):
        with patch("skills.shrimp_vision.run.analyze_snapshot", return_value=None), \
             patch("skills.shrimp_vision.run.post_event") as mock_post:
            result = process_photo(FAKE_JPEG, "photo.jpg", source="telegram")

        assert result is None
        mock_post.assert_not_called()

    def test_error_logged_when_analysis_fails(self):
        with patch("skills.shrimp_vision.run.analyze_snapshot", return_value=None), \
             patch("skills.shrimp_vision.run.post_event"), \
             patch("skills.shrimp_vision.run.log_entry") as mock_log:
            process_photo(FAKE_JPEG, "photo.jpg")

        mock_log.assert_called_once()
        entry = mock_log.call_args.args[0]
        assert entry["status"] == "error"
        assert "reason" in entry

    def test_empty_image_returns_none(self):
        with patch("skills.shrimp_vision.run.log_entry") as mock_log, \
             patch("skills.shrimp_vision.run.post_event") as mock_post:
            result = process_photo(b"", "photo.jpg")
        assert result is None
        mock_post.assert_not_called()
        entry = mock_log.call_args.args[0]
        assert entry["status"] == "error"

    def test_oversized_image_returns_none(self):
        big = b"\xff\xd8\xff" + b"\x00" * (4 * 1024 * 1024 + 1)
        with patch("skills.shrimp_vision.run.log_entry") as mock_log, \
             patch("skills.shrimp_vision.run.post_event") as mock_post:
            result = process_photo(big, "photo.jpg")
        assert result is None
        mock_post.assert_not_called()
        entry = mock_log.call_args.args[0]
        assert entry["status"] == "error"


class TestSafeguards:
    """Schema safeguards: tank_visible guard, zero-shrimp, non-tank images."""

    def test_zero_shrimp_accepted(self):
        zero_shrimp = {**FAKE_ANALYSIS, "shrimp_count_visible": 0}
        with patch("skills.shrimp_vision.run.call_claude", return_value=zero_shrimp):
            result = analyze_snapshot(FAKE_JPEG)
        assert result["shrimp_count_visible"] == 0

    def test_non_tank_image_no_tank_fields(self):
        not_tank = {"tank_visible": False, "concerns": [], "image_subject": "test strip"}
        with patch("skills.shrimp_vision.run.call_claude", return_value=not_tank):
            result = analyze_snapshot(FAKE_JPEG)
        assert result["tank_visible"] is False
        assert result["image_subject"] == "test strip"
        assert "shrimp_count_visible" not in result
        assert "water_clarity" not in result

    def test_schema_has_narrative(self):
        from skills.shrimp_vision.run import TOOL
        assert "narrative" in TOOL["input_schema"]["properties"]
        assert "narrative" in TOOL["input_schema"]["required"]

    def test_schema_tank_visible_required(self):
        from skills.shrimp_vision.run import TOOL
        assert "tank_visible" in TOOL["input_schema"]["required"]

    def test_schema_shrimp_count_visible_not_required(self):
        # shrimp_count_visible optional — image may not show tank
        from skills.shrimp_vision.run import TOOL
        assert "shrimp_count_visible" not in TOOL["input_schema"]["required"]

    def test_prompt_water_clarity_glare_instruction(self):
        """Prompt must instruct model to ignore glare/reflections and default to clear."""
        captured = {}

        def capture(**kwargs):
            captured["prompt"] = kwargs["messages"][0]["content"][1]["text"]
            return FAKE_ANALYSIS

        with patch("skills.shrimp_vision.run.call_claude", side_effect=capture):
            analyze_snapshot(FAKE_JPEG)

        prompt = captured["prompt"]
        assert "Glass glare" in prompt
        assert "reflections" in prompt
        assert "turbid or muddy" in prompt
        assert "Default" in prompt and "clear" in prompt

    def test_non_tank_image_logged_and_posted(self, tmp_path):
        not_tank = {"tank_visible": False, "concerns": [], "image_subject": "equipment"}
        with patch("skills.shrimp_vision.run.analyze_snapshot", return_value=not_tank), \
             patch("skills.shrimp_vision.run.PATHS", {"vision_logs": tmp_path}), \
             patch("skills.shrimp_vision.run.post_event") as mock_post:
            result = process_photo(FAKE_JPEG, "equip.jpg", caption="filter", source="telegram")

        assert result["tank_visible"] is False
        mock_post.assert_called_once()
        today = datetime.now().date()
        log_file = tmp_path / f"{today}.jsonl"
        assert log_file.exists()
        import json
        entry = json.loads(log_file.read_text().strip())
        assert entry["image_subject"] == "equipment"

    def test_prompt_zone_scan_instruction(self):
        """Prompt must instruct model to scan foreground/midground/background zones."""
        captured = {}

        def capture(**kwargs):
            captured["prompt"] = kwargs["messages"][0]["content"][1]["text"]
            return FAKE_ANALYSIS

        with patch("skills.shrimp_vision.run.call_claude", side_effect=capture):
            analyze_snapshot(FAKE_JPEG)

        prompt = captured["prompt"]
        assert "foreground" in prompt
        assert "midground" in prompt
        assert "background" in prompt

    def test_prompt_shrimp_counting_bias(self):
        """Prompt must instruct model to include partial sightings and err toward counting."""
        captured = {}

        def capture(**kwargs):
            captured["prompt"] = kwargs["messages"][0]["content"][1]["text"]
            return FAKE_ANALYSIS

        with patch("skills.shrimp_vision.run.call_claude", side_effect=capture):
            analyze_snapshot(FAKE_JPEG)

        prompt = captured["prompt"]
        assert "partial" in prompt.lower()
        assert "Err on the side of counting" in prompt

    def test_prompt_shrimp_description_includes_juveniles(self):
        """Prompt must describe juvenile and berried female appearance for accurate detection."""
        captured = {}

        def capture(**kwargs):
            captured["prompt"] = kwargs["messages"][0]["content"][1]["text"]
            return FAKE_ANALYSIS

        with patch("skills.shrimp_vision.run.call_claude", side_effect=capture):
            analyze_snapshot(FAKE_JPEG)

        prompt = captured["prompt"]
        assert "Juvenile" in prompt or "juvenile" in prompt
        assert "berried" in prompt.lower()
