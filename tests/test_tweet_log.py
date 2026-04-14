"""
Tests for tweet_log — no API calls, no tweepy required.

Run with:
    cd ~/clawdception && python3 -m pytest tests/test_tweet_log.py -v
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.tweet_log.run import post_thread


class TestPostThreadAttachesPhotoToFirstTweetOnly:
    def _make_clients(self):
        v1 = MagicMock()
        media = MagicMock()
        media.media_id = 999
        v1.media_upload.return_value = media

        v2 = MagicMock()
        # Each create_tweet call returns a unique id
        v2.create_tweet.side_effect = [
            MagicMock(data={"id": 101}),
            MagicMock(data={"id": 102}),
            MagicMock(data={"id": 103}),
        ]
        return v2, v1

    def test_photo_uploaded_once_for_first_tweet(self):
        v2, v1 = self._make_clients()
        with patch("skills.tweet_log.run._get_twitter_clients", return_value=(v2, v1)):
            post_thread(["tweet one", "tweet two", "tweet three"], photo_path="/fake/photo.jpg")

        # v1.media_upload called exactly once
        v1.media_upload.assert_called_once_with("/fake/photo.jpg")

    def test_media_id_passed_only_to_first_tweet(self):
        v2, v1 = self._make_clients()
        with patch("skills.tweet_log.run._get_twitter_clients", return_value=(v2, v1)):
            post_thread(["tweet one", "tweet two", "tweet three"], photo_path="/fake/photo.jpg")

        calls = v2.create_tweet.call_args_list
        # First tweet has media_ids
        assert calls[0] == call(text="tweet one", media_ids=[999])
        # Subsequent tweets have no media_ids, only reply chain
        assert calls[1] == call(text="tweet two", in_reply_to_tweet_id=101)
        assert calls[2] == call(text="tweet three", in_reply_to_tweet_id=102)

    def test_no_photo_skips_media_upload(self):
        v2, v1 = self._make_clients()
        with patch("skills.tweet_log.run._get_twitter_clients", return_value=(v2, v1)):
            post_thread(["tweet one", "tweet two"], photo_path=None)

        v1.media_upload.assert_not_called()
        calls = v2.create_tweet.call_args_list
        assert calls[0] == call(text="tweet one")
        assert calls[1] == call(text="tweet two", in_reply_to_tweet_id=101)
