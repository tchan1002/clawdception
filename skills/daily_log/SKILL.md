# Skill: daily-log

**What it does:** The centerpiece skill. Each morning at 7am, writes the previous day's immutable log and updates the rolling state files. This is the thing Toby reads with his coffee. It's also a key input to the agent's long-term memory.

**When it runs:** 7:00 AM daily via cron, summarizing the previous day.

**What it reads:**
- Yesterday's full sensor data
- Yesterday's journal file (`journal/YYYY-MM-DD.md`)
- Yesterday's events (water tests, observations, interventions)
- Yesterday's decision logs
- Last 3 daily logs (for multi-day trend awareness)
- `state_of_tank.md` (rolling tank state)
- `agent_state.md` (personality/disposition)
- `template.md` (structural reference)

**What it writes:**
- `daily-logs/YYYY-MM-DD.md` — immutable, never edited after creation
- `state_of_tank.md` — updated rolling tank state
- `agent_state.md` — updated agent disposition/personality
- Sends call-toby info: "Morning log ready 🌅 — Day N of the cycle. [one-line teaser]"

**Token budget:** Up to 4000 input tokens. This is the highest-quality call in the stack.

**Dependencies:** call-toby, utils.py, config.py, template.md

**How to test manually:**
```bash
cd ~/clawdception
python3 skills/daily_log/run.py
# Writes yesterday's log. Re-running is safe — will not overwrite existing log.

python3 skills/daily_log/run.py --date 2026-03-31
# Write a log for a specific date (useful for backfilling)
```

**Immutability:** Once a daily log is written, it is never modified. It is a source of truth for what happened that day. The agent reads previous logs but never edits them.

**Modifiable:** Yes. skill-writer may propose changes to this skill.
