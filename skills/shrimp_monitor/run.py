"""
shrimp-monitor — 15-minute core monitoring loop.

Reads sensor data, checks for danger, and asks Claude for a risk assessment
only when something warrants it. Danger checks and alert firing always happen.

Claude is called when:
  - A parameter is outside target range (yellow/red)
  - Rate of change is notable (pH >0.1, temp >1°F, TDS >20 ppm in ~1 hour)
  - A manual event was logged since the last Claude call
  - 4+ hours have passed since the last Claude call (periodic sanity check)

Usage:
    python3 run.py
    python3 run.py --force    # always call Claude regardless of conditions
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import PATHS, RANGES, WATER_TEST_WARNING_HOURS, get_cycle_day
from utils import (
    call_claude,
    compute_stats,
    fetch_events,
    fetch_latest_reading,
    fetch_readings,
    hours_since_last_water_test,
    log_decision,
    parse_json_response,
    read_journal,
)
from skills.call_toby.run import call_toby
from skills.shrimp_alert.run import alert


# How many hours between periodic Claude calls when nothing notable is happening
PERIODIC_CHECK_HOURS = 4

# Rate-of-change thresholds that trigger a Claude call (measured over last ~4 readings / 1 hour)
RATE_THRESHOLDS = {
    "ph": 0.1,
    "temp_f": 1.0,
    "tds_ppm": 20,
}


def check_danger(reading):
    """Returns list of (param, value, threshold, direction) for any danger-zone readings."""
    dangers = []
    for param, cfg in RANGES.items():
        field = cfg.get("field")
        if not field or field not in reading:
            continue
        value = reading[field]
        if value is None:
            continue
        if cfg["danger_high"] is not None and value > cfg["danger_high"]:
            dangers.append((param, value, cfg["danger_high"], "above"))
        elif cfg["danger_low"] is not None and value < cfg["danger_low"]:
            dangers.append((param, value, cfg["danger_low"], "below"))
    return dangers


def get_last_claude_time():
    """
    Returns the datetime of the last successful Claude decision, or None.
    Reads the last line of today's decisions JSONL.
    """
    today = datetime.now().date()
    path = PATHS["decisions"] / f"{today}.jsonl"
    if not path.exists():
        return None
    try:
        lines = [l for l in path.read_text().splitlines() if l.strip()]
        if not lines:
            return None
        last = json.loads(lines[-1])
        ts_str = last.get("_timestamp")
        if ts_str:
            return datetime.fromisoformat(ts_str)
    except Exception:
        pass
    return None


def should_call_claude(latest, readings_recent, recent_events, last_claude_time):
    """
    Decides whether this cycle warrants a Claude call.
    Returns (bool, reason_string).
    """
    # Any manual event logged since last Claude call
    if recent_events:
        if last_claude_time is None:
            return True, f"manual event logged ({recent_events[0].get('event_type')})"
        newest_event_ts = recent_events[0].get("timestamp", "")
        if newest_event_ts > last_claude_time.isoformat():
            return True, f"manual event since last check ({recent_events[0].get('event_type')})"

    # Any parameter outside target range
    for param, cfg in RANGES.items():
        field = cfg.get("field")
        if not field or not latest.get(field):
            continue
        value = latest[field]
        lo, hi = cfg["target"]
        if lo == hi == 0:
            continue  # skip ammonia/nitrite — manual only
        if value < lo or value > hi:
            return True, f"{param} outside target range: {value} (target {lo}–{hi})"

    # Notable rate of change over last ~4 readings (~1 hour)
    if len(readings_recent) >= 4:
        for field, threshold in RATE_THRESHOLDS.items():
            vals = [r[field] for r in readings_recent[:4] if r.get(field) is not None]
            if len(vals) >= 2:
                change = abs(vals[0] - vals[-1])
                if change >= threshold:
                    return True, f"{field} changed {round(change, 3)} in last hour"

    # Periodic check — at least every N hours
    if last_claude_time is None:
        return True, "no prior decision today"
    elapsed_hours = (datetime.now() - last_claude_time).total_seconds() / 3600
    if elapsed_hours >= PERIODIC_CHECK_HOURS:
        return True, f"periodic check ({int(elapsed_hours)}hr since last)"

    return False, "stable — no notable changes"


def summarize_readings_for_prompt(readings):
    if not readings:
        return "No readings available."
    lines = []
    for param, field in [("temperature", "temp_f"), ("ph", "ph"), ("tds", "tds_ppm")]:
        stats = compute_stats(readings, field)
        if stats:
            unit = RANGES[param]["unit"]
            rate = round(stats["last"] - stats["first"], 3)
            direction = "↑" if rate > 0 else ("↓" if rate < 0 else "→")
            lines.append(
                f"  {param}: now={stats['last']}{unit} mean={stats['mean']}{unit} "
                f"min={stats['min']} max={stats['max']} 24hr_change={rate:+}{unit} {direction}"
            )
    return "\n".join(lines)


def format_recent_events(events):
    if not events:
        return "None in past 24 hours."
    lines = []
    for e in events[:8]:
        ts = e.get("timestamp", "")[:16]
        lines.append(f"  [{ts}] {e.get('event_type')}: {json.dumps(e.get('data', {}))}")
    return "\n".join(lines)


def run(force=False):
    ts = datetime.now().isoformat()
    cycle_day = get_cycle_day()

    # --- Fetch data ---
    latest = fetch_latest_reading()
    if not latest:
        print(f"[{ts[:16]}] [shrimp-monitor] No sensor data — skipping.")
        return

    readings_24h = fetch_readings(96)
    readings_recent = readings_24h[:4]  # last ~1 hour
    since_24h = (datetime.now() - timedelta(hours=24)).isoformat()
    recent_events = fetch_events(since=since_24h)
    last_claude_time = get_last_claude_time()

    # --- Always: check for overdue water test (once per 12hrs max, not every 15min) ---
    # Only nag if it's been a while since we last sent a warning
    last_call_hours = (
        (datetime.now() - last_claude_time).total_seconds() / 3600
        if last_claude_time else 999
    )
    if last_call_hours >= 12 or last_claude_time is None:
        hrs_since_test = hours_since_last_water_test()
        if hrs_since_test is None:
            call_toby(
                f"No water test logged yet. Day {cycle_day} of cycle — ammonia and nitrite are unknown.",
                urgency="warning"
            )
        elif hrs_since_test > WATER_TEST_WARNING_HOURS:
            call_toby(
                f"It's been {int(hrs_since_test)}hr since last water test. "
                f"Day {cycle_day} — ammonia/nitrite need checking.",
                urgency="warning"
            )

    # --- Always: check danger zone and fire alerts ---
    for param, value, threshold, direction in check_danger(latest):
        alert(param, value, threshold, direction)

    # --- Decide whether to call Claude ---
    call_it, reason = should_call_claude(latest, readings_recent, recent_events, last_claude_time)
    if not force and not call_it:
        summary_line = (
            f"[{ts[:16]}] Day {cycle_day} | skipped (stable) | "
            f"T={latest.get('temp_f')}°F pH={latest.get('ph')} TDS={latest.get('tds_ppm')}ppm"
        )
        print(summary_line)
        PATHS["logs"].mkdir(parents=True, exist_ok=True)
        with open(PATHS["monitor_log"], "a") as f:
            f.write(summary_line + "\n")
        return

    # --- Build prompt ---
    reading_summary = summarize_readings_for_prompt(readings_24h)
    events_summary = format_recent_events(recent_events)
    journal_snippet = read_journal()
    journal_snippet = journal_snippet[-600:] if len(journal_snippet) > 600 else journal_snippet

    prompt = f"""Day {cycle_day} of nitrogen cycle. Time: {ts[:16]}. Trigger: {reason}.

