# Skill: shrimp-monitor

**What it does:** The core 15-minute heartbeat. Reads sensor data, checks trends, queries Claude for a structured risk assessment, logs the decision, and fires alerts if anything is in the danger zone.

**When it runs:** Every 15 minutes via cron (offset to match ESP32 posting interval).

**What it reads:**
- `GET /api/sensors/latest` — current reading
- `GET /api/sensors?limit=96` — last 24 hours of readings
- `GET /api/events?since=<24hrs_ago>` — recent manual events (water tests, observations)
- Today's journal file (for running context)

**What it writes:**
- `~/clawdception/logs/decisions/YYYY-MM-DD.jsonl` — full Claude decision per run
- `~/clawdception/logs/monitor.log` — one-line summary per run
- Fires shrimp-alert if any parameter is in the danger zone
- Fires call-toby warning if >48hrs since last water_test event

**Token budget:** Stay under 2000 input tokens.

**Dependencies:** call-toby, shrimp-alert, utils.py, config.py

**How to test manually:**
```bash
cd ~/clawdception
python3 skills/shrimp_monitor/run.py
```

**What Claude returns (JSON):**
```json
{
  "parameter_status": {
    "temperature": {"value": 77.4, "unit": "°F", "status": "green", "note": "stable"},
    "ph": {"value": 6.32, "unit": "", "status": "yellow", "note": "low but expected"},
    "tds": {"value": 150, "unit": "ppm", "status": "green", "note": "bottom of range"}
  },
  "risk_level": "green",
  "recommended_actions": ["Test ammonia and nitrite"],
  "reasoning": "Day 9 of cycle. Parameters stable...",
  "suggested_actuator_actions": ["No action needed"]
}
```

**Modifiable:** Yes. skill-writer may propose changes to this skill.
