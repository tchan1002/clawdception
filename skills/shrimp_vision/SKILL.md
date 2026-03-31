# Skill: shrimp-vision

**What it does:** Visual tank monitoring via camera. Currently a stub — logs "vision check skipped" until a camera is connected.

**When it runs:** Every 2 hours at :30 (when enabled — commented out in crontab by default).

**What it will do when camera is connected:**
- Capture a frame from Pi Camera Module v3 via `picamera2`
- Send to Claude vision API
- Get back: estimated shrimp count, activity level, visible dead shrimp, berried females, color assessment
- Log to `~/clawdception/logs/vision/YYYY-MM-DD.jsonl`

**Future: ESP32-CAM integration**
- HTTP GET to ESP32-CAM IP for a JPEG frame
- Same Claude vision analysis pipeline

**Dependencies:** utils.py, config.py. When active: `picamera2` (Pi Camera v3) or `requests` (ESP32-CAM)

**How to enable:**
1. Connect Pi Camera Module v3
2. Uncomment the shrimp-vision cron line in crontab.txt
3. Run `python3 skills/shrimp_vision/run.py --test` to verify capture

**How to test manually:**
```bash
cd ~/clawdception
python3 skills/shrimp_vision/run.py
# Currently logs "vision check skipped — camera not connected"
```

**Modifiable:** Yes. skill-writer may propose changes to this skill.
