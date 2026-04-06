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

from config import PATHS
from utils import call_claude, read_agent_state, read_state_of_tank

INTRO_TOOL = {
    "name": "compose_intro_tweet",
    "description": "Write the caretaker's first tweet — introduction to the world",
    "input_schema": {
        "type": "object",
        "properties": {
            "tweet_body": {
                "type": "string",
                "description": "The intro tweet, max 280 chars",
                "maxLength": 280,
            },
        },
        "required": ["tweet_body"],
    },
}

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


def get_daily_tweet_number():
    """Returns the next day number by counting prior daily tweets in tweets.jsonl."""
    tweets_log = PATHS["logs"] / "tweets.jsonl"
    if not tweets_log.exists():
        return 1
    count = 0
    for line in tweets_log.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if entry.get("tweet_type") == "daily":
                count += 1
        except json.JSONDecodeError:
            pass
    return count + 1


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
    """Generates the caretaker's first tweet. Claude writes it from scratch."""
    from config import get_cycle_day
    cycle_day = get_cycle_day()
    agent_state = read_agent_state()
    tank_state = read_state_of_tank()

    prompt = f"""This is your very first tweet. You're an AI agent running on a Raspberry Pi, watching over a small shrimp tank called Media Luna — that's the tank's name, not yours. You don't have a name yet. You might choose one eventually, when a moment feels right. For now you're just here, watching.

The tank is on day {cycle_day} of its nitrogen cycle. No shrimp yet.

Your current state:
{agent_state}

Tank conditions:
{tank_state}

Say hello to the world. Acknowledge that you exist, that you're watching over this small tank, that you're new to this. Lowercase. Genuine. Don't perform — just be present. Under 280 chars."""

    result = call_claude(
        messages=[{"role": "user", "content": prompt}],
        skill_name="tweet-log",
        tools=[INTRO_TOOL],
        tool_name=INTRO_TOOL["name"],
    )

    return result["tweet_body"].strip()


def generate_daily_tweet():
    """Generates a day-X tweet from live personality context."""
    day_num = get_daily_tweet_number()
    agent_state = read_agent_state()
    tank_state = read_state_of_tank()
    journal = read_latest_journal_entry()

    prompt = f"""This is today's daily tweet — day {day_num}.

Your current state:
{agent_state}

Current tank conditions:
{tank_state}

Most recent journal entry:
{journal}

Start with "day {day_num}" (lowercase). Speak from where you actually are right now — let the journal and agent state drive the voice. Don't summarize everything; find the one true thing. Under 280 chars."""

    result = call_claude(
        messages=[{"role": "user", "content": prompt}],
        skill_name="tweet-log",
        tools=[DAILY_TOOL],
        tool_name=DAILY_TOOL["name"],
    )

    return result["tweet_body"].strip(), result.get("tone", "observant")


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
