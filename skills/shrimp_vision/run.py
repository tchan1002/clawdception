"""
shrimp-vision — visual tank monitoring via ESP32-CAM. DISABLED — camera not yet connected.

Fetches the latest JPEG snapshot from /api/snapshot/latest (posted by the
ESP32-CAM every 5 min), sends it to Claude vision, and logs a structured
analysis. Skips if no snapshot exists or the snapshot is older than 30 min.

Usage:
    python3 run.py
    python3 run.py --force   # skip freshness check (for testing)
"""

import argparse
import base64
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import PATHS, API_BASE, get_cycle_day
from utils import call_claude, post_event

SNAPSHOT_MAX_AGE_MINUTES = 30

TOOL = {
    "name": "analyze_tank_image",
    "description": "Catalog a visual observation from a photo related to the Media Luna shrimp tank",
    "input_schema": {
        "type": "object",
        "properties": {
            "tank_visible": {
                "type": "boolean",
                "description": "Whether the tank itself is visible in this image"
            },
            "shrimp_count_visible": {
                "type": "integer",
                "description": "Number of shrimp clearly visible in the image. Only count confirmed individuals — report 0 if none seen."
            },
            "water_clarity": {
                "type": "string",
                "enum": ["clear", "slightly_cloudy", "cloudy", "murky"],
                "description": "Visual assessment of water clarity"
            },
            "visible_algae": {
                "type": "boolean",
                "description": "Whether algae growth is visible"
            },
            "algae_description": {
                "type": "string",
                "description": "Description of algae type/location if visible"
            },
            "substrate_condition": {
                "type": "string",
                "description": "Appearance of substrate (clean, debris, etc)"
            },
            "plant_health": {
                "type": "string",
                "enum": ["thriving", "stable", "declining", "none_visible"],
                "description": "Overall plant health assessment"
            },
            "concerns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of visual concerns or anomalies"
            },
            "image_subject": {
                "type": "string",
                "description": "What this image is of, if not the tank (e.g. 'test strip', 'equipment', 'full tank shot')"
            }
        },
        "required": ["tank_visible", "concerns"]
    }
}


def get_latest_snapshot(force=False):
    """
    Returns (jpeg_bytes, snapshot_path) if a fresh snapshot is available,
    or (None, reason_string) if not.
    """
    latest = PATHS["snapshots"] / "latest.jpg"

    if not latest.exists():
        return None, "no snapshot on disk"

    age = datetime.now() - datetime.fromtimestamp(latest.stat().st_mtime)
    if not force and age > timedelta(minutes=SNAPSHOT_MAX_AGE_MINUTES):
        minutes_old = int(age.total_seconds() / 60)
        return None, f"snapshot is {minutes_old} min old (threshold: {SNAPSHOT_MAX_AGE_MINUTES} min)"

    return latest.read_bytes(), str(latest)


def analyze_snapshot(img_bytes):
    """Send JPEG bytes to Claude vision. Returns analysis dict."""
    img_b64 = base64.standard_b64encode(img_bytes).decode("utf-8")
    cycle_day = get_cycle_day()

    prompt = f"""Day {cycle_day} of the nitrogen cycle. Catalog what you observe in this photo related to the Media Luna shrimp tank.

This photo may be of the tank, or it may be of something related (test strips, equipment, a product, etc). First determine if the tank itself is visible.

If tank visible:
- Neocaridina shrimp in this colony are small (1-2cm), appear red or reddish-orange, or gray/translucent. Look specifically for these.
- Count ONLY shrimp you can clearly see. If none are visible, report 0. Do not infer, estimate, or guess hidden shrimp.
- Assess water clarity: only mark cloudy/murky if water itself looks turbid or muddy — suspended particles, milky haze, brown tint. Glass glare, reflections, or camera angle artifacts are NOT cloudiness. Default to "clear" unless water column itself is visibly degraded.
- Flag concerns (water quality, disease signs, equipment issues) — not shrimp count

If tank not visible: set tank_visible=false, describe image_subject, leave tank fields empty."""

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": img_b64,
                    },
                },
                {"type": "text", "text": prompt}
            ],
        }
    ]

    return call_claude(
        messages=messages,
        skill_name="shrimp-vision",
        tools=[TOOL],
        tool_name=TOOL["name"],
    )


def log_entry(entry):
    PATHS["vision_logs"].mkdir(parents=True, exist_ok=True)
    log_path = PATHS["vision_logs"] / f"{datetime.now().date()}.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def process_photo(img_bytes, filename, caption=None, source="esp32"):
    """Analyze photo, log vision entry, post owner_photo event. Returns analysis dict or None."""
    ts = datetime.now().isoformat()
    analysis = analyze_snapshot(img_bytes)
    if analysis:
        log_entry({**analysis, "timestamp": ts, "filename": filename, "status": "success",
                   "source": source, "owner_comment": caption})
    event_data = {"filename": filename, "source": source}
    if analysis:
        event_data.update(analysis)
    post_event("owner_photo", notes=caption or "", data=event_data)
    return analysis


def run(force=False):
    ts = datetime.now().isoformat()

    img_bytes, result = get_latest_snapshot(force=force)

    if img_bytes is None:
        entry = {"timestamp": ts, "status": "skipped", "reason": result}
        log_entry(entry)
        print(f"[shrimp-vision] {ts[:16]} — skipped ({result})")
        return

    try:
        analysis = process_photo(img_bytes, str(PATHS["snapshots"] / "latest.jpg"))
        if analysis:
            concerns_str = ", ".join(analysis["concerns"]) if analysis["concerns"] else "none"
            if analysis.get("tank_visible"):
                count = analysis.get("shrimp_count_visible", "?")
                clarity = analysis.get("water_clarity", "unknown")
                print(f"[shrimp-vision] {ts[:16]} — {count} shrimp visible | "
                      f"{clarity} water | concerns: {concerns_str}")
            else:
                subject = analysis.get("image_subject", "unknown subject")
                print(f"[shrimp-vision] {ts[:16]} — tank not visible ({subject}) | concerns: {concerns_str}")

    except Exception as e:
        entry = {"timestamp": ts, "status": "error", "error": str(e)}
        log_entry(entry)
        print(f"[shrimp-vision] {ts[:16]} — error: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="Skip freshness check (use for testing)")
    args = parser.parse_args()
    run(force=args.force)
