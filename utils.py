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

from config import (
    API_BASE,
    CLAUDE_MODEL,
    JOURNAL_MAX_CHARS,
    PATHS,
    SKILL_MAX_TOKENS,
    SKILL_MODELS,
    STALE_READING_THRESHOLD_MINUTES,
    SYSTEM_PROMPT,
    get_cycle_day,
)


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

INTERNAL_EVENT_TYPES = {"smoke_test", "equipment_check"}

NOTABLE_EVENT_TYPES = {
    "shrimp_added", "water_change", "water_test", "plant_addition",
    "maintenance", "heater_adjust", "dosing", "feeding",
    "owner_note", "owner_photo", "correction", "system_update",
}


def post_event(event_type, notes="", data=None):
    """Posts an event to the API."""
    try:
        payload = {"event_type": event_type, "notes": notes, "data": data or {}}
        r = requests.post(f"{API_BASE}/api/events", json=payload, timeout=10)
        r.raise_for_status()
    except Exception as e:
        _log_error("post_event", e)


def fetch_events(since=None, event_type=None, limit=50):
    """
    Returns events from the API, filtered by since (ISO timestamp), event_type, or limit.
    Internal event types (smoke_test) are always excluded.
    """
    try:
        params = {"limit": limit}
        if since:
            params["since"] = since
        if event_type:
            params["type"] = event_type
        r = requests.get(f"{API_BASE}/api/events", params=params, timeout=10)
        r.raise_for_status()
        return [e for e in r.json() if e.get("event_type") not in INTERNAL_EVENT_TYPES]
    except Exception as e:
        _log_error("fetch_events", e)
        return []


def fetch_notable_events(days=14, limit=30):
    """
    Returns notable tank events (water changes, tests, shrimp additions, etc.)
    from the past N days. Excludes observations and internal events.
    Used to give agents persistent memory of significant tank history.
    """
    since = (datetime.now() - timedelta(days=days)).isoformat()
    events = fetch_events(since=since, limit=limit * 2)
    notable = [
        e for e in events
        if e.get("event_type") in NOTABLE_EVENT_TYPES
        and e.get("event_type") != "observation"
    ]
    return notable[:limit]


def format_recent_events(events):
    if not events:
        return "None in past 24 hours."
    lines = []
    for e in events[:8]:
        ts = e.get("timestamp", "")[:16]
        notes = e.get("notes", "")
        data_str = notes or json.dumps({k: v for k, v in e.get("data", {}).items() if k != "source"})
        if len(data_str) > 120:
            data_str = data_str[:120] + "…"
        lines.append(f"  [{ts}] {e.get('event_type')}: {data_str}")
    return "\n".join(lines)


def format_notable_events(events):
    if not events:
        return "None in past 14 days."
    lines = []
    for e in events:
        ts = e.get("timestamp", "")[:10]
        notes = e.get("notes", "")
        data = e.get("data", {})
        detail = notes or (json.dumps(data) if data else "")
        lines.append(f"  [{ts}] {e.get('event_type')}: {detail}")
    return "\n".join(lines)


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


def hours_since_last_photo():
    """
    Returns hours elapsed since the most recent owner_photo event, or None if never.
    """
    events = fetch_events(event_type="owner_photo", limit=1)
    if not events:
        return None
    last_ts = events[0].get("timestamp")
    if not last_ts:
        return None
    try:
        last_dt = datetime.fromisoformat(last_ts)
        return (datetime.now() - last_dt).total_seconds() / 3600
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------

def read_journal(target_date=None, max_chars=None):
    """
    Reads all journal entries for a given date (defaults to today).
    Concatenates individual timestamped files (YYYY-MM-DD-HHMM.md) in chronological order.
    """
    if target_date is None:
        target_date = date.today()
    if max_chars is None:
        max_chars = JOURNAL_MAX_CHARS

    entry_files = sorted(PATHS["journal"].glob(f"{target_date}-*.md"))
    text = "\n".join(f.read_text() for f in entry_files)

    if len(text) > max_chars:
        return text[-max_chars:]
    return text


def write_journal_entry(entry_text, ts=None):
    """
    Writes a single journal entry to its own timestamped file.
    Filename: journal/YYYY-MM-DD-HHMM.md
    """
    if ts is None:
        ts = datetime.now()
    PATHS["journal"].mkdir(parents=True, exist_ok=True)
    filename = f"{ts.strftime('%Y-%m-%d-%H%M')}.md"
    path = PATHS["journal"] / filename
    header = f"## {ts.strftime('%H:%M')}\n\n"
    path.write_text(header + entry_text.strip() + "\n")
    return path

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
    # Archive a dated snapshot before overwriting
    history_dir = PATHS["agent_state_history"]
    history_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d-%H%M")
    archive_path = history_dir / f"{today}.md"
    archive_path.write_text(content)
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

