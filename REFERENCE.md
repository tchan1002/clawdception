# REFERENCE.md — Clawdception Project Reference

Living documentation for the Media Luna aquarium monitoring system.
Update this file as the project evolves. Agents should read this before asking questions.

---

## Project Overview

**Clawdception** is a DIY aquarium monitoring and automation system for a 10-gallon
Neocaridina shrimp colony named **Media Luna**, located in Hyde Park.

- **Tank start date**: March 22, 2026
- **Status**: Nitrogen cycle in progress (Week 1–4)
- **Goal**: Eventually run a Claude AI agent on the Pi that reads all sensors + camera
  and produces daily logs, with potential future control over ESP32 config

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
[Web Dashboard]
  media_luna_dashboard.html
  served by Flask at GET /
  polls /api/sensors every 30 seconds
```

**The Pi is always-on** and holds the live database. The repo on the laptop is for
development. Files are pushed to the Pi manually via SCP.

---

## File Map

| File | Purpose |
|------|---------|
| `media_luna_sensor_hub/media_luna_sensor_hub.ino` | ESP32 firmware |
| `sensor_server.py` | Flask REST API + SQLite backend |
| `media_luna_dashboard.html` | Single-file web dashboard |
| `media_luna.db` | SQLite database (live copy on Pi is source of truth) |
| `CLAUDE.md` | Agent behavior rules |
| `REFERENCE.md` | This file |

---

## Terminal Commands

### Arduino — Compile & Upload

```bash
# Compile only (safe to run anytime)
arduino-cli compile --fqbn esp32:esp32:esp32 ~/clawdception/media_luna_sensor_hub

# Upload to ESP32 (flashes device — confirm before running)
arduino-cli upload --fqbn esp32:esp32:esp32 --port /dev/cu.usbserial-0001 ~/clawdception/media_luna_sensor_hub

# Compile + upload in one shot
arduino-cli compile --fqbn esp32:esp32:esp32 ~/clawdception/media_luna_sensor_hub && \
arduino-cli upload --fqbn esp32:esp32:esp32 --port /dev/cu.usbserial-0001 ~/clawdception/media_luna_sensor_hub
```

**USB port**: `/dev/cu.usbserial-0001` — stable for this ESP32.
If it ever changes, find it with:
```bash
ls /dev/cu.*
# or
arduino-cli board list
```

### Serial Monitor (live ESP32 debug output)

```bash
arduino-cli monitor --port /dev/cu.usbserial-0001 --config baudrate=115200
# or use Arduino IDE / VS Code Serial Monitor
```

### Push Files to Raspberry Pi (SCP)

**The user runs SCP manually. Agents must not run these without explicit instruction.**

```bash
# Push entire repo to Pi
scp -r ~/clawdception pi@192.168.12.76:~/clawdception

# Push specific file (e.g., after editing sensor_server.py)
scp ~/clawdception/sensor_server.py pi@192.168.12.76:~/clawdception/sensor_server.py

# Push dashboard only
scp ~/clawdception/media_luna_dashboard.html pi@192.168.12.76:~/clawdception/media_luna_dashboard.html
```

### SSH into Pi

```bash
ssh pi@192.168.12.76
```

### Manage the Flask Server on Pi (systemd service)

`sensor_server.py` runs as a systemd service on the Pi for reboot persistence.
**Service name**: TBD — run the discovery command below if unknown.

```bash
# Find the service name
ssh pi@192.168.12.76 "systemctl list-units --type=service | grep -i sensor"

# Common operations (replace <service-name> once known)
ssh pi@192.168.12.76 "sudo systemctl restart <service-name>"
ssh pi@192.168.12.76 "sudo systemctl status <service-name>"
ssh pi@192.168.12.76 "sudo systemctl stop <service-name>"
ssh pi@192.168.12.76 "sudo systemctl start <service-name>"

# Tail live logs from the service
ssh pi@192.168.12.76 "sudo journalctl -u <service-name> -f"
```

After pushing a new version of `sensor_server.py`, restart the service for changes to take effect.

### Run Flask Server Locally (laptop, for development)

```bash
pip install flask
python sensor_server.py
# Runs on 0.0.0.0:5001
# Dashboard: http://localhost:5001
# Note: local media_luna.db may be stale — Pi is source of truth
```

### SQLite Database Queries

```bash
# Open database
sqlite3 ~/clawdception/media_luna.db

# Quick inspection
sqlite3 ~/clawdception/media_luna.db ".schema"
sqlite3 ~/clawdception/media_luna.db "SELECT COUNT(*) FROM sensor_readings;"
sqlite3 ~/clawdception/media_luna.db "SELECT * FROM sensor_readings ORDER BY id DESC LIMIT 5;"

