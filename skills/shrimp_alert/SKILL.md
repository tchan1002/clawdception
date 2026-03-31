# Skill: shrimp-alert

**What it does:** Fires when a sensor reading enters the danger zone. Logs the alert and immediately calls call-toby with `critical` urgency. This is the skill that wakes Toby up.

**When it runs:** Called by shrimp-monitor when parameters breach danger thresholds. Not cron-scheduled.

**What it reads:** Nothing (all data passed as arguments).

**What it writes:**
- Appends to `~/clawdception/logs/alerts.jsonl`
- Triggers call-toby (Telegram or log fallback)

**Dependencies:** call-toby

**How to test manually:**
```bash
cd ~/clawdception
python3 skills/shrimp_alert/run.py --param temperature --value 83 --threshold 82
python3 skills/shrimp_alert/run.py --param ph --value 5.8 --threshold 6.0
```

**How to import:**
```python
from skills.shrimp_alert.run import alert
alert("ph", 5.8, threshold=6.0, direction="below")
```

**Protected:** Yes. skill-writer may never propose changes to this skill.
