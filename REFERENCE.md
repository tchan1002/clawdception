# REFERENCE.md — Clawdception Project Reference

Living documentation for the Media Luna aquarium monitoring system.
Update this file as the project evolves. Agents and developers should read this before asking questions.

---

## Project Overview

**Clawdception** is a DIY aquarium monitoring and automation system for a 10-gallon
Neocaridina shrimp colony named **Media Luna**, located in Hyde Park, Chicago.

- **Tank start date**: March 22, 2026
- **Status**: Nitrogen cycle in progress. No shrimp yet.
- **Goal**: Autonomous AI caretaker agent running on the Pi — monitoring sensors, writing daily logs, and eventually controlling the environment via smart plug actuators.

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
  shrimp-monitor (every 15min) → shrimp-journal (every 2hr) → daily-log (7am)
  call-toby → Telegram notifications
  skill-writer (Sundays) → proposals/
      ↓
[Web Dashboard]
  media_luna_dashboard.html
  served by Flask at GET /
  polls /api/sensors every 30 seconds
```

**The Pi is always-on** and holds the live database. The repo on the laptop is for development. Files are pushed to the Pi manually via SCP. The Pi's copy of `media_luna.db` is source of truth.

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
| `setup.sh` | Run once on Pi to install deps and create directories |
| `crontab.txt` | Cron schedule — review and install manually |
| `state_of_tank.md` | Rolling tank state — rewritten daily by daily-log |
| `agent_state.md` | Agent personality/disposition — rewritten daily by daily-log |
| `CLAUDE.md` | Hard rules and behavior guidelines for agents |
| `REFERENCE.md` | This file |

---

## Agent Skills

All skills live in `skills/`. Directory names use underscores for Python import compatibility.
Each skill has `SKILL.md` (spec) and `run.py` (implementation).

| Skill directory | Human name | Runs | Purpose |
|----------------|------------|------|---------|
| `skills/call_toby/` | call-toby | On-demand | Telegram notifications (info/warning/critical) |
| `skills/shrimp_alert/` | shrimp-alert | On-demand | Danger threshold alerter → calls call-toby |
| `skills/shrimp_monitor/` | shrimp-monitor | Every 15min | Core loop: read sensors, Claude risk assessment, log decision |
| `skills/shrimp_journal/` | shrimp-journal | Every 2hr :05 | Narrative consolidation → journal/YYYY-MM-DD.md |
| `skills/daily_log/` | daily-log | 7am daily | Morning summary + update state_of_tank.md + agent_state.md |
| `skills/shrimp_vision/` | shrimp-vision | Every 2hr :30 (disabled) | Camera analysis stub — enable when Pi Camera connected |
| `skills/skill_writer/` | skill-writer | Sundays 8am | Weekly self-improvement proposals → proposals/ |

**Protected skills** (never modified by skill-writer): call-toby, shrimp-alert, skill-writer

**Modifiable skills** (skill-writer may propose changes): shrimp-monitor, shrimp-journal, shrimp-vision, daily-log

### How to import a skill

```python
from skills.call_toby.run import call_toby
from skills.shrimp_alert.run import alert
```

### How to run a skill manually

```bash
cd ~/clawdception
python3 skills/call_toby/run.py --test
python3 skills/shrimp_monitor/run.py
python3 skills/daily_log/run.py
python3 skills/daily_log/run.py --date 2026-03-30   # backfill a specific date
```

---

## Agent File Structure

```
~/clawdception/
├── journal/                  # working memory: journal/YYYY-MM-DD.md (appended by shrimp-journal)
├── daily-logs/               # immutable daily logs: YYYY-MM-DD.md (written by daily-log, never edited)
├── proposals/                # skill-writer proposals: YYYY-MM-DD-{name}/ dirs, reviewed by Toby
├── logs/
│   ├── monitor.log           # one-line summaries from shrimp-monitor
│   ├── alerts.jsonl          # danger alerts fired by shrimp-alert
│   ├── calls.jsonl           # call-toby log (fallback when Telegram not configured)
│   ├── journal.log           # shrimp-journal cron stdout
│   ├── daily_log.log         # daily-log cron stdout
│   ├── skill_writer.log      # skill-writer cron stdout
│   ├── decisions/            # YYYY-MM-DD.jsonl decision logs from shrimp-monitor
│   └── vision/               # YYYY-MM-DD.jsonl vision logs from shrimp-vision
├── state_of_tank.md          # rolling tank state — always current, rewritten daily
├── agent_state.md            # agent personality + disposition — evolves over time
├── config.py                 # all constants, ranges, paths, system prompt
├── utils.py                  # shared functions (fetch, call_claude, read/write helpers)
├── setup.sh                  # Pi initialization script
└── crontab.txt               # cron schedule for all skills
```

---

## The Agent's Memory System

The agent has several layers of memory, from short to long:

| Layer | File/Location | Scope | Written by |
|-------|--------------|-------|------------|
| Immediate | sensor readings in SQLite | real-time | ESP32 |
| Working | `journal/YYYY-MM-DD.md` | today | shrimp-journal (every 2hr) |
| Decision log | `logs/decisions/YYYY-MM-DD.jsonl` | today | shrimp-monitor (every 15min) |
| Daily record | `daily-logs/YYYY-MM-DD.md` | one day — **immutable** | daily-log (7am) |
| Tank state | `state_of_tank.md` | rolling current | daily-log (overwrites daily) |
| Self | `agent_state.md` | personality, disposition | daily-log (overwrites daily) |

Daily logs are **never edited** after creation. They are the source of truth for what happened on a given day.

---

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `ANTHROPIC_API_KEY` | Yes | Claude API access for all skills |
| `TELEGRAM_BOT_TOKEN` | Optional | call-toby Telegram notifications |
| `TELEGRAM_CHAT_ID` | Optional | call-toby Telegram chat target |

If Telegram is not configured, call-toby falls back to `logs/calls.jsonl` + stdout.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Serves dashboard HTML |
| POST | `/api/sensors` | Receive ESP32 reading (returns 201) |
| GET | `/api/sensors` | Recent readings (`?limit=50`, `?hours=N`) |
| GET | `/api/sensors/latest` | Single latest reading |
| POST | `/api/events` | Log a structured event |
| GET | `/api/events` | Query events (`?limit=N`, `?since=ISO`, `?type=water_test`) |
| GET | `/api/health` | Health check, returns last reading timestamp |

### Event Types

```json
{
  "event_type": "water_test" | "water_change" | "feeding" | "observation" | "manual_override" | "snapshot",
  "data": {},
  "source": "nfc" | "manual" | "agent",
  "timestamp": "ISO 8601 (optional, defaults to now)"
}
```

Examples:
```json
{"event_type": "water_test", "data": {"ammonia_ppm": 1.0, "nitrite_ppm": 0.25, "nitrate_ppm": 5.0}, "source": "manual"}
{"event_type": "water_change", "data": {"percent": 25, "treated": true, "notes": "used Prime"}, "source": "manual"}
{"event_type": "observation", "data": {"note": "biofilm forming on driftwood"}, "source": "manual"}
```

---

## Database Schema

```sql
CREATE TABLE sensor_readings (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,
    temp_c REAL, temp_f REAL, ph REAL, tds_ppm REAL,
    source TEXT,
    raw_json TEXT  -- full ESP32 JSON payload
);

CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,
    event_type TEXT,
    data_json TEXT,  -- flexible JSON depending on event_type
    source TEXT      -- "nfc" | "manual" | "agent"
);

-- Legacy table (kept for backward compat)
CREATE TABLE manual_events (
    id INTEGER PRIMARY KEY,
    timestamp TEXT, event_type TEXT, notes TEXT
);
```

---

## Target Water Parameters (Neocaridina shrimp)

| Parameter | Target | Danger zone | Source |
|-----------|--------|-------------|--------|
| Temperature | 72–78°F | <65°F or >82°F | DS18B20 sensor |
| pH | 6.5–7.5 | <6.0 or >8.0 | DFRobot pH v2 |
| TDS | 150–250 ppm | <100 or >350 ppm | DFRobot TDS |
| Ammonia | 0 ppm | >0.25 ppm | Manual API kit |
| Nitrite | 0 ppm | >0.5 ppm | Manual API kit |

---

## Terminal Commands

### Arduino — Compile & Upload

```bash
# Compile only (safe to run anytime)
arduino-cli compile --fqbn esp32:esp32:esp32 ~/clawdception/media_luna_sensor_hub

# Upload to ESP32 (flashes device — confirm before running)
arduino-cli upload --fqbn esp32:esp32:esp32 --port /dev/cu.usbserial-0001 ~/clawdception/media_luna_sensor_hub
```

USB port: `/dev/cu.usbserial-0001` — stable for this ESP32.

### Push Files to Raspberry Pi (SCP)

**The user runs SCP manually. Agents must not run these.**

```bash
# Push entire repo to Pi
scp -r ~/clawdception pi@192.168.12.76:~/clawdception

# Push specific file
scp ~/clawdception/sensor_server.py pi@192.168.12.76:~/clawdception/sensor_server.py
```

### SSH into Pi

```bash
ssh pi@192.168.12.76
```

### Manage the Flask Server on Pi (systemd)

```bash
# Find service name
ssh pi@192.168.12.76 "systemctl list-units --type=service | grep -i sensor"

ssh pi@192.168.12.76 "sudo systemctl restart <service-name>"
ssh pi@192.168.12.76 "sudo systemctl status <service-name>"
ssh pi@192.168.12.76 "sudo journalctl -u <service-name> -f"
```

### Install Cron Jobs on Pi

```bash
# Review crontab.txt first — edit in ANTHROPIC_API_KEY
nano ~/clawdception/crontab.txt

# Install (replaces existing crontab)
crontab ~/clawdception/crontab.txt

