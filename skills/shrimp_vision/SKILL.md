# Skill: shrimp-vision

**What it does:** Visual tank analysis via Claude vision. Called from three sources:
- **telegram-listener** — owner sends photo via Telegram; `process_photo()` called immediately on receipt
- **telegram-listener capture_request** — owner texts "take a photo"; listener GETs `/snapshot` from ESP32-CAM at `192.168.12.32`, calls `process_photo()`, sends photo + vision caption back via Telegram
- **ESP32-CAM cron** — fetches `snapshots/latest.jpg`, analyzes on schedule (cron line in `crontab.txt`)

All paths call `analyze_snapshot(img_bytes)` and write to same log via `log_entry()`.

**When it runs:**
- On demand: whenever telegram-listener receives a photo, or owner sends capture_request text
- Scheduled: every 2 hours at :30 via cron

**What it produces per analysis:**
- `tank_visible` — bool, whether tank appears in image (photo may be test strip, equipment, etc)
- `shrimp_count_visible` — count of clearly-seen shrimp; 0 if none visible (no inference)
- Water clarity, algae presence/description, substrate condition, plant health — only when `tank_visible=true`
- `image_quality` — `clear` | `dark` | `blurry` | `obstructed` — physical quality of image itself; required. Distinguishes "no shrimp seen" from "couldn't see anything"
- `narrative` — 1-2 sentence prose summary; required
- `concerns` — list of visual anomalies; required
- `image_subject` — what image shows if not tank
- `owner_comment` — caption from owner (empty string if none)
- Logged to `logs/vision/YYYY-MM-DD.jsonl`

**Failure behavior:** `process_photo` guards before sending to API — returns `None` and logs error entry if image empty or >4MB. If Claude returns no analysis, logs error entry; no event posted. Event only fires on successful analysis.

**Model:** `claude-sonnet-4-6` (upgraded from haiku for better visual accuracy). Max tokens: 1024.

**Shrimp detection in prompt:** Prompt biased toward finding shrimp, not away. Instructs model to:
- Scan three zones: foreground (front glass), midground (plants/substrate), background (rear glass/hardscape)
- Identify adults (red/orange-red/deep red), juveniles (translucent with faint red tint), berried females (darker, eggs visible)
- Count fully visible AND partially visible shrimp — include partial sightings, err on side of counting
- Exclude only if genuinely can't distinguish from debris

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
  "image_quality": "clear",
  "narrative": "Three shrimp visible near filter. Tank looks healthy.",
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
  "image_quality": "clear",
  "narrative": "Owner holding API test strip against light.",
  "concerns": [],
  "status": "success",
  "source": "telegram"
}
```

Error entry (empty/oversized/API fail):
```json
{
  "timestamp": "...",
  "status": "error",
  "reason": "empty image",
  "filename": "photo.jpg"
}
```

**Freshness check (cron path only):** Skips if `snapshots/latest.jpg` older than 30 min. Use `--force` to bypass.

**Data flow:**
```
Owner Telegram photo         → telegram-listener → process_photo() → logs/vision/ → vision reply via call_toby
Owner texts capture_request  → telegram-listener → GET 192.168.12.32/snapshot → process_photo() → send_photo + caption
ESP32-CAM cron               → snapshots/latest.jpg → shrimp-vision run.py → process_photo() → logs/vision/
```

**ESP32-CAM:** Live at `192.168.12.32`. Endpoints: `GET /snapshot` (JPEG), `GET /livestream` (MJPEG), `GET /` (status).

**Dependencies:** `utils.py`, `config.py`. No extra pip packages required.

**How to test manually:**
```bash
cd ~/clawdception
python3 skills/shrimp_vision/run.py --force   # analyze latest snapshot regardless of age
python3 skills/shrimp_vision/run.py           # normal run (skips if snapshot stale)
```

**Modifiable:** Yes. skill-writer may propose changes to this skill.
