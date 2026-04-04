"""
shrimp-vision — visual tank monitoring via Pi Camera or ESP32-CAM.

Currently a stub. Logs "vision check skipped" until a camera is connected.

Usage:
    python3 run.py
    python3 run.py --test   # test camera capture when connected
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import PATHS, get_cycle_day
from utils import call_claude

# Tool definition for structured tank image analysis
TOOL = {
    "name": "analyze_tank_image",
    "description": "Analyze a camera image of the Media Luna shrimp tank",
    "input_schema": {
        "type": "object",
        "properties": {
            "shrimp_count_estimate": {
                "type": "integer",
                "description": "Estimated number of visible shrimp"
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
            "narrative": {
                "type": "string",
                "description": "2-3 sentence caretaker voice observation"
            }
        },
        "required": ["shrimp_count_estimate", "water_clarity", "visible_algae", "substrate_condition",
                     "plant_health", "concerns", "narrative"]
    }
}


def check_pi_camera():
    """Returns True if picamera2 is importable (Pi Camera connected)."""
    try:
        import picamera2  # noqa
        return True
    except ImportError:
        return False


def capture_and_analyze():
    """Capture a frame and send to Claude vision API. Returns analysis dict or None."""
    # TODO: implement when Pi Camera Module v3 is connected
    from picamera2 import Picamera2
    import base64
    import io
    from PIL import Image

    # Capture image
    cam = Picamera2()
    cam.start()
    frame = cam.capture_array()
    cam.stop()

    # Convert to JPEG bytes
    img = Image.fromarray(frame)
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=85)
    img_bytes = buf.getvalue()
    img_b64 = base64.standard_b64encode(img_bytes).decode("utf-8")

    # Build prompt with image
    cycle_day = get_cycle_day()
    prompt = f"""Day {cycle_day} of the nitrogen cycle. Analyze this image of the Media Luna shrimp tank.

Look for:
- Number of visible shrimp
- Water clarity
- Algae growth (type, location)
- Substrate condition
- Plant health
- Any concerns or anomalies

Provide a structured assessment and a brief narrative observation in caretaker voice."""

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

    result = call_claude(
        messages=messages,
        skill_name="shrimp-vision",
        tools=[TOOL],
        tool_name=TOOL["name"],
    )

    return result


def capture_esp32cam(esp32_cam_ip):
    """Fetch a JPEG frame from an ESP32-CAM. Returns bytes or None."""
    # TODO: implement when ESP32-CAM is wired
    # import requests
    # resp = requests.get(f"http://{esp32_cam_ip}/capture", timeout=10)
    # return resp.content
    raise NotImplementedError("ESP32-CAM integration not yet implemented")


def run():
    ts = datetime.now().isoformat()

    if not check_pi_camera():
        entry = {
            "timestamp": ts,
            "status": "skipped",
            "reason": "camera not connected",
        }
        PATHS["vision_logs"].mkdir(parents=True, exist_ok=True)
        log_path = PATHS["vision_logs"] / f"{datetime.now().date()}.jsonl"
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        print(f"[shrimp-vision] {ts[:16]} — vision check skipped (camera not connected)")
        return

    try:
        analysis = capture_and_analyze()

        # Log structured analysis
        PATHS["vision_logs"].mkdir(parents=True, exist_ok=True)
        log_path = PATHS["vision_logs"] / f"{datetime.now().date()}.jsonl"
        with open(log_path, "a") as f:
            f.write(json.dumps({**analysis, "timestamp": ts, "status": "success"}) + "\n")

        # Print summary
        concerns_str = ", ".join(analysis["concerns"]) if analysis["concerns"] else "none"
        print(f"[shrimp-vision] {ts[:16]} — {analysis['shrimp_count_estimate']} shrimp | "
              f"{analysis['water_clarity']} water | concerns: {concerns_str}")

    except ImportError as e:
        # Camera libraries not available
        entry = {
            "timestamp": ts,
            "status": "error",
            "error": f"Camera libraries not installed: {e}",
        }
        PATHS["vision_logs"].mkdir(parents=True, exist_ok=True)
        log_path = PATHS["vision_logs"] / f"{datetime.now().date()}.jsonl"
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        print(f"[shrimp-vision] {ts[:16]} — camera libraries not installed")
    except Exception as e:
        entry = {
            "timestamp": ts,
            "status": "error",
            "error": str(e),
        }
        PATHS["vision_logs"].mkdir(parents=True, exist_ok=True)
        log_path = PATHS["vision_logs"] / f"{datetime.now().date()}.jsonl"
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        print(f"[shrimp-vision] {ts[:16]} — error: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Test camera capture")
    args = parser.parse_args()

    if args.test:
        if check_pi_camera():
            print("[shrimp-vision] Pi Camera detected. Capture test not yet implemented.")
        else:
            print("[shrimp-vision] No Pi Camera detected. Connect camera and try again.")
    else:
        run()
