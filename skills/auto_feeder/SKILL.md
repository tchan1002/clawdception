# Skill: auto-feeder

**What it does:** Feeding reminder for Media Luna. Checks hours since last "feeding" event. If overdue, nags Toby via Telegram.

**When it runs:** Hourly via cron.

**Logic:**
- Overdue threshold: 48 hours (Neocaridina feed every other day)
- Nag cooldown: 4 hours — won't re-nag within 4h of last sent message
- If no feeding event on record: always overdue

**What it reads:**
- `GET /api/events?type=feeding&limit=1` — timestamp of last feeding

**What it writes:**
- `logs/decisions/YYYY-MM-DD.jsonl` — decision entry
- `logs/auto_feeder_state.json` — last nag timestamp
- `logs/auto_feeder.log` — stdout from cron

**State file schema:**
```json
{
  "last_nag": "2026-04-26T10:00:00"
}
```

**To log a feeding:** Post a `feeding` event via Telegram or API. Resets the 48h clock.

**To test manually:**
```bash
cd ~/clawdception
python3 skills/auto_feeder/run.py --force
```

**Dependencies:** call-toby, utils.py, config.py

**Modifiable:** Yes.