def call_claude(messages, system=None, max_tokens=None, skill_name=None, tools=None, tool_name=None):
    """
    Thin wrapper around the Anthropic SDK.
    Routes to the correct model and max_tokens based on skill_name.
    Logs token usage to logs/spend.jsonl.

    When tools and tool_name are provided, uses tool_use mode and returns
    the tool input as a dict. Otherwise returns response text.
    """
    import anthropic

    # Check API key presence
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    # Route model and max_tokens by skill name
    model = CLAUDE_MODEL
    if skill_name and skill_name in SKILL_MODELS:
        model = SKILL_MODELS[skill_name]
    if max_tokens is None:
        if skill_name and skill_name in SKILL_MAX_TOKENS:
            max_tokens = SKILL_MAX_TOKENS[skill_name]
        else:
            max_tokens = 1500  # default fallback

    client = anthropic.Anthropic(api_key=api_key)

    # Build API call parameters
    api_params = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system or SYSTEM_PROMPT,
        "messages": messages,
    }

    # Add tool_use parameters if provided
    if tools and tool_name:
        api_params["tools"] = tools
        api_params["tool_choice"] = {"type": "tool", "name": tool_name}

    response = client.messages.create(**api_params)

    # Log token usage
    usage = response.usage
    spend_entry = {
        "timestamp": datetime.now().isoformat(),
        "skill": skill_name or "unknown",
        "model": model,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.input_tokens + usage.output_tokens,
    }
    PATHS["logs"].mkdir(parents=True, exist_ok=True)
    spend_log = PATHS["logs"] / "spend.jsonl"
    with open(spend_log, "a") as f:
        f.write(json.dumps(spend_entry) + "\n")

    # Return tool input dict if using tool_use, otherwise text
    if tools and tool_name:
        return response.content[0].input
    else:
        return response.content[0].text


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

class SkillLock:
    """
    Context manager for preventing overlapping cron executions of the same skill.
    Uses fcntl file locking. Non-blocking — raises if lock is held by another process.
    """
    def __init__(self, skill_name):
        import fcntl
        self.skill_name = skill_name
        self.lock_path = PATHS["logs"] / f"{skill_name}.lock"
        self.lock_file = None
        self.fcntl = fcntl

    def __enter__(self):
        PATHS["logs"].mkdir(parents=True, exist_ok=True)
        self.lock_file = open(self.lock_path, "w")
        try:
            self.fcntl.flock(self.lock_file.fileno(), self.fcntl.LOCK_EX | self.fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock_file.close()
            raise RuntimeError(f"[{self.skill_name}] Lock held by another process — skipping")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.lock_file:
            self.fcntl.flock(self.lock_file.fileno(), self.fcntl.LOCK_UN)
            self.lock_file.close()


def parse_json_response(response_text):
    """
    Parses JSON from Claude response, stripping markdown fences if present.
    Logs parse failures to logs/ and raises JSONDecodeError on failure.
    """
    clean = response_text.strip()
    if clean.startswith("```"):
        lines = clean.split("\n")
        # Remove first line (```json or ```) and last line (```)
        clean = "\n".join(lines[1:-1]) if len(lines) > 2 else clean
        clean = clean.strip()

    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        # Log the failure
        PATHS["logs"].mkdir(parents=True, exist_ok=True)
        fail_log = PATHS["logs"] / "parse_failures.jsonl"
        entry = {
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "response_text": response_text[:500],
        }
        with open(fail_log, "a") as f:
            f.write(json.dumps(entry) + "\n")
        raise


def is_reading_stale(reading):
    """
    Returns True if the reading is older than STALE_READING_THRESHOLD_MINUTES
    or if reading is None. Returns False if reading is fresh.
    """
    if reading is None:
        return True
    timestamp = reading.get("timestamp")
    if not timestamp:
        return True
    try:
        reading_dt = datetime.fromisoformat(timestamp)
        age_minutes = (datetime.now() - reading_dt).total_seconds() / 60
        return age_minutes > STALE_READING_THRESHOLD_MINUTES
    except (ValueError, TypeError):
        return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _log_error(context, exc):
    ts = datetime.now().isoformat()
    print(f"[{ts}] ERROR in {context}: {exc}")
    traceback.print_exc()
