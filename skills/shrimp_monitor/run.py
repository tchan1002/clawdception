"""
shrimp-monitor — 15-minute core monitoring loop.

Reads sensor data, checks for danger, and asks Claude for a risk assessment
only when something warrants it. Danger checks and alert firing always happen.

Claude is called when:
  - A manual event was logged since the last Claude call
  - Rate of change is notable (pH >0.1, temp >1°F, TDS >20 ppm in ~1 hour)
  - Scheduled check-in window: 8:00–8:14 or 20:00–20:14 (if >1hr since last call)
  - 10+ hours have passed since the last Claude call (periodic sanity check)

After each Claude call, owner actions are sent to Toby via Telegram if their
per-type cooldown has elapsed. A photo request is injected if >4hr since last owner_photo.

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

from config import PATHS, RANGES, COLONY_START, get_cycle_day
from utils import (
    call_claude,
    compute_stats,
    fetch_events,
    fetch_notable_events,
    fetch_latest_reading,
    fetch_readings,
    format_notable_events,
    format_recent_events,
    hours_since_last_event,
    is_reading_stale,
    log_decision,
    read_journal,
    SkillLock,
)
from skills.call_toby.run import call_toby
from skills.shrimp_alert.run import alert


# How many hours between periodic Claude calls when nothing notable is happening
PERIODIC_CHECK_HOURS = 10

# Hours of day when a status-only check-in is sent if no actions are pending (24hr, local time)
CHECKIN_HOURS = (8, 20)

# Minimum hours between sends of the same action type (urgent actions bypass cooldown)
ACTION_COOLDOWNS = {
    "photo_request":   4,
    "observe":         6,
    "water_test":      24,
    "water_change":    48,
    "check_equipment": 48,
}

# Rate-of-change thresholds that trigger a Claude call (measured over last ~4 readings / 1 hour)
RATE_THRESHOLDS = {
    "ph": 0.1,
    "temp_f": 1.0,
    "tds_ppm": 20,
}

# Human-readable labels for owner action types
ACTION_LABELS = {
    "observe":         "👀 Observe shrimp behavior",
    "water_test":      "🧪 Run a water test (ammonia / nitrite / pH)",
    "water_change":    "💧 Do a water change",
    "photo_request":   "📸 Send a photo of the tank",
    "check_equipment": "🔧 Check equipment",
}

URGENCY_ORDER = {"urgent": 0, "soon": 1, "routine": 2}

# Tool definition — typed actions, optional notes
TOOL = {
    "name": "assess_tank_status",
    "description": (
        "Assess the current status of the shrimp tank. "
        "Use typed actions only — no freeform text in the actions array. "
        "Omit optional fields (note, value) when they add nothing."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "parameter_status": {
                "type": "object",
                "properties": {
                    "temperature": {
                        "type": "object",
                        "properties": {
                            "value":  {"type": "number"},
                            "status": {"type": "string", "enum": ["green", "yellow", "red"]},
                            "note":   {"type": "string", "description": "Only when context is non-obvious."},
                        },
                        "required": ["value", "status"],
                    },
                    "ph": {
                        "type": "object",
                        "properties": {
                            "value":  {"type": "number"},
                            "status": {"type": "string", "enum": ["green", "yellow", "red"]},
                            "note":   {"type": "string", "description": "Only when context is non-obvious."},
                        },
                        "required": ["value", "status"],
                    },
                    "tds": {
                        "type": "object",
                        "properties": {
                            "value":  {"type": "number"},
                            "status": {"type": "string", "enum": ["green", "yellow", "red"]},
                            "note":   {"type": "string", "description": "Only when context is non-obvious."},
                        },
                        "required": ["value", "status"],
                    },
                },
                "required": ["temperature", "ph", "tds"],
            },
            "risk_level": {
                "type": "string",
                "enum": ["green", "yellow", "red"],
            },
            "reasoning": {
                "type": "string",
                "description": "2 sentences max. Be terse.",
            },
            "actions": {
                "type": "array",
                "description": (
                    "All recommended actions. Owner types: observe, water_test, water_change, "
                    "photo_request, check_equipment, none. "
                    "Actuator types: heater, aeration, light, dosing, feeding, none. "
                    "Use none/actuator when no actuator action is needed rather than omitting actuators entirely."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": [
                                "observe", "water_test", "water_change", "photo_request",
                                "check_equipment", "heater", "aeration", "light",
                                "dosing", "feeding", "none",
                            ],
                        },
                        "actor": {
                            "type": "string",
                            "enum": ["owner", "actuator"],
                        },
                        "urgency": {
                            "type": "string",
                            "enum": ["routine", "soon", "urgent"],
                            "description": "Required for owner actions. Omit for actuator.",
                        },
                        "value": {
                            "type": ["number", "string"],
                            "description": "Optional setpoint or state (e.g. heater→76, light→'off').",
                        },
                        "note": {
                            "type": "string",
                            "description": "Only when non-obvious context is needed.",
                        },
                    },
                    "required": ["type", "actor"],
                },
            },
        },
        "required": ["parameter_status", "risk_level", "reasoning", "actions"],
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    Returns the datetime of the last successful Claude call by shrimp-monitor, or None.
    Uses a dedicated file to avoid confusion with other skills' decision log entries.
    """
    path = PATHS["logs"] / "last_monitor_call.txt"
    if not path.exists():
        return None
    try:
        return datetime.fromisoformat(path.read_text().strip())
    except Exception:
        return None