# On Pi (source of truth)
ssh pi@192.168.12.76 "sqlite3 ~/clawdception/media_luna.db 'SELECT * FROM sensor_readings ORDER BY id DESC LIMIT 5;'"
```

---

## Hardware

### ESP32 Wiring

| Sensor | Pin | Notes |
|--------|-----|-------|
| DS18B20 (temp) data | GPIO 4 | 4.7kΩ pullup to 3.3V required |
| DFRobot pH v2 signal | GPIO 34 (ADC1) | Analog input |
| DFRobot TDS signal | GPIO 35 (ADC1) | Analog input |

**ADC config**: 12-bit resolution, 11dB attenuation on GPIO 34 and 35.

### WiFi

- **SSID**: Shroomies
- **ESP32 target server**: `http://192.168.12.76:5001/api/sensors`

---

## Sensor Configuration & Calibration

### Reading Interval
- **Production**: 900,000 ms (15 minutes)
- **Testing**: Change to 30,000 ms (30 seconds) in firmware

### pH Calibration (last calibrated: March 30, 2026)

| Buffer | Measured Voltage |
|--------|----------------|
| pH 7.0 (neutral) | 1.37V |
| pH 4.0 (acidic) | 1.88V |

- **Offset applied**: `-1.10` (matched to API test kit reading of 6.4)
- **Temperature compensation**: `+0.003 pH per °C`
- Calibration solutions needed: pH 4.0 and pH 7.0 buffer solutions

### TDS Calibration
- Uses DFRobot temperature-compensated formula
- No custom offset currently applied

### Temperature (DS18B20)
- Factory spec ±0.5°C, no custom offset applied

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Serves dashboard HTML |
| POST | `/api/sensors` | Receive ESP32 reading (returns 201) |
| GET | `/api/sensors` | Recent readings (`?limit=50`, `?hours=N`) |
| GET | `/api/sensors/latest` | Single latest reading |
| POST | `/api/events` | Log a manual event (NFC / manual) |
| GET | `/api/health` | Health check, returns last reading timestamp |

### ESP32 JSON Payload Structure

```json
{
  "temp_c": 23.5,
  "temp_f": 74.3,
  "ph": 6.8,
  "tds_ppm": 187,
  "debug": {
    "ph_raw_adc": 1750,
    "ph_voltage": 1.37,
    "ph_pre_offset": 7.9,
    "tds_raw_adc": 2100,
    "tds_voltage": 1.69
  },
  "system": {
    "wifi_rssi": -58,
    "heap_free": 215000,
    "uptime_ms": 3600000,
    "reading_count": 4,
    "reconnect_count": 0,
    "failure_count": 0
  },
  "calibration": {
    "ph_offset": -1.10,
    "ph_neutral_voltage": 1.37,
    "ph_acid_voltage": 1.88,
    "temp_compensation": 0.003
  }
}
```

Top-level values are calibrated (for agent consumption).
`debug` section contains raw ADC/voltage for drift detection.
`system` section is for ESP32 health monitoring.
`calibration` section documents what's been applied.

---

## Target Water Parameters (Neocaridina shrimp)

| Parameter | Target Range | Alert Range |
|-----------|-------------|-------------|
| Temperature | 74–76°F (23–24°C) | >78°F or <72°F |
| pH | 6.8–7.2 | <6.5 or >7.5 |
| TDS | 150–250 ppm | <100 or >300 ppm |

---

## Database Schema

```sql
CREATE TABLE sensor_readings (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,
    temp_c REAL,
    temp_f REAL,
    ph REAL,
    tds_ppm REAL,
    source TEXT,
    raw_json TEXT  -- full ESP32 JSON payload stored here
);

CREATE TABLE manual_events (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,
    event_type TEXT,
    notes TEXT
);
```

---

## Roadmap

### Near-term
- [ ] NFC sticker tags → tap to POST to `/api/events` (water changes, feeding, dosing)
- [ ] ESP32-CAM module → visual feed of tank, processed on Pi
- [ ] Daily cron job on Pi → AI-generated log of water parameter trends

### Future
- [ ] Claude agent on Pi reading sensors + camera + generating insights
- [ ] Investigate Pi auto-writing ESP32 config (reading interval, calibration) — **not yet active, safeguards needed first**
- [ ] Open source release

### Completed
- [x] ESP32 sensor hub (temp, pH, TDS) posting every 15 min
- [x] Flask REST API on Pi
- [x] SQLite persistent storage on Pi
- [x] Web dashboard with Chart.js charts + nitrogen cycle tracker
- [x] Pi as always-on server (replaced laptop)
- [x] pH calibration with buffer solutions (Mar 30, 2026)

---

## Notes & Decisions

- **Single HTML file for dashboard**: No build tooling. Keep it self-contained.
- **Pi is source of truth**: Local `media_luna.db` in the repo may be stale. Always query Pi for live data.
- **SCP is manual**: User pushes to Pi themselves. This is intentional while deployment safeguards are being designed.
- **30-min bucketing in dashboard**: Intentional smoothing for chart readability. Raw readings in table below chart.
- **Debug section in ESP payload**: Designed for future agent-based drift detection and re-calibration analysis.
