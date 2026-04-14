# Agent Memory & Skill Architecture

## Memory Layers

| Layer | File/Location | Scope | Written by |
|-------|--------------|-------|------------|
| Immediate | `sensor_readings` in SQLite | real-time | ESP32 |
| Working | `journal/YYYY-MM-DD-HHMM.md` | today (one file per entry) | shrimp-journal (every 6hr) |
| Decision log | `logs/decisions/YYYY-MM-DD.jsonl` | today | shrimp-monitor (every 15min) |
| Daily record | `daily-logs/YYYY-MM-DD.md` | one day — **immutable** | daily-log (7am) |
| Tank state | `state_of_tank.md` | rolling current | daily-log (overwrites daily) |
| Self | `agent_state.md` | personality, disposition | daily-log (overwrites daily) |

Daily logs are **never edited** after creation. They are the source of truth for what happened on a given day. `agent_state.md` is the agent's private self — rewritten daily, this is how personality evolves over time.

Journal entries are individual files (`YYYY-MM-DD-HHMM.md`). `read_journal()` in `utils.py` concatenates all entries for a date in chronological order.

## File Structure

```
~/clawdception/
├── journal/                  # working memory: individual entries as YYYY-MM-DD-HHMM.md
├── daily-logs/               # immutable daily logs: YYYY-MM-DD.md
├── proposals/                # skill-writer proposals: YYYY-MM-DD-{name}/ dirs
├── logs/
│   ├── monitor.log           # one-line summaries from shrimp-monitor
│   ├── alerts.jsonl          # danger alerts fired by shrimp-alert
│   ├── calls.jsonl           # call-toby log
│   ├── journal.log           # shrimp-journal cron stdout
│   ├── daily_log.log         # daily-log cron stdout
│   ├── skill_writer.log      # skill-writer stdout
│   ├── decisions/            # YYYY-MM-DD.jsonl from shrimp-monitor
│   ├── action_cooldowns.json # last-sent timestamp per owner action type
│   └── vision/               # YYYY-MM-DD.jsonl from shrimp-vision
├── state_of_tank.md          # rolling tank state — always current
├── agent_state.md            # agent personality + disposition
├── agent_state_history/      # snapshots of past agent_state.md
├── config.py                 # all constants, ranges, paths, system prompt
└── utils.py                  # shared functions (fetch, call_claude, read/write helpers)
```

## Skill Import Patterns

```python
from skills.call_toby.run import call_toby, send_document
from skills.shrimp_alert.run import alert
```

Skill directories use underscores (Python import compat). Human-readable names use hyphens.

## Decision Log Format

Each line of `logs/decisions/YYYY-MM-DD.jsonl` is a JSON object with:

| Field | Type | Description |
|-------|------|-------------|
| `parameter_status` | object | `temperature`, `ph`, `tds` — each with `value`, `status` (green/yellow/red), optional `note` |
| `risk_level` | string | `green` / `yellow` / `red` |
| `reasoning` | string | 2-sentence caretaker assessment |
| `actions` | array | Typed action objects (see below) |
| `_cycle_day` | int | Day number of nitrogen cycle |
| `_timestamp` | ISO string | When Claude was called |
| `_trigger` | string | Why Claude was called |
| `_latest` | object | Sensor values at decision time |

Each action object: `{ type, actor, urgency?, value?, note? }`.  
Owner actions (`actor: owner`) are sent to Toby when their per-type cooldown has elapsed (state in `logs/action_cooldowns.json`). Urgent actions bypass cooldown.  
Actuator actions (`actor: actuator`) are logged only — future dispatch queue.  
Photo requests inject when `hours_since_last_photo() >= 4`. Cooldown prevents re-nag within 4hr. At 8/20 check-in with no eligible actions, a status-only blurb is sent instead.

---

## shrimp-monitor Claude Call Triggers

Claude is called when **any** of:
- Manual event logged since last Claude call
- Notable rate of change (pH >0.1, temp >1°F, TDS >20ppm over last ~1 hour)
- Scheduled check-in window: 8:00–8:14 or 20:00–20:14 (if >1hr since last call)
- Periodic check: ≥10hr since last call

Params outside target range are **not** a separate trigger — the periodic check handles persistent issues, rate-of-change handles active drift. `shrimp-alert` handles danger zones independently.

Water test reminders are **not** sent as standalone Toby messages — Claude includes `water_test` in owner actions when warranted.

## Key utils.py Functions

| Function | Purpose |
|----------|---------|
| `call_claude(messages, skill_name, tools, tool_name)` | Calls Claude API, logs spend |
| `fetch_latest_reading()` | GET /api/sensors/latest |
| `fetch_readings(limit)` | GET /api/sensors?limit=N |
| `fetch_events(since, type)` | GET /api/events |
| `log_decision(data)` | Appends to logs/decisions/YYYY-MM-DD.jsonl |
| `read_journal(date)` | Reads + concatenates journal entries for a date |
| `read_agent_state()` / `write_agent_state(text)` | agent_state.md |
| `read_state_of_tank()` / `write_state_of_tank(text)` | state_of_tank.md |
| `compute_stats(readings, field)` | mean/min/max/first/last for a field |
| `hours_since_last_water_test()` | Hours since last water_test event, or None |
| `hours_since_last_photo()` | Hours since last owner_photo event, or None |
| `SkillLock(name)` | Context manager — prevents concurrent skill runs |

## Protected vs. Modifiable Skills

**Protected** (never modified by skill-writer): `call-toby`, `shrimp-alert`, `skill-writer`  
**Modifiable** (skill-writer may propose changes): `shrimp-monitor`, `shrimp-journal`, `shrimp-vision`, `daily-log`
