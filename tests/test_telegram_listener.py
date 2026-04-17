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
    answer_question, is_question, handle_text, format_vision_reply, handle_photo,
    handle_proposal_reply, handle_callback_query, handle_edit_reply,
    get_offset, save_offset, run,
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


class TestIsQuestion:
    def test_question_mark_suffix(self):
        assert is_question("is pH ok?") is True

    def test_question_words(self):
        for text in ("what is ammonia", "how are shrimp", "why is TDS high",
                     "when did I feed", "are they stressed", "can I add more",
                     "should I do water change", "will they survive", "did nitrite spike",
                     "does this look normal"):
            assert is_question(text) is True, f"Expected True for {text!r}"

    def test_non_questions(self):
        for text in ("fed them half a tab", "50% water change", "added 2 nerites",
                     "top off tonight", "adjusted heater to 76F", ""):
            assert is_question(text) is False, f"Expected False for {text!r}"

    def test_case_insensitive(self):
        assert is_question("WHAT is the temperature") is True
        assert is_question("Is pH ok?") is True


class TestHandleTextRouting:
    def _base_patches(self):
        return {
            "get_pending_proposal": MagicMock(return_value=None),
            "get_pending_edit": MagicMock(return_value=None),
            "call_toby": MagicMock(),
        }

    def test_question_routes_to_answer_not_classify(self):
        patches = self._base_patches()
        patches["answer_question"] = MagicMock(return_value="pH looks fine.")
        patches["classify_message"] = MagicMock()
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_text("is pH ok?")
        patches["answer_question"].assert_called_once_with("is pH ok?")
        patches["classify_message"].assert_not_called()

    def test_event_routes_to_classify_not_answer(self):
        patches = self._base_patches()
        patches["answer_question"] = MagicMock()
        patches["classify_message"] = MagicMock(return_value={
            "event_type": "feeding", "notes": "half tab", "data": {}
        })
        patches["post_event"] = MagicMock()
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_text("fed them half a tab")
        patches["classify_message"].assert_called_once()
        patches["answer_question"].assert_not_called()
        patches["post_event"].assert_called_once_with("feeding", notes="half tab",
                                                       data={"source": "telegram"})

    def test_question_answer_failure_sends_warning(self):
        patches = self._base_patches()
        patches["answer_question"] = MagicMock(return_value=None)
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_text("how are they?")
        call_args = patches["call_toby"].call_args
        assert call_args.kwargs.get("urgency") == "warning"

    def test_pending_edit_routes_to_handle_edit_reply(self):
        pending = {"proposal": "2026-04-16-some-skill", "waiting_since": "2026-04-16T10:00:00"}
        patches = self._base_patches()
        patches["get_pending_edit"] = MagicMock(return_value=pending)
        patches["handle_edit_reply"] = MagicMock()
        patches["classify_message"] = MagicMock()
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_text("make it run every 5 min instead")
        patches["handle_edit_reply"].assert_called_once_with("make it run every 5 min instead", pending)
        patches["classify_message"].assert_not_called()

    def test_classify_result_source_injected(self):
        patches = self._base_patches()
        patches["classify_message"] = MagicMock(return_value={
            "event_type": "observation", "notes": "molting shrimp", "data": {"color": "pale"}
        })
        patches["post_event"] = MagicMock()
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


FAKE_PROPOSAL = {"proposal": "2026-04-16-auto-feeder", "sent_at": "2026-04-16T10:00:00"}


