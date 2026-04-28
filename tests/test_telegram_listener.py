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

from skills.telegram_listener.run import (
    answer_question, handle_text, format_vision_reply, handle_photo,
    handle_callback_query, get_offset, save_offset, run,
)
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


class TestHandleTextRouting:
    def _base_patches(self):
        return {
            "call_toby": MagicMock(),
            "answer_question": MagicMock(return_value="Tank looks good."),
            "classify_message": MagicMock(return_value={"event_type": "owner_note", "notes": "x", "data": {}}),
            "post_event": MagicMock(),
        }

    def test_question_type_routes_to_answer(self):
        patches = self._base_patches()
        patches["classify_message"] = MagicMock(return_value={
            "event_type": "question", "notes": "is pH ok?", "data": {}
        })
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_text("is pH ok?")
        patches["answer_question"].assert_called_once_with("is pH ok?")
        patches["post_event"].assert_not_called()

    def test_event_type_logs_and_acks(self):
        patches = self._base_patches()
        patches["classify_message"] = MagicMock(return_value={
            "event_type": "feeding", "notes": "half tab", "data": {}
        })
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_text("fed them half a tab")
        patches["post_event"].assert_called_once_with("feeding", notes="half tab",
                                                       data={"source": "telegram"})
        patches["answer_question"].assert_not_called()

    def test_question_answer_failure_sends_warning(self):
        patches = self._base_patches()
        patches["classify_message"] = MagicMock(return_value={
            "event_type": "question", "notes": "how are they?", "data": {}
        })
        patches["answer_question"] = MagicMock(return_value=None)
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_text("how are they?")
        assert patches["call_toby"].call_args.kwargs.get("urgency") == "warning"

    def test_classify_result_source_injected(self):
        patches = self._base_patches()
        patches["classify_message"] = MagicMock(return_value={
            "event_type": "observation", "notes": "molting shrimp", "data": {"color": "pale"}
        })
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_text("molting shrimp spotted")
        _, kwargs = patches["post_event"].call_args
        assert kwargs["data"]["source"] == "telegram"
        assert kwargs["data"]["color"] == "pale"


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


FAKE_ANALYSIS = {
    "tank_visible": True,
    "shrimp_count_visible": 3,
    "water_clarity": "clear",
    "plant_health": "thriving",
    "visible_algae": False,
    "algae_description": "No algae visible",
    "concerns": [],
    "narrative": "Three shrimp foraging actively near moss.",
    "status": "success",
}


class TestFormatVisionReply:
    def test_uses_shrimp_count_visible(self):
        # regression: was 'shrimp_count_estimate' — KeyError killed every photo reply
        result = format_vision_reply(FAKE_ANALYSIS)
        assert "3 shrimp visible" in result

    def test_caption_included_when_present(self):
        result = format_vision_reply(FAKE_ANALYSIS, caption="chilling by the moss")
        assert '"chilling by the moss"' in result

    def test_no_caption_when_empty(self):
        result = format_vision_reply(FAKE_ANALYSIS, caption="")
        assert '"' not in result.split("\n")[0]

    def test_water_clarity_and_plant_health_present(self):
        result = format_vision_reply(FAKE_ANALYSIS)
        assert "clear" in result
        assert "thriving" in result

    def test_concerns_none_when_empty(self):
        result = format_vision_reply(FAKE_ANALYSIS)
        assert "Concerns: none" in result

    def test_concerns_listed_when_present(self):
        analysis = {**FAKE_ANALYSIS, "concerns": ["ammonia spike", "shrimp lethargic"]}
        result = format_vision_reply(analysis)
        assert "ammonia spike" in result
        assert "shrimp lethargic" in result

    def test_algae_description_shown_when_visible(self):
        analysis = {**FAKE_ANALYSIS, "visible_algae": True, "algae_description": "Green hair algae on glass"}
        result = format_vision_reply(analysis)
        assert "Green hair algae on glass" in result

    def test_algae_not_shown_when_not_visible(self):
        result = format_vision_reply(FAKE_ANALYSIS)
        assert "No algae visible" not in result

    def test_narrative_included(self):
        result = format_vision_reply(FAKE_ANALYSIS)
        assert "Three shrimp foraging actively near moss." in result

    def test_underscore_replaced_in_water_clarity(self):
        analysis = {**FAKE_ANALYSIS, "water_clarity": "slightly_cloudy"}
        result = format_vision_reply(analysis)
        assert "slightly cloudy" in result
        assert "slightly_cloudy" not in result


