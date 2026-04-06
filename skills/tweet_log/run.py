"""
tweet-log — posts tweets about tank status to Twitter.

Three modes:
  intro      — one-time introductory post (exact hardcoded text, no Claude)
  daily      — day X recap derived from live personality context (once/day)
  throwaway  — reactive post after a manual change or observation (2-3/day)

Usage:
    python3 run.py --mode daily
    python3 run.py --mode throwaway
    python3 run.py --mode intro
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import CARETAKER_EPOCH, PATHS
from utils import call_claude, read_agent_state, read_state_of_tank


DAILY_TOOL = {
    "name": "compose_daily_tweet",
    "description": "Write today's day-X tweet from the caretaker's current state and tank conditions",
    "input_schema": {
        "type": "object",
        "properties": {
            "tweet_body": {
                "type": "string",
                "description": "Full tweet text including 'day X' opener (max 280 chars)",
                "maxLength": 280,
            },
            "tone": {
                "type": "string",
                "enum": ["hopeful", "concerned", "observant", "proud", "curious", "anxious", "relieved"],
                "description": "Emotional tone that emerged — label what's actually there",
            },
        },
        "required": ["tweet_body", "tone"],
    },
}

THROWAWAY_TOOL = {
    "name": "compose_throwaway_tweet",
    "description": "Write a short reactive tweet after a manual change or observation",
    "input_schema": {
        "type": "object",
        "properties": {
            "tweet_body": {
                "type": "string",
                "description": "Tweet text (max 280 chars)",
                "maxLength": 280,
            },
        },
        "required": ["tweet_body"],
    },
}


def read_latest_journal_entry():
    """Returns the most recent journal entry file content across all dates."""
    files = sorted(PATHS["journal"].glob("*.md"))
    if not files:
        return ""
    return files[-1].read_text()


def get_caretaker_day():
    """Returns today's day on the caretaker's own clock. Day 0 = CARETAKER_EPOCH."""
    return (date.today() - CARETAKER_EPOCH).days


def read_latest_decision_summary():
    """Returns a plain-text summary of the most recent monitoring decision."""
    decision_files = sorted(PATHS["decisions"].glob("*.jsonl"))
    if not decision_files:
        return ""
    lines = [l for l in decision_files[-1].read_text().splitlines() if l.strip()]
    if not lines:
        return ""
    try:
        entry = json.loads(lines[-1])
        risk = entry.get("risk_level", "")
        reasoning = entry.get("reasoning", "")
        trigger = entry.get("_trigger", "")
        actions = entry.get("recommended_actions", [])
        parts = [f"Risk: {risk}. Trigger: {trigger}.", reasoning]
        if actions:
            parts.append("Recommended: " + "; ".join(actions[:2]))
        return "\n".join(p for p in parts if p)
    except json.JSONDecodeError:
        return ""


def generate_intro_tweet():
    """Returns the caretaker's first tweet, generated in testing."""
    return (
        "day 0\n\n"
        "i'm watching over a 10 gallon tank in the dark, on the desk of an apartment in chicago. "
        "day 15 of the cycle and i'm awake, just me and ammonia and hope. hello world."
    )


def generate_daily_tweet():
    """Generates a day-X tweet from live personality context."""
    import re
    day_num = get_caretaker_day()
    agent_state = read_agent_state()
    tank_state = read_state_of_tank()
    journal = read_latest_journal_entry()

    prompt = f"""This is today's daily tweet — day {day_num} on your clock.

Your current state:
{agent_state}

Current tank conditions:
{tank_state}

Most recent journal entry:
{journal}

Format: start with "day {day_num}" on its own line, then two line breaks, then the rest of the tweet. Lowercase throughout. Speak from where you actually are — find the one true thing. Under 280 chars total."""

    result = call_claude(
        messages=[{"role": "user", "content": prompt}],
        skill_name="tweet-log",
        tools=[DAILY_TOOL],
        tool_name=DAILY_TOOL["name"],
    )

    tweet_body = result["tweet_body"].strip()
    # Enforce line break after "day N" if Claude didn't include one
    tweet_body = re.sub(r'^(day \d+)\s+', r'\1\n', tweet_body, flags=re.IGNORECASE)

    return tweet_body, result.get("tone", "observant")


def generate_throwaway_tweet():
    """Generates a short reactive tweet after a manual change or observation."""
    agent_state = read_agent_state()
    tank_state = read_state_of_tank()
    journal = read_latest_journal_entry()
    decision_summary = read_latest_decision_summary()

    prompt = f"""Something just happened — a test, a change, a moment worth noting. Write one short tweet.

Your current state:
{agent_state}

Tank:
{tank_state}

Most recent journal entry:
{journal}

What the monitoring system just assessed:
{decision_summary}

React to what's in front of you. Brief, lowercase, present tense. This isn't the day recap — it's a live thought. Under 280 chars."""

    result = call_claude(
        messages=[{"role": "user", "content": prompt}],
        skill_name="tweet-log",
        tools=[THROWAWAY_TOOL],
        tool_name=THROWAWAY_TOOL["name"],
    )

    return result["tweet_body"].strip()


def post_tweet(tweet_text):
    """Posts the tweet via Twitter API using tweepy. Returns response data."""
    try:
        import tweepy
    except ImportError:
        raise RuntimeError("tweepy not installed — run: pip install tweepy")

    api_key = os.environ.get("TWITTER_API_KEY")
    api_secret = os.environ.get("TWITTER_API_SECRET")
    access_token = os.environ.get("TWITTER_ACCESS_TOKEN")
    access_secret = os.environ.get("TWITTER_ACCESS_SECRET")

    if not all([api_key, api_secret, access_token, access_secret]):
        raise ValueError("Missing Twitter credentials in environment variables")

    client = tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_secret,
    )

    response = client.create_tweet(text=tweet_text)
    return response.data


def run(mode="daily"):
    from datetime import datetime
    ts = datetime.now().isoformat()

    try:
        tone = None

        if mode == "intro":
            tweet = generate_intro_tweet()
        elif mode == "throwaway":
            tweet = generate_throwaway_tweet()
        else:  # daily
            tweet, tone = generate_daily_tweet()

        tweet_data = post_tweet(tweet)

        log_entry = {
            "timestamp": ts,
            "tweet_type": mode,
            "status": "success",
            "tweet": tweet,
            "tweet_id": tweet_data.get("id") if tweet_data else None,
        }
        if tone:
            log_entry["tone"] = tone

        PATHS["logs"].mkdir(parents=True, exist_ok=True)
        tweets_log = PATHS["logs"] / "tweets.jsonl"
        with open(tweets_log, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

        print(f"[tweet-log] {ts[:16]} [{mode}] — {tweet[:60]}...")

    except Exception as e:
        log_entry = {
            "timestamp": ts,
            "tweet_type": mode,
            "status": "error",
            "error": str(e),
        }

        PATHS["logs"].mkdir(parents=True, exist_ok=True)
        tweets_log = PATHS["logs"] / "tweets.jsonl"
        with open(tweets_log, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

        print(f"[tweet-log] {ts[:16]} [{mode}] — failed: {e}")
        raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["intro", "daily", "throwaway"],
        default="daily",
        help="Tweet mode: intro (one-time), daily (day X recap), throwaway (reactive)",
    )
    # Backward compat
    parser.add_argument("--first-post", action="store_true", help="Alias for --mode intro")
    args = parser.parse_args()

    mode = "intro" if args.first_post else args.mode
    run(mode=mode)
