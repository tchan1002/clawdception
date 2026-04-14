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
import shutil
import sys
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import get_cycle_day, PATHS
from utils import call_claude
from skills.call_toby.run import call_toby, send_with_buttons

SERVER_URL = "http://localhost:5001"
PHOTOS_DIR = Path("snapshots/photos")
OFFSET_FILE = Path("logs/telegram_offset.txt")
PENDING_EDIT_FILE = Path("state/pending_edit.json")

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


def set_pending_edit(proposal_id):
    PENDING_EDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    PENDING_EDIT_FILE.write_text(json.dumps({
        "proposal": proposal_id,
        "waiting_since": datetime.now().isoformat(),
    }))


def get_pending_edit():
    if PENDING_EDIT_FILE.exists():
        try:
            return json.loads(PENDING_EDIT_FILE.read_text())
        except Exception:
            pass
    return None


def clear_pending_edit():
    if PENDING_EDIT_FILE.exists():
        PENDING_EDIT_FILE.unlink()


def apply_edit_to_proposal(proposal_id, instructions):
    """Ask Claude to rewrite the proposal files based on edit instructions. Returns summary."""
    proposal_dir = PATHS["proposals"] / proposal_id
    proposal_md = proposal_dir / "proposal.md"
    run_py = proposal_dir / "run.py"

    current_proposal = proposal_md.read_text() if proposal_md.exists() else ""
    current_run = run_py.read_text() if run_py.exists() else ""

    EDIT_TOOL = {
        "name": "apply_proposal_edit",
        "description": "Apply edit instructions to a skill proposal",
        "input_schema": {
            "type": "object",
            "properties": {
                "updated_proposal_md": {
                    "type": "string",
                    "description": "Full updated content for proposal.md"
                },
                "updated_run_py": {
                    "type": "string",
                    "description": "Full updated content for run.py (pass empty string if unchanged)"
                },
                "summary": {
                    "type": "string",
                    "description": "1-2 sentence summary of what changed, for the Telegram reply"
                },
            },
            "required": ["updated_proposal_md", "updated_run_py", "summary"],
        }
    }

    prompt = f"""You are editing a skill proposal for the Media Luna shrimp tank system.

CURRENT proposal.md:
{current_proposal}

CURRENT run.py:
{current_run[:2000] if current_run else '(no run.py yet)'}

EDIT INSTRUCTIONS FROM TOBY:
{instructions}

Apply the edit instructions. Return the full updated files and a short summary of what changed."""

    try:
        result = call_claude(
            messages=[{"role": "user", "content": prompt}],
            skill_name="skill-writer",
            tools=[EDIT_TOOL],
            tool_name=EDIT_TOOL["name"],
        )
    except Exception as e:
        print(f"[telegram-listener] Edit Claude call failed: {e}")
        return None

    if result.get("updated_proposal_md"):
        proposal_md.write_text(result["updated_proposal_md"])
    if result.get("updated_run_py"):
        run_py.write_text(result["updated_run_py"])

    return result.get("summary", "Proposal updated.")


def handle_callback_query(token, chat_id, callback_query):
    """Handle inline button taps (approve / reject / edit)."""
    cq_id = callback_query["id"]
    data = callback_query.get("data", "")

    if ":" not in data:
        answer_callback(token, cq_id, "Unknown action.")
        return

    action, proposal_id = data.split(":", 1)

    if action == "approve":
        answer_callback(token, cq_id, "Installing...")
        success, msg = install_proposal(proposal_id)
        call_toby(msg, urgency="info" if success else "warning")

    elif action == "reject":
        reject_proposal(proposal_id)
        answer_callback(token, cq_id, "Rejected.")
        call_toby(f"Proposal `{proposal_id}` rejected and archived.", urgency="info")

    elif action == "edit":
        set_pending_edit(proposal_id)
        answer_callback(token, cq_id, "Send me your edit instructions.")
        call_toby(
            f"Ready to edit `{proposal_id}`. Send your instructions as a message.",
            urgency="info",
        )

    elif action == "ack":
        # Owner confirmed they've handled the recommended actions
        answer_callback(token, cq_id, "Logged ✓")
        post_event(
            "action_completed",
            notes="Owner acknowledged caretaker actions",
            data={"context": proposal_id, "source": "telegram"},
        )
        print(f"[telegram-listener] action_completed logged (context={proposal_id})")

    else:
        answer_callback(token, cq_id, "Unknown action.")


def handle_edit_reply(text, pending):
    """Process an edit instruction message while a proposal edit is pending."""
    proposal_id = pending["proposal"]
    print(f"[telegram-listener] Applying edit to {proposal_id}: {text!r}")
    summary = apply_edit_to_proposal(proposal_id, text)
    clear_pending_edit()

    if summary is None:
        call_toby("Edit failed — check logs. Proposal unchanged.", urgency="warning")
        return

    # Re-read updated proposal for the summary message
    proposal_dir = PATHS["proposals"] / proposal_id
    proposal_md = proposal_dir / "proposal.md"
    proposal_text = proposal_md.read_text() if proposal_md.exists() else ""
    # Pull first ~200 chars of rationale for the preview
    preview = ""
    in_rationale = False
    for line in proposal_text.splitlines():
        if line.startswith("## Rationale"):
            in_rationale = True
            continue
        if in_rationale and line.startswith("##"):
            break
        if in_rationale and line.strip():
            preview += line + " "
        if len(preview) > 200:
            preview = preview[:200] + "..."
            break

    # Re-extract name/type/risk from proposal.md header
    parts = proposal_id.split("-")
    skill_name = "-".join(parts[3:]) if len(parts) > 3 else proposal_id
    msg = f"*Updated proposal:* `{skill_name}`\n\n{summary}\n\n{preview.strip()}"
    send_with_buttons(
        msg,
        buttons=[
            ("✅ Approve", f"approve:{proposal_id}"),
            ("❌ Reject",  f"reject:{proposal_id}"),
            ("✏️ Edit",    f"edit:{proposal_id}"),
        ],
        urgency="info",
    )


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

        # --- Inline button tap ---
        if "callback_query" in update:
            cq = update["callback_query"]
            if str(cq.get("message", {}).get("chat", {}).get("id", "")) == str(chat_id):
                handle_callback_query(token, chat_id, cq)
                processed += 1
            continue

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
            # Check if we're waiting for edit instructions for a proposal
            pending = get_pending_edit()
            if pending:
                handle_edit_reply(caption, pending)
            else:
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