class TestHandlePhoto:
    def _base_patches(self):
        return {
            "download_photo": MagicMock(return_value=b"imgbytes"),
            "save_photo": MagicMock(return_value="2026-04-16_22-00-00.jpg"),
            "process_photo": MagicMock(return_value=FAKE_ANALYSIS),
            "call_toby": MagicMock(),
            "post_event": MagicMock(),
        }

    def test_sends_vision_reply_on_success(self):
        patches = self._base_patches()
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_photo({"photo": [{"file_id": "abc"}], "caption": "hi"}, token="tok")
        patches["call_toby"].assert_called_once()
        msg = patches["call_toby"].call_args.args[0]
        assert "3 shrimp visible" in msg

    def test_logs_fallback_when_no_analysis(self):
        patches = self._base_patches()
        patches["process_photo"] = MagicMock(return_value=None)
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_photo({"photo": [{"file_id": "abc"}], "caption": "test"}, token="tok")
        msg = patches["call_toby"].call_args.args[0]
        assert "Photo logged" in msg

    def test_download_failure_sends_warning(self):
        patches = self._base_patches()
        patches["download_photo"] = MagicMock(return_value=None)
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_photo({"photo": [{"file_id": "abc"}]}, token="tok")
        assert patches["call_toby"].call_args.kwargs.get("urgency") == "warning"
        patches["post_event"].assert_called_once()

    def test_no_crash_on_missing_shrimp_count_key(self):
        # regression guard: analysis missing shrimp_count_visible must not crash
        analysis_missing_count = {k: v for k, v in FAKE_ANALYSIS.items() if k != "shrimp_count_visible"}
        patches = self._base_patches()
        patches["process_photo"] = MagicMock(return_value=analysis_missing_count)
        with patch.multiple("skills.telegram_listener.run", **patches):
            # should not raise KeyError
            try:
                handle_photo({"photo": [{"file_id": "abc"}]}, token="tok")
            except KeyError as e:
                pytest.fail(f"KeyError raised: {e}")


class TestHandleCallbackQuery:
    def _patches(self):
        return {
            "install_proposal": MagicMock(return_value=(True, "Installed.")),
            "reject_proposal": MagicMock(),
            "answer_callback": MagicMock(),
            "call_toby": MagicMock(),
        }

    def _cq(self, action, proposal_id="2026-04-16-auto-feeder"):
        return {"id": "cq123", "data": f"{action}:{proposal_id}"}

    def test_approve_installs(self):
        patches = self._patches()
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_callback_query("tok", "123", self._cq("approve"))
        patches["install_proposal"].assert_called_once_with("2026-04-16-auto-feeder")
        patches["call_toby"].assert_called_once()

    def test_reject_rejects(self):
        patches = self._patches()
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_callback_query("tok", "123", self._cq("reject"))
        patches["reject_proposal"].assert_called_once_with("2026-04-16-auto-feeder")
        patches["call_toby"].assert_called_once()

    def test_unknown_action_answers_callback(self):
        patches = self._patches()
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_callback_query("tok", "123", {"id": "cq123", "data": "bogus:proposal"})
        patches["answer_callback"].assert_called_once()
        patches["call_toby"].assert_not_called()

    def test_no_colon_in_data_answers_callback_only(self):
        patches = self._patches()
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_callback_query("tok", "123", {"id": "cq123", "data": "malformed"})
        patches["answer_callback"].assert_called_once()
        patches["install_proposal"].assert_not_called()

    def test_approve_failure_sends_warning(self):
        patches = self._patches()
        patches["install_proposal"] = MagicMock(return_value=(False, "Already exists"))
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_callback_query("tok", "123", self._cq("approve"))
        assert patches["call_toby"].call_args.kwargs.get("urgency") == "warning"

    def test_duplicate_reject_skipped(self):
        # Proposal already rejected — second tap must not call reject_proposal or call_toby
        patches = self._patches()
        patches["get_proposal_status"] = MagicMock(return_value="rejected")
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_callback_query("tok", "123", self._cq("reject"))
        patches["reject_proposal"].assert_not_called()
        patches["call_toby"].assert_not_called()
        patches["answer_callback"].assert_called_once()

    def test_duplicate_approve_skipped(self):
        # Proposal already approved — second tap must not install again
        patches = self._patches()
        patches["get_proposal_status"] = MagicMock(return_value="approved")
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_callback_query("tok", "123", self._cq("approve"))
        patches["install_proposal"].assert_not_called()
        patches["call_toby"].assert_not_called()
        patches["answer_callback"].assert_called_once()

    def test_pending_proposal_proceeds(self):
        # status=None (pending) — should process normally
        patches = self._patches()
        patches["get_proposal_status"] = MagicMock(return_value=None)
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_callback_query("tok", "123", self._cq("reject"))
        patches["reject_proposal"].assert_called_once()
        patches["call_toby"].assert_called_once()


