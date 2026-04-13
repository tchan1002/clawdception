# CLAUDE.md — Agent Behavior for Clawdception

**Clawdception** is an aquarium monitoring system for a 10-gallon Neocaridina shrimp colony ("Media Luna"). An ESP32 reads water sensors every 15 min and POSTs JSON to a Flask/SQLite server on a Raspberry Pi (`192.168.12.76:5001`). A cron-driven agent stack monitors the tank and writes logs. See REFERENCE.md for architecture, file map, and skills. See `docs/` for detailed reference.

---

## Hard Rules — Never do without explicit user confirmation

1. **Do not SCP/rsync/deploy to the Pi** — deployment is always manual.
2. **Do not modify sensor calibration constants** — set against physical solutions, non-trivial to re-establish.
3. **Do not change the ESP32 reading interval** (900,000 ms / 15 min) — affects WiFi/data behavior.
4. **Do not run `arduino-cli upload`** — compiling is fine, flashing is not.
5. **Do not auto-commit or auto-push to git.**

---

## Key Context

- **Tank started**: March 22, 2026. **Shrimp introduced**: April 13, 2026 — colony is now active.
- **Target parameters**: Temp 72–78°F, pH 6.5–7.5, TDS 150–250 ppm.
- **ESP JSON payload** has a deliberate 4-section structure (top-level, `debug`, `system`, `calibration`) — do not flatten it.
- **Dashboard** (`media_luna_dashboard.html`) is a single self-contained HTML file — no build tooling. Keep it that way.
- **`media_luna.db`** on the Pi is source of truth. Local copy may be stale.
- **Skill dirs** use underscores (Python imports); human names use hyphens.

---

## Verification

After editing `sensor_server.py`:
```bash
sudo systemctl restart media-luna.service && bash scripts/smoke_test.sh
```

After editing a skill or `utils.py`/`config.py` (no restart needed):
```bash
python3 skills/shrimp_monitor/run.py --force
```

Unit tests: `python3 -m pytest tests/ -v`  
Health check: `/status` slash command, or `curl http://localhost:5001/api/health`

---

## Documentation Protocol

**After every edit session, update the relevant docs:**

- `REFERENCE.md` — architecture diagram, file map, skills table. Update when adding skills, endpoints, or new directories.
- `docs/api.md` — all Flask endpoints and event types. Update when adding/changing endpoints or event schemas.
- `docs/ops.md` — deployment, cron, systemd. Update when changing `crontab.txt` or ops procedures.
- `docs/agent-memory.md` — agent state, memory, skill behavior. Update when changing how skills read/write state.
- `CLAUDE.md` (this file) — key context and hard rules. Update when project state changes (e.g. shrimp added, camera enabled).

This keeps future Claude sessions from having to re-derive the system state from code alone.

---

## Do Not

- Add npm, webpack, or any JS build tooling
- Add Python dependencies beyond Flask without checking
- Create new files speculatively — edit existing files
- Add error handling for scenarios that can't happen in this controlled hardware environment
- Guess Pi username/path — it's `pi@192.168.12.76`, repo at `~/clawdception`
