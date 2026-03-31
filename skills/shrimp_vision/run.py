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
from config import PATHS


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
    # from picamera2 import Picamera2
    # import base64, anthropic, os
    #
    # cam = Picamera2()
    # cam.start()
    # frame = cam.capture_array()
    # cam.stop()
    # ...encode and send to claude vision...
    raise NotImplementedError("Camera capture not yet implemented")


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
        PATHS["vision_logs"].mkdir(parents=True, exist_ok=True)
        log_path = PATHS["vision_logs"] / f"{datetime.now().date()}.jsonl"
        with open(log_path, "a") as f:
            f.write(json.dumps({**analysis, "timestamp": ts}) + "\n")
        print(f"[shrimp-vision] Analysis logged at {ts[:16]}")
    except NotImplementedError:
        print("[shrimp-vision] Capture not yet implemented — camera stub only")
    except Exception as e:
        print(f"[shrimp-vision] Error: {e}")


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
