"""
Shared utility functions for all Media Luna agent skills.
All skills import from here — keep this stable and well-tested.
"""

import json
import os
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from config import API_BASE, CLAUDE_MODEL, PATHS, SYSTEM_PROMPT, get_cycle_day


# ---------------------------------------------------------------------------
# Sensor data
# ---------------------------------------------------------------------------

def fetch_latest_reading():
    """Returns the latest sensor reading as a dict, or None on failure."""
    try:
        r = requests.get(f"{API_BASE}/api/sensors/latest", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        _log_error("fetch_latest_reading", e)
        return None


def fetch_readings(n=96):
    """Returns the last N sensor readings as a list of dicts (newest first)."""
    try:
        r = requests.get(f"{API_BASE}/api/sensors", params={"limit": n}, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        _log_error("fetch_readings", e)
        return []


def compute_stats(readings, field):
    """Returns min/max/mean/first/last for a numeric field across a list of readings."""
    values = [r[field] for r in readings if r.get(field) is not None]
    if not values:
        return None
    return {
        "min": round(min(values), 3),
        "max": round(max(values), 3),
        "mean": round(sum(values) / len(values), 3),
        "first": round(values[-1], 3),   # oldest (list is newest-first)
        "last": round(values[0], 3),     # most recent
        "count": len(values),
    }


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def fetch_events(since=None, event_type=None, limit=50):
    """
    Returns events from the API, filtered by since (ISO timestamp), event_type, or limit.
    """
    try:
        params = {"limit": limit}
        if since:
            params["since"] = since
        if event_type:
            params["type"] = event_type
        r = requests.get(f"{API_BASE}/api/events", params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        _log_error("fetch_events", e)
        return []


def hours_since_last_water_test():
    """
    Returns hours elapsed since the most recent water_test event, or None if never.
    """
    events = fetch_events(event_type="water_test", limit=1)
    if not events:
        return None
    last_ts = events[0].get("timestamp")
    if not last_ts:
        return None
    try:
        last_dt = datetime.fromisoformat(last_ts)
        delta = datetime.now() - last_dt
        return delta.total_seconds() / 3600
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------

def read_journal(target_date=None):
    """
    Returns the full text of a journal file for the given date (defaults to today).
    Returns empty string if no journal exists yet.
    """
    if target_date is None:
        target_date = date.today()
    journal_path = PATHS["journal"] / f"{target_date}.md"
    if journal_path.exists():
        return journal_path.read_text()
    return ""


def append_journal(entry_text, target_date=None):
    """Appends a timestamped entry to the daily journal file."""
    if target_date is None:
        target_date = date.today()
    journal_path = PATHS["journal"] / f"{target_date}.md"
    PATHS["journal"].mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%H:%M")
    with open(journal_path, "a") as f:
        f.write(f"\n## {ts}\n\n{entry_text.strip()}\n")


# ---------------------------------------------------------------------------
# Daily logs
# ---------------------------------------------------------------------------

def read_daily_logs(n=3):
    """
    Returns the last N daily log file contents as a list of strings (most recent first).
    Skips missing files silently.
    """
    logs = []
    today = date.today()
    for i in range(1, n + 10):   # scan back far enough to find N existing logs
        d = today - timedelta(days=i)
        path = PATHS["daily_logs"] / f"{d}.md"
        if path.exists():
            logs.append(path.read_text())
        if len(logs) >= n:
            break
    return logs


def write_daily_log(content, log_date=None):
    """
    Writes an immutable daily log. Will NOT overwrite if the file already exists.
    Returns the path written, or None if skipped.
    """
    if log_date is None:
        log_date = date.today() - timedelta(days=1)  # default: yesterday
    PATHS["daily_logs"].mkdir(parents=True, exist_ok=True)
    path = PATHS["daily_logs"] / f"{log_date}.md"
    if path.exists():
        print(f"[daily-log] Log for {log_date} already exists — skipping write.")
        return None
    path.write_text(content)
    return path


# ---------------------------------------------------------------------------
# State files
# ---------------------------------------------------------------------------

def read_state_of_tank():
    path = PATHS["state_of_tank"]
    if path.exists():
        return path.read_text()
    return ""


def write_state_of_tank(content):
    PATHS["state_of_tank"].write_text(content)


def read_agent_state():
    path = PATHS["agent_state"]
    if path.exists():
        return path.read_text()
    return ""


def write_agent_state(content):
    PATHS["agent_state"].write_text(content)


# ---------------------------------------------------------------------------
# Decision logging
# ---------------------------------------------------------------------------

def log_decision(decision_dict):
    """Appends a decision dict to today's decisions JSONL file."""
    PATHS["decisions"].mkdir(parents=True, exist_ok=True)
    today = date.today()
    path = PATHS["decisions"] / f"{today}.jsonl"
    entry = {**decision_dict, "_logged_at": datetime.now().isoformat()}
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def read_decisions_since(since_dt):
    """
    Returns all decision log entries since a given datetime, across multiple day files.
    """
    entries = []
    d = since_dt.date()
    today = date.today()
    while d <= today:
        path = PATHS["decisions"] / f"{d}.jsonl"
        if path.exists():
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    logged_at = entry.get("_logged_at", "")
                    if logged_at >= since_dt.isoformat():
                        entries.append(entry)
                except json.JSONDecodeError:
                    pass
        d = d + timedelta(days=1)
    return entries


# ---------------------------------------------------------------------------
# Claude API
# ---------------------------------------------------------------------------

def call_claude(messages, system=None, max_tokens=1500):
    """
    Thin wrapper around the Anthropic SDK.
    Returns the response text, or raises on failure (callers should catch).
    """
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system or SYSTEM_PROMPT,
        messages=messages,
    )
    return response.content[0].text


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _log_error(context, exc):
    ts = datetime.now().isoformat()
    print(f"[{ts}] ERROR in {context}: {exc}")
    traceback.print_exc()