# Or append to existing:
(crontab -l 2>/dev/null; cat ~/clawdception/crontab.txt) | crontab -
```

### SQLite Database Queries

```bash
sqlite3 ~/clawdception/media_luna.db ".schema"
sqlite3 ~/clawdception/media_luna.db "SELECT * FROM sensor_readings ORDER BY id DESC LIMIT 5;"
sqlite3 ~/clawdception/media_luna.db "SELECT * FROM events ORDER BY id DESC LIMIT 10;"
```

### First-time Pi Setup

```bash
cd ~/clawdception
./setup.sh
python3 skills/call_toby/run.py --test
```

---

## Hardware

### ESP32 Wiring

| Sensor | Pin | Notes |
|--------|-----|-------|
| DS18B20 (temp) data | GPIO 4 | 4.7kΩ pullup to 3.3V required |
| DFRobot pH v2 signal | GPIO 34 (ADC1) | Analog input |
| DFRobot TDS signal | GPIO 35 (ADC1) | Analog input |

### WiFi

- **SSID**: Shroomies
- **ESP32 target server**: `http://192.168.12.76:5001/api/sensors`

---

## Sensor Calibration

**Do not modify calibration constants without Toby's explicit instruction.**

### pH (last calibrated: March 30, 2026)

| Buffer | Measured Voltage |
|--------|----------------|
| pH 7.0 | 1.37V |
| pH 4.0 | 1.88V |

- Offset applied: `-1.10` (matched to API test kit reading of 6.4)
- Temperature compensation: `+0.003 pH per °C`

### TDS

- DFRobot temperature-compensated formula. No custom offset.

### Temperature (DS18B20)

- Factory spec ±0.5°C. No custom offset.

---

## ESP32 JSON Payload Structure

```json
{
  "temp_c": 23.5, "temp_f": 74.3, "ph": 6.8, "tds_ppm": 187,
  "debug": {
    "ph_raw_adc": 1750, "ph_voltage": 1.37,
    "ph_pre_offset": 7.9, "tds_raw_adc": 2100, "tds_voltage": 1.69
  },
  "system": {
    "wifi_rssi": -58, "heap_free": 215000, "uptime_ms": 3600000,
    "reading_count": 4, "reconnect_count": 0, "failure_count": 0
  },
  "calibration": {
    "ph_offset": -1.10, "ph_neutral_voltage": 1.37,
    "ph_acid_voltage": 1.88, "temp_compensation": 0.003
  }
}
```

Top-level values are calibrated (for agent consumption).
`debug` = raw ADC/voltage for drift detection.
`system` = ESP32 health.
`calibration` = coefficients currently applied.

---

## Tank Context

- **Cycle started**: March 22, 2026. Seeded with live ceramic bio media from Golden Aquarium (Fritz Turbo Start unavailable). Fluval Stratum substrate buffers pH acidic.
- **pH baseline**: ~6.32 (expected — substrate + organic decomposition). Should rise as cycle progresses.
- **TDS baseline**: 150 ppm (bottom of target range). Should rise as nitrogen waste accumulates.
- **Temp baseline**: ~77°F (room temp, heater off during testing).
- No shrimp yet. Tank is cycling. Shrimp introduction pending cycle completion.

---

## Roadmap

### Near-term
- [ ] Set up Telegram for call-toby (BOT_TOKEN + CHAT_ID)
- [ ] Install crons on Pi (`crontab crontab.txt`)
- [ ] NFC sticker tags → tap to POST to `/api/events`
- [ ] First manual water test → POST to `/api/events` as `water_test`
- [ ] Pi Camera Module v3 → enable shrimp-vision

### Future
- [ ] Kasa smart plugs (heater, desk lamp, dosing pump) → actuator control skill
- [ ] ESP32-CAM visual feed
- [ ] skill-writer begins proposing its first improvements
- [ ] Shrimp introduction (post-cycle)
- [ ] Open source release

### Completed
- [x] ESP32 sensor hub (temp, pH, TDS) posting every 15 min
- [x] Flask REST API on Pi
- [x] SQLite persistent storage
- [x] Web dashboard with Chart.js + nitrogen cycle tracker
- [x] Pi as always-on server
- [x] pH calibration with buffer solutions (Mar 30, 2026)
- [x] Full agent infrastructure (config, utils, 7 skills, state files, cron) — Mar 31, 2026

---

## Notes & Decisions

- **Single HTML file for dashboard**: No build tooling. Keep it self-contained.
- **Pi is source of truth**: Local `media_luna.db` may be stale. Always query Pi for live data.
- **SCP is manual**: Intentional while deployment safeguards are being designed.
- **30-min bucketing in dashboard**: Intentional smoothing for chart readability.
- **Debug section in ESP payload**: For future agent-based drift detection.
- **Skill directories use underscores**: Python import compatibility. Human-readable names use hyphens.
- **Daily logs are immutable**: Once written, never edited. Source of truth for each day.
- **agent_state.md is the agent's private self**: Rewritten daily — this is how personality evolves over time.
