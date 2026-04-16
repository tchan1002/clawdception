# Skill: shrimp-vision

**What it does:** Visual tank analysis via Claude vision. Called from two sources:
- **telegram-listener** — owner sends photo via Telegram; `analyze_snapshot()` called immediately on receipt
- **ESP32-CAM cron** (disabled — camera not connected) — fetches `snapshots/latest.jpg`, analyzes on schedule

Both paths call `analyze_snapshot(img_bytes)` and write to the same log via `log_entry()`.

**When it runs:**
- On demand: whenever telegram-listener receives a photo from the owner
- Scheduled: every 2 hours at :30 via cron (uncomment in `crontab.txt` once ESP32-CAM connected)

**What it produces per analysis:**
- `tank_visible` — bool, whether tank appears in image (photo may be test strip, equipment, etc)
- `shrimp_count_visible` — count of clearly-seen shrimp; 0 if none visible (no inference)
- Water clarity, algae presence/description, substrate condition, plant health — only when `tank_visible=true`
- List of visual concerns
- `image_subject` — what image shows if not tank
- `owner_comment` — caption from owner (empty string if none)
- Logged to `logs/vision/YYYY-MM-DD.jsonl`

No narrative field. Output is structured event catalog only.

**Shrimp detection hint in prompt:** Neocaridina in this colony appear red/reddish-orange or gray/translucent, 1-2cm. Prompt instructs: count only clearly visible, report 0 if none, no inference.

**Water clarity in prompt:** Only mark `slightly_cloudy`/`cloudy`/`murky` if water column itself looks turbid or muddy — suspended particles, milky haze, brown tint. Glass glare, reflections, camera angle artifacts are NOT cloudiness. Default to `clear` unless water visibly degraded. (Tank water is crystal clear; false positives from glare were a known issue.)

**Log schema:**
```json
{
  "timestamp": "2026-04-14T11:08:04",
  "filename": "2026-04-14_11-08-04.jpg",
  "owner_comment": "we've got molting behavior",
  "tank_visible": true,
  "shrimp_count_visible": 2,
  "water_clarity": "clear",
  "visible_algae": true,
  "algae_description": "...",
  "substrate_condition": "...",
  "plant_health": "stable",
  "concerns": [],
  "image_subject": null,
  "status": "success",
  "source": "telegram"
}
```

Non-tank image example:
```json
{
  "timestamp": "...",
  "tank_visible": false,
  "image_subject": "test strip",
  "concerns": [],
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
