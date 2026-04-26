"""
auto-feeder — feeding reminder for Media Luna shrimp colony.

Checks hours since last "feeding" event. If overdue, nags Toby via Telegram.
Nag cooldown: 4 hours (won't spam). Feeding threshold: 48 hours.

Usage:
    python3 run.py
    python3 run.py --force    # ignore nag cooldown
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import PATHS, get_cycle_day
from utils import hours_since_last_event, log_decision, SkillLock
from skills.call_toby.run import call_toby

STATE_PATH = PATHS["logs"] / "auto_feeder_state.json"

FEED_THRESHOLD_HOURS = 48
NAG_COOLDOWN_HOURS = 4


def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {}


def save_state(state):
    PATHS["logs"].mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def should_nag(state, force=False):
    if force:
        return True
    last_str = state.get("last_nag")
    if not last_str:
        return True
    hours_since_nag = (datetime.now() - datetime.fromisoformat(last_str)).total_seconds() / 3600
    return hours_since_nag >= NAG_COOLDOWN_HOURS


def run(force=False):
    with SkillLock("auto-feeder"):
        ts = datetime.now().isoformat()
        cycle_day = get_cycle_day()
        state = load_state()

        hours = hours_since_last_event("feeding")

        overdue = hours is None or hours >= FEED_THRESHOLD_HOURS

        if overdue and should_nag(state, force):
            if hours is None:
                msg = "Media Luna — no feeding on record. Time to feed the shrimp."
            else:
                msg = f"Media Luna — last feeding {hours:.0f}h ago. Time to feed the shrimp."
            call_toby(msg, urgency="normal")
            state["last_nag"] = ts

        if hours is None:
            reasoning = "No feeding event on record — overdue."
            risk = "yellow"
        elif overdue:
            reasoning = f"Last feeding {hours:.1f}h ago — exceeds {FEED_THRESHOLD_HOURS}h threshold."
            risk = "yellow"
        else:
            reasoning = f"Last feeding {hours:.1f}h ago — within {FEED_THRESHOLD_HOURS}h threshold."
            risk = "green"

        log_decision({
            "risk_level": risk,
            "reasoning": reasoning,
            "actions": [],
            "_cycle_day": cycle_day,
            "_timestamp": ts,
            "_trigger": "auto_feeder",
            "hours_since_feeding": hours,
            "overdue": overdue,
        })

        summary = f"[{ts[:16]}] auto-feeder | {risk} | {reasoning}"
        print(summary)
        save_state(state)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Ignore nag cooldown")
    args = parser.parse_args()
    run(force=args.force)