def record_monitor_call():
    """Records the current time as the last shrimp-monitor Claude call."""
    PATHS["logs"].mkdir(parents=True, exist_ok=True)
    (PATHS["logs"] / "last_monitor_call.txt").write_text(datetime.now().isoformat())


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
        try:
            newest_event_dt = datetime.fromisoformat(newest_event_ts.rstrip("Z"))
        except (ValueError, AttributeError):
            newest_event_dt = None
        if newest_event_dt and newest_event_dt > last_claude_time:
            return True, f"manual event since last check ({recent_events[0].get('event_type')})"

    # Notable rate of change over last ~4 readings (~1 hour)
    if len(readings_recent) >= 4:
        for field, threshold in RATE_THRESHOLDS.items():
            vals = [r[field] for r in readings_recent[:4] if r.get(field) is not None]
            if len(vals) >= 2:
                change = abs(vals[0] - vals[-1])
                if change >= threshold:
                    return True, f"{field} changed {round(change, 3)} in last hour"

    # Scheduled check-in window
    now = datetime.now()
    if now.hour in CHECKIN_HOURS and now.minute < 15:
        if last_claude_time is None or (now - last_claude_time).total_seconds() > 3600:
            return True, f"scheduled check-in ({now.hour:02d}:00)"

    # Periodic check — at least every N hours
    if last_claude_time is None:
        return True, "no prior decision today"
    elapsed_hours = (datetime.now() - last_claude_time).total_seconds() / 3600
    if elapsed_hours >= PERIODIC_CHECK_HOURS:
        return True, f"periodic check ({int(elapsed_hours)}hr since last)"

    return False, "stable — no notable changes"


def detect_water_change(readings):
    """
    Returns (True, description) if the last few readings show a simultaneous
    step-change in all three parameters — the signature of a water change.
    Looks at delta between reading[0] and reading[2] (~30 min span).
    """
    if len(readings) < 3:
        return False, ""
    r0, r2 = readings[0], readings[2]
    shifts = {}
    for field, threshold in [("temp_f", 0.8), ("ph", 0.08), ("tds_ppm", 15)]:
        v0, v2 = r0.get(field), r2.get(field)
        if v0 is not None and v2 is not None:
            delta = abs(v0 - v2)
            shifts[field] = delta >= threshold
    if all(shifts.values()) and len(shifts) == 3:
        return True, (
            f"Simultaneous shift detected — "
            f"temp {r2.get('temp_f')}→{r0.get('temp_f')}°F, "
            f"pH {r2.get('ph')}→{r0.get('ph')}, "
            f"TDS {r2.get('tds_ppm')}→{r0.get('tds_ppm')}ppm — consistent with a water change."
        )
    return False, ""


def should_inject_photo_request(photo_hours):
    return photo_hours is None or photo_hours >= ACTION_COOLDOWNS["photo_request"]


def load_cooldowns():
    path = PATHS["logs"] / "action_cooldowns.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def save_cooldowns(cooldowns):
    PATHS["logs"].mkdir(parents=True, exist_ok=True)
    (PATHS["logs"] / "action_cooldowns.json").write_text(json.dumps(cooldowns, indent=2))


