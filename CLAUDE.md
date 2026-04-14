# CLAUDE.md — Agent Behavior for Clawdception

**Clawdception** = aquarium monitor for 10gal Neocaridina shrimp colony ("Media Luna"). ESP32 read sensor every 15min, POST JSON to Flask/SQLite on Pi (`192.168.12.76:5001`). Cron agent watch tank, write log. See REFERENCE.md for arch/file/skill. See `docs/` for detail.

---

## Hard Rules — Never do without explicit user confirmation

1. **No SCP/rsync/deploy to Pi** — deploy always manual.
2. **No modify sensor calibration constants** — set against physical solution, hard re-establish.
3. **No change ESP32 reading interval** (900,000 ms / 15 min) — affect WiFi/data.
4. **No run `arduino-cli upload`** — compile ok, flash not.
5. **No auto-commit or auto-push git.**

---

## Key Context

- **Tank start**: March 22, 2026. **Shrimp add**: April 13, 2026 — colony now active.
- **Target param**: Temp 72–78°F, pH 6.5–7.5, TDS 150–250 ppm.
- **ESP JSON** have deliberate 4-section structure (top-level, `debug`, `system`, `calibration`) — no flatten.
- **Dashboard** (`media_luna_dashboard.html`) = single self-contain HTML — no build tool. Keep that way.
- **`media_luna.db`** on Pi = source truth. Local copy maybe stale.
- **Skill dirs** use underscore (Python import); human name use hyphen.

---

## Verification

After edit `sensor_server.py`:
```bash
sudo systemctl restart media-luna.service && bash scripts/smoke_test.sh
```

After edit skill or `utils.py`/`config.py` (no restart need):
```bash
python3 skills/shrimp_monitor/run.py --force
```

Unit test: `python3 -m pytest tests/ -v`  
Health check: `/status` slash command, or `curl http://localhost:5001/api/health`

**Smoke test must pass (18/18) before consider any server-side change done.** Run with `/smoke` or `bash scripts/smoke_test.sh`. If pre-exist fail found, fix before move on.

**Always run `python3 -m pytest tests/ -v` after any code edit to confirm nothing broke.** Do not report edit done until tests pass.

---

## Documentation Protocol

**After every edit session, update relevant docs:**

- `REFERENCE.md` — arch diagram, file map, skill table. Update when add skill/endpoint/new dir.
- `docs/api.md` — all Flask endpoint and event type. Update when add/change endpoint or event schema.
- `docs/ops.md` — deploy, cron, systemd. Update when change `crontab.txt` or ops procedure.
- `docs/agent-memory.md` — agent state, memory, skill behavior. Update when change how skill read/write state.
- `CLAUDE.md` (this file) — key context and hard rule. Update when project state change (e.g. shrimp add, camera enable).

This keep future Claude session from re-derive system state from code alone.

---

## Action System

Monitor use **typed action schema** — no freeform recommended_actions string. Each decision's `actions` array contain object with `{type, actor, urgency?, value?, note?}`.

- `actor: owner` action sent to Toby via Telegram as bundle message after each Claude call.
- `actor: actuator` action log in decision JSON only — future dispatch queue. No send actuator action to Telegram.
- `photo_request` inject auto every 4hr (rate-limit by `logs/last_photo_request.txt`). Claude can also emit independent when visual context would change assess.
- See REFERENCE.md → "Decision Schema" for full action type table.

---

## Do Not

- Add npm, webpack, or any JS build tool
- Add Python dependency beyond Flask without check
- Create new file speculative — edit exist file
- Add error handle for scenario can't happen in this control hardware environment
- Guess Pi username/path — it's `pi@192.168.12.76`, repo at `~/clawdception`