# Skill: shrimp-journal

**What it does:** Every 2 hours, reads the recent decision logs and sensor data, asks Claude to consolidate what happened into a narrative journal entry, and appends it to the daily journal file. This is the agent's working memory — shrimp-monitor reads today's journal for context.

**When it runs:** Every 6 hours at :05 past the hour (offset from shrimp-monitor's :00). Cron: `5 */6 * * *`.

**What it reads:**
- Decision logs from past ~6 hours
- Sensor readings for same window
- Recent events
- The journal file so far today (to avoid repetition)

**What it writes:**
- Appends a timestamped entry to `~/clawdception/journal/YYYY-MM-DD.md`
- Entries are 200-400 words each

**Token budget:** Stay under 1500 input tokens.

**Dependencies:** utils.py, config.py

**How to test manually:**
```bash
cd ~/clawdception
python3 skills/shrimp_journal/run.py
```

**Modifiable:** Yes. skill-writer may propose changes to this skill.