def cooldown_elapsed(action_type, cooldowns):
    hours = ACTION_COOLDOWNS.get(action_type)
    if hours is None:
        return True
    last_sent = cooldowns.get(action_type)
    if not last_sent:
        return True
    try:
        elapsed = (datetime.now() - datetime.fromisoformat(last_sent)).total_seconds() / 3600
        return elapsed >= hours
    except Exception:
        return True


def _send_status_only(decision, latest):
    reasoning = decision.get("reasoning", "").strip()
    reading_str = f"T={latest.get('temp_f')}°F pH={latest.get('ph')} TDS={latest.get('tds_ppm')}ppm"
    msg = f"✅ All clear — {reading_str}"
    if reasoning:
        msg += f"\n{reasoning}"
    call_toby(msg, urgency="info")


def send_owner_actions(decision, latest):
    """
    Send owner actions to Toby, gated by per-type cooldowns.
    Urgent actions bypass cooldowns. If nothing is eligible and it's a check-in
    window, send a status-only blurb.
    """
    actions = decision.get("actions", [])
    owner_actions = [a for a in actions if a.get("actor") == "owner" and a.get("type") != "none"]

    is_emergency = (
        decision.get("risk_level") == "red"
        or any(a.get("urgency") == "urgent" for a in owner_actions)
    )

    cooldowns = load_cooldowns()

    if is_emergency:
        to_send = [a for a in owner_actions if a.get("urgency") == "urgent"]
    else:
        to_send = [a for a in owner_actions if cooldown_elapsed(a["type"], cooldowns)]

    if not to_send:
        now = datetime.now()
        if now.hour in CHECKIN_HOURS and now.minute < 15:
            _send_status_only(decision, latest)
        return

    to_send.sort(key=lambda a: URGENCY_ORDER.get(a.get("urgency", "routine"), 2))
    lines = []
    for a in to_send:
        label = ACTION_LABELS.get(a["type"], a["type"].replace("_", " "))
        urgency = a.get("urgency", "routine")
        prefix = "❗" if urgency == "urgent" else ("⏳" if urgency == "soon" else "•")
        note = a.get("note", "")
        lines.append(f"{prefix} {label}" + (f" — {note}" if note else ""))

    reasoning = decision.get("reasoning", "").strip()
    body = "\n".join(lines)
    msg = f"{reasoning}\n\n{body}" if reasoning else body

    risk = decision.get("risk_level", "green")
    msg_urgency = "critical" if risk == "red" else ("warning" if risk == "yellow" else "info")
    call_toby(msg, urgency=msg_urgency)

    now_iso = datetime.now().isoformat()
    for a in to_send:
        if a["type"] in ACTION_COOLDOWNS:
            cooldowns[a["type"]] = now_iso
    save_cooldowns(cooldowns)


