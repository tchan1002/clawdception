"""
telegram-listener — poll Telegram for owner messages and record them as events.

Runs every 2 minutes via cron. Reads messages from the owner's chat only.

Text messages → classified by Claude into a proper event type (water_change,
  water_test, feeding, etc.) with structured data extracted where possible.
  Falls back to owner_note if intent is unclear.

Photos → saved to snapshots/photos/, analyzed by Claude vision, result sent
  back to owner via Telegram, event logged as owner_photo.

Usage:
    python3 run.py
"""

import base64
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import get_cycle_day
from utils import call_claude
from skills.call_toby.run import call_toby

SERVER_URL = "http://localhost:5001"
PHOTOS_DIR = Path("snapshots/photos")
OFFSET_FILE = Path("logs/telegram_offset.txt")

CLASSIFY_TOOL = {
    "name": "classify_event",
    "description": "Classify an owner message into a tank event with structured data",
    "input_schema": {
        "type": "object",
        "properties": {
            "event_type": {
                "type": "string",
                "enum": [
                    "water_change", "water_test", "feeding", "observation",
                    "heater_adjust", "dosing", "maintenance", "plant_addition",
                    "shrimp_added", "owner_note"
                ],
                "description": "Best-fit event type. Use owner_note if intent is unclear."
            },
            "notes": {
                "type": "string",
                "description": "Cleaned, concise version of the original message"
            },
            "data": {
                "type": "object",
                "description": "Structured fields extracted from the message. Examples: water_change→{percent:20}, water_test→{ammonia:0,nitrite:0.25,nitrate:5}, heater_adjust→{temp_f:76}, shrimp_added→{count:6}"
            }
        },
        "required": ["event_type", "notes", "data"]
    }
}

VISION_TOOL = {
    "name": "analyze_tank_image",
    "description": "Analyze an owner-submitted photo of the Media Luna shrimp tank",
    "input_schema": {
        "type": "object",
        "properties": {
            "shrimp_count_estimate": {
                "type": "integer",
                "description": "Estimated number of visible shrimp"
            },
            "water_clarity": {
                "type": "string",
                "enum": ["clear", "slightly_cloudy", "cloudy", "murky"]
            },
            "visible_algae": {"type": "boolean"},
            "algae_description": {"type": "string"},
            "substrate_condition": {"type": "string"},
            "plant_health": {
                "type": "string",
                "enum": ["thriving", "stable", "declining", "none_visible"]
            },
            "concerns": {
                "type": "array",
                "items": {"type": "string"}
            },
            "narrative": {
                "type": "string",
                "description": "2-3 sentence caretaker voice observation"
            }
        },
        "required": ["shrimp_count_estimate", "water_clarity", "visible_algae",
                     "substrate_condition", "plant_health", "concerns", "narrative"]
    }
}


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
    """Download the highest-res Telegram photo. Returns bytes or None."""
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
    """Save photo bytes to snapshots/photos/. Returns filename."""
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    filename = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".jpg"
    (PHOTOS_DIR / filename).write_bytes(img_bytes)
    return filename


def classify_message(text):
    """Ask Claude to classify a text message into a structured event. Returns dict."""
    cycle_day = get_cycle_day()
    prompt = f"""Day {cycle_day} of the Media Luna shrimp tank nitrogen cycle.

The tank owner sent this message: "{text}"

Classify it as a tank event. Extract any structured data (amounts, values, counts).
Use owner_note only if the message doesn't clearly map to a known event type."""

    try:
        return call_claude(
            messages=[{"role": "user", "content": prompt}],
            skill_name="telegram-listener",
            tools=[CLASSIFY_TOOL],
            tool_name=CLASSIFY_TOOL["name"],
        )
    except Exception as e:
        print(f"[telegram-listener] Classification failed: {e}")
        return {"event_type": "owner_note", "notes": text, "data": {"source": "telegram"}}


def analyze_photo(img_bytes, caption=""):
    """Send photo to Claude vision. Returns analysis dict or None."""
    cycle_day = get_cycle_day()
    img_b64 = base64.standard_b64encode(img_bytes).decode("utf-8")

    context = f' The owner captioned it: "{caption}".' if caption else ""
    prompt = f"""Day {cycle_day} of the nitrogen cycle. The tank owner sent this photo of the Media Luna shrimp tank.{context}

Analyze what's visible: shrimp count, water clarity, algae, substrate, plant health, any concerns.
Write a brief caretaker-voice narrative."""

    try:
        return call_claude(
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64},
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
            skill_name="telegram-listener",
            tools=[VISION_TOOL],
            tool_name=VISION_TOOL["name"],
        )
    except Exception as e:
        print(f"[telegram-listener] Vision analysis failed: {e}")
        return None


def format_vision_reply(analysis, caption=""):
    """Format vision analysis as a concise Telegram reply."""
    lines = []
    if caption:
        lines.append(f'"{caption}"')
    lines.append(
        f"{analysis['shrimp_count_estimate']} shrimp visible · "
        f"water: {analysis['water_clarity'].replace('_', ' ')} · "
        f"plants: {analysis['plant_health'].replace('_', ' ')}"
    )
    if analysis.get("visible_algae") and analysis.get("algae_description"):
        lines.append(f"Algae: {analysis['algae_description']}")
    concerns = analysis.get("concerns", [])
    lines.append(f"Concerns: {', '.join(concerns) if concerns else 'none'}")
    lines.append(f"\n{analysis['narrative']}")
    return "\n".join(lines)


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

        if str(msg.get("chat", {}).get("id", "")) != str(chat_id):
            continue

        caption = msg.get("caption", "") or msg.get("text", "")

        if "photo" in msg:
            file_id = msg["photo"][-1]["file_id"]
            img_bytes = download_photo(token, file_id)

            if img_bytes:
                filename = save_photo(img_bytes)
                post_event("owner_photo", notes=caption, data={"filename": filename, "source": "telegram"})
                print(f"[telegram-listener] Photo saved: {filename} — {caption!r}")

                analysis = analyze_photo(img_bytes, caption)
                if analysis:
                    reply = format_vision_reply(analysis, caption)
                    call_toby(reply, urgency="info")
                    print(f"[telegram-listener] Vision reply sent")
                else:
                    ack = "Photo logged" + (f": {caption}" if caption else "") + " ✓"
                    call_toby(ack, urgency="info")
            else:
                post_event("owner_photo", notes=caption, data={"source": "telegram", "error": "download_failed"})
                call_toby("Photo received but download failed — event logged without image.", urgency="warning")

        elif caption:
            classified = classify_message(caption)
            event_type = classified.get("event_type", "owner_note")
            notes = classified.get("notes", caption)
            data = classified.get("data", {})
            data["source"] = "telegram"

            post_event(event_type, notes=notes, data=data)
            print(f"[telegram-listener] '{caption}' → {event_type}")

            label = event_type.replace("_", " ")
            call_toby(f"Logged as {label}: {notes} ✓", urgency="info")

        processed += 1

    save_offset(new_offset)
    if processed:
        print(f"[telegram-listener] Processed {processed} message(s), offset now {new_offset}")


if __name__ == "__main__":
    run()
