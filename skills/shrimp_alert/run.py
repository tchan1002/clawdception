"""
shrimp-alert — log and escalate a parameter danger alert.

Usage:
    python3 run.py --param temperature --value 83.2 --threshold 82
    python3 run.py --param ph --value 5.8 --threshold 6.0 --direction below

Import:
    from skills.shrimp_alert.run import alert
    alert("ph", 5.8, threshold=6.0, direction="below")
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import PATHS
from skills.call_toby.run import call_toby


def alert(param, value, threshold, direction="above", extra_note=""):
    """
    Log a danger alert and notify Toby.
    direction: "above" | "below"
    """
    ts = datetime.now().isoformat()
    comparison = "above" if direction == "above" else "below"
    message = (
        f"{param} is {comparison} danger threshold: {value} ({comparison} {threshold})"
    )
    if extra_note:
        message += f" — {extra_note}"

    entry = {
        "timestamp": ts,
        "param": param,
        "value": value,
        "threshold": threshold,
        "direction": direction,
        "message": message,
    }

    PATHS["logs"].mkdir(parents=True, exist_ok=True)
    with open(PATHS["alerts_log"], "a") as f:
        f.write(json.dumps(entry) + "\n")

    print(f"[shrimp-alert] 🚨 {message}")
    call_toby(message, urgency="critical")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fire a danger alert")
    parser.add_argument("--param", required=True, help="Parameter name (e.g. 'ph')")
    parser.add_argument("--value", required=True, type=float, help="Current value")
    parser.add_argument("--threshold", required=True, type=float, help="Danger threshold")
    parser.add_argument("--direction", default="above", choices=["above", "below"])
    parser.add_argument("--note", default="", help="Optional extra context")
    args = parser.parse_args()

    alert(args.param, args.value, args.threshold, args.direction, args.note)
