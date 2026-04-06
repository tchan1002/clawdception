# Skill: shrimp-vision

**What it does:** Visual tank monitoring via ESP32-CAM. Fetches the latest JPEG from `snapshots/latest.jpg` (posted by the ESP32-CAM every 5 min), sends it to Claude vision, and logs a structured analysis.

**When it runs:** Every 2 hours at :30 (uncomment in crontab.txt to enable).

**What it produces per run:**
- Estimated shrimp count, water clarity, algae presence, substrate condition, plant health
- List of visual concerns
- 2–3 sentence caretaker voice narrative
- Logged to `~/clawdception/logs/vision/YYYY-MM-DD.jsonl`

**Freshness check:** Skips if `snapshots/latest.jpg` is older than 30 min (camera offline). Use `--force` to bypass for testing.

**Data flow:**
```
ESP32-CAM → POST /api/snapshot (every 5 min)
         → snapshots/latest.jpg
         → shrimp-vision fetches bytes → Claude vision API → logs/vision/
```

**Dependencies:** `utils.py`, `config.py`. No extra pip packages required.

**How to enable:**
1. Flash `esp32_cam/esp32_cam.ino` to AI Thinker ESP32-CAM (set WiFi creds first)
2. Confirm snapshots arriving: `curl http://localhost:5001/api/snapshot/latest -o /tmp/test.jpg`
3. Uncomment the shrimp-vision cron line in `crontab.txt`

**How to test manually:**
```bash
cd ~/clawdception
python3 skills/shrimp_vision/run.py --force   # analyze latest snapshot regardless of age
python3 skills/shrimp_vision/run.py           # normal run (skips if snapshot stale)
```

**Modifiable:** Yes. skill-writer may propose changes to this skill.
