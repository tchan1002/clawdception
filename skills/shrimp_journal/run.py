"""
shrimp-journal — 2-hour narrative consolidation into the daily journal.

Reads recent decisions + sensor data, asks Claude for a narrative entry,
writes to its own timestamped file, and sends to Toby via Telegram.

Usage:
    python3 run.py
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import get_cycle_day
from utils import (
    write_journal_entry,
    call_claude,
    compute_stats,
    fetch_events,
    fetch_notable_events,
    fetch_readings,
    read_decisions_since,
    read_journal,
)
from skills.call_toby.run import call_toby, send_document

# Tool definition for structured journal entry
TOOL = {
    "name": "journal_entry",
    "description": "Write a journal entry for the Media Luna tank covering the past 2 hours",
    "input_schema": {
        "type": "object",
        "properties": {
            "narrative": {
                "type": "string",
                "description": "200-400 word caretaker voice journal entry"
            },
            "key_observations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2-4 key observations from this period"
            },
            "watch_list": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Parameters or conditions to monitor closely"
            },
            "recommended_actions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific, actionable tasks for Toby based on current conditions. Include % for water changes (e.g. 'do a 20% water change'), target values for adjustments (e.g. 'lower heater to 75°F'), and timing (e.g. 'within 24 hours'). Leave empty if nothing needs attention."
            }
        },
        "required": ["narrative", "key_observations", "watch_list", "recommended_actions"]
    }
}


def run():
    ts = datetime.now()
    cycle_day = get_cycle_day()
    window_start = ts - timedelta(hours=6)

    # --- Gather data ---
    readings = fetch_readings(24)  # ~6 hours at 15-min intervals
    decisions = read_decisions_since(window_start)
    events = fetch_events(since=window_start.isoformat(), limit=50)
    notable_events = fetch_notable_events(days=14)
    journal_so_far = read_journal()

    # --- Summarize readings ---
    reading_lines = []
    for field, label, unit in [("temp_f", "Temp", "°F"), ("ph", "pH", ""), ("tds_ppm", "TDS", " ppm")]:
        stats = compute_stats(readings, field)
        if stats:
            reading_lines.append(f"{label}: {stats['mean']}{unit} (min {stats['min']}, max {stats['max']})")
    readings_summary = ", ".join(reading_lines) or "No readings available."

    # --- Summarize decisions ---
    decision_notes = []
    for d in decisions[-12:]:  # last 12 decisions (~6 hours)
        risk = d.get("risk_level", "")
        reasoning = d.get("reasoning", "")[:100]
        decision_notes.append(f"[{risk}] {reasoning}")
    decisions_summary = "\n".join(decision_notes) or "No decisions logged in this window."

    # --- Events ---
    event_lines = []
    for e in events:
        ts_short = e.get("timestamp", "")[:16]
        event_lines.append(f"  [{ts_short}] {e.get('event_type')}: {json.dumps(e.get('data', {}))}")
    events_summary = "\n".join(event_lines) or "No events in this window."

    # --- Notable events (14-day history) ---
    notable_lines = []
    for e in notable_events:
        ts_short = e.get("timestamp", "")[:10]
        notes = e.get("notes", "")
        data = e.get("data", {})
        detail = notes or json.dumps(data) if data else ""
        notable_lines.append(f"  [{ts_short}] {e.get('event_type')}: {detail}")
    notable_summary = "\n".join(notable_lines) or "No notable events in past 14 days."

    # --- Truncate existing journal to save tokens ---
    journal_excerpt = journal_so_far[-600:] if len(journal_so_far) > 600 else journal_so_far

    prompt = f"""Day {cycle_day} of the nitrogen cycle. It is {ts.strftime('%H:%M')}.

You're writing a journal entry covering the past 6 hours in the Media Luna tank.

SENSOR SUMMARY (last 6 hours):
{readings_summary}

AGENT DECISIONS (last 6 hours):
{decisions_summary}

EVENTS (last 6 hours):
{events_summary}

NOTABLE TANK HISTORY (past 14 days):
{notable_summary}

JOURNAL SO FAR TODAY (last portion):
{journal_excerpt or 'Nothing written yet today.'}

Write a journal entry of 200-400 words. This is your internal record — write honestly about what you're observing, what concerns you, what seems fine, what you're curious about. It should read as a thoughtful naturalist's field notes, not a data report. Don't repeat what's already in the journal excerpt. End with a single sentence about your current state of mind regarding the tank.

IMPORTANT: Only refer to physical tank details (plants, substrate, decorations, animal behavior, appearance) that appear explicitly in the events or photos above. Do not invent or assume details from general shrimp tank knowledge. If you haven't been told something is in the tank, it isn't in your record."""

    try:
        result = call_claude(
            messages=[{"role": "user", "content": prompt}],
            skill_name="shrimp-journal",
            tools=[TOOL],
            tool_name=TOOL["name"],
        )
    except Exception as e:
        print(f"[shrimp-journal] Claude call failed: {e} — skipping journal entry")
        return

    # Format the journal entry with narrative, key observations, and watch list
    entry_text = result["narrative"]

    if result.get("key_observations"):
        entry_text += "\n\n**Key Observations:**\n"
        for obs in result["key_observations"]:
            entry_text += f"- {obs}\n"

    if result.get("watch_list"):
        entry_text += "\n**Watch List:**\n"
        for item in result["watch_list"]:
            entry_text += f"- {item}\n"

    recommended_actions = result.get("recommended_actions", [])
    if recommended_actions:
        entry_text += "\n**Recommended Actions:**\n"
        for action in recommended_actions:
            entry_text += f"- {action}\n"

    # --- Write to individual timestamped file ---
    path = write_journal_entry(entry_text, ts=ts)
    print(f"[shrimp-journal] Entry written: {path.name} (Day {cycle_day})")

    # --- Notify Toby ---
    call_toby(
        f"Journal — Day {cycle_day} · {ts.strftime('%Y-%m-%d %H:%M')}",
        urgency="info"
    )
    send_document(path)

    if recommended_actions:
        action_lines = "\n".join(f"• {a}" for a in recommended_actions)
        call_toby(f"Action items:\n{action_lines}", urgency="info")


if __name__ == "__main__":
    run()