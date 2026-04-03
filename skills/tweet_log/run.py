"""
tweet-log — posts a daily tweet about tank status to Twitter.

Reads today's daily log, asks Claude to write a 280-char tweet in the caretaker's
voice, and posts via Twitter API. Signs off with —Media Luna.

Usage:
    python3 run.py
"""

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import PATHS
from utils import call_claude


def read_todays_log():
    """Returns today's daily log content, or None if it doesn't exist yet."""
    # Daily logs are written for yesterday at 7:00 AM, so "today's log" is actually yesterday's file
    log_date = date.today() - timedelta(days=1)
    log_path = PATHS["daily_logs"] / f"{log_date}.md"
    if log_path.exists():
        return log_path.read_text()
    return None


def generate_tweet(daily_log_content):
    """
    Calls Claude to generate a tweet from the daily log.
    Returns the tweet text (max 280 chars, no em dashes, signs off —Media Luna).
    """
    # Extract first 800 chars of log to keep prompt short
    excerpt = daily_log_content[:800] if len(daily_log_content) > 800 else daily_log_content

    prompt = f"""You are the Media Luna caretaker. Write ONE tweet about your tank based on today's log.

DAILY LOG (excerpt):
{excerpt}

Write a single tweet (max 280 chars including signature). Use caretaker voice: personal, observant, caring. NO em dashes (—) except in the signature. Sign off with —Media Luna at the end.

Return ONLY the tweet text, nothing else."""

    response = call_claude(
        messages=[{"role": "user", "content": prompt}],
        skill_name="tweet-log",
    )

    tweet = response.strip()

    # Ensure it doesn't exceed 280 chars
    if len(tweet) > 280:
        # Truncate but preserve the signature
        if "—Media Luna" in tweet:
            body = tweet.split("—Media Luna")[0].strip()
            max_body = 280 - len(" —Media Luna")
            tweet = body[:max_body].strip() + " —Media Luna"
        else:
            tweet = tweet[:280]

    return tweet


def post_tweet(tweet_text):
    """Posts the tweet via Twitter API using tweepy. Returns success status."""
    try:
        import tweepy
    except ImportError:
        raise RuntimeError("tweepy not installed — run: pip install tweepy")

    # Twitter API credentials from environment
    api_key = os.environ.get("TWITTER_API_KEY")
    api_secret = os.environ.get("TWITTER_API_SECRET")
    access_token = os.environ.get("TWITTER_ACCESS_TOKEN")
    access_secret = os.environ.get("TWITTER_ACCESS_SECRET")

    if not all([api_key, api_secret, access_token, access_secret]):
        raise ValueError("Missing Twitter credentials in environment variables")

    # Authenticate and post
    client = tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_secret,
    )

    response = client.create_tweet(text=tweet_text)
    return response.data


def run():
    from datetime import datetime

    ts = datetime.now().isoformat()

    # Exit silently if no daily log exists yet
    daily_log = read_todays_log()
    if not daily_log:
        # Silent exit — this is expected if running before daily-log completes
        return

    try:
        # Generate tweet
        tweet = generate_tweet(daily_log)

        # Post to Twitter
        tweet_data = post_tweet(tweet)

        # Log success
        log_entry = {
            "timestamp": ts,
            "status": "success",
            "tweet": tweet,
            "tweet_id": tweet_data.get("id") if tweet_data else None,
        }

        PATHS["logs"].mkdir(parents=True, exist_ok=True)
        tweets_log = PATHS["logs"] / "tweets.jsonl"
        with open(tweets_log, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

        print(f"[tweet-log] {ts[:16]} — tweet posted: {tweet[:60]}...")

    except Exception as e:
        # Log failure
        log_entry = {
            "timestamp": ts,
            "status": "error",
            "error": str(e),
        }

        PATHS["logs"].mkdir(parents=True, exist_ok=True)
        tweets_log = PATHS["logs"] / "tweets.jsonl"
        with open(tweets_log, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

        print(f"[tweet-log] {ts[:16]} — failed: {e}")
        raise


if __name__ == "__main__":
    run()