class TestHandleProposalReply:
    def _patches(self):
        return {
            "install_proposal": MagicMock(return_value=(True, "Installed to skills/auto_feeder/")),
            "reject_proposal": MagicMock(),
            "clear_pending_proposal": MagicMock(),
            "set_pending_edit": MagicMock(),
            "call_toby": MagicMock(),
        }

    def test_yes_installs_and_clears(self):
        for word in ("yes", "y", "approve", "approved", "yeah", "yep"):
            patches = self._patches()
            with patch.multiple("skills.telegram_listener.run", **patches):
                handle_proposal_reply(word, FAKE_PROPOSAL)
            patches["install_proposal"].assert_called_once_with("2026-04-16-auto-feeder")
            patches["clear_pending_proposal"].assert_called_once()

    def test_no_rejects_and_clears(self):
        for word in ("no", "n", "reject", "rejected", "nope", "pass"):
            patches = self._patches()
            with patch.multiple("skills.telegram_listener.run", **patches):
                handle_proposal_reply(word, FAKE_PROPOSAL)
            patches["reject_proposal"].assert_called_once_with("2026-04-16-auto-feeder")
            patches["clear_pending_proposal"].assert_called_once()

    def test_edit_sets_pending_edit(self):
        for word in ("edit", "e", "change", "modify"):
            patches = self._patches()
            with patch.multiple("skills.telegram_listener.run", **patches):
                handle_proposal_reply(word, FAKE_PROPOSAL)
            patches["set_pending_edit"].assert_called_once_with("2026-04-16-auto-feeder")
            patches["clear_pending_proposal"].assert_called_once()

    def test_unknown_reply_prompts_again(self):
        patches = self._patches()
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_proposal_reply("sure whatever", FAKE_PROPOSAL)
        patches["install_proposal"].assert_not_called()
        patches["reject_proposal"].assert_not_called()
        msg = patches["call_toby"].call_args.args[0]
        assert "yes" in msg and "no" in msg

    def test_install_failure_sends_warning(self):
        patches = self._patches()
        patches["install_proposal"] = MagicMock(return_value=(False, "Already exists"))
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_proposal_reply("yes", FAKE_PROPOSAL)
        assert patches["call_toby"].call_args.kwargs.get("urgency") == "warning"

    def test_case_insensitive(self):
        patches = self._patches()
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_proposal_reply("YES", FAKE_PROPOSAL)
        patches["install_proposal"].assert_called_once()


class TestHandleCallbackQuery:
    def _patches(self):
        return {
            "install_proposal": MagicMock(return_value=(True, "Installed.")),
            "reject_proposal": MagicMock(),
            "set_pending_edit": MagicMock(),
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

    def test_edit_sets_pending_and_prompts(self):
        patches = self._patches()
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_callback_query("tok", "123", self._cq("edit"))
        patches["set_pending_edit"].assert_called_once_with("2026-04-16-auto-feeder")
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


class TestHandleEditReply:
    def _patches(self):
        return {
            "apply_edit_to_proposal": MagicMock(return_value="Interval changed to 5min."),
            "clear_pending_edit": MagicMock(),
            "send_with_buttons": MagicMock(),
            "call_toby": MagicMock(),
        }

    def test_success_clears_edit_and_sends_buttons(self):
        pending = {"proposal": "2026-04-16-auto-feeder", "waiting_since": "2026-04-16T10:00:00"}
        patches = self._patches()
        # patch proposal_dir existence so handle_edit_reply doesn't read real fs
        fake_proposal_dir = MagicMock()
        fake_proposal_dir.exists.return_value = False
        fake_paths = {"proposals": MagicMock()}
        fake_paths["proposals"].__truediv__ = MagicMock(return_value=fake_proposal_dir)
        with patch.multiple("skills.telegram_listener.run", **patches):
            with patch("skills.telegram_listener.run.PATHS", fake_paths):
                handle_edit_reply("run every 5 min", pending)
        patches["clear_pending_edit"].assert_called_once()
        patches["send_with_buttons"].assert_called_once()

    def test_claude_failure_sends_warning(self):
        pending = {"proposal": "2026-04-16-auto-feeder", "waiting_since": "2026-04-16T10:00:00"}
        patches = self._patches()
        patches["apply_edit_to_proposal"] = MagicMock(return_value=None)
        with patch.multiple("skills.telegram_listener.run", **patches):
            handle_edit_reply("run every 5 min", pending)
        patches["clear_pending_edit"].assert_called_once()
        assert patches["call_toby"].call_args.kwargs.get("urgency") == "warning"
        patches["send_with_buttons"].assert_not_called()


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
