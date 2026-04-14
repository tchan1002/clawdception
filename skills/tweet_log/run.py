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


SECTIONS_TO_STRIP = ["What Happened", "What I'm Watching", "Suggested Actions"]


def remove_sections(text, names):
    """Remove named ## sections from markdown before formatting."""
    for name in names:
        pattern = rf'## {re.escape(name)}\n.*?(?=\n---|\Z)'
        text = re.sub(pattern, '', text, flags=re.DOTALL)
    return text


def collapse_table_rows(text):
    """Compress markdown tables into compact single lines. Run before strip_markdown.

    Converts:
      | Parameter   | Avg   | Min → Max         | Day Δ      |
      |-------------|-------|-------------------|------------|
      | Temperature | 78.15°F | 77.79 → 78.46°F | −0.22°F ↓ |
      | pH          | 6.47    | 6.40 → 6.56      | −0.09 ↓   |
    Into:
      temperature 78.15°f (77.79–78.46°f, −0.22°f ↓) · ph 6.47 (6.40–6.56, −0.09 ↓)
    """
    lines = text.split('\n')
    result = []
    header = None
    in_table = False
    data_rows = []

    NITROGEN_PARAMS = {"ammonia", "nitrite", "nitrate"}

    def flush_table():
        nonlocal header, in_table, data_rows
        nitrogen = []
        for row in data_rows:
            if len(row) >= 4:
                param, avg, minmax, delta = row[0], row[1], row[2], row[3]
                minmax = minmax.replace(' → ', '–')
                if param.lower() in NITROGEN_PARAMS:
                    nitrogen.append(f"{param} {avg}")
                else:
                    result.append(f"{param} | {avg} | {minmax} | {delta}")
            elif row:
                result.append(' '.join(row))
        if nitrogen:
            result.append(' | '.join(nitrogen))
        header = None
        in_table = False
        data_rows = []

    for line in lines:
        stripped = line.strip()
        if re.match(r'^\|[-| :]+\|', stripped):
            # Separator row — confirms previous pipe row was the header
            in_table = True
        elif stripped.startswith('|'):
            cells = [c.strip() for c in stripped.split('|') if c.strip()]
            if not in_table:
                # Before separator: this is the header row
                header = cells
            else:
                data_rows.append(cells)
        else:
            if data_rows:
                flush_table()
            elif header is not None:
                # Header with no data — treat as normal line
                result.append(line)
                header = None
                in_table = False
            result.append(line)

    if data_rows:
        flush_table()

    return '\n'.join(result)


def merge_short_chunks(chunks, max_len=275):
    """Merge orphaned short chunks (e.g. bare section labels) into adjacent content."""
    merged = []
    i = 0
    while i < len(chunks):
        chunk = chunks[i]
        if len(chunk) < 50 and i + 1 < len(chunks):
            combined = chunk + '\n\n' + chunks[i + 1]
            if len(combined) <= max_len:
                merged.append(combined)
                i += 2
                continue
        merged.append(chunk)
        i += 1
    return merged


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
    """Convert a daily log markdown file into a list of tweet-sized strings.

    Strips action-oriented sections (What Happened, What I'm Watching, Suggested Actions) —
    those are preserved in the log but not needed in the public thread.
    Numbers table is compressed to a single compact line to save tweets.
    The first tweet always starts with 'day N' on its own line followed by
    two line breaks, matching the established tweet format.
    """
    text = remove_sections(daily_log_text, SECTIONS_TO_STRIP)
    text = collapse_table_rows(text)  # before strip_markdown while structure is intact
    cleaned = strip_markdown(text).lower()
    # Normalize title line: "day 14 — 2026-04-04 — some title" → "day 14"
    cleaned = re.sub(r'^day\s+(\d+)\s*[—–-].*$', r'day \1', cleaned, count=1, flags=re.MULTILINE)
    return merge_short_chunks(chunk_text(cleaned))


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


def _get_twitter_clients():
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

    v2 = tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_secret,
    )
    auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_secret)
    v1 = tweepy.API(auth)
    return v2, v1


def get_latest_photo():
    """Returns path to most recent tank photo, or None."""
    photos_dir = PATHS["snapshots"] / "photos"
    photos = sorted(photos_dir.glob("*.jpg"))
    return str(photos[-1]) if photos else None


def post_tweet(tweet_text):
    """Posts a single tweet. Returns response data."""
    client, _ = _get_twitter_clients()
    response = client.create_tweet(text=tweet_text)
    return response.data


def post_thread(tweets, photo_path=None):
    """Posts a list of tweet texts as a thread. Attaches photo to first tweet if provided."""
    client, v1 = _get_twitter_clients()
    results = []
    reply_to_id = None
    for i, text in enumerate(tweets):
        kwargs = {"text": text}
        if reply_to_id:
            kwargs["in_reply_to_tweet_id"] = reply_to_id
        if i == 0 and photo_path:
            media = v1.media_upload(photo_path)
            kwargs["media_ids"] = [media.media_id]
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
            photo = get_latest_photo()
            thread_data = post_thread(tweets, photo_path=photo)
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
