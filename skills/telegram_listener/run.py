"""
telegram-listener — poll Telegram for owner messages and record them as events.

Runs every 2 minutes via cron. Reads messages from the owner's chat only.
Text messages → event_type: "owner_note"
Photos (with optional caption) → event_type: "owner_photo", saves image to snapshots/photos/

Usage:
    python3 run.py
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

SERVER_URL = "http://localhost:5001"
PHOTOS_DIR = Path("snapshots/photos")
OFFSET_FILE = Path("logs/telegram_offset.txt")


def get_offset():
    if OFFSET_FILE.exists():
        try:
            return int(OFFSET_FILE.read_text().strip())
        except ValueError:
            pass
    return 0


def save_offset(offset):
    OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(str(offset))


def post_event(event_type, notes, data=None):
    payload = {"event_type": event_type, "notes": notes, "data": data or {}}
    try:
        resp = requests.post(f"{SERVER_URL}/api/events", json=payload, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"[telegram-listener] Failed to post event: {e}")


def download_photo(token, file_id):
    """Download the highest-res version of a Telegram photo. Returns bytes or None."""
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{token}/getFile",
            params={"file_id": file_id},
            timeout=15,
        )
        r.raise_for_status()
        file_path = r.json()["result"]["file_path"]
        img = requests.get(
            f"https://api.telegram.org/file/bot{token}/{file_path}",
            timeout=30,
        )
        img.raise_for_status()
        return img.content
    except Exception as e:
        print(f"[telegram-listener] Photo download failed: {e}")
        return None


def save_photo(img_bytes):
    """Save photo bytes to snapshots/photos/. Returns filename or None."""
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    filename = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".jpg"
    dest = PHOTOS_DIR / filename
    dest.write_bytes(img_bytes)
    return filename


def run():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("[telegram-listener] No Telegram credentials — skipping.")
        return

    offset = get_offset()
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            params={"offset": offset, "timeout": 0, "limit": 100},
            timeout=20,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[telegram-listener] getUpdates failed: {e}")
        return

    updates = resp.json().get("result", [])
    if not updates:
        return

    new_offset = offset
    processed = 0

    for update in updates:
        update_id = update["update_id"]
        new_offset = max(new_offset, update_id + 1)

        msg = update.get("message") or update.get("channel_post")
        if not msg:
            continue

        # Only accept messages from the configured chat
        if str(msg.get("chat", {}).get("id", "")) != str(chat_id):
            continue

        ts = datetime.fromtimestamp(msg["date"]).isoformat()
        caption = msg.get("caption", "") or msg.get("text", "")

        if "photo" in msg:
            # Telegram sends multiple sizes; last is largest
            file_id = msg["photo"][-1]["file_id"]
            img_bytes = download_photo(token, file_id)
            if img_bytes:
                filename = save_photo(img_bytes)
                post_event(
                    "owner_photo",
                    notes=caption,
                    data={"filename": filename, "source": "telegram"},
                )
                print(f"[telegram-listener] Photo saved: {filename} — {caption!r}")
            else:
                post_event("owner_photo", notes=caption, data={"source": "telegram", "error": "download_failed"})
        elif caption:
            post_event("owner_note", notes=caption, data={"source": "telegram"})
            print(f"[telegram-listener] Note: {caption!r}")

        processed += 1

    save_offset(new_offset)
    if processed:
        print(f"[telegram-listener] Processed {processed} message(s), offset now {new_offset}")


if __name__ == "__main__":
    run()
