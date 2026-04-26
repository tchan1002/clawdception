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

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import get_cycle_day, PATHS, COLONY_START
from utils import (
    call_claude,
    fetch_events,
    fetch_latest_reading,
    fetch_notable_events,
    format_notable_events,
    format_recent_events,
    post_event,
    read_agent_state,
    read_journal,
)
from skills.call_toby.run import call_toby, send_with_buttons, send_photo
from skills.shrimp_vision.run import process_photo

PHOTOS_DIR = Path("snapshots/photos")
OFFSET_FILE = Path("logs/telegram_offset.txt")
ESP32_CAM_URL = "http://192.168.12.32"

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
                    "shrimp_added", "owner_note", "question", "correction",
                    "system_update", "capture_request"
                ],
                "description": "Best-fit event type. Use correction if owner is explicitly correcting a prior caretaker misinterpretation (e.g. 'that was a bug', 'those photos were not real', 'ignore that reading'). Use question if owner is asking about tank status/parameters/history. Use owner_note if intent is unclear."
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
Use question if the message is asking about tank status, parameters, history, or advice. Use owner_note if intent is unclear."""

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


def answer_question(text):
    """Ask Claude a freeform question about the tank using current state as context."""
    from datetime import timedelta

    latest = fetch_latest_reading()
    since_24h = (datetime.now() - timedelta(hours=24)).isoformat()
    recent_events = fetch_events(since=since_24h)
    notable_events = [e for e in fetch_notable_events(days=7, limit=10) if e.get("event_type") != "owner_photo"]
    journal = read_journal()
    agent_state = read_agent_state()
    cycle_day = get_cycle_day()

    reading_str = (
        f"T={latest.get('temp_f')}°F | pH={latest.get('ph')} | TDS={latest.get('tds_ppm')}ppm"
        if latest else "No sensor data."
    )
    colony_hours = (datetime.now() - COLONY_START).total_seconds() / 3600

    prompt = f"""Day {cycle_day}. Colony: {colony_hours:.1f}hr post-introduction (2026-04-13 16:00).

CURRENT: {reading_str}

RECENT EVENTS (24hr):
{format_recent_events(recent_events)}

NOTABLE HISTORY (7 days):
{format_notable_events(notable_events)}

JOURNAL:
{journal[-300:] or 'None yet.'}

AGENT STATE:
{agent_state[:250] if agent_state else 'None.'}

Toby asks: {text}

Answer in 2-3 sentences. Telegram message, not a report."""

    try:
        return call_claude(
            messages=[{"role": "user", "content": prompt}],
            skill_name="telegram-listener",
            max_tokens=500,
        )
    except Exception as e:
        print(f"[telegram-listener] answer_question failed: {e}")
        return None


def format_vision_reply(analysis, caption=""):
    """Format vision analysis as a concise Telegram reply."""
    lines = []
    if caption:
        lines.append(f'"{caption}"')
    lines.append(
        f"{analysis.get('shrimp_count_visible', '?')} shrimp visible · "
        f"water: {analysis.get('water_clarity', 'unknown').replace('_', ' ')} · "
        f"plants: {analysis.get('plant_health', 'unknown').replace('_', ' ')}"
    )
    if analysis.get("visible_algae") and analysis.get("algae_description"):
        lines.append(f"Algae: {analysis['algae_description']}")
    concerns = analysis.get("concerns", [])
    lines.append(f"Concerns: {', '.join(concerns) if concerns else 'none'}")
    lines.append(f"\n{analysis['narrative']}")
    return "\n".join(lines)


def fetch_esp32_snapshot():
    """GET /snapshot from ESP32-CAM. Returns JPEG bytes or None."""
    try:
        r = requests.get(f"{ESP32_CAM_URL}/snapshot", timeout=10)
        r.raise_for_status()
        return r.content
    except Exception as e:
        print(f"[telegram-listener] ESP32-CAM fetch failed: {e}")
        return None


def handle_capture_request():
    img_bytes = fetch_esp32_snapshot()
    if not img_bytes:
        call_toby("Couldn't reach camera — is it online?", urgency="warning")
        return

    filename = save_photo(img_bytes)
    print(f"[telegram-listener] ESP32-CAM snapshot saved: {filename}")
    analysis = process_photo(img_bytes, filename, source="capture_request")
    if analysis:
        caption = format_vision_reply(analysis)
        send_photo(PHOTOS_DIR / filename, caption=caption)
    else:
        send_photo(PHOTOS_DIR / filename)


def handle_photo(msg, token):
    caption = msg.get("caption", "")
    file_id = msg["photo"][-1]["file_id"]
    img_bytes = download_photo(token, file_id)

    if img_bytes:
        filename = save_photo(img_bytes)
        print(f"[telegram-listener] Photo saved: {filename} — {caption!r}")
        analysis = process_photo(img_bytes, filename, caption=caption, source="telegram")
        if analysis:
            call_toby(format_vision_reply(analysis, caption), urgency="info")
            print("[telegram-listener] Vision reply sent")
        else:
            call_toby("Photo logged" + (f": {caption}" if caption else "") + " ✓", urgency="info")
    else:
        post_event("owner_photo", notes=caption, data={"source": "telegram", "error": "download_failed"})
        call_toby("Photo received but download failed — event logged without image.", urgency="warning")


def handle_text(text):
    classified = classify_message(text)
    event_type = classified.get("event_type", "owner_note")
    notes = classified.get("notes", text)
    print(f"[telegram-listener] '{text}' → {event_type}")

    if event_type == "question":
        reply = answer_question(text)
        call_toby(reply if reply else "Couldn't answer that right now — check logs.",
                  urgency="info" if reply else "warning")
    elif event_type == "capture_request":
        handle_capture_request()
    else:
        data = {**classified.get("data", {}), "source": "telegram"}
        post_event(event_type, notes=notes, data=data)
        call_toby(f"Logged as {event_type.replace('_', ' ')}: {notes} ✓", urgency="info")


def answer_callback(token, callback_query_id, text=""):
    """Dismiss the inline button spinner on Telegram's end."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        print(f"[telegram-listener] answerCallbackQuery failed: {e}")


