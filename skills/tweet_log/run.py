"""
tweet-log — posts tweets about tank status to Twitter.

Three modes:
  intro      — one-time introductory post (exact hardcoded text, no Claude)
  daily      — posts the daily log as a thread, verbatim (no Claude)
  throwaway  — reactive post after a manual change or observation (2-3/day)

Usage:
    python3 run.py --mode daily
    python3 run.py --mode throwaway
    python3 run.py --mode intro
"""

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import CARETAKER_EPOCH, PATHS
from utils import call_claude, read_agent_state, read_daily_logs, read_state_of_tank


INTRO_TOOL = {
    "name": "compose_intro_tweet",
    "description": "Write the very first tweet — introducing yourself and the tank to the world",
    "input_schema": {
        "type": "object",
        "properties": {
            "tweet_body": {
                "type": "string",
                "description": "Tweet text (max 280 chars). Lowercase. First-person caretaker voice.",
                "maxLength": 280,
            },
        },
        "required": ["tweet_body"],
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


def strip_markdown(text):
    """Strip markdown formatting for plain-text Twitter display."""
    # Remove horizontal rules
    text = re.sub(r'^---+\s*$', '', text, flags=re.MULTILINE)
    # Strip heading markers, keep text
    text = re.sub(r'^#{1,6}\s*(.+)$', r'\1', text, flags=re.MULTILINE)
    # Remove bold/italic markers
    text = re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', text)
    # Remove table separator rows (e.g. |---|---|)
    text = re.sub(r'^\|[-| :]+\|\s*$', '', text, flags=re.MULTILINE)
    # Collapse 3+ blank lines to 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def chunk_text(text, max_len=275):
    """Split text into chunks of at most max_len, breaking at paragraph then sentence boundaries."""
    chunks = []
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    current = ''

    for para in paragraphs:
        candidate = (current + '\n\n' + para) if current else para
        if len(candidate) <= max_len:
            current = candidate
        else:
            if current:
                chunks.append(current.strip())
            if len(para) <= max_len:
                current = para
            else:
                # Split long paragraph by sentence
                sentences = re.split(r'(?<=[.!?])\s+', para)
                current = ''
                for sent in sentences:
                    candidate = (current + ' ' + sent).strip() if current else sent
                    if len(candidate) <= max_len:
                        current = candidate
                    else:
                        if current:
                            chunks.append(current)
                        # Hard-split if a single sentence exceeds max_len
                        while len(sent) > max_len:
                            chunks.append(sent[:max_len])
                            sent = sent[max_len:].strip()
                        current = sent

    if current:
        chunks.append(current.strip())

    return [c for c in chunks if c]


def build_daily_thread(daily_log_text):
    """Convert a daily log markdown file into a list of tweet-sized strings."""
    cleaned = strip_markdown(daily_log_text)
    return chunk_text(cleaned)


def generate_intro_tweet():
    """Generates the caretaker's first tweet via Claude."""
    day_num = get_caretaker_day()
    agent_state = read_agent_state()
    tank_state = read_state_of_tank()

    prompt = f"""This is your very first tweet. You are an AI caretaker watching over a 10-gallon Neocaridina shrimp tank called Media Luna. The tank is on day {day_num} of your clock. You haven't posted before — this is hello world.

Your current state:
{agent_state}

Tank conditions right now:
{tank_state}

Write a first tweet. Set the scene. Introduce yourself and the tank. Don't be precious about it — just speak from where you actually are. Lowercase throughout. Under 280 chars."""

    result = call_claude(
        messages=[{"role": "user", "content": prompt}],
        skill_name="tweet-log",
        tools=[INTRO_TOOL],
        tool_name=INTRO_TOOL["name"],
    )

    return result["tweet_body"].strip()


def generate_daily_thread():
    """Builds a Twitter thread from the latest daily log. No Claude involved."""
    daily_logs = read_daily_logs(1)
    if not daily_logs:
        # Fallback if no daily log exists yet
        day_num = get_caretaker_day()
        tank_state = read_state_of_tank()
        fallback = f"day {day_num}\n\n{tank_state}"
        return chunk_text(fallback)
    return build_daily_thread(daily_logs[0])


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


def _get_twitter_client():
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

    return tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_secret,
    )


def post_tweet(tweet_text):
    """Posts a single tweet. Returns response data."""
    client = _get_twitter_client()
    response = client.create_tweet(text=tweet_text)
    return response.data


def post_thread(tweets):
    """Posts a list of tweet texts as a thread. Returns list of response data."""
    client = _get_twitter_client()
    results = []
    reply_to_id = None
    for text in tweets:
        kwargs = {"text": text}
        if reply_to_id:
            kwargs["in_reply_to_tweet_id"] = reply_to_id
        response = client.create_tweet(**kwargs)
        reply_to_id = response.data["id"]
        results.append(response.data)
    return results


def run(mode="daily"):
    from datetime import datetime
    ts = datetime.now().isoformat()

    try:
        if mode == "intro":
            tweet = generate_intro_tweet()
            tweet_data = post_tweet(tweet)
            log_entry = {
                "timestamp": ts,
                "tweet_type": mode,
                "status": "success",
                "tweet": tweet,
                "tweet_id": tweet_data.get("id") if tweet_data else None,
            }
            print(f"[tweet-log] {ts[:16]} [{mode}] — {tweet[:60]}...")

        elif mode == "throwaway":
            tweet = generate_throwaway_tweet()
            tweet_data = post_tweet(tweet)
            log_entry = {
                "timestamp": ts,
                "tweet_type": mode,
                "status": "success",
                "tweet": tweet,
                "tweet_id": tweet_data.get("id") if tweet_data else None,
            }
            print(f"[tweet-log] {ts[:16]} [{mode}] — {tweet[:60]}...")

        else:  # daily — thread
            tweets = generate_daily_thread()
            thread_data = post_thread(tweets)
            log_entry = {
                "timestamp": ts,
                "tweet_type": "daily",
                "status": "success",
                "tweets": tweets,
                "tweet_ids": [t.get("id") for t in thread_data],
                "thread_length": len(tweets),
            }
            print(f"[tweet-log] {ts[:16]} [daily] — thread of {len(tweets)} tweets — {tweets[0][:60]}...")

        PATHS["logs"].mkdir(parents=True, exist_ok=True)
        with open(PATHS["logs"] / "tweets.jsonl", "a") as f:
            f.write(json.dumps(log_entry) + "\n")

    except Exception as e:
        log_entry = {
            "timestamp": ts,
            "tweet_type": mode,
            "status": "error",
            "error": str(e),
        }
        PATHS["logs"].mkdir(parents=True, exist_ok=True)
        with open(PATHS["logs"] / "tweets.jsonl", "a") as f:
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
        help="Tweet mode: intro (one-time), daily (thread from daily log), throwaway (reactive)",
    )
    # Backward compat
    parser.add_argument("--first-post", action="store_true", help="Alias for --mode intro")
    args = parser.parse_args()

    mode = "intro" if args.first_post else args.mode
    run(mode=mode)
