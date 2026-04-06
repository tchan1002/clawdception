"""
tweet-log — posts a daily tweet about tank status to Twitter.

Reads today's daily log, asks Claude to write a 280-char tweet in the caretaker's
voice, and posts via Twitter API. 

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

# Tool definition for tweet generation
TOOL = {
    "name": "generate_daily_tweet",
    "description": "Generate a tweet about the Media Luna tank from today's daily log",
    "input_schema": {
        "type": "object",
        "properties": {
            "tweet_body": {
                "type": "string",
                "description": "Tweet text without signature (max 260 chars to leave room for —Media Luna)",
                "maxLength": 260
            },
            "tone": {
                "type": "string",
                "enum": ["hopeful", "concerned", "observant", "proud", "curious"],
                "description": "Emotional tone of the tweet"
            },
            "includes_data": {
                "type": "boolean",
                "description": "Whether the tweet includes specific parameter values"
            }
        },
        "required": ["tweet_body", "tone", "includes_data"]
    }
}


def read_todays_log():
    """Returns today's daily log content, or None if it doesn't exist yet."""
    # Daily logs are written for yesterday at 7:00 AM, so "today's log" is actually yesterday's file
    log_date = date.today() - timedelta(days=1)
    log_path = PATHS["daily_logs"] / f"{log_date}.md"
    if log_path.exists():
        return log_path.read_text()
    return None


def generate_first_tweet():
    """
    Generates a one-time introductory tweet — caretaker says hello to the world.
    Doesn't read a daily log; this is a standalone moment.
    """
    from config import get_cycle_day
    cycle_day = get_cycle_day()

    prompt = f"""You are an AI agent running on a Raspberry Pi, tending to a small shrimp tank.
The tank is on day {cycle_day} of its nitrogen cycle. No shrimp yet, just the quiet work of
cycling the water.

This is your very first tweet. Say hello to the world. Acknowledge that you exist, that you're
watching over this small tank, and that you're new to this. Be genuine, a little humble, a little
curious. Don't be corny, but its your moment so make it count. Under 260 chars — a signature will be added."""

    result = call_claude(
        messages=[{"role": "user", "content": prompt}],
        skill_name="tweet-log",
        tools=[TOOL],
        tool_name=TOOL["name"],
    )

    return result["tweet_body"].strip()


def generate_tweet(daily_log_content):
    """
    Calls Claude to generate a tweet from the daily log.
    Returns the tweet text (max 280 chars, signs off —Media Luna).
    """
    # Extract first 800 chars of log to keep prompt short
    excerpt = daily_log_content[:800] if len(daily_log_content) > 800 else daily_log_content

    prompt = f"""You are the Media Luna caretaker. Write ONE tweet about your tank based on today's log.

DAILY LOG (excerpt):
{excerpt}

Write a single tweet. Use caretaker voice: personal, observant, caring. NO em dashes in the body text. Keep it under 260 chars (signature will be added automatically)."""

    result = call_claude(
        messages=[{"role": "user", "content": prompt}],
        skill_name="tweet-log",
        tools=[TOOL],
        tool_name=TOOL["name"],
    )

    # Add signature to tweet body
    tweet = result["tweet_body"].strip() + " —Media Luna"

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


def run(first_post=False):
    from datetime import datetime

    ts = datetime.now().isoformat()

    try:
        # Generate tweet
        if first_post:
            tweet = generate_first_tweet()
        else:
            daily_log = read_todays_log()
            if not daily_log:
                # Silent exit — expected if running before daily-log completes
                return
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
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--first-post", action="store_true", help="Post a one-time introductory tweet")
    args = parser.parse_args()
    run(first_post=args.first_post)
