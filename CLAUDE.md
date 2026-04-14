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

## Edit Protocol

Every edit follows this sequence — **in order, no skipping**:

1. **Implement** — make code change
2. **Test** — run `python3 -m pytest tests/ -v` (and smoke test if server-side). Do not report done until tests pass.
3. **Document** — mandatory, not optional. Task not done until docs updated.

**Always update after any code change:**
- `REFERENCE.md` — arch diagram, file map, skill table. Any change to skill behavior, data flow, or file output = update here first.

**Update when relevant section touched:**
- `docs/api.md` — add/change endpoint or event schema
- `docs/ops.md` — change `crontab.txt` or ops procedure
- `docs/agent-memory.md` — change how skill read/write state, logs, or memory files
- `CLAUDE.md` (this file) — project state change (e.g. shrimp add, camera enable, new hard rule)

Future Claude session must not re-derive system state from code alone.

---

## Action System

Monitor use **typed action schema** — no freeform recommended_actions string. Each decision's `actions` array contain object with `{type, actor, urgency?, value?, note?}`.

- `actor: owner` action sent to Toby via Telegram when its per-type cooldown elapsed (see `ACTION_COOLDOWNS` in `shrimp_monitor/run.py`). Urgent actions bypass cooldown.
- `actor: actuator` action log in decision JSON only — future dispatch queue. No send actuator action to Telegram.
- `photo_request` inject auto when `hours_since_last_photo() >= 4`. Cooldown prevents re-nag within 4hr of last sent. State persisted in `logs/action_cooldowns.json`.
- At 8/20 check-in, if no actions pass cooldown, status-only blurb sent ("all clear + readings").
- See REFERENCE.md → "Decision Schema" for full action type table.

---

## Writing Style for Agent Instructions

All docs Claude writes to itself (CLAUDE.md, REFERENCE.md, docs/*.md) use caveman style — drop articles, fragments ok, short synonyms. Technical substance preserved exactly. Code blocks unchanged. Token cost cut ~50%.

---

## Coding Philosophy

Cut > add. Shorter solution beat longer one. If two approaches solve same problem, pick one with less code.

Code self-documents. Name reveals intent. No comment needed for obvious thing. Comment only where logic non-obvious.

No duplication. One pathway per result. Use existing code/resource before build new. Extend, don't parallel.

When cut — clean completely. Remove dead imports, unused constants, obsolete comments, now-unreachable branches. Cut leaves no corpse.

Never add complexity to solve what deletion could solve. No wrapper around thing that should not exist. No flag to suppress behavior that should be removed. No coordination between two paths — delete one path.

Code done when nothing left to remove, not when nothing left to add.

---

## Do Not

- Add npm, webpack, or any JS build tool
- Add Python dependency beyond Flask without check
- Create new file speculative — edit exist file
- Add error handle for scenario can't happen in this control hardware environment
- Write redundant/defensive code — no `.get()` with defaults for keys that always exist in schema, no fallback paths for impossible states. Trust schema.
- Guess Pi username/path — it's `pi@192.168.12.76`, repo at `~/clawdception`
- **Create two pathways to same outcome.** If one thing needs doing, one code path does it. Prefer deleting duplicate logic over adding coordination between duplicates (cooldowns, suppression flags, deduplication). When tempted to add sync between two paths, delete one path instead.