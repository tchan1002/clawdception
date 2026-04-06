# REFERENCE.md — Clawdception Project Map

**Tank**: 10-gallon Neocaridina shrimp colony, Hyde Park, Chicago. Cycle started March 22, 2026. No shrimp yet.

---

## Architecture

```
[ESP32 Sensor Hub]
  DS18B20 (temp) + DFRobot pH v2 + DFRobot TDS
  → POST JSON every 15 min via WiFi
      ↓
[Raspberry Pi — 192.168.12.76]
  sensor_server.py (Flask, port 5001)
  media_luna.db (SQLite — source of truth)
      ↓
[Agent Stack — cron-driven]
  shrimp-monitor (every 15min) → shrimp-journal (every 6hr) → daily-log (7am)
  call-toby → Telegram notifications
  skill-writer (Sundays) → proposals/
      ↓
[Web Dashboard]
  media_luna_dashboard.html — served by Flask at GET /
```

---

## File Map

| File | Purpose |
|------|---------|
| `media_luna_sensor_hub/media_luna_sensor_hub.ino` | ESP32 firmware |
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
| `skills/shrimp_vision/` | shrimp-vision | Every 2hr (disabled) | Camera analysis stub — enable when Pi Camera connected |
| `skills/skill_writer/` | skill-writer | Sundays 8am | Weekly self-improvement proposals → proposals/ |

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
