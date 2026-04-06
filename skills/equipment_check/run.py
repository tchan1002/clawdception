"""
equipment-check — daily equipment health check for Media Luna.

Checks:
  Sensor-derivable:
    - DS18B20 temp probe error rate (temp_raw_c == -127.0)
    - ESP32 post failure trend

  Schedule-based (state tracked in logs/equipment_state.json):
    - Filter cleaning (every 14 days)
    - pH probe recalibration (every 30 days)

Logs a decision entry so the journal picks it up.
Calls Toby if any issue needs attention (at most once per 24hr per item).

Usage:
    python3 run.py
    python3 run.py --force    # ignore nag cooldowns
"""

import argparse
import json
import sys
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import PATHS, get_cycle_day
from utils import fetch_readings, log_decision, SkillLock
from skills.call_toby.run import call_toby

STATE_PATH = PATHS["logs"] / "equipment_state.json"

PH_PROBE_CALIBRATION_INTERVAL_DAYS = 30
NAG_COOLDOWN_HOURS = 23

DEFAULT_STATE = {
    "filter_last_cleaned": None,
    "ph_probe_last_calibrated": "2026-03-22",  # set up at cycle start
    "last_nag": {},
}


def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return dict(DEFAULT_STATE)


def save_state(state):
    PATHS["logs"].mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def should_nag(state, key, force=False):
    if force:
        return True
    last_str = state.get("last_nag", {}).get(key)
    if not last_str:
        return True
    return (datetime.now() - datetime.fromisoformat(last_str)).total_seconds() / 3600 >= NAG_COOLDOWN_HOURS


def record_nag(state, key):
    state.setdefault("last_nag", {})[key] = datetime.now().isoformat()


def run(force=False):
    with SkillLock("equipment-check"):
        ts = datetime.now().isoformat()
        cycle_day = get_cycle_day()
        state = load_state()

        issues = []  # list of (key, message, urgency)
        notes = []   # informational, no alert needed

        # --- Sensor-derivable checks ---
        readings = fetch_readings(96)  # last 24h
        if readings:
            # DS18B20 temp probe errors
            error_count = 0
            for r in readings:
                try:
                    debug = json.loads(r["raw_json"]).get("debug", {})
                    if debug.get("temp_raw_c") == -127.0:
                        error_count += 1
                except Exception:
                    pass
            error_rate = error_count / len(readings)
            if error_rate > 0.1:
                issues.append((
                    "ds18b20_error",
                    f"DS18B20 temp probe erroring in {error_count}/{len(readings)} readings — check wiring.",
                    "warning",
                ))
            elif error_count > 0:
                notes.append(f"DS18B20 had {error_count} transient error(s) in last 24h.")

            # ESP32 post failure trend
            recent_failures = []
            for r in readings[:4]:
                try:
                    system = json.loads(r["raw_json"]).get("system", {})
                    recent_failures.append(system.get("post_failures", 0))
                except Exception:
                    pass
            if recent_failures and max(recent_failures) >= 3:
                issues.append((
                    "post_failures",
                    f"ESP32 post failures elevated ({max(recent_failures)}) in last hour — WiFi instability likely.",
                    "warning",
                ))

        # --- Schedule-based checks ---
        today = date.today()

        ph_last = state.get("ph_probe_last_calibrated")
        if ph_last is None:
            issues.append((
                "ph_probe_never_calibrated",
                "pH probe calibration has never been logged.",
                "warning",
            ))
        else:
            days_since = (today - date.fromisoformat(ph_last)).days
            if days_since >= PH_PROBE_CALIBRATION_INTERVAL_DAYS:
                issues.append((
                    "ph_probe_overdue",
                    f"pH probe last calibrated {days_since}d ago — due every {PH_PROBE_CALIBRATION_INTERVAL_DAYS}d.",
                    "warning",
                ))
            else:
                notes.append(f"pH probe OK — calibrated {days_since}d ago, next in {PH_PROBE_CALIBRATION_INTERVAL_DAYS - days_since}d.")

        # --- Notify ---
        for key, message, urgency in issues:
            if should_nag(state, key, force):
                call_toby(message, urgency=urgency)
                record_nag(state, key)

        # --- Log decision ---
        if issues:
            risk = "yellow"
            reasoning = f"{len(issues)} equipment issue(s): " + "; ".join(m for _, m, _ in issues)
        else:
            risk = "green"
            reasoning = "All equipment checks passed. " + " ".join(notes)

        log_decision({
            "risk_level": risk,
            "reasoning": reasoning,
            "recommended_actions": [m for _, m, _ in issues] or ["No action needed."],
            "_cycle_day": cycle_day,
            "_timestamp": ts,
            "_trigger": "equipment_check",
            "issues": [{"key": k, "message": m} for k, m, _ in issues],
            "notes": notes,
        })

        summary = f"[{ts[:16]}] equipment-check | {risk} | {len(issues)} issue(s) | {reasoning[:80]}"
        print(summary)
        save_state(state)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Ignore nag cooldowns")
    args = parser.parse_args()
    run(force=args.force)
