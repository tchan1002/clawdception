# CLAUDE.md — Agent Behavior for Clawdception

This file defines how Claude Code agents should behave in this repository.
Read REFERENCE.md for full project context, architecture, commands, and roadmap.

---

## Project Summary

**Clawdception** is an aquarium monitoring system for a 10-gallon Neocaridina shrimp colony
("Media Luna") in Hyde Park. An ESP32 microcontroller reads water sensors every 15 minutes
and POSTs JSON to a Flask/SQLite server running on a Raspberry Pi. A web dashboard visualizes
the data in real time.

- **ESP32 firmware**: `media_luna_sensor_hub/media_luna_sensor_hub.ino`
- **Flask API + SQLite**: `sensor_server.py` + `media_luna.db`
- **Web dashboard**: `media_luna_dashboard.html`
- **Pi is the always-on server**: IP `192.168.12.76`, port `5001`

---

## Hard Rules

### Never do these without explicit user confirmation:
1. **Do not push files to the Raspberry Pi** — SCP/rsync/deploy is always manual. The user
   runs SCP themselves. Do not suggest or execute any deployment to the Pi unless asked.
2. **Do not modify sensor calibration constants** (pH offset, TDS compensation, temperature
   calibration) without the user explicitly requesting it — these were set against physical
   calibration solutions and are non-trivial to re-establish.
3. **Do not change the ESP32 firmware reading interval** (currently 900,000 ms / 15 min)
   without asking — it affects battery/WiFi behavior and data density.
4. **Do not run `arduino-cli upload`** unless the user explicitly asks for an upload.
   Compiling is fine; flashing the device is not.
5. **Do not auto-commit or auto-push to git** without explicit instruction.

---

## Preferred Workflows

### Arduino Development
- **Always compile before suggesting an upload** — catch errors before touching hardware.
- When editing `.ino` files, preserve the existing comment structure (calibration notes,
  wiring annotations, JSON payload structure docs — these are intentional).
- The USB port `/dev/cu.usbserial-0001` is stable for this ESP32. If it ever needs to
  be found, see REFERENCE.md.

### Flask / Python
- The server runs on the Pi at `0.0.0.0:5001`. For local testing on laptop, same port.
- `media_luna.db` is the live database on the Pi — the Pi's copy is source of truth.
  The local copy in the repo may be stale.
- If modifying the database schema, note the migration needed and flag it to the user.

### Dashboard (HTML/JS)
- The dashboard is a single self-contained HTML file — no build step, no npm, no bundler.
  Keep it that way unless explicitly asked to change the architecture.
- The 30-minute bucketing logic and chart range values are intentional — check with user
  before changing axis ranges (they reflect target water parameter ranges for shrimp).

---

## Context to Keep in Mind

- **Tank started**: March 22, 2026 — the nitrogen cycle is actively in progress.
  Day counter and nitrogen cycle panel in the dashboard are tied to this date.
- **Target water parameters**: Temp 74–76°F, pH 6.8–7.2, TDS 150–250 ppm.
- **The ESP JSON payload** has a deliberate structure: top-level calibrated values
  (for agent consumption), `debug` section (raw ADC/voltage for drift analysis),
  `system` section (WiFi/heap health), `calibration` section (current coefficients).
  Do not flatten or simplify this structure — it's designed for future AI agent use.
- **NFC manual event logging** is stubbed in `sensor_server.py` (`/api/events`) but
  not yet active. Hardware NFC tags are on the roadmap.
- **ESP camera** is on the roadmap for visual tank monitoring via the Pi.
- **Daily AI-driven log** via cron job on the Pi is on the roadmap.
- Future goal: run a Claude agent on the Pi that reads all sensors + camera.

---

## What Agents Are Typically Asked to Do

- Adjust sensor reading/averaging/filtering logic in the `.ino`
- Add or modify Flask API endpoints
- Refine dashboard chart layout, ranges, or data processing
- Analyze `media_luna.db` for trends or anomalies
- Help set up cron jobs and agent infrastructure on the Pi (future)
- Debug sensor drift using the `debug` section of the JSON payload
- Reference and copy terminal commands from REFERENCE.md rather than guessing

---

## Verifying Changes

### After editing `sensor_server.py`
The Flask server must be restarted to pick up changes. It runs as a systemd service on the Pi:
```bash
sudo systemctl restart media-luna.service
sudo systemctl status media-luna.service   # confirm active
```
Then run the smoke test to verify all endpoints respond correctly:
```bash
bash scripts/smoke_test.sh
# Or target the Pi from a laptop:
bash scripts/smoke_test.sh http://192.168.12.76:5001
```

### After editing a skill (`skills/*/run.py`, `utils.py`, `config.py`)
No restart needed — skills are run directly by cron or manually. Test immediately:
```bash
cd ~/clawdception
python3 skills/shrimp_monitor/run.py --force   # force a Claude call
python3 skills/shrimp_journal/run.py
python3 skills/call_toby/run.py --test
```

### Running unit tests
Tests cover pure Python functions (no server, no hardware required):
```bash
cd ~/clawdception && python3 -m pytest tests/ -v
```

### Quick system health check
Use the `/status` slash command in Claude Code, or manually:
```bash
curl http://localhost:5001/api/health
tail -5 logs/monitor.log
```

---

## Do Not

- Add npm, webpack, or any JS build tooling to this project
- Add Python dependencies beyond Flask without checking
- Create new files speculatively — edit existing files
- Add error handling for scenarios that can't happen in this controlled hardware environment
- Guess the Pi username, path, or SSH config — check REFERENCE.md (`pi@192.168.12.76`, repo at `~/clawdception`)
