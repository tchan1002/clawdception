# REFERENCE.md — Clawdception Project Map

**Tank**: 10-gallon Neocaridina shrimp colony, Hyde Park, Chicago. Cycle started March 22, 2026. Shrimp introduced April 13, 2026.

---

## Architecture

```
[ESP32 Sensor Hub]                    [ESP32-CAM — 192.168.12.32]
  DS18B20 (temp) + pH + TDS            AI Thinker, port 80 (web) + POST /api/snapshot
  → POST JSON every 15 min               → POST JPEG every 5 min
        ↓                                        ↓
[Raspberry Pi — 192.168.12.76]
  sensor_server.py (Flask, port 5001)
  media_luna.db (SQLite — source of truth)
  snapshots/ (latest.jpg + timestamped archive)
      ↓
[Agent Stack — cron-driven]
  shrimp-monitor (every 15min) → shrimp-journal (every 6hr) → daily-log (7am)
  tweet-log (7:05am) → Twitter thread from daily log
  equipment-check (9am) → hardware health checks → call-toby
  shrimp-vision (every 2hr, disabled) → Claude vision analysis of latest snapshot
  telegram-listener (every 2min) → polls owner Telegram messages → owner_note / owner_photo events
  call-toby → Telegram notifications
  skill-writer (8:30am, self-gated) → proposals/
      ↓
[Web Dashboard]
  media_luna_dashboard.html — served by Flask at GET /
```

---

## File Map

| File | Purpose |
|------|---------|
| `media_luna_sensor_hub/media_luna_sensor_hub.ino` | ESP32 sensor hub firmware |
| `esp32_cam/esp32_cam.ino` | ESP32-CAM firmware (AI Thinker, 192.168.12.32) |
| `sensor_server.py` | Flask REST API + SQLite backend |
| `media_luna_dashboard.html` | Single-file web dashboard |
| `media_luna.db` | SQLite database (Pi copy is source of truth) |
| `config.py` | All shared constants: ranges, paths, system prompt, cycle start |
| `utils.py` | Shared functions used by all skills |
| `state_of_tank.md` | Rolling tank state — rewritten daily by daily-log |
| `agent_state.md` | Agent personality/disposition — rewritten daily by daily-log |
| `crontab.txt` | Cron schedule — review and install manually |
| `setup.sh` | Run once on Pi to install deps and create directories |

---

## Agent Skills

| Skill directory | Human name | Runs | Purpose |
|----------------|------------|------|---------|
| `skills/call_toby/` | call-toby | On-demand | Telegram notifications + file sends |
| `skills/shrimp_alert/` | shrimp-alert | On-demand | Danger threshold alerter → call-toby |
| `skills/shrimp_monitor/` | shrimp-monitor | Every 15min | Read sensors, Claude risk assessment, log decision |
| `skills/shrimp_journal/` | shrimp-journal | Every 6hr :05 | Narrative consolidation → journal/YYYY-MM-DD-HHMM.md |
| `skills/daily_log/` | daily-log | 7am daily | Morning summary + update state_of_tank.md + agent_state.md |
| `skills/tweet_log/` | tweet-log | 7:05am daily | Post daily log as Twitter thread; throwaway reactive posts |
| `skills/equipment_check/` | equipment-check | Every 30min | Sensor-derivable + schedule-based hardware health checks |
| `skills/shrimp_vision/` | shrimp-vision | Every 2hr (disabled) | ESP32-CAM snapshot → Claude vision analysis → logs/vision/ |
| `skills/telegram_listener/` | telegram-listener | Every 2min | Poll Telegram for owner messages → `owner_note` / `owner_photo` events |
| `skills/skill_writer/` | skill-writer | 8:30am daily | Self-improvement proposals → proposals/ (self-gated) |

---

## Target Water Parameters

| Parameter | Target | Danger zone |
|-----------|--------|-------------|
| Temperature | 72–78°F | <65°F or >82°F |
| pH | 6.5–7.5 | <6.0 or >8.0 |
| TDS | 150–250 ppm | <100 or >350 ppm |
| Ammonia | 0 ppm | >0.25 ppm |
| Nitrite | 0 ppm | >0.5 ppm |

---

## Detailed Reference Docs

Read these only when the task requires it:

| File | Read when... |
|------|-------------|
| `docs/api.md` | Editing `sensor_server.py`, adding endpoints, or querying the DB |
| `docs/firmware.md` | Editing `.ino`, debugging sensor drift, or checking calibration |
| `docs/ops.md` | Deployment, systemd, SSH, crontab, or git workflow |
| `docs/agent-memory.md` | Editing skills, `utils.py`, or understanding agent state/memory |
