# Skill: shrimp-vision

**What it does:** Visual tank analysis via Claude vision. Called from two sources:
- **telegram-listener** — owner sends photo via Telegram; `analyze_snapshot()` called immediately on receipt
- **ESP32-CAM cron** (disabled — camera not connected) — fetches `snapshots/latest.jpg`, analyzes on schedule

Both paths call `analyze_snapshot(img_bytes)` and write to the same log via `log_entry()`.

**When it runs:**
- On demand: whenever telegram-listener receives a photo from the owner
- Scheduled: every 2 hours at :30 via cron (uncomment in `crontab.txt` once ESP32-CAM connected)

**What it produces per analysis:**
- Estimated shrimp count, water clarity, algae presence/description, substrate condition, plant health
- List of visual concerns
- 2–3 sentence caretaker voice narrative
- `owner_comment` — caption or message text from the owner (empty string if none)
- Logged to `logs/vision/YYYY-MM-DD.jsonl`

**Log schema:**
```json
{
  "timestamp": "2026-04-14T11:08:04",
  "filename": "2026-04-14_11-08-04.jpg",
  "owner_comment": "we've got molting behavior",
  "shrimp_count_estimate": 2,
  "water_clarity": "clear",
  "visible_algae": true,
  "algae_description": "...",
  "substrate_condition": "...",
  "plant_health": "stable",
  "concerns": ["..."],
  "narrative": "...",
  "status": "success",
  "source": "telegram"
}
```

**Freshness check (cron path only):** Skips if `snapshots/latest.jpg` older than 30 min. Use `--force` to bypass.

**Data flow:**
```
Owner Telegram photo → telegram-listener → analyze_snapshot() → logs/vision/
ESP32-CAM (future) → POST /api/snapshot → snapshots/latest.jpg → shrimp-vision cron → analyze_snapshot() → logs/vision/
```

**Dependencies:** `utils.py`, `config.py`. No extra pip packages required.

**How to enable ESP32-CAM cron:**
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
