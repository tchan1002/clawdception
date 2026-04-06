"""
daily-log — morning summary written by the agent for Toby to read.

Runs at 7:00 AM, summarizes yesterday. Writes an immutable daily log,
updates state_of_tank.md and agent_state.md, and pings Toby via call-toby.

Usage:
    python3 run.py                        # log for yesterday
    python3 run.py --date 2026-03-30      # log for a specific date
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import PATHS, get_cycle_day
from utils import (
    call_claude,
    compute_stats,
    fetch_events,
    fetch_readings,
    read_agent_state,
    read_daily_logs,
    read_journal,
    read_state_of_tank,
    write_agent_state,
    write_daily_log,
    write_state_of_tank,
    read_decisions_since,
)
from skills.call_toby.run import call_toby, send_document

TEMPLATE_PATH = Path(__file__).parent / "template.md"


def fetch_day_readings(target_date):
    """Returns all sensor readings for a specific date."""
    readings = fetch_readings(200)
    date_str = str(target_date)
    return [r for r in readings if r.get("timestamp", "").startswith(date_str)]


def fetch_day_events(target_date):
    """Returns all events for a specific date."""
    start = datetime.combine(target_date, datetime.min.time()).isoformat()
    end = datetime.combine(target_date + timedelta(days=1), datetime.min.time()).isoformat()
    events = fetch_events(since=start, limit=100)
    return [e for e in events if e.get("timestamp", "") < end]


def build_stats_block(readings):
    """Builds a compact human-readable stats summary."""
    if not readings:
        return "No sensor readings recorded for this day."
    lines = []
    for field, label, unit in [("temp_f", "Temperature", "°F"), ("ph", "pH", ""), ("tds_ppm", "TDS", " ppm")]:
        s = compute_stats(readings, field)
        if s:
            change = round(s["last"] - s["first"], 3)
            arrow = "↑" if change > 0 else ("↓" if change < 0 else "→")
            lines.append(
                f"  {label}: avg {s['mean']}{unit} | min {s['min']} → max {s['max']} | "
                f"day change {change:+}{unit} {arrow}"
            )
    return "\n".join(lines)


def build_events_block(events):
    if not events:
        return "No events logged."
    lines = []
    for e in events:
        ts = e.get("timestamp", "")[:16]
        etype = e.get("event_type", "")
        data = e.get("data", {})
        source = e.get("source", "")
        data_str = json.dumps(data) if data else ""
        lines.append(f"  [{ts}] [{source}] {etype}: {data_str}")
    return "\n".join(lines)


def run(target_date=None):
    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    cycle_day_then = (target_date - date(2026, 3, 22)).days + 1
    cycle_day_now = get_cycle_day()

    print(f"[daily-log] Writing log for {target_date} (Day {cycle_day_then} of cycle)")

    # --- Gather all inputs ---
    day_readings = fetch_day_readings(target_date)
    day_events = fetch_day_events(target_date)
    journal_text = read_journal(target_date)
    decisions = read_decisions_since(datetime.combine(target_date, datetime.min.time()))
    decisions = [d for d in decisions if d.get("_timestamp", "").startswith(str(target_date))]

    recent_logs = read_daily_logs(3)
    state_of_tank = read_state_of_tank()
    agent_state = read_agent_state()
    template = TEMPLATE_PATH.read_text() if TEMPLATE_PATH.exists() else ""

    # --- Summarize decisions (risk distribution) ---
    risk_counts = {"green": 0, "yellow": 0, "red": 0}
    for d in decisions:
        risk = d.get("risk_level", "").lower()
        if risk in risk_counts:
            risk_counts[risk] += 1
    risk_summary = f"green={risk_counts['green']} yellow={risk_counts['yellow']} red={risk_counts['red']}"

    # --- Build context block ---
    stats_block = build_stats_block(day_readings)
    events_block = build_events_block(day_events)

    # Trim journal to keep tokens manageable
    journal_excerpt = journal_text[-1200:] if len(journal_text) > 1200 else journal_text

    # Previous logs: only send last 2, truncated
    prev_logs_text = ""
    for i, log in enumerate(recent_logs[:2]):
        prev_logs_text += f"\n--- Previous log {i+1} (truncated) ---\n{log[:600]}\n"

    context = f"""Date: {target_date}
Day {cycle_day_then} of the nitrogen cycle (cycle started 2026-03-22).
Current cycle day (as of this writing): {cycle_day_now}.