def install_proposal(proposal_id):
    """
    Copy proposal run.py + SKILL.md into skills/{name}/ and create __init__.py.
    Returns (success, message).
    """
    proposal_dir = PATHS["proposals"] / proposal_id
    if not proposal_dir.exists():
        return False, f"Proposal directory not found: {proposal_id}"

    # Derive skill dir name (underscores for Python import)
    # proposal_id = YYYY-MM-DD-skill-name → take everything after the date
    parts = proposal_id.split("-")
    skill_name = "-".join(parts[3:]) if len(parts) > 3 else proposal_id
    skill_dir_name = skill_name.replace("-", "_")
    skill_dir = Path("skills") / skill_dir_name

    if skill_dir.exists():
        return False, f"skills/{skill_dir_name}/ already exists — manual merge required"

    skill_dir.mkdir(parents=True)

    # Copy proposal files
    for fname in ("run.py", "SKILL.md"):
        src = proposal_dir / fname
        if src.exists():
            shutil.copy2(src, skill_dir / fname)

    # Create minimal __init__.py
    (skill_dir / "__init__.py").write_text("")

    # Mark proposal as approved
    (proposal_dir / "status.json").write_text(json.dumps({
        "status": "approved",
        "installed_at": datetime.now().isoformat(),
        "skill_dir": str(skill_dir),
    }))

    return True, f"Installed to skills/{skill_dir_name}/ — add to cron manually when ready."


def reject_proposal(proposal_id):
    """Mark a proposal as rejected."""
    proposal_dir = PATHS["proposals"] / proposal_id
    if proposal_dir.exists():
        (proposal_dir / "status.json").write_text(json.dumps({
            "status": "rejected",
            "rejected_at": datetime.now().isoformat(),
        }))


def get_proposal_status(proposal_id):
    """Return current proposal status string or None if pending/missing."""
    status_file = PATHS["proposals"] / proposal_id / "status.json"
    if status_file.exists():
        try:
            return json.loads(status_file.read_text()).get("status")
        except Exception:
            pass
    return None


def handle_callback_query(token, chat_id, callback_query):
    """Handle inline button taps (approve / reject / edit)."""
    cq_id = callback_query["id"]
    data = callback_query.get("data", "")

    if ":" not in data:
        answer_callback(token, cq_id, "Unknown action.")
        return

    action, proposal_id = data.split(":", 1)

    # Idempotency: ignore duplicate taps on already-processed proposals
    current_status = get_proposal_status(proposal_id)
    if current_status in ("approved", "rejected"):
        answer_callback(token, cq_id, f"Already {current_status}.")
        return

    if action == "approve":
        answer_callback(token, cq_id, "Installing...")
        success, msg = install_proposal(proposal_id)
        if success:
            skill_name = "-".join(proposal_id.split("-")[3:])
            post_event("system_update", notes=f"Skill approved and installed: {skill_name}", data={"proposal_id": proposal_id, "source": "telegram"})
        call_toby(msg, urgency="info" if success else "warning")

    elif action == "reject":
        reject_proposal(proposal_id)
        answer_callback(token, cq_id, "Rejected.")
        call_toby(f"Proposal `{proposal_id}` rejected and archived.", urgency="info")

    else:
        answer_callback(token, cq_id, "Unknown action.")


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
        safe = str(e).replace(token, "***") if token else str(e)
        print(f"[telegram-listener] getUpdates failed: {safe}")
        return

    updates = resp.json().get("result", [])
    if not updates:
        return

    new_offset = offset
    processed = 0

    for update in updates:
        update_id = update["update_id"]
        new_offset = max(new_offset, update_id + 1)

        if "callback_query" in update:
            cq = update["callback_query"]
            if str(cq.get("message", {}).get("chat", {}).get("id", "")) == str(chat_id):
                handle_callback_query(token, chat_id, cq)
                processed += 1
            continue

        msg = update.get("message") or update.get("channel_post")
        if not msg or str(msg.get("chat", {}).get("id", "")) != str(chat_id):
            continue

        try:
            if "photo" in msg:
                handle_photo(msg, token)
            elif text := (msg.get("text") or msg.get("caption")):
                handle_text(text)
        except Exception as e:
            print(f"[telegram-listener] Message handling failed: {e}")
            call_toby(f"Error processing message — check logs: {e}", urgency="warning")

        processed += 1

    save_offset(new_offset)
    if processed:
        print(f"[telegram-listener] Processed {processed} message(s), offset now {new_offset}")


if __name__ == "__main__":
    run()