class TestOffsetReadWrite:
    def test_get_offset_missing_file(self, tmp_path):
        with patch("skills.telegram_listener.run.OFFSET_FILE", tmp_path / "offset.txt"):
            assert get_offset() == 0

    def test_get_offset_bad_content(self, tmp_path):
        f = tmp_path / "offset.txt"
        f.write_text("not_a_number")
        with patch("skills.telegram_listener.run.OFFSET_FILE", f):
            assert get_offset() == 0

    def test_save_and_get_offset_roundtrip(self, tmp_path):
        f = tmp_path / "offset.txt"
        with patch("skills.telegram_listener.run.OFFSET_FILE", f):
            save_offset(42)
            assert get_offset() == 42


class TestRun:
    def _env(self):
        return {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "999"}

    def _patches(self, updates=None, chat_id="999"):
        updates = updates or []
        return {
            "get_offset": MagicMock(return_value=0),
            "save_offset": MagicMock(),
            "handle_photo": MagicMock(),
            "handle_text": MagicMock(),
            "handle_callback_query": MagicMock(),
        }

    def _mock_get(self, updates, chat_id="999"):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"result": updates}
        return resp

    def test_no_env_skips(self):
        patches = self._patches()
        with patch.dict("os.environ", {}, clear=True):
            with patch.multiple("skills.telegram_listener.run", **patches):
                run()
        patches["handle_text"].assert_not_called()
        patches["handle_photo"].assert_not_called()

    def test_no_updates_returns_early(self):
        patches = self._patches()
        mock_resp = self._mock_get([])
        with patch.dict("os.environ", self._env()):
            with patch.multiple("skills.telegram_listener.run", **patches):
                with patch("requests.get", return_value=mock_resp):
                    run()
        patches["save_offset"].assert_not_called()

    def test_text_message_routes_to_handle_text(self):
        update = {"update_id": 1, "message": {"chat": {"id": 999}, "text": "fed half tab"}}
        patches = self._patches()
        mock_resp = self._mock_get([update])
        with patch.dict("os.environ", self._env()):
            with patch.multiple("skills.telegram_listener.run", **patches):
                with patch("requests.get", return_value=mock_resp):
                    run()
        patches["handle_text"].assert_called_once_with("fed half tab")

    def test_photo_message_routes_to_handle_photo(self):
        update = {
            "update_id": 2,
            "message": {"chat": {"id": 999}, "photo": [{"file_id": "abc"}], "caption": "hi"},
        }
        patches = self._patches()
        mock_resp = self._mock_get([update])
        with patch.dict("os.environ", self._env()):
            with patch.multiple("skills.telegram_listener.run", **patches):
                with patch("requests.get", return_value=mock_resp):
                    run()
        patches["handle_photo"].assert_called_once()

    def test_wrong_chat_id_ignored(self):
        update = {"update_id": 3, "message": {"chat": {"id": 888}, "text": "intruder"}}
        patches = self._patches()
        mock_resp = self._mock_get([update])
        with patch.dict("os.environ", self._env()):
            with patch.multiple("skills.telegram_listener.run", **patches):
                with patch("requests.get", return_value=mock_resp):
                    run()
        patches["handle_text"].assert_not_called()

    def test_callback_query_routes_correctly(self):
        update = {
            "update_id": 4,
            "callback_query": {
                "id": "cq1",
                "data": "approve:2026-04-16-feeder",
                "message": {"chat": {"id": 999}},
            },
        }
        patches = self._patches()
        mock_resp = self._mock_get([update])
        with patch.dict("os.environ", self._env()):
            with patch.multiple("skills.telegram_listener.run", **patches):
                with patch("requests.get", return_value=mock_resp):
                    run()
        patches["handle_callback_query"].assert_called_once()

    def test_callback_wrong_chat_ignored(self):
        update = {
            "update_id": 5,
            "callback_query": {
                "id": "cq2",
                "data": "approve:x",
                "message": {"chat": {"id": 888}},
            },
        }
        patches = self._patches()
        mock_resp = self._mock_get([update])
        with patch.dict("os.environ", self._env()):
            with patch.multiple("skills.telegram_listener.run", **patches):
                with patch("requests.get", return_value=mock_resp):
                    run()
        patches["handle_callback_query"].assert_not_called()

    def test_offset_advanced_after_processing(self):
        update = {"update_id": 10, "message": {"chat": {"id": 999}, "text": "hi"}}
        patches = self._patches()
        mock_resp = self._mock_get([update])
        with patch.dict("os.environ", self._env()):
            with patch.multiple("skills.telegram_listener.run", **patches):
                with patch("requests.get", return_value=mock_resp):
                    run()
        patches["save_offset"].assert_called_once_with(11)

    def test_network_error_returns_gracefully(self):
        patches = self._patches()
        with patch.dict("os.environ", self._env()):
            with patch.multiple("skills.telegram_listener.run", **patches):
                with patch("requests.get", side_effect=Exception("timeout")):
                    run()  # must not raise
        patches["handle_text"].assert_not_called()