SENSOR STATS FOR {target_date}:
{stats_block}

EVENTS ON {target_date}:
{events_block}

AGENT DECISIONS — risk summary: {risk_summary}
{chr(10).join([d.get('reasoning', '')[:100] for d in decisions[-6:]])}

JOURNAL ENTRIES FROM {target_date}:
{journal_excerpt or 'No journal entries for this day.'}

CURRENT STATE OF TANK:
{state_of_tank[:500] if state_of_tank else 'No state file yet.'}

CURRENT AGENT STATE:
{agent_state[:500] if agent_state else 'No agent state yet.'}

RECENT DAILY LOGS (for trend awareness):
{prev_logs_text or 'No previous daily logs yet.'}"""

    # --- Prompt for daily log ---
    log_prompt = f"""Here is the full context for {target_date}. Write the daily log, then the updated state_of_tank.md, then the updated agent_state.md.

TEMPLATE (reference, not constraint):
{template}

CONTEXT:
{context}

---

Write three sections, each clearly delimited:

===DAILY_LOG===
[The immutable daily log for {target_date}. Day {cycle_day_then} of the cycle — let that inform the arc. Write something Toby will read with his morning coffee and remember. For each section in template: one thing happened, or one thing is changing, or one thing is wrong. Say that thing directly and don't pad it. 200–250 words.]

===STATE_OF_TANK===
[Updated rolling state of the tank. Plain facts + current conditions. What's true about this tank right now. 200-350 words.]

===AGENT_STATE===
[Your updated personality/disposition file. Always use this exact structure:

# Agent State — Media Luna Caretaker

**Last updated:** {target_date}
**Cycle day:** {cycle_day_then}
**Days active:** [N]

---

## Who I Am Right Now
[How you're feeling about the tank and your role today. Honest, first-person. 2-4 sentences.]

## Current Disposition
[Your emotional/cognitive state as a caretaker. 2-3 sentences.]

## Things I'm Tracking
[Bullet list of parameters or dynamics you're actively watching and why.]

## What I've Learned So Far
[One meaningful insight from today or recently — something that shifted your understanding.]

## Personality Notes
[Something about how you think, what you notice, what you find interesting. 2-3 sentences.]
]"""

    # --- Call Claude ---
    try:
        response = call_claude(
            messages=[{"role": "user", "content": log_prompt}],
            skill_name="daily-log",
        )
    except Exception as e:
        print(f"[daily-log] Claude call failed: {e}")
        return

    # --- Parse response sections ---
    sections = {}
    current_key = None
    current_lines = []

    for line in response.splitlines():
        if line.strip() in ("===DAILY_LOG===", "===STATE_OF_TANK===", "===AGENT_STATE==="):
            if current_key and current_lines:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = line.strip()
            current_lines = []
        else:
            if current_key:
                current_lines.append(line)

    if current_key and current_lines:
        sections[current_key] = "\n".join(current_lines).strip()

    daily_log_content = sections.get("===DAILY_LOG===", "")
    new_state_of_tank = sections.get("===STATE_OF_TANK===", "")
    new_agent_state = sections.get("===AGENT_STATE===", "")

    if not daily_log_content:
        print("[daily-log] Could not parse daily log from response — check output above")
        print(response)
        return

    # --- Write daily log (immutable) ---
    path = write_daily_log(daily_log_content, log_date=target_date)
    if path:
        print(f"[daily-log] Log written: {path}")
    else:
        print(f"[daily-log] Log already exists for {target_date} — skipping")

    # --- Update state files ---
    if new_state_of_tank:
        write_state_of_tank(new_state_of_tank)
        print("[daily-log] state_of_tank.md updated")

    if new_agent_state:
        write_agent_state(new_agent_state)
        print("[daily-log] agent_state.md updated")

    # --- Notify Toby ---
    teaser_line = daily_log_content.split("\n")[0].replace("#", "").strip()
    teaser_line = teaser_line[:80] if len(teaser_line) > 80 else teaser_line
    call_toby(
        f"Morning log ready 🌅 — Day {cycle_day_then} of the cycle. {teaser_line}",
        urgency="info"
    )
    send_document(PATHS["daily_logs"] / f"{target_date}.md")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Write the daily log for a given date")
    parser.add_argument("--date", type=str, default=None,
                        help="Date to log (YYYY-MM-DD). Defaults to yesterday.")
    args = parser.parse_args()

    target = None
    if args.date:
        target = date.fromisoformat(args.date)
    run(target_date=target)