# ---------------------------------------------------------------------------
# Prompt formatting
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(force=False):
    with SkillLock("shrimp-monitor"):
        ts = datetime.now().isoformat()
        cycle_day = get_cycle_day()

        # --- Fetch data ---
        latest = fetch_latest_reading()
        if not latest:
            print(f"[{ts[:16]}] [shrimp-monitor] No sensor data — skipping.")
            return

        stale_nag_path = PATHS["logs"] / "last_stale_nag.txt"
        if is_reading_stale(latest):
            reading_ts = datetime.fromisoformat(latest["timestamp"])
            reading_age_min = (datetime.now() - reading_ts).total_seconds() / 60
            last_stale_nag = None
            if stale_nag_path.exists():
                try:
                    last_stale_nag = datetime.fromisoformat(stale_nag_path.read_text().strip())
                except Exception:
                    pass
            hours_since_stale_nag = (
                (datetime.now() - last_stale_nag).total_seconds() / 3600
                if last_stale_nag else 999
            )
            if hours_since_stale_nag >= 1:
                call_toby(
                    f"ESP32 offline — no sensor data for {int(reading_age_min)} min. "
                    f"Last reading: {reading_ts.strftime('%H:%M')}.",
                    urgency="warning"
                )
                stale_nag_path.write_text(datetime.now().isoformat())
            log_decision({
                "risk_level": "red",
                "reasoning": f"ESP32 offline — no sensor data for {int(reading_age_min)} min. Last reading at {reading_ts.strftime('%H:%M')}.",
                "_cycle_day": cycle_day,
                "_timestamp": ts,
                "_trigger": "stale_sensor",
            })
            summary_line = (
                f"[{ts[:16]}] Day {cycle_day} | stale | "
                f"last reading {int(reading_age_min)}min ago ({reading_ts.strftime('%H:%M')})"
            )
            with open(PATHS["monitor_log"], "a") as f:
                f.write(summary_line + "\n")
            return

        readings_24h = fetch_readings(96)
        readings_recent = readings_24h[:4]  # last ~1 hour
        since_24h = (datetime.now() - timedelta(hours=24)).isoformat()
        recent_events = fetch_events(since=since_24h)
        correction_events = fetch_events(event_type="correction", limit=10)
        notable_events = fetch_notable_events(days=14)
        last_claude_time = get_last_claude_time()

        for param, value, threshold, direction in check_danger(latest):
            alert(param, value, threshold, direction)

        call_it, reason = should_call_claude(latest, readings_recent, recent_events, last_claude_time)
        if not force and not call_it:
            summary_line = (
                f"[{ts[:16]}] Day {cycle_day} | skipped (stable) | "
                f"T={latest.get('temp_f')}°F pH={latest.get('ph')} TDS={latest.get('tds_ppm')}ppm"
            )
            PATHS["logs"].mkdir(parents=True, exist_ok=True)
            with open(PATHS["monitor_log"], "a") as f:
                f.write(summary_line + "\n")
            return

        reading_summary = summarize_readings_for_prompt(readings_24h)
        events_summary = format_recent_events(recent_events)
        notable_summary = format_notable_events(notable_events)
        water_change_likely, water_change_note = detect_water_change(readings_24h)
        journal_snippet = read_journal()
        journal_snippet = journal_snippet[-600:] if len(journal_snippet) > 600 else journal_snippet

        photo_hours = hours_since_last_event("owner_photo")
        photo_line = f"{int(photo_hours)}hr ago" if photo_hours is not None else "never"

        water_change_line = f"\n    ⚠ CONTEXT: {water_change_note}" if water_change_likely else ""

        colony_hours = (datetime.now() - COLONY_START).total_seconds() / 3600
        colony_line = f"{colony_hours:.1f}hr post-introduction (introduced 2026-04-13 16:00)"

        corrections_lines = ""
        if correction_events:
            lines = []
            for e in correction_events:
                ts_c = e.get("timestamp", "")[:16]
                lines.append(f"  [{ts_c}] {e.get('notes', '')}")
            corrections_lines = "\n    ⚠ OWNER CORRECTIONS (treat as ground truth — override prior reasoning):\n" + "\n".join(lines) + "\n"

        prompt = f"""Day {cycle_day}. Time: {ts[:16]}. Colony: {colony_line}. Trigger: {reason}.{water_change_line}{corrections_lines}

    CURRENT: Temp {latest.get('temp_f')}°F | pH {latest.get('ph')} | TDS {latest.get('tds_ppm')}ppm

    24HR STATS:
    {reading_summary}

    EVENTS (last 24hr):
    {events_summary}

    NOTABLE TANK HISTORY (past 14 days):
    {notable_summary}

    JOURNAL (recent):
    {journal_snippet or 'None yet.'}

    LAST PHOTO: {photo_line}

    TARGET: Temp 72-78°F | pH 6.5-7.5 | TDS 150-250ppm
    DANGER: Temp <65/>82 | pH <6.0/>8.0 | TDS <100/>350

    Keep reasoning to 2 sentences. Use typed actions only. Omit notes unless non-obvious."""

        try:
            decision = call_claude(
                messages=[{"role": "user", "content": prompt}],
                skill_name="shrimp-monitor",
                tools=[TOOL],
                tool_name=TOOL["name"],
            )
        except Exception as e:
            print(f"[shrimp-monitor] Claude call failed: {e}")
            log_decision({"error": str(e), "latest_reading": latest, "cycle_day": cycle_day})
            return

        if should_inject_photo_request(photo_hours):
            existing_types = {a.get("type") for a in decision.get("actions", [])}
            if "photo_request" not in existing_types:
                decision.setdefault("actions", []).append({
                    "type": "photo_request",
                    "actor": "owner",
                    "urgency": "routine",
                })

        send_owner_actions(decision, latest)
        record_monitor_call()

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
        PATHS["logs"].mkdir(parents=True, exist_ok=True)
        with open(PATHS["monitor_log"], "a") as f:
            f.write(summary_line + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Always call Claude regardless of conditions")
    args = parser.parse_args()
    run(force=args.force)