# ---------------------------------------------------------------------------
# capture_request / ESP32-CAM flow
# ---------------------------------------------------------------------------

class TestHandleCaptureRequest:
    def _base_patches(self):
        return {
            "fetch_esp32_snapshot": MagicMock(return_value=b"\xff\xd8\xff" + b"x" * 1000),
            "save_photo": MagicMock(return_value="2026-04-28_12-00-00.jpg"),
            "process_photo": MagicMock(return_value=FAKE_ANALYSIS),
            "send_photo": MagicMock(return_value=True),
            "call_toby": MagicMock(),
        }

    def test_success_sends_photo_with_caption(self):
        patches = self._base_patches()
        with patch.multiple("skills.telegram_listener.run", **patches):
            from skills.telegram_listener.run import handle_capture_request
            handle_capture_request()
        patches["send_photo"].assert_called_once()
        _, kwargs = patches["send_photo"].call_args
        assert "3 shrimp visible" in kwargs.get("caption", "")

    def test_camera_offline_sends_warning(self):
        patches = self._base_patches()
        patches["fetch_esp32_snapshot"] = MagicMock(return_value=None)
        with patch.multiple("skills.telegram_listener.run", **patches):
            from skills.telegram_listener.run import handle_capture_request
            handle_capture_request()
        patches["send_photo"].assert_not_called()
        assert patches["call_toby"].call_args.kwargs.get("urgency") == "warning"

    def test_analysis_failure_sends_photo_without_caption(self):
        patches = self._base_patches()
        patches["process_photo"] = MagicMock(return_value=None)
        with patch.multiple("skills.telegram_listener.run", **patches):
            from skills.telegram_listener.run import handle_capture_request
            handle_capture_request()
        patches["send_photo"].assert_called_once()
        _, kwargs = patches["send_photo"].call_args
        assert not kwargs.get("caption")

    def test_capture_request_event_type_routes_to_handler(self):
        patches = {
            "classify_message": MagicMock(return_value={
                "event_type": "capture_request", "notes": "take a photo", "data": {}
            }),
            "handle_capture_request": MagicMock(),
            "call_toby": MagicMock(),
            "post_event": MagicMock(),
            "answer_question": MagicMock(),
        }
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_text("take a photo")
        patches["handle_capture_request"].assert_called_once()
        patches["post_event"].assert_not_called()

    def test_capture_request_in_classify_enum(self):
        from skills.telegram_listener.run import CLASSIFY_TOOL
        enum = CLASSIFY_TOOL["input_schema"]["properties"]["event_type"]["enum"]
        assert "capture_request" in enum


# ---------------------------------------------------------------------------
# correction event type
# ---------------------------------------------------------------------------

class TestCorrectionEventType:
    def test_correction_in_classify_enum(self):
        from skills.telegram_listener.run import CLASSIFY_TOOL
        enum = CLASSIFY_TOOL["input_schema"]["properties"]["event_type"]["enum"]
        assert "correction" in enum

    def test_classify_description_mentions_correction(self):
        from skills.telegram_listener.run import CLASSIFY_TOOL
        desc = CLASSIFY_TOOL["input_schema"]["properties"]["event_type"]["description"]
        assert "correction" in desc
