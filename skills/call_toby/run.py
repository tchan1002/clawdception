"""
call-toby — send a notification to Toby via Telegram (or log to file as fallback).

Usage:
    python3 run.py --test
    python3 run.py --message "pH is dropping" --urgency warning

Import:
    from skills.call_toby.run import call_toby
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Allow running from any directory
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import PATHS

URGENCY_EMOJI = {
    "info": "ℹ️",
    "warning": "⚠️",
    "critical": "🚨",
}


def call_toby(message, urgency="info"):
    """
    Send a notification to Toby.
    urgency: "info" | "warning" | "critical"
    Returns True if Telegram succeeded, False if fell back to log file.
    """
    urgency = urgency.lower()
    if urgency not in URGENCY_EMOJI:
        urgency = "info"

    emoji = URGENCY_EMOJI[urgency]
    full_message = f"{emoji} *Media Luna* — {message}"

    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if telegram_token and telegram_chat_id:
        try:
            import requests
            url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
            resp = requests.post(url, json={
                "chat_id": telegram_chat_id,
                "text": full_message,
                "parse_mode": "Markdown",
            }, timeout=15)
            resp.raise_for_status()
            print(f"[call-toby] Telegram sent ({urgency}): {message}")
            _log_call(message, urgency, sent_via="telegram")
            return True
        except Exception as e:
            print(f"[call-toby] Telegram failed: {e} — falling back to log file")

    # Fallback: write to calls.jsonl
    _log_call(message, urgency, sent_via="log_fallback")
    print(f"[call-toby] {emoji} {message}")
    return False


def _log_call(message, urgency, sent_via):
    PATHS["logs"].mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "urgency": urgency,
        "message": message,
        "sent_via": sent_via,
    }
    with open(PATHS["calls_log"], "a") as f:
        f.write(json.dumps(entry) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send a notification to Toby")
    parser.add_argument("--message", "-m", type=str, help="Message to send")
    parser.add_argument("--urgency", "-u", type=str, default="info",
                        choices=["info", "warning", "critical"], help="Urgency level")
    parser.add_argument("--test", action="store_true", help="Send a test ping")
    args = parser.parse_args()

    if args.test:
        call_toby("Media Luna test ping 🦐 — agent infrastructure is online.", urgency="info")
    elif args.message:
        call_toby(args.message, urgency=args.urgency)
    else:
        parser.print_help()