CURRENT: Temp {latest.get('temp_f')}°F | pH {latest.get('ph')} | TDS {latest.get('tds_ppm')}ppm

24HR STATS:
{reading_summary}

EVENTS:
{events_summary}

JOURNAL (recent):
{journal_snippet or 'None yet.'}

TARGET: Temp 72-78°F | pH 6.5-7.5 | TDS 150-250ppm
DANGER: Temp <65/>82 | pH <6.0/>8.0 | TDS <100/>350

Keep reasoning to 2 sentences. Be terse in all string fields.

Return ONLY valid JSON:
{{"parameter_status":{{"temperature":{{"value":0,"unit":"°F","status":"green","note":""}},"ph":{{"value":0,"unit":"","status":"green","note":""}},"tds":{{"value":0,"unit":"ppm","status":"green","note":""}}}},"risk_level":"green","recommended_actions":[""],"reasoning":"2 sentences max","suggested_actuator_actions":[""]}}"""

    # --- Call Claude ---
    try:
        response_text = call_claude(
            messages=[{"role": "user", "content": prompt}],
            skill_name="shrimp-monitor",
        )
        decision = parse_json_response(response_text)
    except json.JSONDecodeError as e:
        print(f"[shrimp-monitor] Failed to parse JSON response: {e}")
        log_decision({"error": f"JSON parse failed: {e}", "latest_reading": latest, "cycle_day": cycle_day})
        return
    except Exception as e:
        print(f"[shrimp-monitor] Claude call failed: {e}")
        log_decision({"error": str(e), "latest_reading": latest, "cycle_day": cycle_day})
        return

    # --- Log decision ---
    decision["_cycle_day"] = cycle_day
    decision["_timestamp"] = ts
    decision["_trigger"] = reason
    decision["_latest"] = {k: latest.get(k) for k in ("temp_f", "ph", "tds_ppm", "timestamp")}
    log_decision(decision)

    # --- One-line summary ---
    risk = decision.get("risk_level", "?")
    reasoning_snippet = decision.get("reasoning", "")[:80]
    summary_line = (
        f"[{ts[:16]}] Day {cycle_day} | risk={risk} | [{reason[:30]}] | "
        f"T={latest.get('temp_f')}°F pH={latest.get('ph')} TDS={latest.get('tds_ppm')}ppm | "
        f"{reasoning_snippet}"
    )
    print(summary_line)
    PATHS["logs"].mkdir(parents=True, exist_ok=True)
    with open(PATHS["monitor_log"], "a") as f:
        f.write(summary_line + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Always call Claude regardless of conditions")
    args = parser.parse_args()
    run(force=args.force)
